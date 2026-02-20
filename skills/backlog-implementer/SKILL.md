---
name: backlog-implementer
description: "Implement backlog tickets with Agent Teams, wave parallelization, 5 quality gates (Plan→TDD→Lint→Review→Commit), smart agent routing, embedded skill catalog (7 disciplines), configurable review pipeline with confidence scoring, 2 Iron Laws, ticket enrichment, and cost tracking. Config-driven and stack-agnostic. v7.0."
allowed-tools: Read, Glob, Grep, Bash, Edit, Write, Task, TeamCreate, TeamDelete, SendMessage, TaskCreate, TaskList, TaskUpdate, TaskGet
---

# Backlog Implementer v7.0 — Smart Agent Routing + Embedded Skill Catalog + Configurable Reviews

## Role
**Leader coordinator**: Selects waves, creates teams, orchestrates quality gates. **DOES NOT implement code directly.**

## MODEL RULES FOR TASK TOOL

```
model: "haiku"   → DEFAULT for implementers, investigators, write-agents,
                   wave planning subagents. Cost-optimized tier.

model: "sonnet"  → REVIEWERS ONLY. All Gate 4 review subagents use Sonnet
                   for higher-quality defect detection.

ESCALATION to parent model (omit model: parameter):
  - Ticket tagged ARCH or SECURITY
  - qualityGateFails >= 2 for a ticket
  - ticket.complexity == "high"
  In these cases, the subagent inherits the parent model.

OLLAMA (free tier, via llm_call.sh):
  - Wave planning JSON generation
  - Gate 1 PLAN text generation
  - Gate 5 COMMIT message generation
  - Classification/triage
  These use llm_call.sh --model free. If Ollama fails → fallback to
  Task(model: "haiku") subagent.
```

## OUTPUT DISCIPLINE

```
- Never output wave analysis or ticket content inline
- Max response length: ~30 lines
- Wave planning → llm_call.sh --model free (returns JSON), fallback to haiku subagent
- Wave summary → delegate to haiku write-agent (writes log, returns JSON)
```

## WRITE-AGENT CHUNKING RULE

Write-agents MUST write files in chunks to avoid hitting the output token limit:
```
1. Write tool    → first chunk (~40-50 lines): creates the file
2. Bash cat >>   → each subsequent chunk (~40-50 lines): appends sections
Never generate more than 50 lines of file content per tool call.
```

---

## Prompt Caching Strategy

This skill is structured for maximum prompt cache efficiency:
```
STATIC PREFIX (cached — never changes between projects or sessions):
  Frontmatter → Model Rules → Output Discipline → Chunking Rule →
  Cost-Aware Execution → Team Composition → Main Loop → Phases →
  Iron Laws → Context Management → Constraints

DYNAMIC SUFFIX (appended at runtime in Phase 0 — project-specific):
  Config values → Code Rules content → State → Ticket data
```

**Rules for cache preservation:**
1. NEVER modify the static prefix sections during a session
2. All project-specific data is read in Phase 0 and passed via conversation messages
3. State updates between waves go in messages, not re-reads of the skill prompt
4. Model switching happens via subagents (Task tool), never mid-session
5. Tool set (allowed-tools) is fixed — never conditionally add/remove tools

## Configuration Reference

Config keys read from `backlog.config.json` at runtime (Phase 0). Defaults in parentheses:

```
backlog.dataDir (backlog/data) | backlog.ticketPrefixes (["FEAT","BUG","SEC"])
codeRules.source (skip if unset) | codeRules.hardGates ([]) | codeRules.softGates ([])
qualityGates: lintCommand, typeCheckCommand (skip if unset) | testCommand (REQUIRED) | buildCommand, healthCheckCommand (skip if unset)
agentRouting.rules (general-purpose) | agentRouting.llmOverride (true)
reviewPipeline.reviewers (2: spec+quality) | reviewPipeline.confidenceThreshold (80)
llmOps.routing: entryModelImplement (balanced) | entryModelReview (cheap) | escalationRules ([])
llmOps.batchPolicy ({forceBatchWhenQueueOver: 1})
llmOps.ragPolicy: enabled (false) | serverUrl (http://localhost:8001)
llmOps.cachePolicy: warnBelowHitRate (0.80) | sessionMaxWaves (5)
```

