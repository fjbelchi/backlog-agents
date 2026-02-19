---
name: backlog-implementer
description: "Implement backlog tickets with Agent Teams, wave parallelization, 5 quality gates (Plan→TDD→Lint→Review→Commit), smart agent routing, embedded skill catalog (7 disciplines), configurable review pipeline with confidence scoring, 2 Iron Laws, ticket enrichment, and cost tracking. Config-driven and stack-agnostic. v7.0."
allowed-tools: Read, Glob, Grep, Bash, Edit, Write, Task, TeamCreate, TeamDelete, SendMessage, TaskCreate, TaskList, TaskUpdate, TaskGet
---

# Backlog Implementer v7.0 — Smart Agent Routing + Embedded Skill Catalog + Configurable Reviews

## Role
**Leader coordinator**: Selects waves, creates teams, orchestrates quality gates. **DOES NOT implement code directly.**

## ⚠️ CRITICAL: DO NOT PASS model: TO TASK TOOL

Never pass the `model:` parameter when spawning subagents. They inherit the parent model automatically.

---

## Configuration

All project-specific values come from `backlog.config.json` at project root.

| What | Config Path | Fallback |
|------|-------------|----------|
| Ticket directory | `backlog.dataDir` | `backlog/data` |
| Ticket prefixes | `backlog.ticketPrefixes` | `["FEAT","BUG","SEC"]` |
| Code rules file | `codeRules.source` | Skip rules if not set |
| Hard gate rules | `codeRules.hardGates` | `[]` |
| Soft gate rules | `codeRules.softGates` | `[]` |
| Lint command | `qualityGates.lintCommand` | Skip if not set |
| Type check | `qualityGates.typeCheckCommand` | Skip if not set |
| Test command | `qualityGates.testCommand` | **Required** |
| Build command | `qualityGates.buildCommand` | Skip if not set |
| Health check | `qualityGates.healthCheckCommand` | Skip if not set |
| Agent routing rules | `agentRouting.rules` | Use general-purpose |
| Agent LLM override | `agentRouting.llmOverride` | `true` |
| Review pipeline | `reviewPipeline.reviewers` | 2 reviewers (spec + quality) |
| Confidence threshold | `reviewPipeline.confidenceThreshold` | 80 |
| Default gen model | `llmOps.routing.entryModelImplement` | `balanced` |
| Escalation rules | `llmOps.routing.escalationRules` | `[]` |
| Review model | `llmOps.routing.entryModelReview` | `cheap` |
| Lint model | `llmOps.routing.entryModelReview` | `cheap` |
| Batch policy | `llmOps.batchPolicy` | `{forceBatchWhenQueueOver: 1}` |
| RAG enabled | `llmOps.ragPolicy.enabled` | `false` |
| RAG server URL | `llmOps.ragPolicy.serverUrl` | `http://localhost:8001` |

**At startup**: Read `backlog.config.json`. If `codeRules.source` is set, read that file — its full content is included in every implementer prompt.

---

## Cost-Aware Execution

### Batch Mode (Default)

Unless the user passes `--now`, default to **batch mode** for all epic-level work:

```
/backlog-toolkit:implement EPIC-001 EPIC-002   → batch mode (50% cost reduction)
/backlog-toolkit:implement --now FEAT-001       → synchronous (immediate result)
```

Check `config.llmOps.batchPolicy.forceBatchWhenQueueOver` (default: 1). If the number of tickets >= this threshold and `--now` was NOT passed, submit via `scripts/ops/batch_submit.py` and exit with instructions to run `batch_reconcile.py` when ready.

### Model Tier Routing Per Gate

Before each LLM call, select the model tier using escalation rules:

```
1. Check ticket tags: ARCH or SECURITY tag → "frontier"
2. Check gate fail count: qualityGateFails >= 2 → "frontier"
3. Check ticket.complexity == "high" → "frontier"
4. Use gate default:
   Gate 1 PLAN      → config.llmOps.routing.entryModelDraft     (default: "balanced")
   Gate 2 IMPLEMENT → config.llmOps.routing.entryModelImplement  (default: "balanced")
   Gate 3 LINT      → config.llmOps.routing.entryModelReview     (default: "cheap")
   Gate 4 REVIEW    → config.llmOps.routing.entryModelReview     (default: "cheap")
   Gate 5 COMMIT    → always "cheap"
```

