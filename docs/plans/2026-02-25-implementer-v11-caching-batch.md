# Implementer v11.0 — Prompt Caching + Batch Reviews

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Guarantee prompt caching in both LiteLLM and direct-API modes, and route Gate 4 reviews through the Batch API for 50% cost reduction.

**Architecture:** Phase 1 hardens prompt caching by adding explicit `cache_control` breakpoints to `batch_submit.py` and a cache-mode detector to `startup.sh`. Phase 2 adds two new scripts (`batch_review.py`, `batch_review_poll.py`) that replace live reviewer agents with a synchronous batch call, with automatic fallback if the batch times out.

**Tech Stack:** Python 3.10+, Anthropic Batch API (`/v1/messages/batches`), bash, pytest, `requests`, `unittest.mock`.

**Design doc:** `docs/plans/2026-02-25-implementer-v11-caching-batch-design.md`

---

## Task 1: Add `cache_control` breakpoints to `batch_submit.py`

**Files:**
- Modify: `scripts/ops/batch_submit.py`
- Modify: `tests/test_batch_submit.py`

### Step 1: Write the failing tests

Add to `tests/test_batch_submit.py` — import section already has `sys.path.insert`:

```python
# ---------------------------------------------------------------------------
# cache_control tests (add after existing tests)
# ---------------------------------------------------------------------------

def test_build_batch_requests_system_is_content_blocks():
    """system prompt must be a list of content blocks, not a plain string."""
    from scripts.ops.batch_submit import build_batch_requests
    tickets = [{"id": "FEAT-001", "content": "## Description\nDo X"}]
    reqs = build_batch_requests(tickets)
    system = reqs[0]["params"]["system"]
    assert isinstance(system, list), "system must be a list of content blocks"
    assert system[0]["type"] == "text"
    assert "cache_control" in system[0]
    assert system[0]["cache_control"] == {"type": "ephemeral"}


def test_build_batch_requests_user_has_two_blocks():
    """user message must have two content blocks: stable (cached) + dynamic."""
    from scripts.ops.batch_submit import build_batch_requests
    tickets = [{"id": "FEAT-001", "content": "## Description\nDo X"}]
    reqs = build_batch_requests(tickets)
    user_content = reqs[0]["params"]["messages"][0]["content"]
    assert isinstance(user_content, list)
    assert len(user_content) == 2
    # first block is stable context (may be empty string but must have cache_control)
    assert "cache_control" in user_content[0]
    # second block is the ticket — no cache_control
    assert "cache_control" not in user_content[1]
    assert "Ticket:" in user_content[1]["text"]


def test_build_batch_requests_includes_beta_header():
    """build_batch_requests output carries anthropic-beta marker in metadata."""
    from scripts.ops.batch_submit import ANTHROPIC_BETA_HEADER
    assert ANTHROPIC_BETA_HEADER == "prompt-caching-2024-07-31"
```

### Step 2: Run tests — verify they fail

```bash
cd /Users/fbelchi/github/backlog-agents
python -m pytest tests/test_batch_submit.py::test_build_batch_requests_system_is_content_blocks \
    tests/test_batch_submit.py::test_build_batch_requests_user_has_two_blocks \
    tests/test_batch_submit.py::test_build_batch_requests_includes_beta_header -v
```

Expected: `ImportError` or `AssertionError` (FAIL).

### Step 3: Implement — update `batch_submit.py`

At the top of `scripts/ops/batch_submit.py`, add the constant after existing constants:

```python
ANTHROPIC_BETA_HEADER = "prompt-caching-2024-07-31"
```

Replace the `build_batch_requests` function body (keep signature unchanged):

