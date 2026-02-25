# Implementer v11.0 — Prompt Caching Hardening + Batch Reviews

**Date**: 2026-02-25
**Status**: Approved
**Scope**: `backlog-implementer` skill + `scripts/implementer/` + `config/`

---

## Problem

The implementer has a prompt caching strategy (static prefix pattern, `cachePolicy` config) but two gaps reduce its effectiveness:

1. **`batch_submit.py` sends plain-string system prompts** — no explicit `cache_control` breakpoints. In direct-API mode (without LiteLLM proxy), Anthropic caching is not guaranteed to activate.

2. **Gate 4 reviews are spawned as live agents** — reviews are single-shot (no tool use, no multi-turn) and are therefore eligible for the Batch API's 50% cost reduction. Currently they're spawned as interactive Task agents at full price.

Additionally, the SKILL.md documents caching with a vague claim ("~90% hit after first call") rather than actionable boundary instructions the leader can follow.

---

## Goals

- Prompt caching guaranteed in both LiteLLM proxy mode and direct Anthropic API mode
- Gate 4 reviews submitted via Batch API by default, with automatic fallback
- Zero regression: all changes are additive or have fallback paths
- No new infrastructure dependencies

---

## Non-Goals

- Batching Gate 2 (implementation) — impossible; requires tool use and multi-turn
- Batching Gate 1 (plan) — already handled by `batch_submit.py`
- Async-only batch flow (no waiting) — adds session management complexity not worth it for 4-10 ticket sessions

---

## Design

### Phase 1: Cache Hardening

#### 1a. `batch_submit.py` — explicit `cache_control` breakpoints

Replace plain-string system prompts with content block arrays that carry `cache_control` markers.

**Placement rules** (Anthropic supports max 4 breakpoints per call):
- Breakpoint 1: after system prompt (PLAN_SYSTEM_PROMPT)
- Breakpoint 2: after code rules in user message (stable per session, varies per project)
- No breakpoint on ticket content (dynamic — different every call)

```python
# system message — content block with cache_control
"system": [
    {
        "type": "text",
        "text": PLAN_SYSTEM_PROMPT,
        "cache_control": {"type": "ephemeral"}
    }
],

# user message — two blocks: stable (cached) + dynamic (not cached)
"messages": [
    {
        "role": "user",
        "content": [
            {
                "type": "text",
                "text": code_rules_content,          # stable per session
                "cache_control": {"type": "ephemeral"}
            },
            {
                "type": "text",
                "text": f"Ticket:\n{ticket_content}" # dynamic — not cached
            }
        ]
    }
]
```

Add header to all batch API calls:
```python
headers["anthropic-beta"] = "prompt-caching-2024-07-31"
```

When LiteLLM proxy is active, the proxy handles caching automatically via
`providerPromptCaching: true`. The `anthropic-beta` header is a no-op in that
case but harmless.

#### 1b. `startup.sh` — cache mode detection

Detect whether LiteLLM is active and emit a `cache_mode` field in startup JSON:

```bash
if curl -sf "$LITELLM_BASE_URL/health" > /dev/null 2>&1; then
    CACHE_MODE="litellm"
else
    CACHE_MODE="direct"
fi
# Include in startup JSON output: "cache_mode": "$CACHE_MODE"
```

The SKILL.md startup banner updates to show:
```
Cache: litellm (auto) | Hit target: 80%
# or
Cache: direct (cache_control headers) | Hit target: 80%
```

#### 1c. `SKILL.md` — cache boundary documentation

Replace the vague `"cached ~90% hit after first call"` note in Gate 2 with an
explicit ordered boundary:

```
Prompt cache boundary (Gate 2):
  [CACHED]   1. implementer-prefix.md      (static, never changes)
  [CACHED]   2. CODE RULES                 (stable per session)
  [BOUNDARY] ← cache_control breakpoint
  [DYNAMIC]  3. PLAYBOOK BULLETS           (top-10, varies per ticket)
  [DYNAMIC]  4. CATALOG DISCIPLINES        (varies by ticket type)
  [DYNAMIC]  5. RAG CONTEXT                (varies per ticket)
  [DYNAMIC]  6. TICKET CONTENT             (varies per ticket)
  [DYNAMIC]  7. GATE INSTRUCTIONS          (varies per gate)

Rule: NEVER interleave dynamic content before the boundary.
      Static blocks must be contiguous at the top of the prompt.
```

---

### Phase 2: Gate 4 Batch Reviews

#### 2a. New script: `scripts/implementer/batch_review.py`

Submits Gate 4 reviews as a single Batch API job instead of spawning live agents.

**Inputs** (CLI args):
- `--diff` — path to git diff file (or `-` for stdin)
- `--ticket` — path to ticket `.md`
- `--code-rules` — path to code-rules file (optional)
- `--focus` — comma-separated focus types: `spec,quality,security,history`
- `--batch-state` — output state file path (default: `.backlog-ops/review-batch-state.json`)
- `--base-url` — LiteLLM or Anthropic base URL
- `--api-key-env` — env var name for API key (default: `ANTHROPIC_API_KEY`)

**Behavior**:
1. Read `templates/reviewer-prefix.md` as the static system prefix (cached)
2. For each focus type, build one Batch API request:
   - `custom_id`: `{ticket_id}-review-{focus}`
   - system: `[reviewer-prefix (cached), focus instruction]`
   - user: `[code_rules (cached), diff + ACs (dynamic)]`
3. Submit as one batch job to `/v1/messages/batches`
4. Save `{batch_id, ticket_id, focus_types, submitted_at}` to state file
5. Print JSON to stdout: `{"batch_id": "...", "request_count": N, "ticket_id": "..."}`