**Config is read ONLY in Phase 0** — not at skill load time. This keeps the prompt prefix 100% static and cacheable across all projects.

---

## Cost-Aware Execution

### Batch Mode (Default)

Unless `--now` is passed, default to batch mode for epic-level work (50% cost reduction). If tickets >= `config.llmOps.batchPolicy.forceBatchWhenQueueOver` (default: 1) and no `--now`: submit via `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/ops/batch_submit.py"`, exit with instructions to run `batch_reconcile.py`. If script not found, proceed synchronously.

### Model Tier Routing Per Gate

Before each LLM call, select the model tier using escalation rules:

```
1. Check ticket tags: ARCH or SECURITY tag → "frontier"
2. Check gate fail count: qualityGateFails >= 2 → "frontier"
3. Check ticket.complexity == "high" → "frontier"
4. Use gate default:
   Wave Plan  → config.llmOps.routing.entryModelPlan      (default: "free" via llm_call.sh)
   Gate 1 PLAN      → config.llmOps.routing.entryModelPlan (default: "free" via llm_call.sh)
   Gate 2 IMPLEMENT → config.llmOps.routing.entryModelImplement  (default: "cheap")
   Gate 3 LINT      → always "cheap" (runs tools, LLM analyzes output)
   Gate 4 REVIEW    → config.llmOps.routing.entryModelReview     (default: "balanced")
   Gate 5 COMMIT    → "free" via llm_call.sh (template fallback if Ollama unavailable)
```

Model aliases resolve via LiteLLM config: `free` → Ollama qwen3-coder, `cheap` → Haiku, `balanced` → Sonnet, `frontier` → Opus.

### Local Model Routing (Junior Programmer Pattern)

When Ollama is detected in Phase 0.5, simple tickets route through LiteLLM proxy `free` tier via `scripts/ops/llm_call.sh` instead of spawning Claude Code subagents.

The leader calls `llm_call.sh --model free` for plan gates. Review always uses cloud (Sonnet/Haiku) — local never reviews itself.

LOCAL-ELIGIBLE tickets (ALL must be true):
  - complexity != "high"
  - NO tags: ARCH, SECURITY
  - affected_files <= 3
  - NOT depends_on another ticket in this wave
  - localModelStats.escalatedToCloud / totalAttempts < 0.30

For LOCAL-ELIGIBLE tickets:
  Gate 1 PLAN:      result=$(bash scripts/ops/llm_call.sh --model free --system "Write implementation plan" --file ticket.md)
                    If empty or error → fallback to Task(model: "haiku") subagent
  Gate 2 IMPLEMENT: Task() subagent (needs tool_use for edits). Use normal routing.
  Gate 3 LINT:      → run locally (no LLM)
  Gate 4 REVIEW:    → Task(model: "haiku") subagent — cloud reviews local output
  Gate 5 COMMIT:    → always "cheap"

ESCALATION RULES:

  Haiku IMPLEMENT fails Gate 3 (LINT) or Gate 4 (REVIEW) once:
    1. stats.localModelStats.escalatedToCloud++
    2. stats.localModelStats.failuresByType[gate]++
    3. Re-run Gate 2 IMPLEMENT with Task(model: "sonnet") with full context
    4. Message: "Haiku failed on {id} at {gate}. Escalated to Sonnet."

  Ollama PLAN (Gate 1) returns empty or invalid JSON:
    → Fallback to Task(model: "haiku") subagent
    → No stats increment (expected fallback behavior)

  Ollama COMMIT (Gate 5) returns empty:
    → Use template: "{type}({area}): implement {ticket_id}"
    → No stats increment (expected fallback behavior)

  Ollama WAVE PLANNING returns invalid JSON:
    → Fallback to Task(model: "haiku") subagent
    → No stats increment (expected fallback behavior)

