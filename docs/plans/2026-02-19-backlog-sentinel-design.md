# Design: backlog-sentinel v1.0

**Date:** 2026-02-19
**Status:** Draft
**Scope:** New skill for the backlog-agents toolkit
**Based on:** sentinel-calidad v3.0 from mi-auditor, redesigned for efficiency

---

## Context

`sentinel-calidad` in `mi-auditor` is a proven autonomous code reviewer that monitors commits and creates backlog tickets. It works well but has two inefficiencies:

1. **Always-on daemon** — infinite loop, expensive, requires a dedicated terminal
2. **Hardcoded Opus for all reviewers** — no model tier routing, no stack-agnostic design

`backlog-sentinel` brings the same quality gates into the toolkit as a **one-shot skill** with deterministic pre-scanning, RAG context compression, and config-driven model routing.

**Estimated cost per commit:** ~$0.05–0.15 (vs ~$0.80–1.50 in mi-auditor v3 with Opus)

---

## Architecture Overview

```
Trigger: /backlog-toolkit:sentinel  OR  pre-push git hook
                      |
                      v
Phase 0: sentinel_prescan.py       ← deterministic, $0
  - git diff HEAD~1..HEAD
  - Run linter on changed files (qualityGates.lintCommand)
  - Run type checker (qualityGates.typeCheckCommand)
  - Run tests (qualityGates.testCommand)
  - grep: hardcoded secrets, TODO/FIXME, console.log in prod
  - awk: functions > sentinel.prescan.maxFunctionLines
  → JSON of deterministic findings
                      |
                      v
Phase 0.5: RAG lookups             ← deterministic, $0
  - Compress context: RAG snippets for changed files (~800t vs ~3k full files)
  - Retrieve relevant rules from codeRules.source via RAG
  - Pre-check duplicates against existing backlog tickets
                      |
                      v
Phase 1: LLM reviewer team (parallel)
  TeamCreate("sentinel-{hash7}")
  ├── security-reviewer (security-engineer)
  │     receives: diff + RAG security snippets + security rules
  │     analyzes: auth bypass, injection, insecure data flows
  │     model: balanced → frontier if finding > Medium
  └── quality-reviewer (code-quality)
        receives: diff + RAG snippets + architecture rules
        analyzes: race conditions, null bugs, arch violations, perf patterns
        model: cheap → balanced for bugs/arch
                      |
                      v
Phase 2: Per finding → backlog-ticket integration
  For each finding (prescan + reviewers):
    1. RAG duplicate check (similarity > 0.85 → skip)
    2. Map to ticket type (SEC/BUG/TASK)
    3. Auto-tag ARCH/SECURITY for model escalation
    4. Invoke backlog-ticket logic → validated ticket with ID + cost estimate
                      |
                      v
Phase 3: Summary report + usage ledger
```

---

## Phase 0: Deterministic Pre-Scan (`sentinel_prescan.py`)

Runs before any LLM is called. Covers ~30–50% of typical findings at $0.

```python
# Returns JSON: {"findings": [...], "changed_files": [...], "test_results": {...}}

checks = {
    "lint":        run(config.qualityGates.lintCommand, changed_files_only=True),
    "typecheck":   run(config.qualityGates.typeCheckCommand, changed_files_only=True),
    "tests":       run(config.qualityGates.testCommand),
    "hardcoded":   grep(r'(password|api_key|secret|token)\s*=\s*["\'][^"\']+["\']'),
    "todos":       grep(r'TODO|FIXME|HACK|XXX'),
    "console_log": grep(r'console\.log|print\(', exclude=["test", "spec"]),
    "long_funcs":  awk_function_length(threshold=config.sentinel.prescan.maxFunctionLines),
    "n_plus_one":  grep(r'for.*\n.*\.(find|where|query)\(', multiline=True),
}
```

Each prescan finding becomes a directly-actionable ticket description — no LLM needed to interpret lint output or test failures.

---

## Phase 0.5: RAG Integration

Three RAG queries before spawning any LLM agent:

### 1. Context Compression
```python
for file in changed_files:
    snippets = rag.search(f"implementation patterns in {file}", n=config.llmOps.ragPolicy.topK)
    # Reviewers receive snippets (~800t) not full files (~3000t)
```

### 2. Architecture Rules Retrieval
```python
relevant_rules = rag.search(
    f"architecture and coding rules for {', '.join(changed_files)}",
    n=5
)
# Only applicable rules sent to reviewers, not the full codeRules.source
```

### 3. Duplicate Pre-Check
```python
for finding in prescan_findings:
    results = rag.search(finding["description"], n=3)
    if results[0].similarity > 0.85:
        finding["status"] = "duplicate_skipped"
        finding["duplicate_of"] = results[0].ticket_id
```

RAG must index both source code and existing backlog tickets (`backlog/data/pending/*.md`).

---

## Phase 1: LLM Reviewer Team

### `security-reviewer` (security-engineer agent)

**Model:** `balanced` → escalates to `frontier` if finding.severity > Medium
**Receives:** git diff + RAG security snippets + prescan results (to avoid overlap)
**Analyzes:**
- Auth bypass and privilege escalation requiring code flow understanding
- Injection vulnerabilities not caught by static patterns
- Insecure cryptographic choices
- Data exposure through logic errors

