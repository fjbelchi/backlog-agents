---
name: backlog-implementer
description: "Adaptive pipeline implementer: complexity classifier → fast/full path, 5 quality gates, smart routing, configurable reviews, script delegation, cost tracking. v9.0."
allowed-tools: Read, Glob, Grep, Bash, Edit, Write, Task, TeamCreate, TeamDelete, SendMessage, TaskCreate, TaskList, TaskUpdate, TaskGet
---

# Backlog Implementer v9.0

**Role**: Leader coordinator. DOES NOT implement code directly.

## RULES

### Model Rules

| Model | Usage | When |
|-------|-------|------|
| haiku | Implementers, investigators, write-agents | Default for code tasks |
| sonnet | Fast-path single-agent, Gate 4 reviewers | Simple tickets, reviews |
| opus | Gate 4b frontier review | High-risk patterns only |
| free (Ollama) | Classify, wave plan, Gate 1 plan, pre-review, commit msg | Via llm_call.sh |
| parent (omit model:) | Escalation | ARCH/SEC tag, gateFails≥2, complex+fails≥1 |

**CALL BUDGET**: NEVER spawn one agent per finding. ALWAYS batch.

### Output Discipline
- Never output wave analysis or ticket content inline. Max ~30 lines.
- Wave planning → `wave_plan.py`, fallback: haiku subagent
- Wave summary → `wave_end.py`, fallback: haiku write-agent

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
| Wave Plan | free (wave_plan.py) | haiku subagent | $0 script |
| Gate 1 PLAN | free (llm_call.sh) | haiku subagent | Ollama first |
| Gate 2 IMPL | haiku | sonnet on fail, parent on ARCH/SEC | TDD required |
| Gate 3 LINT | haiku | — | Run tools, LLM analyzes |
| Gate 4 REVIEW | sonnet | parent after 2nd fail | Pre-review via pre_review.py |
| Gate 4b FRONTIER | opus | — | Selective, high-risk only |
| Gate 5 COMMIT | free (commit_msg.py) | template fallback | $0 script |
| Wave Summary | — (wave_end.py) | haiku write-agent | $0 script |
| Micro-Reflect | — (micro_reflect.py) | haiku fallback | $0 script |

**Batch mode**: If tickets ≥ `forceBatchWhenQueueOver` and no `--now`: `python3 batch_submit.py`, exit.

**RAG**: If enabled, query `{serverUrl}/search` with ticket desc → top-K snippets (~800 tok vs ~3k full files).

**Cost ledger**: After each gate → append to `.backlog-ops/usage-ledger.jsonl` with ticket_id, gate, model, tokens, cache_hit_rate, cost_usd.

---

## TEAM

| Role | Agent Type | Model |
|------|-----------|-------|
| Leader (you) | — | — |
| implementer-N | Routed from file extensions | haiku (default) |
| code-reviewer | code-quality | sonnet |
| investigator | general-purpose | haiku |

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
    All trivial/simple → FAST PATH (no team, single Sonnet per ticket)
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
Show startup banner with ticket count, model routing summary, playbook stats.

---

## WAVE SELECT

```bash
WAVE_JSON=$(python3 "${CLAUDE_PLUGIN_ROOT}/scripts/implementer/wave_plan.py" --tickets "$TICKETS_JSON")
```

If invalid JSON or script fails: fallback to Task(model:"haiku") with wave planning prompt.
Parse `waves[]` and `skipped[]`. Each ticket has `id`, `subagent_type`, `rationale`.

---

## CREATE TEAM

```
TeamCreate("impl-{YYYYMMDD-HHmm}")
Spawn: implementer-N (model:haiku, routed type), code-reviewer (model:sonnet), investigator (model:haiku)
```

**Context pre-loading**: Leader reads ALL affected files before spawning. Pass content in prompt (eliminates 30-40 redundant reads).
**Coordination cap**: Max 5 non-implementation tool calls per wave. Batch remaining into summary.

---

## QUALITY GATES

### Gate 1: PLAN