Success: stats.localModelStats.successCount++, totalAttempts++

### RAG Context Compression

If `config.llmOps.ragPolicy.enabled`: query `{serverUrl}/search` with ticket description, get top-K snippets (~800 tokens vs ~3k full files), use in prompt instead of full file reads. If unreachable, fall back to direct reads without error.

### Cost & Cache Ledger

After each gate, append to `.backlog-ops/usage-ledger.jsonl`:
```json
{"ticket_id": "FEAT-001", "gate": "implement", "model": "balanced", "input_tokens": 1200, "output_tokens": 800, "cache_read_tokens": 1050, "cache_creation_tokens": 150, "cache_hit_rate": 0.88, "cost_usd": 0.0156, "date": "2026-02-19"}
```

**Cache fields** (extract from LiteLLM response headers or Task metadata):
- `cache_read_tokens`: tokens served from cache (header: `x-litellm-cache-read-input-tokens`)
- `cache_creation_tokens`: tokens written to cache (header: `x-litellm-cache-creation-input-tokens`)
- `cache_hit_rate`: `cache_read_tokens / input_tokens` (0.0-1.0). If headers unavailable, set to `null`.
- `cost_usd`: actual cost from `x-litellm-response-cost` header, or calculated from tokens

**Cache health monitoring**: The Phase 0 startup reads the last 10 ledger entries and warns if average cache_hit_rate drops below threshold. This catches prompt/tool changes that silently break cache.

---

## Team Composition (Smart Routing)

The leader analyzes each ticket's Affected Files and routes to the best agent type.

### Routing Algorithm
1. Read `Affected Files` from ticket, match against `config.agentRouting.rules` (first match wins)
2. Multiple agent matches: majority vote. If `llmOverride` true: LLM can override (e.g., ML ticket with .py -> ml-engineer)
3. No match: general-purpose. Apply `config.agentRouting.overrides` by ticket type

### Default Routing Rules

frontend: *.tsx/jsx/css/vue | backend: *.ts/js, *.py, *.go, *.rs | general-purpose: *.swift, *.kt/java | devops: Dockerfile/yaml/tf | ml-engineer: *.ipynb/train*/model*

### Team Structure Per Wave

```
LEADER (you) — coordinates, DOES NOT implement
├── implementer-1 ({routed_agent_type} from routing)
├── implementer-2 ({routed_agent_type} - may differ per ticket)
├── implementer-3 (optional, if 3 compatible slots)
├── reviewer-1..N (from reviewPipeline config)
└── investigator (general-purpose) — unblocks complex tickets
```

## Priority Order

Read prefixes from `config.backlog.ticketPrefixes`. Default: SEC->P0, BUG->P1, QUALITY->P2, FEAT->P3, rest->P4

---

## MAIN LOOP

```
PHASE 0: STARTUP → load config + codeRules + state (dynamic context), cache health check, show banner
PHASE 0.5: DETECT CAPABILITIES → scan plugins + MCP servers, log capabilities
WHILE pending_tickets_exist() AND wavesThisSession < sessionMaxWaves: cycle++
  PHASE 1: WAVE SELECTION → top 10 by priority, analyze blast radius, select 2-3 compatible slots
  PHASE 2: CREATE TEAM → TeamCreate, spawn implementers + reviewer + investigator
  PHASE 3: ORCHESTRATE → per ticket: 3a PLAN → 3b IMPLEMENT (TDD) → 3c LINT → 3d REVIEW → 3e COMMIT
  PHASE 4: VERIFY & ENRICH & MOVE → git log -1 confirms, enrich ticket, mv to completed/
  PHASE 5: CLEANUP → shutdown teammates, TeamDelete, save state
  PHASE 6: WAVE SUMMARY → delegate log to write-agent, print banner, check session limits
IF pending_tickets_exist() AND wavesThisSession >= sessionMaxWaves:
  → save state, print "Session wave limit reached. Run /backlog-toolkit:implementer to continue."
```