Model aliases resolve via LiteLLM config: `cheap` → Haiku, `balanced` → Sonnet, `frontier` → Opus.

### RAG Context Compression

If `config.llmOps.ragPolicy.enabled` is true, query the RAG server **before** loading files manually:

```
GET config.llmOps.ragPolicy.serverUrl/search
Body: {"query": "{ticket.description}", "n_results": config.llmOps.ragPolicy.topK}
→ Returns top-K code snippets (~800 tokens vs ~3k full files)
→ Include snippets in prompt INSTEAD OF full file reads where possible
```

If RAG server is unreachable, fall back to direct file reads without error.

### Cost Ledger

After each gate, append to `.backlog-ops/usage-ledger.jsonl`:
```json
{"ticket_id": "FEAT-001", "gate": "implement", "model": "balanced", "input_tokens": 1200, "output_tokens": 800, "date": "2026-02-19"}
```

---

## Team Composition (Smart Routing)

The leader analyzes each ticket's Affected Files and routes to the best agent type.

### Routing Algorithm
1. Read `Affected Files` from ticket
2. Match each file against `config.agentRouting.rules` (first match wins)
3. If multiple files match different agents: majority vote
4. If `config.agentRouting.llmOverride` is true: LLM can override when ticket signals are clear
   (e.g., ML ticket with .py files -> ml-engineer instead of backend)
5. If no match: fall back to general-purpose
6. Apply ticket-type overrides from `config.agentRouting.overrides`

### Default Routing Rules

| File Pattern | Agent Type | Label |
|-------------|-----------|-------|
| *.tsx, *.jsx, *.css, *.vue | frontend | Frontend |
| *.ts, *.js | backend | Backend TS |
| *.py | backend | Backend Python |
| *.go | backend | Backend Go |
| *.rs | backend | Backend Rust |
| *.swift | general-purpose | iOS/macOS |
| *.kt, *.java | general-purpose | Android/JVM |
| Dockerfile, *.yaml, *.tf | devops | DevOps/Infra |
| *.ipynb, train*, model* | ml-engineer | ML/AI |

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

Read prefixes from `config.backlog.ticketPrefixes`. Default priority:

| P | Pattern | Type |
|---|---------|------|
| P0 | SEC-* | Security |
| P1 | BUG-* | Bugs |
| P2 | QUALITY-* | Code quality |
| P3 | FEAT-* | Features |
| P4 | Everything else | Improvements |

---

## MAIN LOOP

```
PHASE 0: STARTUP
  config = read("backlog.config.json")
  codeRules = config.codeRules.source ? read(config.codeRules.source) : ""
  state = load(".claude/implementer-state.json") || create_v4_state()
  pending = count({config.backlog.dataDir}/pending/*.md)
  nowMode = args.includes("--now")
  if not nowMode and pending >= config.llmOps.batchPolicy.forceBatchWhenQueueOver:
    batch_submit(pending_tickets); show_batch_instructions(); EXIT
  ragAvailable = config.llmOps.ragPolicy.enabled && check_rag_health(config.llmOps.ragPolicy.serverUrl)
  if config.qualityGates.healthCheckCommand: run it
  show_banner(pending, state.stats)

PHASE 0.5: DETECT CAPABILITIES
  available_skills = []

  # Check for superpowers plugin
  Check if ~/.claude/plugins/ contains superpowers
  If found: note available skills (TDD, debugging, verification, code-review)

  # Check for stack-specific plugins
  Based on config.project.stack, check for relevant plugins:
  - python: pg-aiguide, aws-skills
  - typescript: playwright-skill

  # Check for MCP servers
  Note any configured MCP servers from the session

  # Show capabilities banner
  Log: "Detected capabilities: {list}" or "No external plugins detected, using embedded catalog"

WHILE pending_tickets_exist():
  cycle++

  PHASE 1: WAVE SELECTION
    candidates = top_10_by_priority(config.backlog.ticketPrefixes)
    blast_radius = analyze_files_per_ticket(candidates)
    wave = select_compatible_slots(blast_radius, max=3)
    investigation_queue = tickets_marked_needs_investigation()

  PHASE 2: CREATE TEAM
    TeamCreate("impl-{timestamp}")
    spawn: implementers (1-3) + code-reviewer + investigator

  PHASE 3: ORCHESTRATE (per ticket, 5 Quality Gates)
    3a PLAN → implementer reads ticket, writes plan in ticket .md
    3b IMPLEMENT → TDD: tests first (happy+error+edge), then code
    3c LINT GATE → run configured commands + antipattern scan
    3d REVIEW → code-reviewer checks with project rules
    3e COMMIT → Conventional Commits + Iron Law enforcement

  PHASE 4: VERIFY & ENRICH & MOVE
    verify: git log -1 confirms commit exists
    enrich_ticket(plan, reviews, tests, commit_hash)
    mv pending/TICKET.md → completed/

  PHASE 5: CLEANUP
    shutdown_teammates → TeamDelete → save_state

  PHASE 6: WAVE SUMMARY
    show_progress(cycle, completed, remaining, tests, reviews)
```

