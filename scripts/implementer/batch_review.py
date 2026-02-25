#!/usr/bin/env python3
"""Submit Gate 4 code reviews to Anthropic Batch API.

Each focus type (spec, quality, security, history) becomes one request
in a single batch job, with cache_control breakpoints on stable content.

Usage:
    python3 scripts/implementer/batch_review.py \
        --diff <(git diff HEAD~1) \
        --ticket backlog/data/pending/FEAT-001.md \
        --focus spec,quality \
        --batch-state .backlog-ops/review-batch-state.json

Output (stdout): JSON  {"batch_id": "...", "request_count": N, "ticket_id": "..."}
Exit codes: 0=ok, 1=API error, 2=empty diff
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

BATCH_API_PATH = "/v1/messages/batches"
ANTHROPIC_BETA_HEADER = "prompt-caching-2024-07-31"
BATCH_MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 4096
DEFAULT_STATE_PATH = Path(".backlog-ops/review-batch-state.json")
DEFAULT_REVIEWER_PREFIX_PATHS = [
    "skills/backlog-implementer/templates/reviewer-prefix.md",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_reviewer_prefix(plugin_root: str | None) -> str:
    """Load reviewer-prefix.md from plugin root or fallback paths."""
    search = []
    if plugin_root:
        search.append(
            Path(plugin_root) / "skills/backlog-implementer/templates/reviewer-prefix.md"
        )
    for rel in DEFAULT_REVIEWER_PREFIX_PATHS:
        search.append(Path(rel))
    for p in search:
        if p.exists():
            return p.read_text(encoding="utf-8")
    return "You are a code reviewer. Review the diff against the acceptance criteria."


def build_review_requests(
    ticket_id: str,
    diff: str,
    ticket_content: str,
    code_rules: str,
    focus_types: list[str],
    reviewer_prefix: str,
) -> list[dict]:
    """Build one Batch API request per focus type.

    Raises ValueError if diff is empty.
    """
    if not diff or not diff.strip():
        raise ValueError("empty diff — nothing to review")

    acs = _extract_section(ticket_content, "Acceptance Criteria") or ticket_content
    requests_list = []

    for focus in focus_types:
        req = {
            "custom_id": f"{ticket_id}-review-{focus}",
            "params": {
                "model": BATCH_MODEL,
                "max_tokens": MAX_TOKENS,
                "system": [
                    {
                        "type": "text",
                        "text": reviewer_prefix,
                        "cache_control": {"type": "ephemeral"},
                    },
                    {
                        "type": "text",
                        "text": f"Focus: {focus}",
                        # no cache_control — varies per focus type
                    },
                ],
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": code_rules or "",
                                "cache_control": {"type": "ephemeral"},
                            },
                            {
                                "type": "text",
                                "text": (
                                    f"DIFF:\n```\n{diff}\n```\n\n"
                                    f"ACCEPTANCE CRITERIA:\n{acs}"
                                ),
                            },
                        ],
                    }
                ],
            },
        }
        requests_list.append(req)

    return requests_list


def _extract_section(content: str, heading: str) -> str | None:
    import re
    pattern = re.compile(
        rf"^##\s+{re.escape(heading)}\s*\n(.*?)(?=^##\s|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    m = pattern.search(content)
    return m.group(1).strip() if m else None


def submit_batch(requests_list: list[dict], base_url: str, api_key: str) -> str:
    """Submit batch to API, return batch_id."""
    endpoint = f"{base_url.rstrip('/')}{BATCH_API_PATH}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "anthropic-beta": ANTHROPIC_BETA_HEADER,
    }
    resp = requests.post(
        endpoint, headers=headers, json={"requests": requests_list}, timeout=60
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Batch API error {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    batch_id = data.get("id", "")
    if not batch_id:
        raise RuntimeError("No batch ID in response")
    return batch_id


def save_state(
    batch_id: str,
    ticket_id: str,
    focus_types: list[str],
    state_path: Path,
) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state = {
        "batch_id": batch_id,
        "ticket_id": ticket_id,
        "focus_types": focus_types,
        "submitted_at": now_iso(),
        "status": "in_progress",
    }
    state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Submit Gate 4 reviews via Batch API")
    ap.add_argument("--diff", required=True, help="Path to diff file (or - for stdin)")
    ap.add_argument("--ticket", required=True, help="Path to ticket .md")
    ap.add_argument("--code-rules", default="", help="Path to code-rules.md")
    ap.add_argument("--focus", default="spec,quality", help="Comma-separated focus types")
    ap.add_argument("--batch-state", default=str(DEFAULT_STATE_PATH))
    ap.add_argument("--base-url", default=os.environ.get("LITELLM_BASE_URL", "https://api.anthropic.com"))
    ap.add_argument("--api-key-env", default="ANTHROPIC_API_KEY")
    ap.add_argument("--plugin-root", default=os.environ.get("CLAUDE_PLUGIN_ROOT", ""))
    a = ap.parse_args()

    # Read diff
    if a.diff == "-":
        diff = sys.stdin.read()
    else:
        diff_path = Path(a.diff)
        diff = diff_path.read_text(encoding="utf-8") if diff_path.exists() else ""

    if not diff.strip():
        print("Error: empty diff", file=sys.stderr)
        return 2

    ticket_content = Path(a.ticket).read_text(encoding="utf-8")
    ticket_id = Path(a.ticket).stem

    code_rules = ""
    if a.code_rules and Path(a.code_rules).exists():
        code_rules = Path(a.code_rules).read_text(encoding="utf-8")

    focus_types = [f.strip() for f in a.focus.split(",") if f.strip()]
    reviewer_prefix = load_reviewer_prefix(a.plugin_root or None)
    api_key = os.environ.get(a.api_key_env, "")
    if not api_key:
        print(f"Error: env var {a.api_key_env} not set", file=sys.stderr)
        return 1

    try:
        reqs = build_review_requests(
            ticket_id=ticket_id,
            diff=diff,
            ticket_content=ticket_content,
            code_rules=code_rules,
            focus_types=focus_types,
            reviewer_prefix=reviewer_prefix,
        )
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    try:
        batch_id = submit_batch(reqs, a.base_url, api_key)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    save_state(batch_id, ticket_id, focus_types, Path(a.batch_state))
    print(json.dumps({"batch_id": batch_id, "request_count": len(reqs), "ticket_id": ticket_id}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
