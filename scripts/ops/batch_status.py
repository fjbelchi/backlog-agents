#!/usr/bin/env python3
"""Show status of in-flight and recent Anthropic Batch API jobs.

Usage:
    python scripts/ops/batch_status.py
    python scripts/ops/batch_status.py --all     # include completed jobs
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

try:
    import anthropic
except ImportError:
    print("Error: anthropic SDK not installed. Run: pip install anthropic", file=sys.stderr)
    sys.exit(1)


ACTIVE_JOBS_FILE = Path(".backlog-ops/batch-queue/active.jsonl")
COMPLETED_JOBS_FILE = Path(".backlog-ops/batch-queue/completed.jsonl")


def load_jobs(path: Path) -> list[dict]:
    if not path.exists():
        return []
    jobs = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            jobs.append(json.loads(line))
    return jobs


def main() -> int:
    parser = argparse.ArgumentParser(description="Show Anthropic Batch API job status")
    parser.add_argument("--all", action="store_true", help="Include completed jobs")
    args = parser.parse_args()

    active_jobs = load_jobs(ACTIVE_JOBS_FILE)
    completed_jobs = load_jobs(COMPLETED_JOBS_FILE) if args.all else []

    if not active_jobs and not completed_jobs:
        print("No batch jobs found.")
        print(f"Submit jobs with: python scripts/ops/batch_submit.py --queue <queue.jsonl>")
        return 0

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    client = anthropic.Anthropic(api_key=api_key) if api_key else None

    if not api_key:
        print("Warning: ANTHROPIC_API_KEY not set — showing local state only.\n")

    # ─── Active jobs ────────────────────────────────────────────────
    if active_jobs:
        print(f"{'─' * 70}")
        print(f"  IN-FLIGHT BATCH JOBS ({len(active_jobs)})")
        print(f"{'─' * 70}")

        for job in active_jobs:
            batch_id = job["batch_id"]
            submitted = job.get("submitted_at", "unknown")
            count = job.get("request_count", "?")
            print(f"\n  Batch ID:    {batch_id}")
            print(f"  Submitted:   {submitted}  ({count} requests)")

            if client:
                try:
                    batch = client.messages.batches.retrieve(batch_id)
                    print(f"  API Status:  {batch.processing_status}")
                    counts = batch.request_counts
                    print(f"  Progress:    {counts.succeeded} succeeded / "
                          f"{counts.errored} errored / "
                          f"{counts.processing} processing / "
                          f"{counts.canceled} canceled")
                    if batch.processing_status == "ended":
                        print(f"  → Ready to reconcile: python scripts/ops/batch_reconcile.py")
                    else:
                        print(f"  → Still processing. Check again later.")
                except anthropic.APIError as exc:
                    print(f"  API Error:   {exc}")
            else:
                print(f"  Status:      (set ANTHROPIC_API_KEY to check live status)")

    # ─── Completed jobs ─────────────────────────────────────────────
    if completed_jobs:
        print(f"\n{'─' * 70}")
        print(f"  COMPLETED BATCH JOBS ({len(completed_jobs)})")
        print(f"{'─' * 70}")

        for job in completed_jobs[-10:]:  # show last 10
            batch_id = job["batch_id"]
            completed_at = job.get("completed_at", "unknown")
            counts = job.get("counts", {})
            print(f"\n  Batch ID:    {batch_id}")
            print(f"  Completed:   {completed_at}")
            if counts:
                print(f"  Results:     {counts.get('succeeded', '?')} succeeded / "
                      f"{counts.get('errored', '?')} errored")
            result_paths = job.get("result_paths", [])
            if result_paths:
                print(f"  Output:      {result_paths[0]} (+{max(0, len(result_paths)-1)} more)")

    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