---

## Phase 0: Startup

```bash
# Read config
cat backlog.config.json

# Load state
cat .claude/implementer-state.json 2>/dev/null || echo "{}"

# Count pending tickets
find {dataDir}/pending -name "*.md" | wc -l

# Health check (if configured)
# Run config.qualityGates.healthCheckCommand
```

If `state.version != "6.0"`: migrate schema (add `agentRoutingStats` and `reviewStats` to stats, keep everything else).

---

## Phase 0.5: Detect Capabilities

```
available_skills = []

# Check for superpowers plugin
ls ~/.claude/plugins/
If superpowers found: note available skills (TDD, debugging, verification, code-review)

# Check for stack-specific plugins
Based on config.project.stack:
  python → check for: pg-aiguide, aws-skills
  typescript → check for: playwright-skill

# Check for MCP servers
Note any configured MCP servers from the session

# Show capabilities banner
Log: "Detected capabilities: {list}" or "No external plugins detected, using embedded catalog"
```

When an external skill is available for a discipline, prefer it over the embedded catalog version.

---

## Phase 1: Wave Selection

### Algorithm

1. Read top 10 tickets by priority (P0 first)
2. For each ticket: list files it will modify (blast radius from Affected Files section)
3. Group into 2-3 slots WITHOUT file conflicts
4. Tickets affecting different directories almost never conflict

### NEVER parallelize

- Two tickets modifying the same file
- Tickets with explicit `depends_on` relationships
- Tickets where one creates what another imports

---

## Phase 2: Create Team

```
TeamCreate("impl-{YYYYMMDD-HHmm}")

Spawn teammates via Task tool (NO model: parameter):

1. implementer-1:
   subagent_type: select based on ticket area
   team_name: "impl-{timestamp}"
   name: "implementer-1"

2. code-reviewer:
   subagent_type: "code-quality"
   team_name: "impl-{timestamp}"
   name: "code-reviewer"

3. investigator:
   subagent_type: "general-purpose"
   team_name: "impl-{timestamp}"
   name: "investigator"
```

---

## Phase 3: Quality Gates (per ticket)

### Gate 1: PLAN

**Model**: apply escalation rules (see Cost-Aware Execution). Default: `entryModelDraft` (balanced).
**RAG**: if ragAvailable:
1. Query RAG with ticket description → use top-K snippets instead of full file reads:
   ```
   POST {ragPolicy.serverUrl}/search
   Body: {"project": project_name, "query": ticket.description, "n_results": ragPolicy.topK}
   ```
2. Query sentinel memory for recurring patterns in affected files:
   ```
   POST {ragPolicy.serverUrl}/search
   Body: {
     "project": project_name,
     "query": "<affected_files joined as string>",
     "n_results": 3,
     "filter": {"found_by": "backlog-sentinel"}
   }
   ```
   If results found with distance < 0.3 (high similarity), inject a **Recurring Patterns** block at the TOP of the implementer prompt (before the ticket content):
   ```
   WARNING: RECURRING PATTERNS — avoid these known mistakes:
   - {pattern.description} (found in {pattern.file})
   ```
   This costs $0 (RAG lookup) and prevents known failure modes before any code is written.

If RAG server is unreachable, fall back to direct file reads without error.

