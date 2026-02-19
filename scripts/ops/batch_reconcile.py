#!/usr/bin/env python3
"""Reconcile completed Batch API results and write plans into ticket .md files.

Reads batch state from .backlog-ops/batch-state.json, checks batch status via
the LiteLLM proxy /v1/batches/{batch_id} endpoint, and when complete extracts
plan results and writes them into each ticket under ## Implementation Plan.

Usage:
    python3 scripts/ops/batch_reconcile.py
    python3 scripts/ops/batch_reconcile.py --state .backlog-ops/batch-state.json

Environment:
    LITELLM_MASTER_KEY  API key for LiteLLM proxy (default: sk-litellm-changeme)
    LITELLM_BASE_URL    Base URL for proxy (default: http://localhost:8000)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests


DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_API_KEY = "sk-litellm-changeme"
DEFAULT_STATE_PATH = Path(".backlog-ops/batch-state.json")


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# State loading
# ---------------------------------------------------------------------------


def load_batch_state(state_path: Path) -> dict | None:
    """Load batch state from JSON file. Returns None if not found."""
    if not state_path.exists():
        return None
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def save_batch_state(state: dict, state_path: Path) -> None:
    """Write updated state back to disk."""
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Result extraction
# ---------------------------------------------------------------------------


def extract_plan_content(result: dict) -> str | None:
    """Extract plan text from a single batch result entry.

    Expected structure (OpenAI-compatible via LiteLLM):
        {
            "custom_id": "FEAT-001-plan",
            "response": {
                "status_code": 200,
                "body": {
                    "choices": [{"message": {"content": "..."}}]
                }
            }
        }

    Returns None if the result indicates failure.
    """
    resp = result.get("response", {})
    status = resp.get("status_code", 0)
    if status != 200:
        return None

    body = resp.get("body", {})
    choices = body.get("choices", [])
    if not choices:
        return None

    return choices[0].get("message", {}).get("content")


# ---------------------------------------------------------------------------
# Ticket writing
# ---------------------------------------------------------------------------


_PLAN_HEADING = "## Implementation Plan"
_PLAN_SECTION_RE = re.compile(
    rf"^{re.escape(_PLAN_HEADING)}\s*\n(.*?)(?=^##\s|\Z)",
    re.MULTILINE | re.DOTALL,
)


def write_plan_to_ticket(ticket_path: str, plan_text: str) -> bool:
    """Write or replace the ## Implementation Plan section in a ticket .md file.

    Returns True if the file was updated, False otherwise.
    """
    path = Path(ticket_path)
    if not path.exists():
        return False

    content = path.read_text(encoding="utf-8")
    plan_block = f"{_PLAN_HEADING}\n\n{plan_text}\n\n"

    if _PLAN_SECTION_RE.search(content):
        # Replace existing section
        content = _PLAN_SECTION_RE.sub(plan_block, content, count=1)
    else:
        # Append before end of file
        content = content.rstrip() + "\n\n" + plan_block

    path.write_text(content, encoding="utf-8")
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(state_path: Path | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reconcile Batch API results into ticket .md files"
    )
    parser.add_argument(
        "--state",
        default=None,
        help="Path to batch-state.json (default: .backlog-ops/batch-state.json)",
    )
    args = parser.parse_args()

    if state_path is None:
        state_path = Path(args.state) if args.state else DEFAULT_STATE_PATH

    state = load_batch_state(state_path)
    if state is None:
        print("No batch state found. Nothing to reconcile.")
        print(f"Expected state file at: {state_path}")
        return 0

    batch_id = state.get("batch_id", "")
    if not batch_id:
        print("Error: batch state has no batch_id.", file=sys.stderr)
        return 1

    if state.get("status") == "completed":
        print(f"Batch {batch_id} is already reconciled.")
        return 0

    # Check batch status
    base_url = os.environ.get("LITELLM_BASE_URL", DEFAULT_BASE_URL)
    api_key = os.environ.get("LITELLM_MASTER_KEY", DEFAULT_API_KEY)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    status_url = f"{base_url.rstrip('/')}/v1/batches/{batch_id}"
    print(f"Checking batch {batch_id}...")

    try:
        resp = requests.get(status_url, headers=headers, timeout=30)
    except requests.RequestException as exc:
        print(f"Error: could not reach LiteLLM proxy: {exc}", file=sys.stderr)
        return 1

    if resp.status_code != 200:
        print(f"Error: status check failed (HTTP {resp.status_code})", file=sys.stderr)
        return 1

    batch_info = resp.json()
    batch_status = batch_info.get("status", "unknown")
    counts = batch_info.get("request_counts", {})

    print(f"  Status: {batch_status}")
    print(f"  Counts: {json.dumps(counts)}")

    if batch_status not in ("completed", "ended"):
        pending = counts.get("total", 0) - counts.get("completed", 0) - counts.get("failed", 0)
        print(f"\nBatch is still in_progress ({pending} pending).")
        print("Run this script again later to collect results.")
        return 0

    # Fetch results
    results_url = f"{base_url.rstrip('/')}/v1/batches/{batch_id}/results"
    try:
        results_resp = requests.get(results_url, headers=headers, timeout=60)
    except requests.RequestException as exc:
        print(f"Error: could not fetch results: {exc}", file=sys.stderr)
        return 1

    if results_resp.status_code != 200:
        print(f"Error: results fetch failed (HTTP {results_resp.status_code})", file=sys.stderr)
        return 1

    # Parse JSONL results (one JSON object per line)
    ticket_mapping = state.get("ticket_mapping", {})
    completed_count = 0
    failed_count = 0
    pending_count = 0

    results = []
    for line in results_resp.iter_lines():
        if not line:
            continue
        if isinstance(line, bytes):
            line = line.decode("utf-8")
        try:
            results.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    for result in results:
        custom_id = result.get("custom_id", "")
        plan_text = extract_plan_content(result)

        if plan_text is None:
            failed_count += 1
            print(f"  FAILED: {custom_id}")
            continue

        ticket_path = ticket_mapping.get(custom_id)
        if not ticket_path:
            print(f"  Warning: no ticket mapped for {custom_id}", file=sys.stderr)
            failed_count += 1
            continue

        if write_plan_to_ticket(ticket_path, plan_text):
            completed_count += 1
            print(f"  OK: {custom_id} -> {ticket_path}")
        else:
            failed_count += 1
            print(f"  SKIP: {custom_id} (ticket file not found: {ticket_path})")

    # Update state
    state["status"] = "completed"
    state["completed_at"] = now_iso()
    state["results"] = {
        "completed": completed_count,
        "failed": failed_count,
    }
    save_batch_state(state, state_path)

    # Summary
    print(f"\nReconciliation complete:")
    print(f"  Completed: {completed_count}")
    print(f"  Failed:    {failed_count}")
    print(f"  Pending:   {pending_count}")

    if state.get("review_templates"):
        print(f"\nReview templates saved in state for post-implementation use.")
        print(f"State: {state_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
