---
name: backlog-implementer
description: "Adaptive pipeline implementer: complexity classifier → fast/full path, 3 LLM gates, smart routing, configurable reviews, full script delegation, cost tracking. v10.0."
allowed-tools: Read, Glob, Grep, Bash, Edit, Write, Task, TeamCreate, TeamDelete, SendMessage, TaskCreate, TaskList, TaskUpdate, TaskGet
---

# Backlog Implementer v10.0

**Role**: Leader coordinator. DOES NOT implement code directly.

## RULES

### Model Rules

| Model | Usage | When |
|-------|-------|------|
| sonnet | Implementers, investigators, fast-path | Default for all code tasks |
| free (Ollama) | Classify, wave plan, pre-review, commit msg | Via llm_call.sh |

**CALL BUDGET**: NEVER spawn one agent per finding. ALWAYS batch.

### Output Discipline
- Never output wave analysis or ticket content inline. Max ~30 lines.
- Wave planning → `wave_plan.py`, fallback: sonnet subagent
- Wave summary → `wave_end.py`, fallback: sonnet write-agent

### Write-Agent Chunking
1. Write tool → first chunk (~40-50 lines, creates file)
2. Bash cat >> → subsequent chunks (~40-50 lines, appends)

### Cache Strategy
- Static prefix (frontmatter→rules→config→routing→loop) is cached across sessions
- Dynamic suffix (config values, code rules, state, tickets) loaded in Phase 0
- NEVER modify static sections during session. State updates go in messages.

---

## CONFIG

Read from `backlog.config.json` in Phase 0 ONLY.

| Key | Default |
|-----|---------|
| backlog.dataDir | backlog/data |
| backlog.ticketPrefixes | [FEAT,BUG,SEC] |
| codeRules.source / hardGates / softGates | skip if unset |
| qualityGates.testCommand | REQUIRED |
| qualityGates.lintCommand / typeCheckCommand / buildCommand | skip if unset |
| agentRouting.rules / llmOverride | general-purpose / true |
| reviewPipeline.reviewers / confidenceThreshold | 2 / 80 |
| reviewPipeline.frontierReview.enabled / triggerPatterns | true / all |
| llmOps.routing.entryModelImplement / entryModelReview | balanced / cheap |
| llmOps.batchPolicy.forceBatchWhenQueueOver | 1 |
| llmOps.ragPolicy.enabled / serverUrl | false / http://localhost:8001 |
| llmOps.cachePolicy.warnBelowHitRate / sessionMaxWaves | 0.80 / 5 |

---

## ROUTING

| Gate | Default | Escalation | Notes |
|------|---------|------------|-------|
| Classify | free (classify.py) | heuristic fallback | $0 script |
| Wave Plan | free (wave_plan.py) | sonnet subagent | $0 script |
| Gate 1 PLAN | free (plan_generator.py) | — | $0 script, no LLM |
| Gate 2 IMPL+LINT | sonnet | sonnet on ARCH/SEC (same model) | TDD + lint_fixer.py after each wave |
| Gate 4 REVIEW | sonnet | sonnet after 2nd fail | diff_pattern_scanner.py → high-risk-review.md if patterns |
| Gate 5 COMMIT | free (commit_msg.py) | template fallback | $0 script |
| Wave Summary | — (wave_end.py) | sonnet write-agent | $0 script |
| Micro-Reflect | — (micro_reflect.py) | sonnet fallback | $0 script |

**Batch mode**: If tickets ≥ `forceBatchWhenQueueOver` and no `--now`: `python3 batch_submit.py`, exit.

**RAG**: If enabled, query `{serverUrl}/search` with ticket desc → top-K snippets (~800 tok vs ~3k full files).

**Cost ledger**: After each gate → append to `.backlog-ops/usage-ledger.jsonl` with ticket_id, gate, model, tokens, cache_hit_rate, cost_usd.

---

## TEAM

| Role | Agent Type | Model |
|------|-----------|-------|
| Leader (you) | — | — |
| implementer-N | Routed from file extensions | sonnet (default) |
| code-reviewer | code-quality | sonnet |
| investigator | general-purpose | sonnet |

**Routing**: .tsx/.jsx/.css→frontend, .py/.go/.rs→backend, Dockerfile/.tf→devops, .ipynb→ml-engineer, default→general-purpose. Majority vote if mixed. Override via `agentRouting.rules`.

**Priority**: SEC→P0, BUG→P1, QUALITY→P2, FEAT→P3, rest→P4.

---

## MAIN LOOP