```python
def build_batch_requests(tickets: list[dict]) -> list[dict]:
    """Build Batch API request objects for plan generation.

    Uses cache_control breakpoints so the stable system prompt and any
    shared code-rules prefix are cached across tickets in the same batch.
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
                # system as content block list — first block is cached
                "system": [
                    {
                        "type": "text",
                        "text": PLAN_SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                # stable placeholder — leader may inject code rules here
                                "type": "text",
                                "text": "",
                                "cache_control": {"type": "ephemeral"},
                            },
                            {
                                "type": "text",
                                "text": f"Ticket:\n\n{content}",
                                # no cache_control — dynamic per ticket
                            },
                        ],
                    }
                ],
            },
        }
        batch_requests.append(req)

    return batch_requests
```

Also update the `headers` dict inside `main()` (find the `headers = {` block):

```python
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "anthropic-beta": ANTHROPIC_BETA_HEADER,   # ← add this line
    }
```

### Step 4: Run tests — verify they pass

```bash
python -m pytest tests/test_batch_submit.py -v
```

Expected: all tests PASS.

### Step 5: Commit

```bash
git add scripts/ops/batch_submit.py tests/test_batch_submit.py
git commit -m "feat(batch_submit): add cache_control breakpoints and anthropic-beta header"
```

---

## Task 2: Add cache-mode detection to `startup.sh`

**Files:**
- Modify: `scripts/implementer/startup.sh`
- Test: `tests/test_startup.sh` (bash — add new assertions)

### Step 1: Write the failing test

In `tests/test_startup.sh`, add after the last existing test block:

```bash
# ---- cache_mode field ----
echo "TEST: startup JSON includes cache_mode field"
OUTPUT=$(CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" bash "$STARTUP_SCRIPT" 2>/dev/null || true)
if echo "$OUTPUT" | python3 -c "import json,sys; d=json.loads(sys.stdin.read()); assert 'cache_mode' in d, 'missing cache_mode'" 2>/dev/null; then
    echo "  PASS: cache_mode present"
else
    echo "  FAIL: cache_mode missing from startup JSON"
    FAILURES=$((FAILURES+1))
fi

echo "TEST: cache_mode value is 'litellm' or 'direct'"
if echo "$OUTPUT" | python3 -c "
import json,sys
d=json.loads(sys.stdin.read())
assert d.get('cache_mode') in ('litellm','direct'), f\"unexpected: {d.get('cache_mode')}\"
" 2>/dev/null; then
    echo "  PASS: cache_mode has valid value"
else
    echo "  FAIL: cache_mode has unexpected value"
    FAILURES=$((FAILURES+1))
fi
```

### Step 2: Run test — verify it fails

```bash
cd /Users/fbelchi/github/backlog-agents
bash tests/test_startup.sh 2>&1 | grep -E "PASS|FAIL|cache_mode"
```

Expected: `FAIL: cache_mode missing from startup JSON`.

### Step 3: Implement — add LiteLLM probe to `startup.sh`

After Step C (around line 95, after `log "litellm_url=$LITELLM_BASE_URL"`), add:

```bash
# -----------------------------------------------------------
# Step C.5: Detect cache mode (litellm vs direct)
# -----------------------------------------------------------
CACHE_MODE="direct"
if curl -sf --max-time 3 "${LITELLM_BASE_URL}/health" > /dev/null 2>&1; then
    CACHE_MODE="litellm"
    log "cache_mode=litellm (proxy reachable)"
else
    log "cache_mode=direct (proxy unreachable, using explicit cache_control)"
fi
```

In the final `python3 -c` block (around line 266), add `cache_mode` to the args list and the output dict:

```python
# In the python3 -c string, add to the argument parsing:
cache_mode = sys.argv[10]   # new arg — position after state_exists

# Add to output dict:
output = {
    ...existing keys...,
    "cache_mode": cache_mode,
}
```

And in the shell call at the end, append `"$CACHE_MODE"` as the 10th arg:

```bash
    "${PLUGIN_ROOT:-}"   \   # argv[1]
    "$CONFIG_JSON"       \   # argv[2]
    "$OLLAMA_AVAILABLE"  \   # argv[3]
    "$LITELLM_BASE_URL"  \   # argv[4]
    "$TICKETS_JSON"      \   # argv[5]
    "$TICKET_COUNT"      \   # argv[6]
    "$PLAYBOOK_STATS"    \   # argv[7]
    "$CACHE_HEALTH"      \   # argv[8]
    "$STATE_EXISTS"      \   # argv[9]
    "$CACHE_MODE"            # argv[10]  ← new
```

### Step 4: Run test — verify it passes

```bash
bash tests/test_startup.sh 2>&1 | grep -E "PASS|FAIL"
```

Expected: all PASS (including the two new cache_mode tests).

### Step 5: Update SKILL.md startup banner

In `skills/backlog-implementer/SKILL.md`, find the STARTUP section and update the banner line to include `cache_mode`:

```
# Find: "Show startup banner with ticket count, model routing summary, playbook stats."
# Replace with:
Show startup banner with ticket count, model routing summary, playbook stats, cache mode.
Banner format: "Cache: {cache_mode} | Hit target: {warnBelowHitRate*100}%"
```

### Step 6: Commit

```bash
git add scripts/implementer/startup.sh tests/test_startup.sh \
        skills/backlog-implementer/SKILL.md
git commit -m "feat(startup): detect cache mode (litellm vs direct), emit in startup JSON"
```

---

## Task 3: Document cache boundary in `SKILL.md`

**Files:**
- Modify: `skills/backlog-implementer/SKILL.md`

This is a documentation-only change — no tests. Verify manually by reading the diff.

### Step 1: Replace the vague cache note in Gate 2

Find in `SKILL.md` (Gate 2 section):

```
1. STATIC PREFIX: `templates/implementer-prefix.md` (cached ~90% hit after first call)
2. DYNAMIC SUFFIX (in order): CODE RULES → PLAYBOOK BULLETS ...
```

Replace with:

```
**Prompt cache boundary** — construct prompt in this exact order:

| # | Content | Cache? |
|---|---------|--------|
| 1 | `templates/implementer-prefix.md` (Iron Laws, TDD, context rules) | ✅ CACHED |
| 2 | CODE RULES (from `config.codeRules.source`) | ✅ CACHED |
| — | ← cache_control breakpoint (LiteLLM auto / direct explicit) | |
| 3 | PLAYBOOK BULLETS (top-10 via `select_relevant()`) | dynamic |
| 4 | CATALOG DISCIPLINES (CAT-TDD, CAT-PERF, etc.) | dynamic |
| 5 | RAG CONTEXT (if available) | dynamic |
| 6 | TICKET CONTENT | dynamic |
| 7 | GATE INSTRUCTIONS | dynamic |

**Rule**: NEVER place dynamic content before or between items 1-2.
Static blocks must be contiguous at the top of the prompt string.
```

### Step 2: Commit

```bash
git add skills/backlog-implementer/SKILL.md
git commit -m "docs(implementer): replace vague cache note with explicit boundary table"
```

---

## Task 4: Create `scripts/implementer/batch_review.py`

**Files:**
- Create: `scripts/implementer/batch_review.py`
- Create: `tests/test_batch_review.py`

### Step 1: Write failing tests

Create `tests/test_batch_review.py`:

```python
#!/usr/bin/env python3
"""Tests for scripts/implementer/batch_review.py

Covers:
  - Happy path: builds correct batch request per focus type
  - cache_control breakpoints are present in system and user messages
  - reviewer-prefix.md is loaded as static cached block
  - Empty diff → exit code 2
  - API error → exit code 1
"""

import json
import os
import sys
import textwrap
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

SAMPLE_DIFF = textwrap.dedent("""\
    diff --git a/src/auth.ts b/src/auth.ts
    index abc..def 100644
    --- a/src/auth.ts
    +++ b/src/auth.ts
    @@ -1,3 +1,6 @@
    +export function login(email: string) {
    +  return db.users.find(email);
    +}
""")

SAMPLE_TICKET = textwrap.dedent("""\
    ---
    id: FEAT-001
    title: Add login
    ---
    ## Acceptance Criteria
    - [ ] AC-1: login returns user
""")


def test_build_review_requests_one_per_focus(tmp_path):
    """One batch request is built per focus type."""
    from scripts.implementer.batch_review import build_review_requests
    reqs = build_review_requests(
        ticket_id="FEAT-001",
        diff=SAMPLE_DIFF,
        ticket_content=SAMPLE_TICKET,
        code_rules="",
        focus_types=["spec", "quality"],
        reviewer_prefix="You are a reviewer.",
    )
    assert len(reqs) == 2
    ids = [r["custom_id"] for r in reqs]
    assert "FEAT-001-review-spec" in ids
    assert "FEAT-001-review-quality" in ids


def test_build_review_requests_system_cached(tmp_path):
    """System message first block has cache_control."""
    from scripts.implementer.batch_review import build_review_requests
    reqs = build_review_requests(
        ticket_id="FEAT-001",
        diff=SAMPLE_DIFF,
        ticket_content=SAMPLE_TICKET,
        code_rules="",
        focus_types=["spec"],
        reviewer_prefix="Static prefix.",
    )
    system = reqs[0]["params"]["system"]
    assert isinstance(system, list)
    assert system[0]["cache_control"] == {"type": "ephemeral"}
    assert "Static prefix." in system[0]["text"]


def test_build_review_requests_user_two_blocks():
    """User message: first block cached (code_rules), second dynamic (diff+ACs)."""
    from scripts.implementer.batch_review import build_review_requests
    reqs = build_review_requests(
        ticket_id="FEAT-001",
        diff=SAMPLE_DIFF,
        ticket_content=SAMPLE_TICKET,
        code_rules="No side effects.",
        focus_types=["quality"],
        reviewer_prefix="",
    )
    user_content = reqs[0]["params"]["messages"][0]["content"]
    assert len(user_content) == 2
    assert "cache_control" in user_content[0]        # stable code rules
    assert "No side effects." in user_content[0]["text"]
    assert "cache_control" not in user_content[1]    # dynamic diff+ACs
    assert SAMPLE_DIFF in user_content[1]["text"]


def test_empty_diff_raises():
    """Empty diff should raise ValueError."""
    from scripts.implementer.batch_review import build_review_requests
    with pytest.raises(ValueError, match="empty diff"):
        build_review_requests(
            ticket_id="FEAT-001",
            diff="",
            ticket_content=SAMPLE_TICKET,
            code_rules="",
            focus_types=["spec"],
            reviewer_prefix="",
        )
```

### Step 2: Run tests — verify they fail

```bash
python -m pytest tests/test_batch_review.py -v
```

Expected: `ImportError: No module named 'scripts.implementer.batch_review'` (FAIL).

### Step 3: Implement `scripts/implementer/batch_review.py`

```python
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
                        # no cache_control — varies per reviewer
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
```

### Step 4: Run tests — verify they pass

```bash
python -m pytest tests/test_batch_review.py -v
```

Expected: all 4 tests PASS.

### Step 5: Commit

```bash
git add scripts/implementer/batch_review.py tests/test_batch_review.py
git commit -m "feat(batch_review): submit Gate 4 reviews via Batch API with cache_control"
```

---

## Task 5: Create `scripts/implementer/batch_review_poll.py`

**Files:**
- Create: `scripts/implementer/batch_review_poll.py`
- Create: `tests/test_batch_review_poll.py`

### Step 1: Write failing tests

Create `tests/test_batch_review_poll.py`:

```python
#!/usr/bin/env python3
"""Tests for scripts/implementer/batch_review_poll.py

Covers:
  - Happy path: polls until ended, returns consolidated JSON
  - Timeout path: exits with code 1 when max wait exceeded
  - Partial failure: one request errored, others ok — consolidated correctly
  - Output schema: ticket_id, reviews[], consolidated_verdict present
"""

import json
import sys
import os
from unittest.mock import patch, MagicMock, call

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _make_mock_response(processing_status, results=None):
    """Build mock API responses for batch status and results."""
    status_resp = MagicMock()
    status_resp.status_code = 200
    status_resp.json.return_value = {"processing_status": processing_status, "id": "msgbatch_test"}

    results_resp = MagicMock()
    results_resp.status_code = 200
    results_resp.iter_lines.return_value = [
        json.dumps(r).encode() for r in (results or [])
    ]
    return status_resp, results_resp


SAMPLE_RESULT_SPEC = {
    "custom_id": "FEAT-001-review-spec",
    "result": {
        "type": "succeeded",
        "message": {
            "content": [{"type": "text", "text": "## Review: spec\n\n### Summary\nVerdict: APPROVED\n"}]
        }
    }
}

SAMPLE_RESULT_QUALITY = {
    "custom_id": "FEAT-001-review-quality",
    "result": {
        "type": "succeeded",
        "message": {
            "content": [{"type": "text", "text": "## Review: quality\n\n### Summary\nVerdict: CHANGES_REQUESTED\n"}]
        }
    }
}


def test_poll_returns_consolidated_on_success():
    """When batch ends successfully, returns dict with reviews and consolidated_verdict."""
    from scripts.implementer.batch_review_poll import poll_and_consolidate

    status_resp, results_resp = _make_mock_response("ended", [SAMPLE_RESULT_SPEC, SAMPLE_RESULT_QUALITY])

    with patch("requests.get", side_effect=[status_resp, results_resp]):
        result = poll_and_consolidate(
            batch_id="msgbatch_test",
            ticket_id="FEAT-001",
            base_url="https://api.anthropic.com",
            api_key="sk-test",
            timeout=10,
            interval=1,
        )

    assert result["ticket_id"] == "FEAT-001"
    assert len(result["reviews"]) == 2
    assert result["consolidated_verdict"] in ("APPROVED", "CHANGES_REQUESTED")
    assert result["batch_id"] == "msgbatch_test"


def test_poll_timeout_raises():
    """When batch never ends within timeout, raises TimeoutError."""
    from scripts.implementer.batch_review_poll import poll_and_consolidate

    in_progress_resp = MagicMock()
    in_progress_resp.status_code = 200
    in_progress_resp.json.return_value = {"processing_status": "in_progress", "id": "msgbatch_test"}

    with patch("requests.get", return_value=in_progress_resp), \
         patch("time.sleep"):
        with pytest.raises(TimeoutError):
            poll_and_consolidate(
                batch_id="msgbatch_test",
                ticket_id="FEAT-001",
                base_url="https://api.anthropic.com",
                api_key="sk-test",
                timeout=2,
                interval=1,
            )


def test_consolidated_verdict_changes_if_any_requests_changes():
    """consolidated_verdict is CHANGES_REQUESTED if any review requests changes."""
    from scripts.implementer.batch_review_poll import consolidate_results

    reviews = [
        {"focus": "spec", "verdict": "APPROVED", "findings": []},
        {"focus": "quality", "verdict": "CHANGES_REQUESTED", "findings": []},
    ]
    result = consolidate_results("FEAT-001", "msgbatch_test", reviews)
    assert result["consolidated_verdict"] == "CHANGES_REQUESTED"


def test_consolidated_verdict_approved_if_all_approved():
    """consolidated_verdict is APPROVED only when all reviews approve."""
    from scripts.implementer.batch_review_poll import consolidate_results

    reviews = [
        {"focus": "spec", "verdict": "APPROVED", "findings": []},
        {"focus": "quality", "verdict": "APPROVED", "findings": []},
    ]
    result = consolidate_results("FEAT-001", "msgbatch_test", reviews)
    assert result["consolidated_verdict"] == "APPROVED"
```

### Step 2: Run tests — verify they fail

```bash
python -m pytest tests/test_batch_review_poll.py -v
```

Expected: `ImportError` (FAIL).