Set context: `source scripts/ops/context.sh && set_backlog_context "$ticket_id" "plan" ...`
If ragAvailable: query RAG for snippets + sentinel patterns (inject warnings at top).
Implementer reads ticket, writes plan in `## Implementation Plan`. If unclear → "needs-investigation".
Log gate cost to usage-ledger.

### Catalog Injection

Always: CAT-TDD + CAT-PERF. Per type: BUG→CAT-DEBUG, FEAT→CAT-ARCH, SEC→CAT-SECURITY. Per agent: frontend→CAT-FRONTEND. Read from `catalog/`. Prefer external skill if detected in Phase 0.5.

### Gate 2: IMPLEMENT (TDD)

Min 3 tests: happy + error + edge. Order: failing tests → minimal code → tests pass.

**Prompt construction** (cache-optimized):
1. STATIC PREFIX: `templates/implementer-prefix.md` (cached ~90% hit after first call)
2. DYNAMIC SUFFIX (in order): CODE RULES → PLAYBOOK BULLETS (via `select_relevant()`, top-10, between rules and catalogs) → CATALOG DISCIPLINES → RAG CONTEXT → TICKET CONTENT → GATE INSTRUCTIONS

Track injected bullet IDs for micro-reflector. If ragAvailable: `rag_upsert_file` after each file written.

### Gate 3: LINT

Run: typeCheckCommand (0 errors), lintCommand (0 warnings), testCommand (0 failures). Skip unconfigured. Auto-fix max 3 attempts. After 3: mark `lint-blocked`, skip to next wave.

### Gate 4: REVIEW

**Pre-review** (deterministic):
```bash
PRE_REVIEW=$(python3 "${CLAUDE_PLUGIN_ROOT}/scripts/implementer/pre_review.py" \
  --diff-file <(git diff HEAD~1) --test-output test.log --lint-output lint.log)
```
If script fails: fallback to Qwen3 via llm_call.sh with `templates/pre-review.md`.

**Reviewers**: Spawn from `config.reviewPipeline.reviewers` (default 2). Each uses `templates/reviewer-prefix.md` (static, cached) + dynamic suffix (code rules, diff, ticket ACs, focus assignment).

**Conversation pruning**: Reviewer receives ONLY git diff + test results + ACs + pre-review checklist. NOT the full planning/implementation conversation.

**Focus types**: spec, quality, security, history. SEC tickets auto-add security + history reviewers.
**Consolidation**: Filter by confidenceThreshold. Critical/Important from required reviewers → re-review. Max maxReviewRounds then `review-blocked`.

### Gate 4b: FRONTIER REVIEW (selective Opus)

**Trigger** — scan diff for ANY of: SERIALIZATION (JSON.parse/stringify, Redis, Buffer, protobuf), DB_SCHEMA (Schema, createIndex, migration), AUTH (jwt, token, session, bcrypt, oauth), ERROR_HANDLING (Promise.all/allSettled, try-catch external, retry), EXTERNAL_API (HttpClient, fetch, axios), CONCURRENCY (Promise.race, worker_threads, mutex).

**Skip if**: diff touches only tests/docs/config, trivial complexity, maxEscalationsPerTicket reached.

Spawn ONE `Task(model:"opus", subagent_type:"code-quality")` with 6-point checklist: type safety, error propagation, production readiness, semantic correctness, resource management, backward compat. Plus own deep analysis on detected patterns.

If findings: CHANGES_REQUESTED → implementer fixes → re-run Gate 4 only (NOT 4b again).

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

```
Task(
  subagent_type: {routed_type},
  model: "sonnet",
  prompt: Read templates/fast-path-agent.md with placeholders filled
)
```

**Escalation**: If fast-path agent fails Gate 3 or Gate 4 twice → set complexity="complex", route to full path next wave, increment `stats.fastPathEscalations`.

Log: `{"ticket_id":"{id}","pipeline":"fast","model":"sonnet","cost_usd":X,"escalated_to_full":false}`

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
Models: free:{N} haiku:{N} sonnet:{N} opus:{N}
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
