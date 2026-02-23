#!/usr/bin/env python3
"""Graph-based deterministic wave planner.

Replaces LLM-based wave planning with a conflict-detection graph,
topological sort on dependencies, and greedy bin-packing into
parallel-safe waves.

Algorithm:
  1. Build file-overlap graph: edge between tickets sharing any affected file.
  2. Detect circular dependencies via Kahn's algorithm; skip cyclic tickets.
  3. Topological sort on depends_on relationships.
  4. Greedy bin-packing: for each ticket (sorted by topo-layer then priority),
     assign to first wave slot without file conflict, respecting max_slots.
  5. Route subagent type from file extensions using majority vote.

Only uses Python stdlib -- no external dependencies.

Usage:
    python3 wave_plan.py --tickets '[{"id":"T1","priority":0,"affected_files":["a.py"],"depends_on":[]}]'
    echo '<json>' | python3 wave_plan.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict, deque


# ---------------------------------------------------------------------------
# Subagent routing
# ---------------------------------------------------------------------------

_FRONTEND_EXTS = {".tsx", ".jsx", ".css", ".vue", ".svelte"}
_BACKEND_EXTS = {".py", ".go", ".rs", ".rb"}
_DEVOPS_EXTS = {".yaml", ".yml", ".tf", ".toml"}
_DEVOPS_NAMES = {"Dockerfile", "docker-compose.yml", "docker-compose.yaml"}
_ML_EXTS = {".ipynb"}
_ML_NAME_PATTERNS = {"train", "model"}


def route_subagent(files: list[str]) -> str:
    """Determine subagent type from a list of affected files.

    Uses majority vote across all files.  Priority when tied:
    ml-engineer > frontend > backend > devops > general-purpose
    (ties broken by this order since ml/frontend tend to be more specialized).
    """
    votes: dict[str, int] = defaultdict(int)

    for filepath in files:
        basename = os.path.basename(filepath)
        _, ext = os.path.splitext(basename)
        ext_lower = ext.lower()
        name_lower = basename.lower()

        # ML by extension (.ipynb is unambiguous)
        if ext_lower in _ML_EXTS:
            votes["ml-engineer"] += 1
            continue

        # Devops by exact name (e.g. Dockerfile)
        if basename in _DEVOPS_NAMES:
            votes["devops"] += 1
            continue

        # Extension-based routing (most common case)
        if ext_lower in _FRONTEND_EXTS:
            votes["frontend"] += 1
        elif ext_lower in _BACKEND_EXTS:
            # Secondary check: ML name patterns override backend extension
            # only when the stem (not the extension) matches "train" or "model"
            stem = os.path.splitext(name_lower)[0]
            if any(pat == stem or stem.startswith(pat + "_") or stem.endswith("_" + pat)
                   for pat in _ML_NAME_PATTERNS):
                votes["ml-engineer"] += 1
            else:
                votes["backend"] += 1
        elif ext_lower in _DEVOPS_EXTS:
            votes["devops"] += 1
        else:
            # For unknown extensions, check ML name patterns
            stem = os.path.splitext(name_lower)[0]
            if any(pat in stem for pat in _ML_NAME_PATTERNS):
                votes["ml-engineer"] += 1
            else:
                votes["general-purpose"] += 1

    if not votes:
        return "general-purpose"

    # Majority vote: pick the category with most votes.
    # Tie-break order: ml-engineer > frontend > backend > devops > general-purpose
    priority_order = ["ml-engineer", "frontend", "backend", "devops", "general-purpose"]
    max_count = max(votes.values())
    for category in priority_order:
        if votes.get(category, 0) == max_count:
            return category

    return "general-purpose"  # unreachable but satisfies type checker


# ---------------------------------------------------------------------------
# Topological sort with cycle detection (Kahn's algorithm)
# ---------------------------------------------------------------------------

def _topo_sort(
    ticket_ids: set[str],
    depends_map: dict[str, list[str]],
) -> tuple[list[str], set[str]]:
    """Return (ordered_ids, cyclic_ids).

    ordered_ids: tickets in valid topological order (dependencies first).
    cyclic_ids: tickets involved in dependency cycles (to be skipped).

    Only considers dependencies on tickets present in ticket_ids.
    Dependencies on unknown IDs are treated as already satisfied.
    """
    # Build adjacency: dependency -> dependents (forward edges)
    in_degree: dict[str, int] = {tid: 0 for tid in ticket_ids}
    adjacency: dict[str, list[str]] = {tid: [] for tid in ticket_ids}

    for tid in ticket_ids:
        for dep in depends_map.get(tid, []):
            if dep in ticket_ids:
                in_degree[tid] += 1
                adjacency[dep].append(tid)

    # Kahn's algorithm (sorted seeds for deterministic output)
    queue: deque[str] = deque(sorted(tid for tid in ticket_ids if in_degree[tid] == 0))

    ordered: list[str] = []
    while queue:
        node = queue.popleft()
        ordered.append(node)
        for neighbor in sorted(adjacency[node]):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    cyclic = ticket_ids - set(ordered)
    return ordered, cyclic


# ---------------------------------------------------------------------------
# Wave planner
# ---------------------------------------------------------------------------

def plan_wave(tickets: list[dict], max_slots: int = 3) -> dict:
    """Plan parallel-safe execution waves for a list of tickets.

    Args:
        tickets: List of dicts with keys: id, priority, affected_files, depends_on.
        max_slots: Maximum number of tickets per wave.

    Returns:
        Dict matching the expected LLM output format with keys:
        - waves: list of {wave: int, tickets: [{id, subagent_type, rationale}]}
        - skipped: list of {id, reason} for tickets that couldn't be planned.
    """
    if not tickets:
        return {"waves": [], "skipped": []}

    # Index tickets by ID
    ticket_map: dict[str, dict] = {}
    for t in tickets:
        ticket_map[t["id"]] = t

    all_ids = set(ticket_map.keys())

    # Build depends_on map (only intra-batch dependencies)
    depends_map: dict[str, list[str]] = {}
    for t in tickets:
        depends_map[t["id"]] = [d for d in t.get("depends_on", []) if d in all_ids]

    # Topological sort with cycle detection
    topo_order, cyclic_ids = _topo_sort(all_ids, depends_map)

    # Build skipped list for cyclic tickets
    skipped = [{"id": tid, "reason": "circular dependency"} for tid in sorted(cyclic_ids)]

    # Compute topological layer for each ticket (used for wave-minimum)
    # Layer = 1 + max(layer of dependencies). No deps = layer 0.
    topo_layer: dict[str, int] = {}
    for tid in topo_order:
        deps_in_batch = depends_map.get(tid, [])
        if not deps_in_batch:
            topo_layer[tid] = 0
        else:
            topo_layer[tid] = 1 + max(topo_layer[dep] for dep in deps_in_batch)

    # Sort plannable tickets by (topo_layer, priority, id) for determinism
    plannable = [
        ticket_map[tid]
        for tid in topo_order
    ]
    plannable.sort(key=lambda t: (topo_layer[t["id"]], t.get("priority", 99), t["id"]))

    # Greedy bin-packing into waves
    # Each wave tracks: which files are "taken" and how many slots used.
    # A ticket goes into the earliest wave where:
    #   - wave number > max(wave of any dependency)
    #   - no file overlap with other tickets in that wave
    #   - slot count < max_slots
    waves: list[dict] = []  # [{wave: int, tickets: [...], _files: set}]
    ticket_wave: dict[str, int] = {}  # ticket_id -> wave number (1-indexed)

    for t in plannable:
        tid = t["id"]
        files = set(t.get("affected_files", []))
        subagent = route_subagent(t.get("affected_files", []))

        # Minimum wave: must be after all dependencies
        deps_in_batch = depends_map.get(tid, [])
        if deps_in_batch:
            min_wave = max(ticket_wave[dep] for dep in deps_in_batch) + 1
        else:
            min_wave = 1

        # Find earliest compatible wave
        placed = False
        for wave in waves:
            if wave["wave"] < min_wave:
                continue
            if len(wave["tickets"]) >= max_slots:
                continue
            if files & wave["_files"]:
                continue
            # Place here
            wave["tickets"].append({
                "id": tid,
                "subagent_type": subagent,
                "rationale": _build_rationale(t, deps_in_batch, files, wave),
            })
            wave["_files"] |= files
            ticket_wave[tid] = wave["wave"]
            placed = True
            break

        if not placed:
            # Create new wave
            wave_num = len(waves) + 1
            # Ensure wave_num >= min_wave
            wave_num = max(wave_num, min_wave)
            new_wave = {
                "wave": wave_num,
                "tickets": [{
                    "id": tid,
                    "subagent_type": subagent,
                    "rationale": _build_rationale(t, deps_in_batch, files, None),
                }],
                "_files": set(files),
            }
            waves.append(new_wave)
            ticket_wave[tid] = wave_num

    # Clean up internal _files field and sort waves by number
    waves.sort(key=lambda w: w["wave"])
    clean_waves = []
    for w in waves:
        clean_waves.append({
            "wave": w["wave"],
            "tickets": w["tickets"],
        })

    return {"waves": clean_waves, "skipped": skipped}


def _build_rationale(
    ticket: dict,
    deps_in_batch: list[str],
    files: set[str],
    wave: dict | None,
) -> str:
    """Build a human-readable rationale for wave placement."""
    parts = []
    if not files:
        parts.append("no affected files")
    elif wave is None:
        parts.append("no file conflicts")
    elif not (files & wave.get("_files", set())):
        parts.append("no file conflicts")
    else:
        parts.append("file conflict resolved")

    if deps_in_batch:
        parts.append(f"after {', '.join(deps_in_batch)}")

    return "; ".join(parts)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    """CLI entry point: reads tickets from --tickets arg or stdin."""
    parser = argparse.ArgumentParser(
        description="Graph-based wave planner for backlog tickets.",
    )
    parser.add_argument(
        "--tickets",
        type=str,
        default=None,
        help="JSON string of ticket list. If omitted, reads from stdin.",
    )
    parser.add_argument(
        "--max-slots",
        type=int,
        default=3,
        help="Maximum tickets per wave (default: 3).",
    )
    args = parser.parse_args()

    if args.tickets:
        raw = args.tickets
    else:
        raw = sys.stdin.read()

    try:
        tickets = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"Error: invalid JSON input: {exc}", file=sys.stderr)
        return 1

    if not isinstance(tickets, list):
        print("Error: input must be a JSON array of tickets", file=sys.stderr)
        return 1

    result = plan_wave(tickets, max_slots=args.max_slots)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