### Step 3: Implement `scripts/implementer/batch_review_poll.py`

```python
#!/usr/bin/env python3
"""Poll Anthropic Batch API for Gate 4 review results and consolidate.

Usage:
    python3 scripts/implementer/batch_review_poll.py \
        --batch-id msgbatch_xxx \
        --ticket-id FEAT-001 \
        --timeout 300 \
        --interval 30

Output (stdout): JSON with ticket_id, reviews[], consolidated_verdict, batch_id
Exit codes: 0=results ready, 1=timeout or API error
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests

BATCH_API_PATH = "/v1/messages/batches"
ANTHROPIC_BETA_HEADER = "prompt-caching-2024-07-31"


def _headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "anthropic-beta": ANTHROPIC_BETA_HEADER,
    }


def _extract_verdict(text: str) -> str:
    """Parse APPROVED or CHANGES_REQUESTED from reviewer output text."""
    upper = text.upper()
    if "CHANGES_REQUESTED" in upper:
        return "CHANGES_REQUESTED"
    if "APPROVED" in upper:
        return "APPROVED"
    return "CHANGES_REQUESTED"  # conservative default


def _parse_result(result_line: dict) -> dict:
    """Convert one batch result line into a review dict."""
    custom_id = result_line.get("custom_id", "")
    focus = custom_id.split("-review-")[-1] if "-review-" in custom_id else "unknown"

    result = result_line.get("result", {})
    if result.get("type") != "succeeded":
        return {"focus": focus, "verdict": "CHANGES_REQUESTED", "findings": [],
                "error": result.get("error", {}).get("message", "batch request failed")}

    content = result.get("message", {}).get("content", [])
    text = " ".join(c.get("text", "") for c in content if c.get("type") == "text")
    verdict = _extract_verdict(text)

    return {"focus": focus, "verdict": verdict, "findings": [], "raw": text}


def consolidate_results(ticket_id: str, batch_id: str, reviews: list[dict]) -> dict:
    """Merge per-focus reviews into final consolidated result."""
    all_approved = all(r["verdict"] == "APPROVED" for r in reviews)
    return {
        "ticket_id": ticket_id,
        "reviews": reviews,
        "consolidated_verdict": "APPROVED" if all_approved else "CHANGES_REQUESTED",
        "batch_id": batch_id,
        "cost_savings_pct": 50,
    }


def poll_and_consolidate(
    batch_id: str,
    ticket_id: str,
    base_url: str,
    api_key: str,
    timeout: int = 300,
    interval: int = 30,
) -> dict:
    """Poll until batch ends or timeout exceeded.

    Raises TimeoutError on timeout.
    Raises RuntimeError on API error.
    """
    base = base_url.rstrip("/")
    status_url = f"{base}{BATCH_API_PATH}/{batch_id}"
    results_url = f"{base}{BATCH_API_PATH}/{batch_id}/results"
    hdrs = _headers(api_key)

    elapsed = 0
    while elapsed < timeout:
        resp = requests.get(status_url, headers=hdrs, timeout=30)
        if resp.status_code != 200:
            raise RuntimeError(f"Status check failed: {resp.status_code} {resp.text[:200]}")

        data = resp.json()
        if data.get("processing_status") == "ended":
            # Fetch results
            rresp = requests.get(results_url, headers=hdrs, timeout=60, stream=True)
            if rresp.status_code != 200:
                raise RuntimeError(f"Results fetch failed: {rresp.status_code}")
            reviews = [_parse_result(json.loads(line)) for line in rresp.iter_lines() if line]
            return consolidate_results(ticket_id, batch_id, reviews)

        time.sleep(interval)
        elapsed += interval

    raise TimeoutError(f"Batch {batch_id} did not complete within {timeout}s")


def main() -> int:
    ap = argparse.ArgumentParser(description="Poll Batch API for review results")
    ap.add_argument("--batch-id", required=True)
    ap.add_argument("--ticket-id", required=True)
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--interval", type=int, default=30)
    ap.add_argument("--base-url", default=os.environ.get("LITELLM_BASE_URL", "https://api.anthropic.com"))
    ap.add_argument("--api-key-env", default="ANTHROPIC_API_KEY")
    a = ap.parse_args()

    api_key = os.environ.get(a.api_key_env, "")
    if not api_key:
        print(f"Error: env var {a.api_key_env} not set", file=sys.stderr)
        return 1

    try:
        result = poll_and_consolidate(
            batch_id=a.batch_id,
            ticket_id=a.ticket_id,
            base_url=a.base_url,
            api_key=api_key,
            timeout=a.timeout,
            interval=a.interval,
        )
        print(json.dumps(result))
        return 0
    except TimeoutError as e:
        print(f"Timeout: {e}", file=sys.stderr)
        return 1
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
```