---

## Phase 0: Startup (Dynamic Context Loading)

All project-specific data is loaded here — NOT at skill prompt load time. This keeps the cached prefix stable.

1. Read `backlog.config.json` → store all values in working memory
2. If `codeRules.source` is set → read that file, store full content for injection into implementer prompts
3. Load `.claude/implementer-state.json` (if `state.version != "6.1"` or missing, run: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/implementer/migrate-state.py"`)
4. Count pending tickets in `{dataDir}/pending/*.md`
5. Run health check if `healthCheckCommand` is configured
6. **Cache health check**: if `usage-ledger.jsonl` exists, read last 10 entries. If average `cache_hit_rate` < `config.llmOps.cachePolicy.warnBelowHitRate` (default: 0.80), log: `⚠ Cache hit rate {rate}% below threshold. Check for prompt/tool changes.`
7. Show startup banner with stats

---

## Phase 0.5: Detect Capabilities

Scan `~/.claude/plugins/` for superpowers (TDD, debugging, verification, code-review) and stack-specific plugins (python: pg-aiguide, aws-skills; typescript: playwright-skill). Note any configured MCP servers. Log detected capabilities. When an external skill is available for a discipline, prefer it over the embedded catalog version. Also check Ollama: `bash scripts/ops/llm_call.sh --model free --user "Reply OK"`. If response received, set ollamaAvailable=true, log "Local model: free tier via Ollama".

---

## Phase 1: Wave Selection

Read ticket metadata (IDs, priorities, affected files) — do NOT output analysis inline.

# Try Ollama first (free)
WAVE_JSON=$(bash "${CLAUDE_PLUGIN_ROOT}/scripts/ops/llm_call.sh" --model free \
  --system "You analyze tickets and return wave plans as JSON. No explanations." \
  --user "Tickets (id, priority, affected_files):
{ticket_metadata_list}

Rules:
- Group into 2-3 slots WITHOUT file conflicts
- Never parallelize: same file, depends_on relationships, create-then-import chains
- Tickets affecting different directories almost never conflict
- Select subagent_type per ticket based on file patterns
- BATCH SIMILAR TICKETS: If 2+ tickets share the same prefix, same directory, and same
  change pattern, group them into ONE slot with batch: true.

Return ONLY this JSON:
{\"waves\":[{\"wave\":1,\"tickets\":[{\"id\":\"BUG-001\",\"subagent_type\":\"backend\",\"rationale\":\"auth service\"}]}],\"skipped\":[]}")

# Validate JSON response; fallback to Haiku subagent if invalid
if ! echo "$WAVE_JSON" | python3 -c "import json,sys; json.load(sys.stdin)" 2>/dev/null; then
  # Ollama failed or returned invalid JSON — use Haiku subagent
  Task(
    subagent_type: "general-purpose",
    model: "haiku",
    prompt: """...same wave planning prompt as above..."""
  )
fi

Use the returned JSON to create the team and assign tasks.

---

## Phase 2: Create Team

```
TeamCreate("impl-{YYYYMMDD-HHmm}")

Spawn teammates via Task tool (model: "sonnet" by default):

1. implementer-1:
   subagent_type: select based on ticket area
   model: "haiku"  (omit if ARCH/SECURITY/escalation → inherits parent)
   team_name: "impl-{timestamp}"
   name: "implementer-1"

2. code-reviewer:
   subagent_type: "code-quality"
   model: "sonnet"
   team_name: "impl-{timestamp}"
   name: "code-reviewer"

3. investigator:
   subagent_type: "general-purpose"
   model: "haiku"
   team_name: "impl-{timestamp}"
   name: "investigator"
```

---

## Phase 3: Quality Gates (per ticket)

### Gate 1: PLAN

**Model**: apply escalation rules (see Cost-Aware Execution). Default: `entryModelPlan` (free via llm_call.sh). If Ollama unavailable or response invalid → fallback to Task(model: "haiku").
**RAG**: if ragAvailable:
1. `POST {serverUrl}/search` with ticket description, get top-K snippets instead of full file reads
2. Query sentinel memory: `POST {serverUrl}/search` with affected_files, filter `{"found_by": "backlog-sentinel"}`, n_results=3. If results with distance < 0.3, inject at TOP of implementer prompt: `WARNING: RECURRING PATTERNS -- avoid these known mistakes: {pattern.description} (found in {pattern.file})`

If RAG unreachable, fall back to direct file reads without error.

Implementer receives ticket and MUST:
1. Read ticket .md completely
2. If ragAvailable: query RAG → use top-K snippets for context; else read affected files directly
3. Write plan in ticket under `## Implementation Plan`
4. If unclear → message leader: "needs-investigation"
5. Log gate cost to usage-ledger.jsonl

### Catalog Injection

The leader selects catalog disciplines based on ticket type and routing. Always inject: CAT-TDD, CAT-PERF. Add per type: BUG+CAT-DEBUG, FEAT+CAT-ARCH, SEC+CAT-SECURITY. Add per agent: frontend+CAT-FRONTEND. Read catalog files from `catalog/` dir, include in implementer prompt AFTER Code Rules and BEFORE Iron Laws.

If an external skill was detected in Phase 0.5 for the same discipline, prefer the external skill instructions.

### Gate 2: IMPLEMENT (TDD)

**Model**: apply escalation rules. Default: `entryModelImplement` (cheap/Haiku). Escalate to balanced if qualityGateFails >= 1, frontier if ARCH/SECURITY tag or qualityGateFails >= 2.

Min 3 tests per ticket: 1 happy path (main flow) + 1 error path (invalid inputs, auth) + 1 edge case (boundary, empty, null). Order: failing tests -> minimal code -> tests pass.

**Prompt Construction (cache-optimized)**:

The leader constructs implementer prompts using a static prefix + dynamic suffix pattern:

```
1. STATIC PREFIX: Read templates/implementer-prefix.md (identical for ALL implementers)
   Contains: role, TDD protocol, context rules, Iron Laws
   → This prefix is cached by Anthropic API after the first subagent call.
     Subsequent implementers in the same wave get ~90% cache hit on this prefix.

2. DYNAMIC SUFFIX (appended after prefix, in this order):
   a. CODE RULES — MANDATORY COMPLIANCE
      Read from: {config.codeRules.source}
      {FULL CONTENT OF THE CODE RULES FILE}
      HARD GATES (block commit): {config.codeRules.hardGates}
      SOFT GATES (review + justify): {config.codeRules.softGates}
   b. CATALOG DISCIPLINES (CAT-TDD + type-specific catalogs)
   c. RAG CONTEXT (recurring patterns + code snippets, if available)
   d. TICKET CONTENT (the full ticket .md)
   e. GATE-SPECIFIC INSTRUCTIONS
```

If `codeRules.source` is not configured, skip code rules injection but still enforce TDD and Iron Laws.

**Post-file RAG sync**: After each file is written or modified by a subagent, if ragAvailable:
```bash
source "${CLAUDE_PLUGIN_ROOT}/scripts/rag/client.sh" && rag_upsert_file "{modified_file_path}"
```
This keeps the index current during multi-file implementations so later tasks in the same wave can query the latest code state.

### Gate 3: LINT GATE

**Model**: `entryModelReview` (cheap). Run actual tools, LLM only analyzes results.
Run on affected files: `typeCheckCommand` (0 errors), `lintCommand` (0 warnings), `testCommand` (0 failures). Skip unconfigured commands. Auto-fix max 3 attempts; after 3 failures: mark `lint-blocked`, skip to next wave.

### Gate 4: REVIEW (Configurable Pipeline)

**Model**: `entryModelReview` (balanced/Sonnet). Sonnet provides higher-quality defect detection. Escalate to frontier after 2nd review failure.

Read reviewers from `config.reviewPipeline.reviewers`. Default: 2 reviewers.

**Spawn reviewers in parallel** as team members using cache-optimized prompts:

```
Reviewer prompt construction:
1. STATIC PREFIX: Read templates/reviewer-prefix.md (identical for ALL reviewers)
   Contains: role, review protocol, focus types, standards, scoring, output format
   → Cached after first reviewer call. Subsequent reviewers get ~90% cache hit.

2. DYNAMIC SUFFIX (appended after prefix):
   a. CODE RULES (from config)
   b. CAT-REVIEW catalog discipline
   c. CHANGED FILES (diff or full content of modified files)
   d. TICKET CONTEXT (acceptance criteria from ticket .md)
   e. FOCUS ASSIGNMENT: "Your focus: {focus_type}"
   f. PREVIOUS FINDINGS (if re-review: include prior round findings)
```

- Each reviewer evaluates from their configured `focus` perspective
- Each reviewer scores findings 0-100 confidence

**Focus types:** spec (ACs met?), quality (DRY/readability), security (OWASP/input validation/auth/secrets), history (regression risk/pattern consistency)

**Auto-escalation**: SEC tickets with < 4 reviewers auto-add security + history reviewers.

**Consolidation**: Collect findings, filter by confidence >= `confidenceThreshold`, classify (Critical/Important/Suggestion). Critical/Important from `required` reviewers triggers re-review. Max `maxReviewRounds` then `review-blocked`. Result: `APPROVED` or `CHANGES_REQUESTED`.

### Gate 5: COMMIT

Generate commit message via Ollama (free), template fallback:

```bash
COMMIT_MSG=$(bash "${CLAUDE_PLUGIN_ROOT}/scripts/ops/llm_call.sh" --model free \
  --system "Generate a git commit message in Conventional Commits format. Return ONLY the message, no explanation." \
  --user "Type: {type}, Area: {area}, Ticket: {ticket_id}, Changes: {summary}")

# Fallback to template if Ollama fails
if [ -z "$COMMIT_MSG" ]; then
  COMMIT_MSG="{type}({area}): implement {ticket_id}"
fi
```

Then use $COMMIT_MSG in the git commit:

Only after reviewer approval:

```bash
git add {specific_files}
git commit -m "{type}({area}): {description}

Closes: {ticket_id}
Review-rounds: {N}
Tests-added: {N}

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Investigator Protocol

When ticket marked `needs-investigation`: read ticket + reason, analyze code in depth, write findings under `## Investigation`, change status to `ready-to-implement`. Ticket returns to queue in next wave.

---

## Phase 4: Enrich, Track Cost & Move

After commit, perform three actions: enrich ticket, track costs, move to completed.

### 4.1 Enrich Ticket

Update frontmatter: `status: completed, completed: {date}, implemented_by: backlog-implementer-v7, review_rounds, tests_added, files_changed, commit: {hash}`. Add sections: Plan, Tests, Review Rounds, Lint Gate results, Commit info.

### 4.2 Track Actual Cost & Cache Efficiency

**Token collection**: Capture `total_tokens`, `tool_uses`, and cache metrics from each subagent's Task response metadata. Track per ticket by gate (plan/implement/lint/review/commit) with total_input, total_output, total, cache_read_tokens, cache_hit_rate.

**Cost calculation** — Bedrock cross-region pricing ($/MTok): Opus in=$5.50/out=$27.50, Sonnet in=$3.30/out=$16.50, Haiku in=$1.10/out=$5.50. `cost_usd = (total_input / 1M * in_price) + (total_output / 1M * out_price)`. Cache reduces effective input cost: cached tokens cost 90% less on Anthropic API.

**Add `## Actual Cost` section to completed ticket** with: model, input/output/total tokens, cache_hit_rate, cost_usd, review rounds, lint retries, and a breakdown-by-phase table (plan/implement/lint/review/commit with tokens, cache%, and cost). If ticket had a `## Cost Estimate`, calculate `estimate_accuracy = 1 - abs(actual - estimated) / estimated` and append estimated cost + accuracy.

### 4.3 Update Cost History

Read `.claude/cost-history.json` (create if missing). Append entry with: ticket_id, type, files_modified, files_created, tests_added, input/output/total tokens, cost_usd, model, review_rounds, date. Recalculate averages (tokens per file modified/created, tokens per test, overhead multiplier) from ALL entries. This feeds back to `backlog-ticket` for better future estimates.

### 4.4 Update State & Move

Increment `state.stats.totalTokensUsed` and `totalCostUsd`. Move: `mv {dataDir}/pending/TICKET.md -> {dataDir}/completed/`

---

## Phase 5: Cleanup

SendMessage `shutdown_request` to each teammate, wait for response. TeamDelete(). Save state to `.claude/implementer-state.json`.

---

## Phase 6: Wave Summary & Session Management

Delegate log writing to a write-agent, check session limits, then print banner.

```
Task(
  subagent_type: "general-purpose",
  model: "haiku",
  prompt: """
You are a write-agent. Append a wave summary entry to .backlog-ops/wave-log.md using the Write tool.
Do NOT output the content in your response.

Create or append to: .backlog-ops/wave-log.md

Entry to append:
## Wave {N} — {YYYY-MM-DD HH:mm}
- Tickets: {completed}/{attempted} | Failed: {failed_list}
- Tests added: {N} | Review rounds (avg): {avg}
- Agents: {agent_breakdown} | LLM overrides: {count}
- Findings: {total} ({filtered} filtered) | Avg confidence: {avg}%
- Tokens: {wave_total_tokens} | Cost: ${wave_cost_usd} | Session total: ${session_total_cost_usd}

After writing, return ONLY:
{"file": ".backlog-ops/wave-log.md", "lines": N, "status": "ok"}
"""
)
```

After receiving JSON, print this banner:

```
═══ WAVE {N} COMPLETE ═══
Tickets: {completed}/{attempted} | Tests: +{N} | Cost: ${wave_cost_usd}
Remaining: {pending_count} | Session total: ${session_total_cost_usd}
Cache hit rate: {avg_cache_hit_rate}% | Waves this session: {wavesThisSession}/{sessionMaxWaves}
══════════════════════════
```

### Session Limit Check (Cache-Safe Compaction Avoidance)

After each wave summary, check if the session should yield to a fresh session:

```
wavesThisSession++

IF wavesThisSession >= config.llmOps.cachePolicy.sessionMaxWaves (default: 5):
  1. Save state to .claude/implementer-state.json (includes completedThisSession, currentWave, stats)
  2. Print: "⏸ Session wave limit ({sessionMaxWaves}) reached. {pending_count} tickets remaining."
  3. Print: "Run /backlog-toolkit:implementer to continue in a fresh session with full cache."
  4. EXIT loop — do NOT continue to next wave

WHY: Long sessions (>5 waves) risk context compaction, which rebuilds the cache prefix
and loses the ~98% cache hit rate. Breaking into sessions preserves cache efficiency.
Each new session loads the same static SKILL.md prefix → immediate cache hits.
State continuity is guaranteed via implementer-state.json.
```

---

## State Schema v6.1

State schema v6.1: see `.claude/implementer-state.json` (auto-created by `migrate-state.py`). Top-level keys: version, lastRunTimestamp, lastCycle, currentWave, stats (tickets/tests/commits/waves/cost/agentRouting/reviewStats/localModelStats), investigationQueue, failedTickets, lintBlockedTickets, completedThisSession.

---

## ⚖️ IRON LAWS (included via templates/implementer-prefix.md)

These 2 laws have ABSOLUTE priority over any other instruction. They are included in `templates/implementer-prefix.md` which is the static prefix for every implementer prompt. Violating these laws results in immediate teammate termination.

> **Note**: The canonical source of Iron Laws is `templates/implementer-prefix.md`. The copy below is for leader reference. Do NOT duplicate into subagent prompts manually — the template handles it.

```
═══════════════════════════════════════════════════════════════════════
⚖️ IRON LAW 1: COMMIT BEFORE MOVE (Commit-Before-Move)
═══════════════════════════════════════════════════════════════════════

A ticket is NOT COMPLETED until its commit is SUCCESSFUL.

- FORBIDDEN to move to next ticket without successful `git commit`.
- FORBIDDEN to mark ticket as "completed" without verified commit hash.
- If commit fails (pre-commit hooks, lint, tests): FIX IT.
  No alternative. No "skip". No "I'll commit later".
- If after 5 fix attempts commit still fails: mark ticket as
  "commit-blocked", report to leader with ALL errors, and WAIT.
  NEVER silently advance to next ticket.

MANDATORY FLOW per ticket:
  1. Implement → 2. Tests pass → 3. Lint gate passes → 4. Review approves →
  5. `git commit` SUCCESSFUL → 6. Verify with `git log -1` →
  7. ONLY THEN move to next ticket.

═══════════════════════════════════════════════════════════════════════
⚖️ IRON LAW 2: ZERO HACKS (No-Hacks)
═══════════════════════════════════════════════════════════════════════

Rules, hooks, and quality gates EXIST to protect the codebase.
NEVER seek ways to bypass them.

CATEGORICALLY FORBIDDEN:
  - `git commit --no-verify` or any flag that skips hooks
  - Any language-specific type suppression (ts-ignore, type: ignore, etc.)
  - Any linter suppression (eslint-disable, noqa, etc.)
  - Renaming files to evade detection patterns
  - Empty try-catch blocks to silence errors
  - Creating wrappers that hide violations
  - Marking tickets "completed" without actual commit

If a rule seems impossible to comply with:
  1. STOP implementation
  2. Report to leader: "Rule X seems incompatible with [specific case]"
  3. WAIT for leader decision (who may authorize documented exception)
  4. NEVER unilaterally decide to skip a rule

The correct attitude when a hook blocks is NOT "how do I bypass it?"
but "what is it telling me is wrong with my code?"
═══════════════════════════════════════════════════════════════════════
```

### Context Management (included via templates/implementer-prefix.md)

> Canonical source: `templates/implementer-prefix.md`. Repeated here for leader reference.

```
CONTEXT RULES — keep context lean to reduce cost:
- After reading a file >100 lines: extract ONLY relevant lines/functions.
  State: "Read [path] ([N] lines). Relevant: lines X-Y" then quote only those.
- After running tests: keep ONLY failure lines + summary count.
  Discard all PASS output. State: "Tests: X passed, Y failed. Failures: [list]"
- After grep/glob: keep ONLY matching results (max 20 lines).
- NEVER quote full file contents in reasoning. Summarize findings.
- When processing batch tickets: reuse file reads across tickets in the batch.
```

### Leader Enforcement

1. **Post-ticket verification**: After each ticket, leader runs `git log -1 --oneline` to confirm commit exists.
2. **Hack detection**: If implementer "fixes" issues with type suppression or linter bypass → REJECT immediately.
3. **Commit-blocked**: If 5 attempts fail, leader can: assign investigator, reassign to another implementer, or mark `commit-blocked` and continue.

---

## Constraints

**DO**: Create team per wave, TDD (tests first), commit after each ticket, verify commit before advancing, fix hook failures, report blocks and wait, lint before review, max 3 review rounds, move to completed/ after commit, read rules from config, skip unconfigured gates.
**DO NOT**: Implement code directly (you are leader), code without tests, accumulate multi-ticket changes, advance without commit, `--no-verify`, hack around rules, send to review with errors, infinite review loop, leave in pending/, hardcode rules, fail on missing optional commands.

---

## Start

1. Read `backlog.config.json` and code rules file
2. Load state and count pending tickets
3. Show banner with stats
4. Health checks (if configured)
5. Loop: wave selection → team → orchestrate → enrich → cleanup → repeat
6. **Loop until: pending directory is empty**