**Error handling**:
- Network error or non-200 response → exit code 1, print error to stderr
- Empty diff → exit code 2 (caller decides whether to skip review)

#### 2b. New script: `scripts/implementer/batch_review_poll.py`

Polls the Batch API until results are ready, then consolidates into the same
JSON format that live reviewer agents produce.

**Inputs** (CLI args):
- `--batch-id` — batch ID from `batch_review.py`
- `--ticket-id` — for output labeling
- `--timeout` — max wait in seconds (default: 300)
- `--interval` — poll interval in seconds (default: 30)
- `--base-url` / `--api-key-env` — same as above

**Poll loop**:
```
GET /v1/messages/batches/{batch_id}
  if processing_status == "ended" → fetch results → consolidate → exit 0
  if elapsed >= timeout → exit 1 (timeout)
  else → sleep(interval) → repeat
```

**Output JSON** (stdout, same structure as live reviewer output):
```json
{
  "ticket_id": "FEAT-042",
  "reviews": [
    {
      "focus": "spec",
      "findings": [...],
      "verdict": "APPROVED"
    },
    {
      "focus": "quality",
      "findings": [...],
      "verdict": "CHANGES_REQUESTED"
    }
  ],
  "consolidated_verdict": "CHANGES_REQUESTED",
  "batch_id": "msgbatch_xxx",
  "cost_savings_pct": 50
}
```

**Timeout fallback**: exit code 1 → SKILL.md fallback path spawns live agents.

#### 2c. `SKILL.md` — Gate 4 updated flow

```
### Gate 4: REVIEW

IF config.batchPolicy.reviewBatchEnabled (default: true):

  SUBMIT:
    BATCH_REVIEW=$(python3 "${CLAUDE_PLUGIN_ROOT}/scripts/implementer/batch_review.py" \
      --diff <(git diff HEAD~1) \
      --ticket "$TICKET_PATH" \
      --code-rules "${CODE_RULES_PATH}" \
      --focus "${REVIEW_FOCUS_TYPES}" \
      --base-url "${LITELLM_BASE_URL:-https://api.anthropic.com}" \
      --api-key-env "${API_KEY_ENV:-ANTHROPIC_API_KEY}")

  IF exit code 0:
    POLL (sync, max reviewBatchTimeoutSec):
      REVIEW_RESULT=$(python3 ".../batch_review_poll.py" \
        --batch-id $(echo $BATCH_REVIEW | jq -r .batch_id) \
        --ticket-id "$TICKET_ID" \
        --timeout "${reviewBatchTimeoutSec:-300}" \
        --interval "${reviewBatchIntervalSec:-30}")

    IF exit code 0: use REVIEW_RESULT → proceed to consolidation
    IF exit code 1 (timeout): → FALLBACK

  IF any exit code != 0: → FALLBACK

  FALLBACK: spawn Task reviewers as before (current v10.0 behavior)
```

**Focus type selection** (unchanged from v10.0):
- Default: `spec,quality`
- SEC tickets: add `security,history`
- High-risk scan positive: add `security`

#### 2d. Config schema — 3 new keys

New keys under `llmOps.batchPolicy`:

```json
{
  "reviewBatchEnabled": {
    "type": "boolean",
    "default": true,
    "description": "Submit Gate 4 reviews via Batch API (50% cost reduction). Falls back to live agents on timeout."
  },
  "reviewBatchTimeoutSec": {
    "type": "integer",
    "default": 300,
    "description": "Max seconds to wait for batch reviews before falling back to live agents."
  },
  "reviewBatchIntervalSec": {
    "type": "integer",
    "default": 30,
    "description": "Polling interval in seconds for batch review status checks."
  }
}
```

---

## File Change Summary

| File | Type | Change |
|------|------|--------|
| `scripts/ops/batch_submit.py` | modify | `cache_control` in system + user messages; add `anthropic-beta` header |
| `scripts/implementer/startup.sh` | modify | Cache mode detection → emit `cache_mode` in startup JSON |
| `scripts/implementer/batch_review.py` | new | Submit Gate 4 reviews as Batch API job |
| `scripts/implementer/batch_review_poll.py` | new | Poll + consolidate batch review results |
| `skills/backlog-implementer/SKILL.md` | modify | Cache boundary docs + Gate 4 batch path |
| `skills/backlog-implementer/CLAUDE.md` | modify | Update cost model, add script layer entries |
| `config/backlog.config.schema.json` | modify | 3 new keys in `batchPolicy` |
| `config/presets/default.json` | modify | Add new `batchPolicy` keys with defaults |

Total: 6 modified files, 2 new files.

---

## Cost Model (updated)

| Ticket type | Gate 4 before | Gate 4 after | Savings |
|-------------|--------------|-------------|---------|
| trivial | $0.04 (1 reviewer) | $0.02 | ~50% |
| simple | $0.08 (2 reviewers) | $0.04 | ~50% |
| complex | $0.16 (2 reviewers + re-review) | $0.08 | ~50% |

For a 7-ticket session: **~$0.40-0.70 savings on Gate 4 alone**.
Cache hardening (Phase 1): additional **10-15% savings on Gate 2** prompts.

---

## Risk & Mitigations

| Risk | Mitigation |
|------|-----------|
| Batch API unavailable | Fallback to live agents (automatic, no config needed) |
| Batch takes >5min | Timeout → fallback. Configurable via `reviewBatchTimeoutSec` |
| `cache_control` breaks LiteLLM proxy | LiteLLM strips or passes through — either way benign |
| Batch API doesn't support tool use | Confirmed: reviews are single-shot, no tool use required |
| `anthropic-beta` header rejected | Non-fatal; caching just won't activate — graceful degradation |