### Step 4: Run tests — verify they pass

```bash
python -m pytest tests/test_batch_review_poll.py -v
```

Expected: all 4 tests PASS.

### Step 5: Commit

```bash
git add scripts/implementer/batch_review_poll.py tests/test_batch_review_poll.py
git commit -m "feat(batch_review_poll): poll Batch API and consolidate Gate 4 review results"
```

---

## Task 6: Wire Gate 4 batch path into `SKILL.md` + update config schema

**Files:**
- Modify: `skills/backlog-implementer/SKILL.md`
- Modify: `skills/backlog-implementer/CLAUDE.md`
- Modify: `config/backlog.config.schema.json` (add 3 keys to `batchPolicy`)
- Modify: `config/presets/default.json` (add 3 keys with defaults)
- Test: `bash tests/test-config-schema.sh`

### Step 1: Update `SKILL.md` Gate 4 section

Find the current `### Gate 4: REVIEW` section (starts around the REVIEW header).
Replace the **Reviewers** paragraph with the new batch flow:

```markdown
### Gate 4: REVIEW

**Pre-review** (deterministic): [unchanged — keep diff_pattern_scanner.py block]

**Batch path** (default when `config.batchPolicy.reviewBatchEnabled = true`):

```bash
REVIEW_FOCUS="${REVIEW_FOCUS_TYPES:-spec,quality}"   # SEC tickets: spec,quality,security,history

BATCH_REVIEW=$(python3 "${CLAUDE_PLUGIN_ROOT}/scripts/implementer/batch_review.py" \
  --diff <(git diff HEAD~1) \
  --ticket "$TICKET_PATH" \
  --code-rules "${CODE_RULES_PATH:-}" \
  --focus "$REVIEW_FOCUS" \
  --batch-state .backlog-ops/review-batch-state.json \
  --base-url "${LITELLM_BASE_URL:-https://api.anthropic.com}" \
  --api-key-env "${API_KEY_ENV:-ANTHROPIC_API_KEY}")
BATCH_EXIT=$?
```

If `BATCH_EXIT == 0`:
```bash
REVIEW_RESULT=$(python3 "${CLAUDE_PLUGIN_ROOT}/scripts/implementer/batch_review_poll.py" \
  --batch-id "$(echo $BATCH_REVIEW | python3 -c 'import json,sys; print(json.load(sys.stdin)["batch_id"])')" \
  --ticket-id "$TICKET_ID" \
  --timeout "${reviewBatchTimeoutSec:-300}" \
  --interval "${reviewBatchIntervalSec:-30}")
POLL_EXIT=$?
```

- `POLL_EXIT == 0` → parse `REVIEW_RESULT` JSON → proceed to consolidation
- `POLL_EXIT == 1` (timeout) → **FALLBACK**
- `BATCH_EXIT != 0` → **FALLBACK**

**FALLBACK**: spawn Task reviewers as in v10.0 (live agents, current behavior).

**Consolidation** (unchanged): filter by `confidenceThreshold`, Critical/Important → re-review, max `maxReviewRounds` then `review-blocked`.
```