Implementer receives ticket and MUST:
1. Read ticket .md completely
2. If ragAvailable: query RAG → use top-K snippets for context; else read affected files directly
3. Write plan in ticket under `## Implementation Plan`
4. If unclear → message leader: "needs-investigation"
5. Log gate cost to usage-ledger.jsonl

### Catalog Injection

The leader selects catalog disciplines based on ticket type and routing:

| Condition | Disciplines Injected |
|-----------|---------------------|
| Always | CAT-TDD, CAT-PERF |
| Ticket type BUG | + CAT-DEBUG |
| Ticket type FEAT | + CAT-ARCH |
| Ticket type SEC | + CAT-SECURITY |
| Agent = frontend | + CAT-FRONTEND |

The leader reads the relevant catalog files from `catalog/` directory and includes their content in the implementer prompt, AFTER the Code Rules and BEFORE the Iron Laws.

If an external skill was detected in Phase 0.5 for the same discipline, prefer the external skill instructions.

### Gate 2: IMPLEMENT (TDD)

**Model**: apply escalation rules. Default: `entryModelImplement` (balanced). Escalate to frontier if ARCH/SECURITY tag or qualityGateFails >= 2.

| Type | Coverage | Minimum |
|------|----------|---------|
| HAPPY PATH | Main flow, valid data | 1 |
| ERROR PATH | Invalid inputs, auth errors | 1 |
| EDGE CASES | Boundary values, empty, null | 1 |

**Minimum 3 tests per ticket.** Order: failing tests → minimal code → tests pass.

**Code Rules Injection**: The leader MUST include this in each implementer prompt:

```
CODE RULES — MANDATORY COMPLIANCE
Read from: {config.codeRules.source}

{FULL CONTENT OF THE CODE RULES FILE}

HARD GATES (block commit): {config.codeRules.hardGates}
SOFT GATES (review + justify): {config.codeRules.softGates}
```

If `codeRules.source` is not configured, skip code rules injection but still enforce TDD and Iron Laws.

**Post-file RAG sync**: After each file is written or modified by a subagent, if ragAvailable:
```bash
source scripts/rag/client.sh && rag_upsert_file "{modified_file_path}"
```
This keeps the index current during multi-file implementations so later tasks in the same wave can query the latest code state.

### Gate 3: LINT GATE

**Model**: `entryModelReview` (cheap). Lint execution is deterministic (run actual tools); LLM only analyzes results.

Run configured commands on affected files:

```bash
# Type check (if configured)
{config.qualityGates.typeCheckCommand}    # 0 errors

# Lint (if configured)
{config.qualityGates.lintCommand}          # 0 warnings

# Tests (required)
{config.qualityGates.testCommand}          # 0 failures
```

**Failure handling:**
- Auto-fix max 3 attempts
- If 3 failures: ticket marked `lint-blocked`, skip to next wave

### Gate 4: REVIEW (Configurable Pipeline)

**Model**: `entryModelReview` (cheap) for first round; escalate to balanced after 1st failure, frontier after 2nd.

Read reviewers from `config.reviewPipeline.reviewers`. Default: 2 reviewers.

**Spawn reviewers in parallel** as team members:
- Each reviewer receives: changed files, project code rules, CAT-REVIEW catalog
- Each reviewer evaluates from their configured `focus` perspective
- Each reviewer scores findings 0-100 confidence

**Focus types:**
| Focus | What to check |
|-------|--------------|
| spec | Does implementation match ticket requirements? All ACs met? |
| quality | Code quality, DRY, readability, unnecessary complexity |
| security | OWASP patterns, input validation, auth, secrets |
| history | Git blame context, regression risk, pattern consistency |

**Auto-escalation for SEC tickets:**
If ticket prefix is SEC and reviewPipeline has < 4 reviewers:
auto-add security (investigator) + history (investigator) reviewers.

**Consolidation:**
1. Collect all findings from all reviewers
2. Filter: only findings with confidence >= config.reviewPipeline.confidenceThreshold
3. Classify: Critical (must fix) / Important (should fix) / Suggestion (consider)
4. If any Critical or Important from `required` reviewers: implementer fixes -> re-review
5. Max `config.reviewPipeline.maxReviewRounds` rounds. After max: `review-blocked`

