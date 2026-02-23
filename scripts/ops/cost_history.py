#!/usr/bin/env python3
"""Cost-history feedback loop for ticket cost estimation.

Stores historical ticket costs in `.claude/cost-history.json` and computes
rolling averages to improve future cost estimates.  Used by the backlog-ticket
skill to provide data-driven cost predictions.

Usage:
    python3 scripts/ops/cost_history.py stats [path]
    python3 scripts/ops/cost_history.py estimate <type> <complexity> <files> [path]
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_PATH = ".claude/cost-history.json"

ROLLING_WINDOW = 20


def _default_data() -> dict:
    """Return the default empty cost-history structure."""
    return {
        "version": "1.0",
        "entries": [],
        "averages": {
            "by_type": {},
            "by_complexity": {},
            "by_pipeline": {},
        },
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_history(path: str = DEFAULT_PATH) -> dict:
    """Load cost-history JSON file.

    Args:
        path: Filesystem path to the cost-history JSON file.

    Returns:
        Parsed dict.  If the file is missing or contains malformed JSON,
        returns the default empty structure.
    """
    p = Path(path)
    if not p.exists():
        return _default_data()

    try:
        text = p.read_text(encoding="utf-8")
        data = json.loads(text)
        if not isinstance(data, dict):
            return _default_data()
        return data
    except (json.JSONDecodeError, OSError):
        return _default_data()


def add_entry(path: str, entry: dict) -> None:
    """Append *entry* to the history, recalculate averages, and persist.

    Creates the parent directory when it does not already exist.

    Args:
        path: Filesystem path to the cost-history JSON file.
        entry: A single cost-history entry dict.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    data = load_history(path)
    data["entries"].append(entry)
    data = recalculate_averages(data)

    p.write_text(json.dumps(data, indent=2), encoding="utf-8")


def recalculate_averages(data: dict) -> dict:
    """Compute rolling averages from entries (last 20 per category).

    Updates ``data["averages"]`` in-place with:

    - **by_type**: avg_cost, avg_tokens, avg_files, sample_size
    - **by_complexity**: avg_cost, sample_size
    - **by_pipeline**: avg_cost, success_rate

    Args:
        data: The full cost-history dict (must contain ``entries``).

    Returns:
        The same *data* dict with updated ``averages``.
    """
    entries = data.get("entries", [])

    # --- by_type ---
    by_type: dict[str, list[dict]] = defaultdict(list)
    for e in entries:
        by_type[e["ticket_type"]].append(e)

    type_avgs: dict[str, dict] = {}
    for ttype, group in by_type.items():
        window = group[-ROLLING_WINDOW:]
        type_avgs[ttype] = {
            "avg_cost": round(mean(e["cost_usd"] for e in window), 4),
            "avg_tokens": round(mean(e["total_tokens"] for e in window), 2),
            "avg_files": round(mean(e["files_modified"] for e in window), 2),
            "sample_size": len(window),
        }

    # --- by_complexity ---
    by_complexity: dict[str, list[dict]] = defaultdict(list)
    for e in entries:
        by_complexity[e["complexity"]].append(e)

    complexity_avgs: dict[str, dict] = {}
    for cplx, group in by_complexity.items():
        window = group[-ROLLING_WINDOW:]
        complexity_avgs[cplx] = {
            "avg_cost": round(mean(e["cost_usd"] for e in window), 4),
            "sample_size": len(window),
        }

    # --- by_pipeline ---
    by_pipeline: dict[str, list[dict]] = defaultdict(list)
    for e in entries:
        by_pipeline[e["pipeline"]].append(e)

    pipeline_avgs: dict[str, dict] = {}
    for pipe, group in by_pipeline.items():
        window = group[-ROLLING_WINDOW:]
        successes = sum(1 for e in window if e.get("gates_passed_first_try", 0) == 5)
        pipeline_avgs[pipe] = {
            "avg_cost": round(mean(e["cost_usd"] for e in window), 4),
            "success_rate": round(successes / len(window), 4),
        }

    data["averages"] = {
        "by_type": type_avgs,
        "by_complexity": complexity_avgs,
        "by_pipeline": pipeline_avgs,
    }
    return data


