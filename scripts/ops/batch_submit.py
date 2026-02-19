#!/usr/bin/env python3
"""Submit tickets to the Anthropic Batch API for 50% cost reduction.

Reads ticket requests from a JSONL queue file, submits them as a single
batch job to the Anthropic Batch API, and writes the batch ID to the
active jobs file for later reconciliation.

Usage:
    python scripts/ops/batch_submit.py --queue tmp/batch-queue.jsonl
    python scripts/ops/batch_submit.py --queue tmp/batch-queue.jsonl --dry-run

Queue entry format (JSONL):
    {
        "id": "FEAT-001",
        "custom_id": "feat-001-implement",
        "model": "claude-sonnet-4-6",
        "max_tokens": 8192,
        "system": "...",
        "messages": [{"role": "user", "content": "..."}],
        "status": "queued"
    }
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

# Map from LiteLLM alias to actual Anthropic model ID
MODEL_ALIASES: dict[str, str] = {
    "cheap":    "claude-haiku-4-5",
    "balanced": "claude-sonnet-4-6",
    "frontier": "claude-opus-4-6",
}


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def resolve_model(model: str) -> str:
    """Resolve a LiteLLM alias or pass through a real model ID."""
    return MODEL_ALIASES.get(model, model)


def load_queue(qpath: Path) -> list[dict]:
    """Load queued (not yet submitted) entries from the queue file."""
    entries = []
    for line in qpath.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        item = json.loads(line)
        if item.get("status") == "queued":
            entries.append(item)
    return entries


def build_batch_requests(entries: list[dict]) -> list[dict]:
    """Convert queue entries to Anthropic Batch API request format."""
    requests = []
    for entry in entries:
        model = resolve_model(entry.get("model", "balanced"))
        req: dict = {
            "custom_id": entry.get("custom_id", entry.get("id", f"req-{len(requests)}")),
            "params": {
                "model": model,
                "max_tokens": entry.get("max_tokens", 8192),
                "messages": entry["messages"],
            },
        }
        if entry.get("system"):
            req["params"]["system"] = entry["system"]
        requests.append(req)
    return requests


def mark_submitted(qpath: Path, submitted_ids: set[str]) -> None:
    """Mark submitted entries in the queue file."""
    updated = []
    for line in qpath.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        item = json.loads(line)
        custom_id = item.get("custom_id", item.get("id", ""))
        if custom_id in submitted_ids and item.get("status") == "queued":
            item["status"] = "submitted"
            item["submitted_at"] = now()
        updated.append(json.dumps(item))
    qpath.write_text("\n".join(updated) + "\n", encoding="utf-8")


def save_active_job(batch_id: str, queue_path: str, count: int) -> None:
    """Append the new batch job to the active jobs file."""
    ACTIVE_JOBS_FILE.parent.mkdir(parents=True, exist_ok=True)
    job = {
        "batch_id": batch_id,
        "queue_path": str(queue_path),
        "request_count": count,
        "status": "in_progress",
        "submitted_at": now(),
    }
    with ACTIVE_JOBS_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(job) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Submit batch jobs to Anthropic Batch API")
    parser.add_argument("--queue", required=True, help="Path to JSONL queue file")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be submitted without sending")
    args = parser.parse_args()

    qpath = Path(args.queue)
    if not qpath.exists():
        print(f"Error: queue file not found: {qpath}", file=sys.stderr)
        return 1

    entries = load_queue(qpath)
    if not entries:
        print("No queued entries found — nothing to submit.")
        return 0

    requests = build_batch_requests(entries)
    print(f"Preparing batch with {len(requests)} request(s)...")

    if args.dry_run:
        print("[dry-run] Would submit:")
        for r in requests:
            print(f"  custom_id={r['custom_id']}  model={r['params']['model']}  max_tokens={r['params']['max_tokens']}")
        return 0

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY environment variable not set.", file=sys.stderr)
        print("Note: Batch API calls go directly to Anthropic, not via LiteLLM proxy.", file=sys.stderr)
        return 1

    client = anthropic.Anthropic(api_key=api_key)

    try:
        batch = client.messages.batches.create(requests=requests)
    except anthropic.APIError as exc:
        print(f"Error: Batch API call failed: {exc}", file=sys.stderr)
        return 1

    submitted_ids = {r["custom_id"] for r in requests}
    mark_submitted(qpath, submitted_ids)
    save_active_job(batch.id, args.queue, len(requests))

    print(f"Batch submitted: id={batch.id}  requests={len(requests)}")
    print(f"Active jobs logged to: {ACTIVE_JOBS_FILE}")
    print(f"Check status: python scripts/ops/batch_status.py")
    print(f"Collect results: python scripts/ops/batch_reconcile.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
