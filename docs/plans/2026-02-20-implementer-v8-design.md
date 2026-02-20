# Implementer v8.0 — Adaptive Pipeline Design

**Goal:** Reduce implementer cost 5-10x for simple tickets by classifying complexity upfront and routing trivial/simple tickets through a single-agent fast path, while keeping the full pipeline for complex work.

**Architecture:** Phase 0 classifier (Qwen3/Haiku) determines ticket complexity. Trivial/simple tickets skip team coordination entirely and run all 5 gates in a single Sonnet agent. Complex tickets use the existing v7.0 full pipeline with optimizations. Qwen3 gets expanded pre-review role.

**Motivation:** Benchmark on AUDIT-BUG-20260220-003 (single-file bug fix) showed the v7.0 implementer used 120 API requests ($2.04) for a task an Opus agent solved in ~10 requests ($0.30). Code quality was equivalent. The overhead came from team coordination, multiple subagents, and the full gate ceremony being applied regardless of ticket complexity.

---

## 1. Complexity Classifier (Phase 0 Addition)

After loading the ticket in Phase 0, classify before executing:

```
Input to classifier:
  - Ticket summary + description
  - affected_files list and count
  - Tags (ARCH, SECURITY, etc.)
  - Dependencies (depends_on other tickets)

Output: trivial | simple | complex

Classification rules:
  trivial: 1 file, obvious fix (typo, config, missing import, style)
  simple:  1-3 files, clear bug fix or small feature, no cross-cutting
  complex: 4+ files, architecture, security, cross-cutting, dependencies

Implementation:
  1. Call Qwen3 (free tier) via llm_call.sh with classification prompt
  2. If Qwen3 unavailable or returns invalid → heuristic fallback:
     - affected_files <= 2 AND no ARCH/SEC tags AND no dependencies → simple
     - affected_files <= 5 AND no ARCH/SEC tags → complex
     - else → complex
  3. Store in ticket.computed_complexity
  4. Override: ticket.complexity field (if set manually) takes precedence

Cost: 1 Qwen3 call ($0.00) or 1 Haiku fallback ($0.001)
```

## 2. Pipeline Routing

```
computed_complexity == "trivial" OR "simple"  →  FAST PATH
computed_complexity == "complex"              →  FULL PATH (v7.0)
```

### 2a. Fast Path — Single Agent, All Gates Inline

One Sonnet agent receives a comprehensive prompt containing:

```
Pre-loaded by leader (before agent spawn):
  - Full ticket markdown
  - Content of all affected files (pre-read, not agent-read)
  - Code rules from config
  - Test command, lint command from config

Agent executes sequentially in one session:
  Gate 1 PLAN:      Write plan inline (3-5 bullet points, no subagent)
  Gate 2 IMPLEMENT: Apply changes with TDD (write test first, implement, run)
  Gate 3 LINT:      Run lint/typecheck command, fix if needed
  Gate 4 REVIEW:    Self-review against AC checklist + code rules
  Gate 5 COMMIT:    Stage files and commit with conventional message

No TeamCreate. No TaskCreate. No SendMessage. No wave planning.
```

**Expected cost (simple ticket):** 5-15 requests, $0.15-0.50

**vs v7.0 benchmark:** 120 requests, $2.04

**Escalation:** If the Sonnet agent fails Gate 3 (LINT) or Gate 4 (self-REVIEW) twice, the leader falls back to the full pipeline for that ticket.

### 2b. Full Path — v7.0 with Optimizations

Complex tickets use the existing team-based pipeline with these improvements:

1. **Context pre-loading:** Leader reads all affected files ONCE and passes content to subagents in their prompt. Eliminates redundant file reads across agents (estimated 30-40 Haiku calls saved per ticket).

2. **Gate fusion:** For tickets with <= 3 affected files, LINT + pre-REVIEW run in the same Haiku agent. One less subagent spawn.

3. **Conversation pruning:** After Gate 2 (IMPLEMENT), the review agent receives only: diff output, test results, and original ticket — NOT the full planning/implementation conversation. Prevents the 44K→99K prompt growth observed in the benchmark.

4. **Coordination overhead cap:** Maximum 5 coordination messages per wave (TaskCreate, TaskUpdate, SendMessage). Beyond that, batch remaining updates into a single summary message.

## 3. Qwen3 Expanded Role (Pre-Review)

Qwen3 gets three jobs:

```
1. CLASSIFICATION (Phase 0): Ticket complexity classification
   Already described in section 1.

2. PRE-REVIEW (before Gate 4):
   Input: git diff of changes + test results + lint output
   Output: Structured checklist:
     - [ ] All imports used, no missing
     - [ ] Lint output clean
     - [ ] Tests pass
     - [ ] Format consistent
     - [ ] No debug artifacts (console.log, TODO, etc.)

   This structured report is injected into Sonnet's review prompt,
   reducing what Sonnet needs to analyze.

   If Qwen3 unavailable: skip, Sonnet does full review (current behavior).

3. COMMIT MESSAGES (Gate 5):
   Generate conventional commit message from diff.
   If Qwen3 unavailable: template fallback (current behavior).
```

**Cost of expanded Qwen3 role:** $0.00 (local model). Fallback cost: 2 extra Haiku calls ($0.002).

## 4. Expected Cost Model

```
Ticket Type    │ v7.0 (current)  │ v8.0 (projected)  │ Savings
───────────────┼─────────────────┼────────────────────┼────────
trivial        │ $1.50-2.50      │ $0.10-0.25         │ 85-93%
simple         │ $1.50-2.50      │ $0.25-0.50         │ 67-90%
complex        │ $2.00-4.00      │ $1.50-3.00         │ 25-50%
```

## 5. Files to Change

```
Modify: skills/backlog-implementer/SKILL.md
  - Add Phase 0 classifier step
  - Add fast-path routing logic
  - Add single-agent prompt template
  - Add context pre-loading in full path
  - Add Qwen3 pre-review template
  - Bump to v8.0

Modify: skills/backlog-implementer/CLAUDE.md
  - Update cost model
  - Document fast-path behavior
  - Update version

Modify: config/schema.json (if needed)
  - Add llmOps.routing.fastPathModel config key

No new files needed — this is a SKILL.md rewrite with new prompt templates.
```

## 6. Verification

1. Re-run AUDIT-BUG-20260220-003 with v8.0 → should classify as "simple", use fast path
2. Expected: 5-15 requests, $0.15-0.50 (vs 120 requests, $2.04)
3. Code quality: diff against v7.0 output and Opus baseline
4. Run a complex ticket to verify full path still works
5. Check Qwen3 classification accuracy on 5+ tickets