def estimate_cost(path: str, ticket_type: str, complexity: str, file_count: int) -> dict:
    """Estimate cost for a ticket based on historical data.

    Finds entries matching *ticket_type* **and** *complexity*, then scales the
    average cost by the ratio ``file_count / avg_files``.

    Args:
        path: Filesystem path to the cost-history JSON file.
        ticket_type: Ticket type string (e.g. ``"BUG"``, ``"FEAT"``).
        complexity: Complexity level (e.g. ``"simple"``, ``"complex"``).
        file_count: Expected number of files to be modified.

    Returns:
        Dict with ``estimate`` (float or None), ``confidence`` (str), and
        ``sample_size`` (int).
    """
    data = load_history(path)
    matching = [
        e for e in data.get("entries", [])
        if e.get("ticket_type") == ticket_type and e.get("complexity") == complexity
    ]

    if not matching:
        return {"estimate": None, "confidence": "none", "sample_size": 0}

    window = matching[-ROLLING_WINDOW:]
    n = len(window)
    avg_cost = mean(e["cost_usd"] for e in window)
    avg_files = mean(e["files_modified"] for e in window)

    if avg_files > 0:
        estimate = avg_cost * (file_count / avg_files)
    else:
        estimate = avg_cost

    if n >= 20:
        confidence = "high"
    elif n >= 5:
        confidence = "medium"
    else:
        confidence = "low"

    return {
        "estimate": round(estimate, 4),
        "confidence": confidence,
        "sample_size": n,
    }


def get_classifier_accuracy(path: str) -> dict:
    """Measure pipeline classifier accuracy from historical data.

    An *escalation* is an entry where complexity was ``"simple"`` or
    ``"trivial"`` but the pipeline used was ``"full"``.

    Args:
        path: Filesystem path to the cost-history JSON file.

    Returns:
        Dict with ``accuracy`` (float), ``total`` (int), ``escalations``
        (int), ``fast_count`` (int), and ``full_count`` (int).
    """
    data = load_history(path)
    entries = data.get("entries", [])
    total = len(entries)

    fast_count = sum(1 for e in entries if e.get("pipeline") == "fast")
    full_count = sum(1 for e in entries if e.get("pipeline") == "full")

    escalations = sum(
        1
        for e in entries
        if e.get("complexity") in ("simple", "trivial") and e.get("pipeline") == "full"
    )

    accuracy = (1 - escalations / total) if total > 0 else 0.0

    return {
        "accuracy": round(accuracy, 4),
        "total": total,
        "escalations": escalations,
        "fast_count": fast_count,
        "full_count": full_count,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    """CLI entry point.

    Usage::

        python3 cost_history.py stats [path]
        python3 cost_history.py estimate <type> <complexity> <files> [path]
    """
    args = sys.argv[1:]

    if not args:
        print("Usage: cost_history.py {stats|estimate} ...", file=sys.stderr)
        return 1

    command = args[0]

    if command == "stats":
        path = args[1] if len(args) > 1 else DEFAULT_PATH
        data = load_history(path)
        data = recalculate_averages(data)
        acc = get_classifier_accuracy(path)

        print(json.dumps({"averages": data["averages"], "classifier_accuracy": acc}, indent=2))
        return 0

    if command == "estimate":
        if len(args) < 4:
            print("Usage: cost_history.py estimate <type> <complexity> <files> [path]", file=sys.stderr)
            return 1

        ticket_type = args[1]
        complexity = args[2]
        file_count = int(args[3])
        path = args[4] if len(args) > 4 else DEFAULT_PATH

        result = estimate_cost(path, ticket_type, complexity, file_count)
        print(json.dumps(result, indent=2))
        return 0

    print(f"Unknown command: {command}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
