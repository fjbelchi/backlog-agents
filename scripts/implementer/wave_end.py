#!/usr/bin/env python3
"""Post-wave orchestrator (merged Phase 4 + 6). Stdlib only.

Orchestrates all post-wave operations: enrich completed tickets, move them
to completed/, write wave log, run micro-reflection, update playbook counters,
and check session limits.

Usage:
    echo '{"wave": 1, ...}' | python3 wave_end.py --data-dir backlog/data
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import date
from pathlib import Path

# Ensure sibling imports work regardless of how this is invoked
_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR))
sys.path.insert(0, str(_SCRIPT_DIR.parent / "ops"))

from enrich_ticket import enrich_ticket
from micro_reflect import reflect_wave

# Optional import: playbook_utils may not be available in all environments
try:
    from playbook_utils import update_counters as _playbook_update_counters
except ImportError:
    _playbook_update_counters = None


def _write_wave_log(
    wave_log_path: str,
    wave_data: dict,
    enriched_ids: list[str],
    failed_ids: list[str],
) -> None:
    """Append a wave summary entry to the wave log file.

    Creates parent directories and the file if they don't exist.
    """
    p = Path(wave_log_path)
    p.parent.mkdir(parents=True, exist_ok=True)

    wave_num = wave_data.get("wave", "?")
    wave_date = wave_data.get("date", date.today().isoformat())
    total_cost = wave_data.get("session_total_cost", 0.0)
    models = wave_data.get("models_used", {})

    lines = [
        f"### Wave {wave_num} — {wave_date}\n",
        f"- Completed: {', '.join(enriched_ids) if enriched_ids else 'none'}\n",
    ]
    if failed_ids:
        lines.append(f"- Failed/Skipped: {', '.join(failed_ids)}\n")
    lines.append(f"- Session cost: ${total_cost:.2f}\n")
    if models:
        model_parts = [f"{k}={v}" for k, v in models.items() if v]
        if model_parts:
            lines.append(f"- Models: {', '.join(model_parts)}\n")
    lines.append("\n")

    with open(wave_log_path, "a", encoding="utf-8") as f:
        f.writelines(lines)


def run_wave_end(
    wave_data: dict,
    data_dir: str = "backlog/data",
    playbook_path: str = ".claude/playbook.md",
    wave_log_path: str = ".backlog-ops/wave-log.md",
) -> dict:
    """Orchestrate all post-wave operations.

    Steps:
        1. Enrich completed tickets with metadata and cost sections.
        2. Move completed tickets from pending/ to completed/.
        3. Write wave summary entry to wave log.
        4. Run micro_reflect() on wave results and bullets_used.
        5. Apply playbook counter updates if playbook exists.
        6. Check session limit (waves_this_session >= max_waves).
        7. Count remaining pending tickets.

    Args:
        wave_data: Dict with wave number, tickets, bullets_used, etc.
        data_dir: Path to backlog/data directory.
        playbook_path: Path to playbook.md (skip update if missing).
        wave_log_path: Path to wave log file (appended).

    Returns:
        Dict with enriched_count, moved_count, wave_log_written,
        micro_reflect results, session_limit_reached, pending_remaining.
    """
    pending_dir = Path(data_dir) / "pending"
    completed_dir = Path(data_dir) / "completed"
    tickets = wave_data.get("tickets", [])
    bullets_used = wave_data.get("bullets_used", [])

    enriched_count = 0
    moved_count = 0
    enriched_ids: list[str] = []
    failed_ids: list[str] = []

    # Step 1 + 2: Enrich and move completed tickets
    for ticket in tickets:
        ticket_id = ticket.get("id", "unknown")

        if ticket.get("status") != "completed":
            failed_ids.append(ticket_id)
            continue

        ticket_path = ticket.get("path", "")

        # Step 1: Enrich
        if ticket_path and Path(ticket_path).exists():
            enrich_ticket(
                ticket_path=ticket_path,
                commit_hash=ticket.get("commit", ""),
                review_rounds=ticket.get("review_rounds", 1),
                tests_added=ticket.get("tests_added", 0),
                cost_usd=ticket.get("cost_usd", 0.0),
                model=ticket.get("model", "haiku"),
            )
            enriched_count += 1
            enriched_ids.append(ticket_id)

            # Step 2: Move to completed/
            completed_dir.mkdir(parents=True, exist_ok=True)
            dest = completed_dir / Path(ticket_path).name
            shutil.move(ticket_path, str(dest))
            moved_count += 1

    # Step 3: Write wave log
    _write_wave_log(wave_log_path, wave_data, enriched_ids, failed_ids)
    wave_log_written = True

    # Step 4: Run micro_reflect
    # Build wave_results in the format micro_reflect expects
    wave_results = {
        "completed": enriched_ids,
        "failed": {tid: "gate failure" for tid in failed_ids},
        "escalated": [],
    }
    reflect_result = reflect_wave(wave_results, bullets_used)
    micro_reflect_summary = {
        "tags": len(reflect_result.get("bullet_tags", [])),
        "new_bullets": len(reflect_result.get("new_bullets", [])),
    }

    # Step 5: Apply playbook updates if playbook exists
    if (
        _playbook_update_counters is not None
        and Path(playbook_path).exists()
        and reflect_result.get("bullet_tags")
    ):
        _playbook_update_counters(playbook_path, reflect_result["bullet_tags"])

    # Step 6: Check session limit
    waves_this_session = wave_data.get("waves_this_session", 0)
    max_waves = wave_data.get("max_waves", 5)
    session_limit_reached = waves_this_session >= max_waves

    # Step 7: Count remaining pending tickets
    pending_remaining = 0
    if pending_dir.exists():
        pending_remaining = len(
            [f for f in pending_dir.iterdir() if f.suffix == ".md"]
        )

    return {
        "enriched_count": enriched_count,
        "moved_count": moved_count,
        "wave_log_written": wave_log_written,
        "micro_reflect": micro_reflect_summary,
        "session_limit_reached": session_limit_reached,
        "pending_remaining": pending_remaining,
    }


def main() -> int:
    """CLI entry point: reads wave_data from stdin."""
    ap = argparse.ArgumentParser(description="Post-wave orchestrator.")
    ap.add_argument(
        "--data-dir",
        default="backlog/data",
        help="Path to backlog/data directory",
    )
    ap.add_argument(
        "--playbook",
        default=".claude/playbook.md",
        help="Path to playbook.md",
    )
    ap.add_argument(
        "--wave-log",
        default=".backlog-ops/wave-log.md",
        help="Path to wave log file",
    )
    a = ap.parse_args()

    raw = sys.stdin.read()
    try:
        wave_data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"Error: invalid JSON: {e}", file=sys.stderr)
        return 1

    result = run_wave_end(
        wave_data=wave_data,
        data_dir=a.data_dir,
        playbook_path=a.playbook,
        wave_log_path=a.wave_log,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
