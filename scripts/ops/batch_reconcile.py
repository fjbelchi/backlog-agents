#!/usr/bin/env python3
"""Reconcile completed Anthropic Batch API jobs and write results to disk.

Reads active batch job IDs from .backlog-ops/batch-queue/active.jsonl,
polls the Anthropic Batch API for completed results, writes output to
disk, and moves jobs to completed status.

Usage:
    python scripts/ops/batch_reconcile.py
    python scripts/ops/batch_reconcile.py --output-dir tmp/batch-results
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import anthropic
except ImportError:
    print("Error: anthropic SDK not installed. Run: pip install anthropic", file=sys.stderr)
    sys.exit(1)


ACTIVE_JOBS_FILE = Path(".backlog-ops/batch-queue/active.jsonl")
COMPLETED_JOBS_FILE = Path(".backlog-ops/batch-queue/completed.jsonl")


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_active_jobs() -> list[dict]:
    """Load jobs that are not yet completed."""
    if not ACTIVE_JOBS_FILE.exists():
        return []
    jobs = []
    for line in ACTIVE_JOBS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        job = json.loads(line)
        if job.get("status") not in {"completed", "errored", "expired"}:
            jobs.append(job)
    return jobs


def save_active_jobs(jobs: list[dict]) -> None:
    """Rewrite the active jobs file with updated statuses."""
    ACTIVE_JOBS_FILE.parent.mkdir(parents=True, exist_ok=True)
    ACTIVE_JOBS_FILE.write_text(
        "\n".join(json.dumps(j) for j in jobs) + "\n",
        encoding="utf-8",
    )


def append_completed_job(job: dict) -> None:
    """Append a finished job to the completed log."""
    COMPLETED_JOBS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with COMPLETED_JOBS_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(job) + "\n")


def write_result(result, output_dir: Path) -> Path:
    """Write a single batch result to disk. Returns the output path."""
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_id = result.custom_id.replace("/", "_").replace(" ", "_")
    out_path = output_dir / f"{safe_id}.json"

    output: dict = {"custom_id": result.custom_id}

    if result.result.type == "succeeded":
        msg = result.result.message
        output["status"] = "succeeded"
        output["model"] = msg.model
        output["content"] = [block.text for block in msg.content if hasattr(block, "text")]
        output["usage"] = {
            "input_tokens": msg.usage.input_tokens,
            "output_tokens": msg.usage.output_tokens,
        }
    elif result.result.type == "errored":
        output["status"] = "errored"
        output["error"] = {
            "type": result.result.error.type,
            "message": getattr(result.result.error, "message", str(result.result.error)),
        }
    else:
        output["status"] = result.result.type

    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcile Anthropic Batch API results")
    parser.add_argument(
        "--output-dir",
        default="tmp/batch-results",
        help="Directory to write result files (default: tmp/batch-results)",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    active_jobs = load_active_jobs()

    if not active_jobs:
        print("No active batch jobs to reconcile.")
        return 0

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY environment variable not set.", file=sys.stderr)
        return 1

    client = anthropic.Anthropic(api_key=api_key)

    total_succeeded = 0
    total_errored = 0
    updated_jobs = list(active_jobs)  # copy to mutate

    for i, job in enumerate(updated_jobs):
        batch_id = job["batch_id"]
        print(f"Checking batch {batch_id}...")

        try:
            batch = client.messages.batches.retrieve(batch_id)
        except anthropic.APIError as exc:
            print(f"  Warning: could not retrieve batch {batch_id}: {exc}", file=sys.stderr)
            continue

        print(f"  Status: {batch.processing_status}  "
              f"({batch.request_counts.succeeded} succeeded, "
              f"{batch.request_counts.errored} errored, "
              f"{batch.request_counts.processing} processing)")

        if batch.processing_status != "ended":
            print("  Not finished yet — skipping.")
            continue

        # Collect results
        result_paths = []
        for result in client.messages.batches.results(batch_id):
            path = write_result(result, output_dir)
            result_paths.append(str(path))
            if result.result.type == "succeeded":
                total_succeeded += 1
            else:
                total_errored += 1

        # Mark job completed
        updated_jobs[i]["status"] = "completed"
        updated_jobs[i]["completed_at"] = now()
        updated_jobs[i]["result_paths"] = result_paths
        updated_jobs[i]["counts"] = {
            "succeeded": batch.request_counts.succeeded,
            "errored": batch.request_counts.errored,
        }

        append_completed_job(updated_jobs[i])
        print(f"  Results written to: {output_dir}/")

    save_active_jobs([j for j in updated_jobs if j.get("status") not in {"completed", "errored", "expired"}])

    if total_succeeded + total_errored > 0:
        print(f"\nReconciliation complete: {total_succeeded} succeeded, {total_errored} errored")
        print(f"Results in: {output_dir}/")
    else:
        print("\nNo completed results found — batches may still be processing.")
        print("Run: python scripts/ops/batch_status.py")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