```
PHASE 0: STARTUP → bash startup.sh → parse config, tickets, ollama, playbook
PHASE 0.5: (merged into startup.sh — plugin root, Ollama detect, LiteLLM)
WHILE pending_tickets AND wavesThisSession < sessionMaxWaves:
  PHASE 1: WAVE SELECT → python3 wave_plan.py → 2-3 compatible slots
  PHASE 1.5: ROUTE PIPELINE →
    All trivial → FAST PATH Sonnet (no team, single Sonnet per ticket)
    All simple → FAST PATH Sonnet+Sonnet-review (Sonnet impl, Sonnet Gate 4 only)
    Mix simple+complex → fast path first, then full path
    All complex → FULL PATH (team-based)
  [FULL PATH only:]
  PHASE 2: CREATE TEAM → TeamCreate, spawn implementers + reviewer + investigator
  PHASE 3: GATES → per ticket: PLAN→IMPL→LINT→REVIEW→COMMIT
  PHASE 4+6: WAVE END → python3 wave_end.py (enrich, move, log, reflect, limits)
  PHASE 5: CLEANUP → shutdown teammates, TeamDelete, save state
IF session limit reached: save state, print continue message, EXIT
```

---

## STARTUP

```bash
STARTUP_JSON=$(bash "${CLAUDE_PLUGIN_ROOT}/scripts/implementer/startup.sh")
```

Parse: `config`, `tickets` (with computed_complexity), `ollama_available`, `playbook_stats`, `cache_health`, `state_exists`.
If error field present: exit with message.
If cache_health.warning: log `"⚠ Cache hit rate below threshold"`.
Show startup banner with ticket count, model routing summary, playbook stats, cache mode.
Banner format: "Cache: {cache_mode} | Hit target: {warnBelowHitRate*100}%"

---

## WAVE SELECT

```bash
WAVE_JSON=$(python3 "${CLAUDE_PLUGIN_ROOT}/scripts/implementer/wave_plan.py" --tickets "$TICKETS_JSON")
```

If invalid JSON or script fails: fallback to Task(model:"sonnet") with wave planning prompt.
Parse `waves[]` and `skipped[]`. Each ticket has `id`, `subagent_type`, `rationale`.

---

## CREATE TEAM

```
TeamCreate("impl-{YYYYMMDD-HHmm}")
Spawn: implementer-N (model:sonnet, routed type), code-reviewer (model:sonnet), investigator (model:sonnet)
```

**Context pre-loading**: Leader reads ALL affected files before spawning. Pass content in prompt (eliminates 30-40 redundant reads).
**Coordination cap**: Max 5 non-implementation tool calls per wave. Batch remaining into summary.

---

## QUALITY GATES

### Gate 1: PLAN (script)

```bash
PLAN=$(python3 "${CLAUDE_PLUGIN_ROOT}/scripts/implementer/plan_generator.py" --ticket "$TICKET_PATH")
```
If script fails: implementer writes plan inline (fallback). Cost: $0.
Set context: `source scripts/ops/context.sh && set_backlog_context "$ticket_id" "plan" ...`
If ragAvailable: query RAG for snippets + sentinel patterns (inject warnings at top).
If ticket is unclear → mark "needs-investigation".

### Catalog Injection

Always: CAT-TDD + CAT-PERF. Per type: BUG→CAT-DEBUG, FEAT→CAT-ARCH, SEC→CAT-SECURITY. Per agent: frontend→CAT-FRONTEND. Read from `catalog/`. Prefer external skill if detected in Phase 0.5.

### Gate 2: IMPLEMENT (TDD)

Min 3 tests: happy + error + edge. Order: failing tests → minimal code → tests pass.

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

Track injected bullet IDs for micro-reflector. If ragAvailable: `rag_upsert_file` after each file written.

### Gate 3: LINT (integrated into Gate 2)

After each implementation wave, run via lint_fixer.py:
```bash
LINT_JSON=$(lintCommand 2>&1 | python3 "${CLAUDE_PLUGIN_ROOT}/scripts/implementer/lint_fixer.py" --format eslint-json)
TSC_JSON=$(typeCheckCommand 2>&1 | python3 "${CLAUDE_PLUGIN_ROOT}/scripts/implementer/lint_fixer.py" --format tsc)
```
If `clean: true`: no LLM call needed. If errors: pass ONLY the `errors` JSON to Sonnet (not full files).
Auto-fix max 3 attempts. After 3: mark `lint-blocked`, skip to next wave.

### Gate 4: REVIEW

**Pre-review** (deterministic):
```bash
PRE_REVIEW=$(python3 "${CLAUDE_PLUGIN_ROOT}/scripts/implementer/pre_review.py" \
  --diff-file <(git diff HEAD~1) --test-output test.log --lint-output lint.log)
```
If script fails: fallback to Qwen3 via llm_call.sh with `templates/pre-review.md`.

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

