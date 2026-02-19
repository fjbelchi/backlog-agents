#!/usr/bin/env python3
"""Submit ticket .md files to the Anthropic Batch API (via LiteLLM proxy)
for asynchronous Plan and Review gate processing at 50% cost reduction.

Accepts ticket markdown files as positional arguments, builds single-shot
plan requests for each, submits them as one batch to the LiteLLM /v1/batches
endpoint, and saves batch state for later reconciliation.

Usage:
    python3 scripts/ops/batch_submit.py backlog/data/pending/*.md
    python3 scripts/ops/batch_submit.py --dry-run backlog/data/pending/FEAT-*.md

Environment:
    LITELLM_MASTER_KEY  API key for LiteLLM proxy (default: sk-litellm-changeme)
    LITELLM_BASE_URL    Base URL for proxy (default: http://localhost:8000)

Constraints:
    - Batch API does NOT support tool_use or multi-turn conversations
    - Only single-shot messages (one user message -> one assistant response)
    - Uses model "balanced" (maps to Sonnet via LiteLLM)
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
BATCH_MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 8192

MODEL_ALIASES: dict[str, str] = {
    "cheap": "claude-haiku-4-5",
    "balanced": "claude-sonnet-4-6",
    "frontier": "claude-opus-4-6",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Ticket parsing
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_SECTION_RE = re.compile(r"^##\s+(.+)$", re.MULTILINE)


def _parse_yaml_simple(text: str) -> dict[str, str]:
    """Minimal YAML-like key: value parser (no dependency on PyYAML)."""
    result: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, _, val = line.partition(":")
            result[key.strip()] = val.strip()
    return result


def _extract_section(content: str, heading: str) -> str | None:
    """Extract text under a ## heading until the next ## heading."""
    pattern = re.compile(
        rf"^##\s+{re.escape(heading)}\s*\n(.*?)(?=^##\s|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(content)
    if match:
        return match.group(1).strip()
    return None


def parse_ticket(filepath: str) -> dict | None:
    """Parse a ticket .md file into a structured dict.

    Returns None if the file does not exist.
    """
    path = Path(filepath)
    if not path.exists():
        return None

    raw = path.read_text(encoding="utf-8")
    meta: dict[str, str] = {}
    body = raw

    fm_match = _FRONTMATTER_RE.match(raw)
    if fm_match:
        meta = _parse_yaml_simple(fm_match.group(1))
        body = raw[fm_match.end():]

    description = _extract_section(raw, "Description") or ""

    return {
        "id": meta.get("id", ""),
        "title": meta.get("title", ""),
        "priority": meta.get("priority", "medium"),
        "filepath": str(path.resolve()),
        "content": raw,
        "description": description,
    }


# ---------------------------------------------------------------------------
# Batch request construction
# ---------------------------------------------------------------------------

PLAN_SYSTEM_PROMPT = (
    "You are a senior software engineer creating an implementation plan for a "
    "backlog ticket. Analyze the ticket below and produce a clear, step-by-step "
    "implementation plan. Include:\n"
    "1. Files to create or modify (with brief description of changes)\n"
    "2. Test strategy (which tests to write first — TDD)\n"
    "3. Potential risks or edge cases\n"
    "4. Estimated complexity (low/medium/high)\n\n"
    "Keep the plan concise and actionable. Do NOT write code — just the plan."
)

REVIEW_TEMPLATE = (
    "You are a code reviewer. Review the implementation of ticket {ticket_id} "
    "against the acceptance criteria below. Check for:\n"
    "1. All acceptance criteria met\n"
    "2. Test coverage (happy path, error path, edge cases)\n"
    "3. Code quality and readability\n"
    "4. Potential bugs or security issues\n\n"
    "Ticket content:\n{ticket_content}\n\n"
    "Score each finding 0-100 confidence. Return findings as a structured list."
)


def build_batch_requests(tickets: list[dict]) -> list[dict]:
    """Build Batch API request objects for plan generation.

    Each ticket becomes one single-shot request (no tool_use, no multi-turn).
    """
    if not tickets:
        return []

    batch_requests = []
    for ticket in tickets:
        ticket_id = ticket.get("id", "unknown")
        content = ticket.get("content", "")

        req = {
            "custom_id": f"{ticket_id}-plan",
            "params": {
                "model": BATCH_MODEL,
                "max_tokens": MAX_TOKENS,
                "system": PLAN_SYSTEM_PROMPT,
                "messages": [
                    {
                        "role": "user",
                        "content": f"Create an implementation plan for this ticket:\n\n{content}",
                    }
                ],
            },
        }
        batch_requests.append(req)

    return batch_requests


def _build_review_templates(tickets: list[dict]) -> dict[str, str]:
    """Build review message templates to save for later (post-implementation)."""
    templates = {}
    for ticket in tickets:
        ticket_id = ticket.get("id", "unknown")
        templates[ticket_id] = REVIEW_TEMPLATE.format(
            ticket_id=ticket_id,
            ticket_content=ticket.get("content", ""),
        )
    return templates


# ---------------------------------------------------------------------------
# State persistence
# ---------------------------------------------------------------------------


def save_batch_state(
    batch_id: str,
    ticket_mapping: dict[str, str],
    state_path: Path = DEFAULT_STATE_PATH,
    review_templates: dict[str, str] | None = None,
) -> None:
    """Save batch ID and ticket mapping to state file."""
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state = {
        "batch_id": batch_id,
        "status": "in_progress",
        "submitted_at": now_iso(),
        "request_count": len(ticket_mapping),
        "ticket_mapping": ticket_mapping,
        "review_templates": review_templates or {},
    }
    state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(state_path: Path | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Submit ticket .md files to Batch API via LiteLLM proxy"
    )
    parser.add_argument(
        "tickets",
        nargs="*",
        help="Ticket .md files to process",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be submitted without sending",
    )
    args = parser.parse_args()

    if state_path is None:
        state_path = DEFAULT_STATE_PATH

    if not args.tickets:
        print("Error: no ticket files provided.", file=sys.stderr)
        print("Usage: python3 batch_submit.py backlog/data/pending/*.md", file=sys.stderr)
        return 1

    # Parse tickets
    tickets = []
    for fpath in args.tickets:
        parsed = parse_ticket(fpath)
        if parsed is None:
            print(f"Warning: skipping {fpath} (file not found)", file=sys.stderr)
            continue
        tickets.append(parsed)

    if not tickets:
        print("Error: no valid tickets found.", file=sys.stderr)
        return 1

    # Build requests
    batch_requests = build_batch_requests(tickets)
    review_templates = _build_review_templates(tickets)

    # Build ticket mapping: custom_id -> filepath
    ticket_mapping = {}
    for ticket in tickets:
        ticket_id = ticket.get("id", "unknown")
        ticket_mapping[f"{ticket_id}-plan"] = ticket["filepath"]

    print(f"Prepared {len(batch_requests)} plan request(s) for batch submission.")
    for req in batch_requests:
        print(f"  {req['custom_id']}  model={req['params']['model']}")

    if args.dry_run:
        print("[dry-run] No API call made.")
        return 0

    # Submit to LiteLLM proxy
    base_url = os.environ.get("LITELLM_BASE_URL", DEFAULT_BASE_URL)
    api_key = os.environ.get("LITELLM_MASTER_KEY", DEFAULT_API_KEY)

    endpoint = f"{base_url.rstrip('/')}/v1/batches"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {"requests": batch_requests}

    print(f"Submitting batch to {endpoint}...")

    try:
        resp = requests.post(endpoint, headers=headers, json=payload, timeout=60)
    except requests.RequestException as exc:
        print(f"Error: could not reach LiteLLM proxy: {exc}", file=sys.stderr)
        return 1

    if resp.status_code != 200:
        print(f"Error: batch submission failed (HTTP {resp.status_code})", file=sys.stderr)
        print(f"Response: {resp.text[:500]}", file=sys.stderr)
        return 1

    data = resp.json()
    batch_id = data.get("id", "")
    if not batch_id:
        print("Error: no batch ID returned in response.", file=sys.stderr)
        return 1

    # Save state
    save_batch_state(
        batch_id=batch_id,
        ticket_mapping=ticket_mapping,
        state_path=state_path,
        review_templates=review_templates,
    )

    print(f"Batch submitted: id={batch_id}  requests={len(batch_requests)}")
    print(f"State saved to: {state_path}")
    print()
    print("Next steps:")
    print(f"  Check status:     python3 scripts/ops/batch_status.py")
    print(f"  Collect results:  python3 scripts/ops/batch_reconcile.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