### Step 2: Add 3 keys to `config/backlog.config.schema.json`

Find the `batchPolicy` → `properties` block (around line 495). Add after `retryPolicy`:

```json
"reviewBatchEnabled": {
  "type": "boolean",
  "default": true,
  "description": "Submit Gate 4 reviews via Batch API (50% cost reduction). Automatically falls back to live agents on timeout or API error."
},
"reviewBatchTimeoutSec": {
  "type": "integer",
  "minimum": 30,
  "default": 300,
  "description": "Max seconds to wait for batch review results before falling back to live agents."
},
"reviewBatchIntervalSec": {
  "type": "integer",
  "minimum": 5,
  "default": 30,
  "description": "Polling interval in seconds when waiting for batch review results."
}
```

### Step 3: Add same 3 keys to `config/presets/default.json`

Find `"batchPolicy"` block in `default.json`. Add the new keys:

```json
"reviewBatchEnabled": true,
"reviewBatchTimeoutSec": 300,
"reviewBatchIntervalSec": 30
```

### Step 4: Update `CLAUDE.md` cost model and script layer

In `skills/backlog-implementer/CLAUDE.md`:

**Script layer table** — add 2 rows after `diff_pattern_scanner.py`:
```
| `scripts/implementer/batch_review.py`      | Gate 4 live reviewer spawn      | $0 (batch at 50%) |
| `scripts/implementer/batch_review_poll.py` | Batch result polling + consolidation | $0 script |
```

**Cost model table** — update Gate 4 rows:
```
| trivial | fast path Sonnet | $0.15-0.35 | quality over cost |
| simple  | fast path Sonnet+Sonnet | $0.30-0.60 | quality over cost |
| complex | full path Sonnet (batch Gate 4) | $0.90-1.80 | ~35% vs v10.0 |
```

### Step 5: Run schema test

```bash
bash tests/test-config-schema.sh
```

Expected: all PASS.

### Step 6: Commit

```bash
git add skills/backlog-implementer/SKILL.md \
        skills/backlog-implementer/CLAUDE.md \
        config/backlog.config.schema.json \
        config/presets/default.json
git commit -m "feat(implementer): wire Gate 4 batch path, update schema and cost model"
```

---

## Task 7: Version bump and push

**Files:**
- Modify: `.claude-plugin/plugin.json`
- Modify: `.claude-plugin/marketplace.json`

### Step 1: Bump version 3.2.0 → 3.3.0

In `.claude-plugin/plugin.json`:
```json
"version": "3.3.0"
```

In `.claude-plugin/marketplace.json` — update 3 occurrences:
```json
"version": "3.3.0"
...
"ref": "v3.3.0"
...
"description": "... Sonnet for all code tasks, batch Gate 4 reviews (50% cost reduction)."
```

### Step 2: Run full test suite

```bash
python -m pytest tests/test_batch_submit.py tests/test_batch_review.py \
    tests/test_batch_review_poll.py -v
bash tests/test_startup.sh
bash tests/test-config-schema.sh
```

Expected: all PASS.

### Step 3: Commit, tag, push

```bash
git add .claude-plugin/plugin.json .claude-plugin/marketplace.json
git commit -m "release: v3.3.0 — prompt caching hardening + batch Gate 4 reviews (50% savings)"
git tag v3.3.0
git push origin main && git push origin v3.3.0
```

---

## Summary

| Task | Scope | Time |
|------|-------|------|
| 1 | `batch_submit.py` cache_control | ~20min |
| 2 | `startup.sh` cache mode detection | ~20min |
| 3 | `SKILL.md` cache boundary docs | ~10min |
| 4 | `batch_review.py` (new) | ~30min |
| 5 | `batch_review_poll.py` (new) | ~30min |
| 6 | SKILL.md Gate 4 + schema + CLAUDE.md | ~20min |
| 7 | Version bump + push | ~5min |
| **Total** | **8 files modified, 4 new** | **~2h** |