**Does NOT analyze:** hardcoded secrets, missing .env entries (prescan handles these)

**Output format:**
```json
{
  "findings": [
    {
      "category": "security",
      "severity": "high",
      "file": "src/auth/login.ts",
      "line": 42,
      "description": "JWT token not validated before use — attacker can forge claims",
      "current_code": "const user = jwt.decode(token)",
      "suggested_fix": "const user = jwt.verify(token, process.env.JWT_SECRET)"
    }
  ]
}
```

### `quality-reviewer` (code-quality agent)

**Model:** `cheap` (Haiku) → `balanced` (Sonnet) if finding involves logic/arch
**Receives:** git diff + RAG code snippets + architecture rules from codeRules
**Analyzes:**
- Race conditions and async bugs requiring context understanding
- Null/undefined edge cases in complex flows
- Architecture violations (patterns defined in codeRules.source)
- Performance anti-patterns requiring data shape awareness (N+1 in complex ORMs)

**Does NOT analyze:** function length, cyclomatic complexity, unused imports (prescan/linter)

---

## Phase 2: Ticket Creation

Each finding (prescan + reviewers) flows through:

```
1. RAG duplicate check → skip if similarity > 0.85

2. Map category to ticket type:
   security          → SEC-*
   bug / logic error → BUG-*
   hardcoded value   → TASK-*
   arch violation    → TASK-* + tag: ARCH
   tech debt/todo    → TASK-*
   test failure      → BUG-*

3. Auto-tag for model escalation:
   auth/crypto/injection keywords → tags: [SECURITY]
   refactor/migrate/arch keywords → tags: [ARCH]

4. Invoke backlog-ticket logic:
   - description: "{finding.description} found in {file}:{line}"
   - affected_files: pre-filled from diff
   - context: "Found in commit {hash} ({author}, {date}) by backlog-sentinel"
   - batchEligible: true
   - found_by: "backlog-sentinel-v1"
   - Runs 6-check validation, assigns ID, estimates cost

5. Append to usage-ledger.jsonl:
   {ticket_id, gate: "sentinel", model, tokens, cost, date}
```

---

## Phase 3: Summary

```
sentinel complete — commit a3f9c12 (author, 2026-02-19)
─────────────────────────────────────────────────────
prescan (deterministic, $0):
  lint errors:    2  → BUG-018, BUG-019
  test failures:  1  → BUG-020
  hardcoded:      1  → TASK-034
  todos:          0

reviewers (LLM):
  security:       1  → SEC-007
  quality:        2  → BUG-021, TASK-035

skipped:          1  duplicate (similar to TASK-029)
─────────────────────────────────────────────────────
tickets created:  6
cost:             $0.09
```

---

## Trigger Modes

### On-demand
```bash
/backlog-toolkit:sentinel          # analyze HEAD, batch ticket creation
/backlog-toolkit:sentinel --now    # force synchronous ticket creation
```

### Git hook (auto-installed by `backlog-init`)
```bash
# .git/hooks/pre-push
#!/bin/bash
claude --skip-permissions -p "/backlog-toolkit:sentinel"
```
Installed when `sentinel.installGitHook: true` in config (default: true).

---

## Configuration

New `sentinel` section added to `backlog.config.json` by `backlog-init`:

```json
{
  "sentinel": {
    "enabled": true,
    "installGitHook": true,
    "prescan": {
      "runLinter": true,
      "runTests": true,
      "runTypeCheck": true,
      "detectHardcoded": true,
      "detectTodos": true,
      "maxFunctionLines": 80
    },
    "reviewers": {
      "security": true,
      "quality": true
    },
    "ragDeduplication": true,
    "ticketMapping": {
      "security": "SEC",
      "bug": "BUG",
      "techDebt": "TASK",
      "architecture": "TASK"
    }
  }
}
```

Model routing inherited from `llmOps.routing` — no duplication.

---

## Files to Create

```
skills/backlog-sentinel/SKILL.md       ← skill definition
skills/backlog-sentinel/CLAUDE.md      ← context doc
commands/sentinel.md                   ← /backlog-toolkit:sentinel command
scripts/ops/sentinel_prescan.py        ← deterministic pre-scan script
```

**Files to modify:**
```
skills/backlog-init/SKILL.md           ← add sentinel config + git hook install step
config/presets/default.json            ← add sentinel section defaults
config/backlog.config.schema.json      ← add sentinel schema
```

---

## Key Improvements vs mi-auditor sentinel-calidad v3

| Aspect | mi-auditor v3 | backlog-sentinel v1 |
|--------|--------------|---------------------|
| Mode | Daemon (infinite loop) | One-shot (on-demand + git hook) |
| Model | Hardcoded Opus everywhere | Config-driven tier routing |
| Context | Full files passed to LLM | RAG snippets (~75% fewer input tokens) |
| Stack | NestJS/TypeScript specific | Stack-agnostic (rules from codeRules.source) |
| Prescan | None (all LLM) | Deterministic: lint + tests + grep |
| Ticket creation | Custom REVIEW-* format | Via backlog-ticket skill (validated, ID, cost) |
| Deduplication | LLM-based | RAG similarity (deterministic, $0) |
| Cost estimate | ~$0.80–1.50/commit | ~$0.05–0.15/commit |