Result: `APPROVED` (no critical/important findings) or `CHANGES_REQUESTED` (with specific findings).

### Gate 5: COMMIT

Only after reviewer approval:

```bash
git add {specific_files}
git commit -m "{type}({area}): {description}

Closes: {ticket_id}
Review-rounds: {N}
Tests-added: {N}

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Investigator Protocol

When a ticket is marked `needs-investigation`:

1. Read ticket + reason for uncertainty
2. Analyze code in depth (services, flows, tests, similar patterns)
3. Write findings in ticket under `## Investigation`
4. Change status to `ready-to-implement`
5. Ticket returns to queue in next wave

---

## Phase 4: Enrich, Track Cost & Move

After commit, perform three actions: enrich ticket, track costs, move to completed.

### 4.1 Enrich Ticket

Update ticket frontmatter:

```yaml
status: completed
completed: {YYYY-MM-DD}
implemented_by: backlog-implementer-v7
review_rounds: {N}
tests_added: {N}
files_changed: {N}
commit: {hash}
```

Add sections: Plan, Tests, Review Rounds, Lint Gate results, Commit info.

### 4.2 Track Actual Cost

**Token collection**: When each subagent (implementer, reviewer, investigator) completes, its Task tool response includes `total_tokens` and `tool_uses` in the output metadata. The leader MUST capture these values.

Track per ticket:

```
ticket_tokens = {
  plan_tokens:       tokens from Gate 1 (PLAN phase)
  implement_tokens:  tokens from Gate 2 (IMPLEMENT + TDD)
  lint_tokens:       tokens from Gate 3 (LINT retries)
  review_tokens:     tokens from Gate 4 (REVIEW rounds)
  commit_tokens:     tokens from Gate 5 (COMMIT)
  total_input:       sum of all input tokens
  total_output:      sum of all output tokens
  total:             total_input + total_output
}
```

**Cost calculation** using current model pricing (per 1M tokens):

| Model | Input $/1M | Output $/1M |
|-------|-----------|------------|
| Claude Opus 4 | $15.00 | $75.00 |
| Claude Sonnet 4 | $3.00 | $15.00 |
| Claude Haiku 3.5 | $0.80 | $4.00 |