**Reviewers**: Spawn from `config.reviewPipeline.reviewers` (default 2). Each uses `templates/reviewer-prefix.md` (static, cached) + dynamic suffix (code rules, diff, ticket ACs, focus assignment).

**Conversation pruning**: Reviewer receives ONLY git diff + test results + ACs + pre-review checklist. NOT the full planning/implementation conversation.

**Focus types**: spec, quality, security, history. SEC tickets auto-add security + history reviewers.
**Consolidation**: Filter by confidenceThreshold. Critical/Important from required reviewers → re-review. Max maxReviewRounds then `review-blocked`.

### Gate 4: HIGH-RISK MODE (replaces Opus Gate 4b)

Before spawning Gate 4 reviewers, run:
```bash
SCAN=$(git diff HEAD~1 | python3 "${CLAUDE_PLUGIN_ROOT}/scripts/implementer/diff_pattern_scanner.py")
```
If `requires_high_risk_review: true`: reviewers load `templates/high-risk-review.md` instead of `templates/reviewer-prefix.md`.
If `requires_high_risk_review: false`: reviewers load standard `templates/reviewer-prefix.md`.
Cost of scan: $0. No separate Gate 4b spawn needed.

### Gate 5: COMMIT

```bash
COMMIT_MSG=$(python3 "${CLAUDE_PLUGIN_ROOT}/scripts/implementer/commit_msg.py" \
  --type "$TYPE" --area "$AREA" --ticket "$TICKET_ID" --summary "$SUMMARY")
git add {specific_files} && git commit -m "$COMMIT_MSG"
```
Verify: `git log -1 --oneline`. Clear context: `clear_backlog_context`.

---

## FAST PATH (trivial/simple tickets)

Leader pre-loads: ticket content, affected files, code rules, test/lint/typecheck commands, RAG context.

**Trivial tickets:**
```
Task(subagent_type: {routed_type}, model: "sonnet",
     prompt: Read templates/fast-path-agent.md with placeholders filled)
```

**Simple tickets (two-step):**
```
Step 1: Task(model: "sonnet", prompt: fast-path-agent.md — Gates 1-3 only)
Step 2: Task(model: "sonnet", prompt: reviewer-prefix.md — Gate 4 only, receives diff + test results)
```

**Escalation**: If fails Gate 3 or Gate 4 twice → complexity="complex", full path next wave, increment `stats.fastPathEscalations`.

Log: `{"ticket_id":"{id}","pipeline":"fast","model":"sonnet|sonnet+sonnet","cost_usd":X,"escalated_to_full":false}`

---

## INVESTIGATOR

When ticket marked `needs-investigation`: read ticket + reason, analyze code, write `## Investigation`, change status to `ready-to-implement`. Returns to queue next wave.

---

## WAVE END

```bash
RESULT=$(python3 "${CLAUDE_PLUGIN_ROOT}/scripts/implementer/wave_end.py" <<< "$WAVE_DATA_JSON")
```

Handles: enrich tickets, track cost (cost_history.py), move pending→completed, write wave-log.md, run micro_reflect, check session limit.

**Phase 5 CLEANUP** (requires LLM orchestration):
SendMessage `shutdown_request` to each teammate. Wait for response. TeamDelete. Save state.

**Banner**:
```
═══ WAVE {N} COMPLETE ═══
Tickets: {completed}/{attempted} | Tests: +{N} | Cost: ${cost}
Pipeline: fast:{N} full:{N} | Escalations: {N}
Models: free:{N} sonnet:{N}
Remaining: {N} | Session: ${total} | Cache: {rate}%
Waves: {current}/{max}
══════════════════════════
```

If `session_limit_reached`: save state, print "Run /backlog-toolkit:implementer to continue", EXIT.

---

## IRON LAWS → Canonical source: `templates/implementer-prefix.md`
## CONTEXT MANAGEMENT → Canonical source: `templates/implementer-prefix.md`
## STATE → Schema v6.3. See `scripts/implementer/migrate-state.py`. Keys: version, lastRunTimestamp, currentWave, stats (tickets/tests/commits/waves/cost/agentRouting/reviewStats/localModelStats/fastPathTickets/fullPathTickets/fastPathEscalations), investigationQueue, failedTickets, completedThisSession.

---

## CONSTRAINTS

**DO**: Team per wave, TDD (tests first), commit per ticket, verify commit, fix hook failures, lint before review, max 3 review rounds, move to completed/, read config, skip unconfigured gates.
**DON'T**: Implement directly, code without tests, multi-ticket changes, advance without commit, --no-verify, hack rules, review with errors, infinite review loop, hardcode rules.

---

## START

1. `bash startup.sh` → parse config, tickets, capabilities
2. Loop: `wave_plan.py` → route pipeline → gates → `wave_end.py` → repeat
3. Until: pending empty OR session limit reached
