#!/usr/bin/env python3
"""Ticket enrichment with git metrics and cost data. Stdlib only.

Reads a completed ticket's markdown, updates frontmatter with completion
metadata, appends an Actual Cost section, and writes back to the same path.

Usage:
    python3 enrich_ticket.py --ticket path.md --commit abc123 --reviews 2 --tests 5 --cost 0.25
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str, str]:
    """Parse YAML-ish frontmatter from markdown text.

    Returns (frontmatter_dict, frontmatter_raw, body).
    frontmatter_raw includes the ``---`` delimiters.
    body is everything after the closing ``---``.
    If no frontmatter, returns ({}, "", full_text).
    """
    match = re.match(r"^(---\s*\n)(.*?\n)(---\s*\n?)", text, re.DOTALL)
    if not match:
        return {}, "", text

    opening = match.group(1)
    inner = match.group(2)
    closing = match.group(3)
    body = text[match.end():]

    fm: dict[str, str] = {}
    for line in inner.splitlines():
        kv = re.match(r"^(\w[\w_]*):\s*(.*)", line)
        if kv:
            fm[kv.group(1)] = kv.group(2).strip()

    return fm, match.group(0), body


def _rebuild_frontmatter(
    original_raw: str,
    updates: dict[str, str],
) -> str:
    """Update or insert key-value pairs in frontmatter text.

    Existing keys are replaced in-place. New keys are appended
    before the closing ``---``.
    """
    if not original_raw:
        # No frontmatter existed; create one
        lines = ["---"]
        for k, v in updates.items():
            lines.append(f"{k}: {v}")
        lines.append("---\n")
        return "\n".join(lines)

    lines = original_raw.splitlines()
    updated_keys: set[str] = set()

    for i, line in enumerate(lines):
        kv = re.match(r"^(\w[\w_]*):\s*(.*)", line)
        if kv and kv.group(1) in updates:
            key = kv.group(1)
            lines[i] = f"{key}: {updates[key]}"
            updated_keys.add(key)

    # Append new keys before closing ---
    new_keys = [k for k in updates if k not in updated_keys]
    if new_keys:
        # Find the last --- line (closing delimiter)
        close_idx = len(lines) - 1
        for idx in range(len(lines) - 1, -1, -1):
            if lines[idx].strip() == "---":
                close_idx = idx
                break
        for key in new_keys:
            lines.insert(close_idx, f"{key}: {updates[key]}")
            close_idx += 1

    return "\n".join(lines) + "\n"


def _build_actual_cost_section(
    model: str,
    cost_usd: float,
    review_rounds: int,
) -> str:
    """Build the ## Actual Cost markdown section."""
    return (
        f"## Actual Cost\n"
        f"- model: {model}\n"
        f"- cost_usd: {cost_usd}\n"
        f"- review_rounds: {review_rounds}\n"
    )


def enrich_ticket(
    ticket_path: str,
    commit_hash: str,
    review_rounds: int = 1,
    tests_added: int = 0,
    cost_usd: float = 0.0,
    model: str = "haiku",
) -> dict:
    """Enrich a completed ticket with implementation metadata.

    Reads the ticket markdown, updates frontmatter fields, appends
    an Actual Cost section, writes back to the same path, and returns
    a dict with the enriched field values.

    Args:
        ticket_path: Path to the ticket .md file.
        commit_hash: Git commit hash for the implementation.
        review_rounds: Number of review rounds completed.
        tests_added: Number of tests added during implementation.
        cost_usd: Total cost in USD for this ticket.
        model: Primary model used for implementation.

    Returns:
        Dict with enriched fields: status, completed, commit, review_rounds,
        tests_added, cost_usd, model, implemented_by.
    """
    today = date.today().isoformat()

    # Read the file
    with open(ticket_path, encoding="utf-8") as f:
        text = f.read()

    fm, fm_raw, body = _parse_frontmatter(text)

    # Build frontmatter updates
    updates = {
        "status": "completed",
        "completed": today,
        "implemented_by": "backlog-implementer-v9",
        "review_rounds": str(review_rounds),
        "tests_added": str(tests_added),
        "commit": commit_hash,
    }

    new_fm = _rebuild_frontmatter(fm_raw, updates)

    # Remove existing Actual Cost section if present (idempotency)
    body = re.sub(
        r"## Actual Cost\n(?:- [^\n]+\n)*\n?",
        "",
        body,
    )

    # Append Actual Cost section
    cost_section = _build_actual_cost_section(model, cost_usd, review_rounds)
    body = body.rstrip("\n") + "\n\n" + cost_section

    # Write back
    with open(ticket_path, "w", encoding="utf-8") as f:
        f.write(new_fm + body)

    return {
        "status": "completed",
        "completed": today,
        "commit": commit_hash,
        "review_rounds": review_rounds,
        "tests_added": tests_added,
        "cost_usd": cost_usd,
        "model": model,
        "implemented_by": "backlog-implementer-v9",
    }


def main() -> int:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description="Enrich completed ticket with metrics.")
    ap.add_argument("--ticket", required=True, help="Path to ticket .md file")
    ap.add_argument("--commit", required=True, help="Git commit hash")
    ap.add_argument("--reviews", type=int, default=1, help="Number of review rounds")
    ap.add_argument("--tests", type=int, default=0, help="Number of tests added")
    ap.add_argument("--cost", type=float, default=0.0, help="Cost in USD")
    ap.add_argument("--model", default="haiku", help="Primary model used")
    a = ap.parse_args()

    try:
        result = enrich_ticket(
            ticket_path=a.ticket,
            commit_hash=a.commit,
            review_rounds=a.reviews,
            tests_added=a.tests,
            cost_usd=a.cost,
            model=a.model,
        )
    except OSError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