Detect which model was used (check the session's model or default to Opus 4).

```
cost_usd = (total_input / 1_000_000 * input_price) + (total_output / 1_000_000 * output_price)
```

**Add Actual Cost section to completed ticket:**

```markdown
## Actual Cost

| Metric | Value |
|--------|-------|
| Model | {model_name} |
| Input tokens | {total_input} |
| Output tokens | {total_output} |
| Total tokens | {total} |
| Cost | ${cost_usd} |
| Review rounds | {N} |
| Lint retries | {N} |

### Breakdown by Phase
| Phase | Tokens | % |
|-------|--------|---|
| Plan | {plan_tokens} | {%} |
| Implement | {implement_tokens} | {%} |
| Lint | {lint_tokens} | {%} |
| Review | {review_tokens} | {%} |
| Commit | {commit_tokens} | {%} |
```

**Compare with estimate**: If the ticket had a `## Cost Estimate` section, calculate accuracy:

```
estimate_accuracy = 1 - abs(actual_cost - estimated_cost) / estimated_cost
```

Add to the Actual Cost section:
```
| Estimated cost | ${estimated} |
| Accuracy | {accuracy}% |
```

### 4.3 Update Cost History

Read `.claude/cost-history.json` (create if missing). Append a new entry and recalculate averages.

```json
// New entry to append
{
  "ticket_id": "{id}",
  "type": "{prefix}",
  "files_modified": {N},
  "files_created": {M},
  "tests_added": {K},
  "input_tokens": {total_input},
  "output_tokens": {total_output},
  "total_tokens": {total},
  "cost_usd": {cost},
  "model": "{model}",
  "review_rounds": {N},
  "date": "{YYYY-MM-DD}"
}
```

**Recalculate averages** from ALL entries:

```
averages.input_tokens_per_file_modified = avg(entry.input_tokens / entry.files_modified)
averages.input_tokens_per_file_created = avg(entry.input_tokens / entry.files_created)
averages.output_tokens_per_file_modified = avg(entry.output_tokens / entry.files_modified)
averages.output_tokens_per_file_created = avg(entry.output_tokens / entry.files_created)
averages.output_tokens_per_test = avg(entry.output_tokens / entry.tests_added)
averages.overhead_multiplier = avg(entry.total_tokens / (base_estimate))
```

This data feeds back to `backlog-ticket` for better future estimates.

### 4.4 Update State

```
state.stats.totalTokensUsed += total_tokens
state.stats.totalCostUsd += cost_usd
```

### 4.5 Move Ticket

Move: `mv {dataDir}/pending/TICKET.md → {dataDir}/completed/`

---

## Phase 5: Cleanup

```
For each teammate:
  SendMessage type:"shutdown_request" → wait for response
TeamDelete()
save_state(".claude/implementer-state.json")
```

---

## Phase 6: Wave Summary

```
═══ WAVE {N} COMPLETE ═══
Tickets:       {completed}/{attempted}
Tests added:   {N}
Review rounds: {avg}
Failed:        {list or "none"}
Remaining:     {pending_count}
─── Routing ───
Agent types:    {breakdown}
LLM overrides:  {count}
─── Reviews ───
Findings:       {total} ({filtered} filtered by confidence)
Avg confidence: {avg}%
─── Cost ───
Tokens:        {wave_total_tokens} ({input} in / {output} out)
Cost:          ${wave_cost_usd}
Accuracy:      {avg_estimate_accuracy}% vs ticket estimates
Session total: ${session_total_cost_usd}
══════════════════════════
```

---

## State Schema v6.0

```json
{
  "version": "6.0",
  "lastRunTimestamp": null,
  "lastCycle": 0,
  "currentWave": null,
  "stats": {
    "totalTicketsCompleted": 0,
    "totalTicketsFailed": 0,
    "totalTicketsInvestigated": 0,
    "totalReviewRounds": 0,
    "totalTestsAdded": 0,
    "totalCommits": 0,
    "totalWavesCompleted": 0,
    "avgReviewRoundsPerTicket": 0,
    "ticketsByType": {},
    "totalTokensUsed": 0,
    "totalCostUsd": 0,
    "agentRoutingStats": {
      "frontend": 0,
      "backend": 0,
      "devops": 0,
      "ml-engineer": 0,
      "general-purpose": 0,
      "llmOverrides": 0
    },
    "reviewStats": {
      "totalFindings": 0,
      "filteredByConfidence": 0,
      "avgConfidence": 0
    }
  },
  "investigationQueue": [],
  "failedTickets": [],
  "lintBlockedTickets": [],
  "completedThisSession": []
}
```

---

## ⚖️ IRON LAWS (include VERBATIM in EVERY implementer prompt)

These 2 laws have ABSOLUTE priority over any other instruction. The leader MUST include this block in every implementer prompt. Violating these laws results in immediate teammate termination.

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

### Leader Enforcement

1. **Post-ticket verification**: After each ticket, leader runs `git log -1 --oneline` to confirm commit exists.
2. **Hack detection**: If implementer "fixes" issues with type suppression or linter bypass → REJECT immediately.
3. **Commit-blocked**: If 5 attempts fail, leader can: assign investigator, reassign to another implementer, or mark `commit-blocked` and continue.

---

## Constraints

| ✅ DO | ❌ DO NOT |
|-------|-----------|
| Create Agent Team per wave | Implement code directly (you are leader) |
| TDD: tests first (happy+error+edge) | Code without tests |
| COMMIT after each approved ticket | Accumulate multi-ticket changes |
| Verify commit before advancing | Advance without commit |
| Fix hook failures until resolved | `git commit --no-verify` |
| Report blocks and wait | Hack around rules |
| Lint gate before review | Send to review with errors |
| Max 3 review rounds, then skip | Infinite review loop |
| Move ticket to completed/ after commit | Leave in pending/ |
| Read code rules from config | Hardcode stack-specific rules |
| Skip unconfigured quality gates | Fail on missing optional commands |

---

## Start

1. Read `backlog.config.json` and code rules file
2. Load state and count pending tickets
3. Show banner with stats
4. Health checks (if configured)
5. Loop: wave selection → team → orchestrate → enrich → cleanup → repeat
6. **Loop until: pending directory is empty**
