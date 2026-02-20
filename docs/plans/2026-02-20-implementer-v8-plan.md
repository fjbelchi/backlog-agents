# Implementer v8.0 — Adaptive Pipeline Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add complexity classifier + fast-path single-agent routing + Qwen3 pre-review to reduce cost 5-10x on simple tickets.

**Architecture:** Phase 0 gets a classifier step. Simple/trivial tickets route to a single Sonnet agent that runs all 5 gates inline. Complex tickets use the existing v7.0 full pipeline with optimizations. Qwen3 gets expanded pre-review role.

**Tech Stack:** Markdown/prompt engineering (SKILL.md), shell (llm_call.sh integration)

**Design doc:** `docs/plans/2026-02-20-implementer-v8-design.md`

---

### Task 1: Bump version and update frontmatter

**Files:**
- Modify: `skills/backlog-implementer/SKILL.md:1-8`

**Step 1: Update frontmatter description**

Change line 3 description from v7.0 to v8.0, adding "adaptive pipeline" and "complexity classifier":

```yaml
description: "Implement backlog tickets with adaptive pipeline (complexity classifier → fast-path or full pipeline), Agent Teams, wave parallelization, 5 quality gates (Plan→TDD→Lint→Review→Commit), smart agent routing, embedded skill catalog (7 disciplines), configurable review pipeline with confidence scoring, 2 Iron Laws, ticket enrichment, and cost tracking. Config-driven and stack-agnostic. v8.0."
```

**Step 2: Update h1 title**

Change line 7 from:
```
# Backlog Implementer v7.0 — Smart Agent Routing + Embedded Skill Catalog + Configurable Reviews
```
To:
```
# Backlog Implementer v8.0 — Adaptive Pipeline + Smart Agent Routing + Configurable Reviews
```

**Step 3: Commit**

```bash
git add skills/backlog-implementer/SKILL.md
git commit -m "feat(implementer): bump to v8.0 — adaptive pipeline"
```

---

### Task 2: Add complexity classifier to Phase 0

**Files:**
- Modify: `skills/backlog-implementer/SKILL.md` — Phase 0 section (lines ~242-253)

**Step 1: Add classifier step after step 6 (cache health check)**

Insert between step 6 and step 7 (show banner). New step 6.5:

```markdown
6.5. **Classify pending tickets** (per ticket, before wave selection):
   For each ticket in `{dataDir}/pending/*.md`, extract: summary, affected_files count, tags, depends_on.

   Call Qwen3 classifier (cost: $0.00):
   ```bash
   COMPLEXITY=$(bash "${CLAUDE_PLUGIN_ROOT}/scripts/ops/llm_call.sh" --model free \
     --tag "gate:classify" --tag "ticket:${TICKET_ID}" \
     --system "Classify ticket complexity. Reply with ONLY one word: trivial, simple, or complex.
   Rules:
   - trivial: 1 file, obvious fix (typo, config, missing import, style change)
   - simple: 1-3 files, clear bug fix or small feature, no cross-cutting concerns
   - complex: 4+ files, architecture changes, security, cross-cutting, has dependencies" \
     --user "Ticket: ${TICKET_SUMMARY}
   Affected files: ${AFFECTED_FILES_COUNT} (${AFFECTED_FILES_LIST})
   Tags: ${TAGS}
   Dependencies: ${DEPENDS_ON:-none}")
   ```

   Validate response is one of: trivial, simple, complex. If invalid or Qwen3 unavailable:
   ```
   Heuristic fallback:
     affected_files <= 2 AND no ARCH/SEC tags AND no depends_on → simple
     affected_files <= 5 AND no ARCH/SEC tags → complex
     else → complex
   ```

   Override: if ticket has explicit `complexity:` field in frontmatter, use that instead.
   Store as `ticket.computed_complexity`. Log: `"Classified {TICKET_ID}: {complexity} (source: {qwen3|heuristic|manual})"`
```

**Step 2: Commit**

```bash
git add skills/backlog-implementer/SKILL.md
git commit -m "feat(implementer): add Phase 0 complexity classifier"
```

---

### Task 3: Add pipeline routing to MAIN LOOP

**Files:**
- Modify: `skills/backlog-implementer/SKILL.md` — MAIN LOOP section (lines ~226-238)

**Step 1: Update the MAIN LOOP pseudocode**

Replace the existing MAIN LOOP block with:

```
PHASE 0: STARTUP → load config + codeRules + state, cache health, classify tickets, show banner
PHASE 0.5: DETECT CAPABILITIES → scan plugins + MCP servers, log capabilities
WHILE pending_tickets_exist() AND wavesThisSession < sessionMaxWaves: cycle++
  PHASE 1: WAVE SELECTION → top 10 by priority, analyze blast radius, select 2-3 compatible slots
  PHASE 1.5: ROUTE PIPELINE →
    IF all wave tickets have computed_complexity in (trivial, simple):
      → FAST PATH: run each ticket through single-agent pipeline (no team)
      → Skip Phase 2-3, use "Fast Path" section instead
    ELSE IF mix of simple + complex:
      → Run simple tickets via FAST PATH first (sequentially)
      → Then run complex tickets via FULL PATH (team-based)
    ELSE:
      → FULL PATH (existing v7.0 team pipeline)
  [FULL PATH only:]
  PHASE 2: CREATE TEAM → TeamCreate, spawn implementers + reviewer + investigator
  PHASE 3: ORCHESTRATE → per ticket: 3a PLAN → 3b IMPLEMENT → 3c LINT → 3d REVIEW → 3e COMMIT
  PHASE 4: VERIFY & ENRICH & MOVE → git log -1 confirms, enrich ticket, mv to completed/
  PHASE 5: CLEANUP → shutdown teammates, TeamDelete, save state
  PHASE 6: WAVE SUMMARY → delegate log to write-agent, print banner, check session limits
```

**Step 2: Commit**

```bash
git add skills/backlog-implementer/SKILL.md
git commit -m "feat(implementer): add adaptive pipeline routing in main loop"
```

---

### Task 4: Add Fast Path section

**Files:**
- Modify: `skills/backlog-implementer/SKILL.md` — insert new section after Phase 3 (after line ~595, before Investigator Protocol)

**Step 1: Insert new "Fast Path" section**

Add this section between Phase 3 (Quality Gates) and "Investigator Protocol":

```markdown
## Fast Path: Single-Agent Pipeline (trivial/simple tickets)

When Phase 1.5 routes to FAST PATH, the leader handles each ticket WITHOUT creating a team.

### Pre-loading (leader does this BEFORE spawning the agent)

1. Read ticket .md completely
2. Read ALL affected files and store their content
3. Read code rules from config (if configured)
4. Get test command, lint command, typecheck command from config
5. If ragAvailable: query RAG for context snippets

### Spawn Single Sonnet Agent

```
Task(
  subagent_type: {routed_agent_type from ticket files},
  model: "sonnet",
  prompt: """
You are implementing ticket {TICKET_ID}. Execute ALL 5 gates sequentially.

## TICKET
{full_ticket_markdown}

## AFFECTED FILES (pre-loaded — do NOT re-read these)
{file_contents_pre_read_by_leader}

## CODE RULES
{code_rules_content_or_"No code rules configured"}

## COMMANDS
Test: {testCommand}
Lint: {lintCommand or "not configured"}
TypeCheck: {typeCheckCommand or "not configured"}

## EXECUTE THESE 5 GATES IN ORDER:

### Gate 1: PLAN
Write a 3-5 bullet implementation plan. Do not create a separate file.

### Gate 2: IMPLEMENT (TDD)
1. Write failing test(s) first (min 3: happy path + error + edge)
2. Run: {testCommand} — verify tests fail
3. Implement minimal code to make tests pass
4. Run: {testCommand} — verify tests pass

### Gate 3: LINT
Run: {lintCommand} and {typeCheckCommand}
If errors: fix and re-run (max 3 attempts). If still failing after 3: STOP and report.

### Gate 4: SELF-REVIEW
Check against acceptance criteria:
{acceptance_criteria_from_ticket}
Check code rules compliance. Report any issues found and fix them.

### Gate 5: COMMIT
Stage ONLY the files you modified:
git add {specific_files}
git commit with conventional format: "{type}({area}): {description}\n\nCloses: {TICKET_ID}"

IRON LAWS: Never use --no-verify. Never use type suppressions. Never skip hooks.
"""
)
```

### Escalation to Full Path

If the fast-path agent fails Gate 3 (LINT) or Gate 4 (self-REVIEW) twice:
1. Log: `"Fast path failed for {TICKET_ID} after 2 attempts. Escalating to full pipeline."`
2. Set `ticket.computed_complexity = "complex"` (override)
3. Ticket enters next wave via FULL PATH
4. Increment `stats.fastPathEscalations`

### Fast Path Cost Tracking

After fast-path completion, log to usage-ledger.jsonl:
```json
{"ticket_id": "{id}", "pipeline": "fast", "gates_passed": 5, "model": "sonnet", "cost_usd": 0.XX, "escalated_to_full": false}
```
```

**Step 2: Commit**

```bash
git add skills/backlog-implementer/SKILL.md
git commit -m "feat(implementer): add fast-path single-agent pipeline"
```

---

### Task 5: Add Qwen3 pre-review to Gate 4

**Files:**
- Modify: `skills/backlog-implementer/SKILL.md` — Gate 4 REVIEW section (lines ~463-493)

**Step 1: Insert Qwen3 pre-review before Sonnet reviewer spawn**

Add this block at the start of Gate 4 REVIEW, before "Read reviewers from config":

```markdown
**Pre-review via Qwen3** (cost: $0.00, reduces Sonnet review tokens):

Before spawning Sonnet reviewers, run a Qwen3 pre-check:

```bash
PRE_REVIEW=$(bash "${CLAUDE_PLUGIN_ROOT}/scripts/ops/llm_call.sh" --model free \
  --tag "ticket:${TICKET_ID}" --tag "gate:pre-review" \
  --system "You are a code review pre-checker. Analyze the diff and output a structured checklist. Be brief." \
  --user "## Git Diff
${GIT_DIFF}

## Test Results
${TEST_OUTPUT}

## Lint Output
${LINT_OUTPUT}

Checklist (mark [x] or [ ]):
- All imports used, no missing imports
- Lint output is clean (0 warnings)
- All tests pass
- No debug artifacts (console.log, TODO, FIXME, HACK)
- Format is consistent with surrounding code
- Error messages match project language (check existing patterns)")
```

If Qwen3 returns valid checklist: inject into Sonnet reviewer prompt as `## Pre-Review Results\n{PRE_REVIEW}`.
If Qwen3 unavailable or empty response: skip pre-review, Sonnet does full review (current behavior).
```

**Step 2: Update OLLAMA section in MODEL RULES**

Add pre-review to the list of Ollama tasks:
```
OLLAMA (free tier, via llm_call.sh):
  - Wave planning JSON generation
  - Gate 1 PLAN text generation
  - Gate 4 PRE-REVIEW checklist (NEW — reduces Sonnet review tokens)
  - Gate 5 COMMIT message generation
  - Ticket complexity classification (NEW)
```

**Step 3: Commit**

```bash
git add skills/backlog-implementer/SKILL.md
git commit -m "feat(implementer): add Qwen3 pre-review before Gate 4"
```

---

### Task 6: Add full-path optimizations

**Files:**
- Modify: `skills/backlog-implementer/SKILL.md` — multiple sections

**Step 1: Context pre-loading in Phase 2**

In the Phase 2 "Create Team" section, after the team structure, add:

```markdown
### Context Pre-Loading (v8.0 optimization)

Before spawning implementers, the leader pre-reads all affected files for every ticket in the wave:

```
For each ticket in wave:
  affected_content[ticket_id] = {}
  For each file in ticket.affected_files:
    affected_content[ticket_id][file] = Read(file)
```

Pass `affected_content[ticket_id]` in each implementer's prompt instead of letting subagents read files themselves. This eliminates 30-40 redundant Haiku file-read calls per wave.
```

**Step 2: Conversation pruning note in Gate 4**

In Gate 4 REVIEW, add after the reviewer prompt construction section:

```markdown
**Conversation pruning (v8.0):** The reviewer agent receives ONLY:
- Git diff of changes (`git diff HEAD~1`)
- Test results summary (pass/fail counts + failure details)
- Original ticket ACs
- Pre-review checklist (if available from Qwen3)

It does NOT receive the full planning/implementation conversation. This prevents the 44K→99K prompt growth observed in v7.0 benchmarks.
```

**Step 3: Coordination overhead cap in Phase 2**

Add to Phase 2 after team creation:

```markdown
### Coordination Cap (v8.0)

Maximum 5 coordination tool calls (TaskCreate, TaskUpdate, SendMessage) per wave for non-implementation work. Beyond 5, batch remaining status updates into a single summary message at wave end. This reduces the ~40 coordination-only API calls observed in v7.0 benchmarks.
```

**Step 4: Commit**

```bash
git add skills/backlog-implementer/SKILL.md
git commit -m "refactor(implementer): add full-path optimizations for v8.0"
```

---

### Task 7: Update MODEL RULES and Cost-Aware Execution

**Files:**
- Modify: `skills/backlog-implementer/SKILL.md` — MODEL RULES (lines ~12-34) and Cost-Aware (lines ~97-121)

**Step 1: Update MODEL RULES block**

Replace the MODEL RULES code block with:

```
model: "haiku"   → DEFAULT for implementers, investigators, write-agents,
                   wave planning subagents. Cost-optimized tier.

model: "sonnet"  → FAST PATH single-agent (trivial/simple tickets).
                   Also: REVIEWERS in full path (Gate 4).

ESCALATION to parent model (omit model: parameter):
  - Ticket tagged ARCH or SECURITY
  - qualityGateFails >= 2 for a ticket
  - ticket.computed_complexity == "complex" AND qualityGateFails >= 1

OLLAMA (free tier, via llm_call.sh):
  - Ticket complexity classification (Phase 0)
  - Wave planning JSON generation
  - Gate 1 PLAN text generation
  - Gate 4 PRE-REVIEW checklist (reduces Sonnet review tokens)
  - Gate 5 COMMIT message generation
  These use llm_call.sh --model free. If Ollama fails → fallback to
  Task(model: "haiku") subagent.
```

**Step 2: Update Model Tier Routing table**

In the Cost-Aware Execution section, update the routing table to add fast-path:

```
4. Use gate default:
   FAST PATH    → "sonnet" (single agent, all gates inline)
   Wave Plan    → "free" via llm_call.sh (fallback: haiku subagent)
   Classify     → "free" via llm_call.sh (fallback: heuristic)
   Pre-Review   → "free" via llm_call.sh (fallback: skip)
   Gate 1 PLAN  → "free" via llm_call.sh (fallback: haiku subagent)
   Gate 2 IMPL  → "cheap" (haiku)
   Gate 3 LINT  → "cheap" (haiku)
   Gate 4 REVIEW→ "balanced" (sonnet)
   Gate 4b      → "frontier" (opus, selective)
   Gate 5 COMMIT→ "free" via llm_call.sh (fallback: template)
```

**Step 3: Add v8.0 cost model**

After the Model Tier Routing table, add:

```markdown
### v8.0 Projected Cost Model

| Ticket Type | v7.0 Cost | v8.0 Cost | Savings | Pipeline |
|-------------|-----------|-----------|---------|----------|
| trivial     | $1.50-2.50 | $0.10-0.25 | 85-93% | fast path |
| simple      | $1.50-2.50 | $0.25-0.50 | 67-90% | fast path |
| complex     | $2.00-4.00 | $1.50-3.00 | 25-50% | full path |

Based on benchmark: AUDIT-BUG-20260220-003 (simple bug fix) cost $2.04 on v7.0 vs projected $0.25-0.50 on v8.0 fast path.
```

**Step 4: Commit**

```bash
git add skills/backlog-implementer/SKILL.md
git commit -m "feat(implementer): update model rules for adaptive pipeline"
```

---

### Task 8: Update CLAUDE.md and wave summary

**Files:**
- Modify: `skills/backlog-implementer/CLAUDE.md`
- Modify: `skills/backlog-implementer/SKILL.md` — Phase 6 wave summary

**Step 1: Update CLAUDE.md**

Read `skills/backlog-implementer/CLAUDE.md` and update:
- Any version references from v7.0 → v8.0
- Add a section documenting the fast-path behavior
- Update any cost model references

**Step 2: Update Phase 6 wave summary banner**

In SKILL.md Phase 6, update the banner template to include pipeline info:

```
═══ WAVE {N} COMPLETE ═══
Tickets: {completed}/{attempted} | Tests: +{N} | Cost: ${wave_cost_usd}
Pipeline: fast:{fast_count} full:{full_count} | Escalations: {fastPathEscalations}
Models: free:{N} haiku:{N} sonnet:{N} opus:{N} | Ollama: {ok}/{total}
Remaining: {pending_count} | Session total: ${session_total_cost_usd}
Cache hit rate: {avg_cache_hit_rate}% | Waves this session: {wavesThisSession}/{sessionMaxWaves}
══════════════════════════
```

**Step 3: Update state schema reference**

In State Schema section, add to stats:
```
stats.fastPathTickets, stats.fullPathTickets, stats.fastPathEscalations
```

**Step 4: Commit**

```bash
git add skills/backlog-implementer/SKILL.md skills/backlog-implementer/CLAUDE.md
git commit -m "docs(implementer): update CLAUDE.md and wave summary for v8.0"
```

---

## Verification

After all tasks:
1. Read full SKILL.md and verify no broken sections
2. Re-run AUDIT-BUG-20260220-003 with v8.0 → should classify as "simple", use fast path
3. Expected: 5-15 requests, $0.15-0.50 (vs 120 requests, $2.04 on v7.0)
4. Run a complex ticket to verify full path still works