---

## Continuous Learning Layer

Without a learning mechanism, the sentinel detects the same errors indefinitely. This layer closes the feedback loop so future implementations avoid known patterns.

```
Sentinel detects error → creates ticket
Implementer fixes it  → commit
        ↑                      ↓
Next implementations     Sentinel records pattern
avoid the pattern   ←    occurrences >= N threshold
(codeRules updated)  ←   → auto-update codeRules
```

### Layer 1 — Pattern Ledger (`.backlog-ops/sentinel-patterns.json`)

Updated by the sentinel at the end of every Phase 3:

```json
{
  "version": "1.0",
  "patterns": [
    {
      "id": "jwt-not-validated",
      "description": "JWT decoded without signature verification",
      "category": "security",
      "occurrences": 4,
      "files": ["src/auth/login.ts", "src/api/middleware.ts"],
      "first_seen": "2026-02-10",
      "last_seen": "2026-02-19",
      "status": "recurring",
      "escalated_to_rules": false
    }
  ],
  "thresholds": {
    "recurring": 2,
    "escalate_to_soft_gate": 3,
    "escalate_to_hard_gate": 5
  }
}
```

The sentinel matches each new finding against existing patterns using RAG similarity. On match: increments `occurrences`. On miss: creates new entry.

### Layer 2 — Auto-Update `codeRules.source`

When `occurrences >= thresholds.escalate_to_soft_gate`, the sentinel proposes adding the pattern as a gate:

```markdown
## Soft Gates  (auto-added by sentinel — review before accepting)
- [ ] JWT tokens MUST use `jwt.verify()`, never `jwt.decode()` alone
      [sentinel: 4 occurrences across 2 files — last seen 2026-02-19]
- [ ] Never call ORM queries inside forEach/map (N+1 pattern)
      [sentinel: 3 occurrences — last seen 2026-02-18]
```

**In git hook mode:** proposes the diff and asks for confirmation before push.
**In on-demand mode:** applies directly with an `[auto-added]` marker.

When `occurrences >= thresholds.escalate_to_hard_gate`: promoted to `hardGates` — blocks commit if violated. The implementer's Gate 3 (LINT) enforces hard gates.

### Layer 3 — RAG as Implementer Memory

The RAG server indexes completed sentinel tickets alongside source code. Before Gate 2 (IMPLEMENT), the implementer queries:

```python
warnings = rag.search(
    query=f"recurring errors in {', '.join(affected_files)}",
    filter={"found_by": "backlog-sentinel"},
    n=3
)
```

The implementer's prompt receives a **Recurring Patterns** block before writing any code:

```
RECURRING PATTERNS (from sentinel history) — avoid these:
- jwt-not-validated (4× in src/auth/) — always use jwt.verify()
- n-plus-one-query (3× in src/services/) — batch queries outside loops
```

This costs ~$0 (RAG lookup) and eliminates the most common error categories before the LLM writes a single line.

### Learning Loop Summary

```
sentinel_prescan.py
  + reviewer findings
        ↓
Update sentinel-patterns.json       ← every commit, $0
        ↓
occurrences >= 3?
  YES → propose codeRules update    ← human confirms or auto-applies
        ↓
codeRules.source updated
        ↓
backlog-implementer reads codeRules ← Gate 1 PLAN injection
  + RAG sentinel memory query       ← Gate 2 IMPLEMENT injection
        ↓
Implementer avoids known patterns → fewer bugs → fewer sentinel tickets
→ lower cost per session over time
```

The learning is cumulative. Projects that use the sentinel for 2–4 weeks converge toward a hardened `codeRules.source` that encodes the team's actual failure modes — not generic best practices.

### New Files for Learning Layer

```
scripts/ops/sentinel_patterns.py    ← pattern matching + ledger update
.backlog-ops/sentinel-patterns.json ← pattern ledger (gitignored or committed)
```

The `sentinel_prescan.py` script calls `sentinel_patterns.py` at the end of Phase 3.

---

## Cost Model

Per typical commit (3–5 files changed):

```
Phase 0 prescan:        $0.00  (grep, lint, tests)
Phase 0.5 RAG:          $0.00  (vector search + duplicate check)
security-reviewer:      ~$0.04 (Sonnet, ~800t in + ~400t out)
quality-reviewer:       ~$0.02 (Haiku, ~600t in + ~300t out)
ticket creation (×5):   ~$0.03 (Haiku for validation)
pattern ledger update:  $0.00  (deterministic)
─────────────────────────────────────────────
Total per commit:       ~$0.09

Over time (learning effect):
  Week 1:  ~$0.09/commit  (baseline)
  Week 4:  ~$0.05/commit  (recurring patterns caught by prescan/codeRules)
  Week 8:  ~$0.03/commit  (hardened codeRules, few surprises for LLM)
```
