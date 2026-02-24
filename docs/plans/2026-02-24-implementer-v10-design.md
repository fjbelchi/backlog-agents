# Implementer v10.0 Design

**Date:** 2026-02-24
**Status:** Approved
**Scope:** `skills/backlog-implementer/`, `scripts/implementer/`, `config/presets/`

## Problem

Implementer v9.0 still has three cost inefficiencies:

1. **Opus in Gate 4b** — selective frontier review adds $0.30-0.60 per complex ticket with high-risk patterns
2. **Opus as escalation ceiling** — ARCH/SEC tags and 2+ gate failures route to parent (Opus), adding unpredictable cost spikes
3. **Gate 1 uses LLM** — Ollama/Haiku generates a plan that could be produced deterministically from ticket metadata
4. **Gate 3 is a separate LLM gate** — Haiku receives entire files to parse lint errors; only the error lines + context are needed
5. **Fast path uses Sonnet** — trivial and simple tickets run a full Sonnet agent when Haiku suffices

## Goals

- Eliminate Opus entirely from the pipeline
- Reduce from 5 LLM gates to 3
- Replace 3 LLM steps with deterministic Python scripts
- Move fast path from Sonnet → Haiku (trivial) and Haiku+Sonnet-review (simple)
- Target savings: ~40-60% across all ticket types

## Architecture

### Pipeline: v9.0 → v10.0

**Before:**
```
Startup(script) → Classify(script) → WavePlan(script)
  → Gate 1 PLAN (Ollama/Haiku)
  → Gate 2 IMPL (Haiku)
  → Gate 3 LINT (Haiku — separate gate)
  → Gate 4 REVIEW (Sonnet)
  → Gate 4b FRONTIER (Opus — selective)
  → Commit(script) → WaveEnd(script)
```

**After:**
```
Startup(script) → Classify(script) → WavePlan(script)
  → Gate 1 PLAN (plan_generator.py — $0)
  → Gate 2 IMPL+LINT (Haiku + lint_fixer.py after each wave)
  → Gate 4 REVIEW (Sonnet + diff_pattern_scanner.py → high-risk-review.md if patterns)
  → Commit(script) → WaveEnd(script)
```

### Model Routing: v9.0 → v10.0

| Gate | v9.0 | v10.0 |
|------|------|-------|
| Gate 1 PLAN | Ollama/free | `plan_generator.py` — $0 |
| Gate 2 IMPL | Haiku | Haiku (unchanged) |
| Gate 3 LINT | Haiku (separate gate) | `lint_fixer.py` → Haiku only if errors |
| Gate 4 REVIEW | Sonnet | Sonnet (unchanged) |
| Gate 4b FRONTIER | **Opus** | **removed** → Gate 4 with `high-risk-review.md` |
| Escalation | **Parent/Opus** | Sonnet with strict prompt |
| Fast path trivial | Sonnet | **Haiku** |
| Fast path simple | Sonnet | **Haiku impl + Sonnet review** |

## The 3 New Scripts

### `scripts/implementer/plan_generator.py`

Replaces Gate 1 LLM call. Reads the ticket and produces a structured implementation plan deterministically.

**Input:** `--ticket <path>`

**Algorithm:**
1. Parse ticket YAML frontmatter + body
2. Extract `affected_files` table rows
3. Extract `acceptance_criteria` lines
4. Order files: `create` first → `modify` → `delete`
5. Generate plan bullets: `"- {action} {path}: {description}"`
6. Generate test bullets from acceptance criteria: `"- Test: {ac}"`

**Output:** `## Implementation Plan` markdown written to stdout

**Cost:** $0 — pure data transformation, no inference

---

### `scripts/implementer/lint_fixer.py`

Replaces Gate 3 as a separate LLM gate. Runs the linter and returns only the minimum context needed for Haiku to fix each error.

**Input:** `--root <path> --lint-cmd <cmd> --type-cmd <cmd>`

**Algorithm:**
1. Run `lintCommand` and `typeCheckCommand` (subprocess)
2. Parse output format (auto-detect: eslint JSON, ruff JSON, tsc `--noEmit`)
3. Group errors by `{file}:{line}`
4. For each error: extract ±5 lines of context from file
5. If 0 errors → `{"errors": [], "clean": true}` (no Haiku call)
6. If errors → `{"errors": [{file, line, rule, message, context}], "clean": false}`

**Output:** JSON to stdout. Parent passes ONLY this JSON to Haiku — not full files.

**Token savings:** ~70% reduction vs current Gate 3 (Haiku received entire files + all lint output)

---

### `scripts/implementer/diff_pattern_scanner.py`

Replaces LLM-based pattern detection for high-risk review activation. Scans git diff with regex.

**Input:** `--diff <path_to_diff_file>` or reads from stdin

**Patterns:**
```python
PATTERNS = {
    "auth":           r"jwt|bcrypt|session\.|\.token|oauth|password",
    "db_schema":      r"createIndex|migration|ALTER\s+TABLE|schema\.",
    "serialization":  r"JSON\.parse|JSON\.stringify|Buffer\.from|\.encode\(",
    "error_handling": r"Promise\.all|\.catch\(|retry\(|backoff",
    "external_api":   r"fetch\(|axios\.|http\.request|got\(",
    "concurrency":    r"worker_threads|Promise\.race|mutex|semaphore",
}
```

**Output:** `{"detected": ["auth", "db_schema"], "requires_high_risk_review": true}`

**Usage in Gate 4:**
```
result = diff_pattern_scanner.py
if result.requires_high_risk_review:
    Gate 4 uses high-risk-review.md template (Sonnet)
else:
    Gate 4 uses reviewer-prefix.md template (Sonnet, standard)
```

**Cost:** $0 — regex scan only

## New Template: `high-risk-review.md`

Sonnet-optimized 6-point review prompt for high-risk patterns. Replaces what Opus did in Gate 4b.

Activated when `diff_pattern_scanner.py` returns `requires_high_risk_review: true`.

**6-point checklist (loaded per detected pattern):**
1. **Type safety** — no `any` suppressions, no unchecked casts
2. **Error propagation** — all error paths handled, no silent swallows
3. **Production readiness** — no debug artifacts, secrets, TODOs in changed lines
4. **Semantic correctness** — logic matches the ticket's acceptance criteria exactly
5. **Resource management** — connections closed, streams ended, locks released
6. **Backward compatibility** — no breaking changes to public interfaces

Pattern-specific additional checks injected when pattern is detected:
- `auth` → verify token expiry, session invalidation, no secrets in logs
- `db_schema` → verify migration is reversible, indexes don't lock table
- `serialization` → verify input validation before parse, output escaping
- `concurrency` → verify no race conditions, proper lock ordering

## Fast Path Changes

### Trivial tickets → Haiku

`fast-path-agent.md` updated to use `model: "haiku"` for trivial complexity.
Haiku runs all 4 inline gates (PLAN via script output, IMPL, LINT via lint_fixer.py, REVIEW self-check).
No Gate 4b, no team overhead.

### Simple tickets → Haiku impl + Sonnet review

Two-step fast path:
1. Haiku agent: Gate 1 (script), Gate 2 IMPL+LINT, Gate 3 (lint_fixer.py)
2. Sonnet agent: Gate 4 REVIEW only (receives diff + test results)

## Escalation Changes

`config/presets/default.json`:
```json
"routing": {
  "escalationModel": "balanced"   // was "frontier" (Opus)
},
"frontierReview": {
  "enabled": false                 // pattern detection moved to diff_pattern_scanner.py
}
```

Escalation behavior (ARCH/SEC tags, 2+ gate failures):
- Was: route to "frontier" (Opus)
- Now: route to "balanced" (Sonnet) with strict escalation prompt loaded from `high-risk-review.md`

## Cost Model

| Type | Pipeline | v9.0 | v10.0 | Savings |
|------|----------|------|-------|---------|
| trivial | fast path Haiku | $0.08-0.20 | $0.03-0.08 | ~60% |
| simple | Haiku+Sonnet review | $0.20-0.40 | $0.10-0.20 | ~50% |
| complex | full path, no Opus | $1.20-2.50 | $0.70-1.50 | ~40% |

## Files Affected

| File | Change |
|------|--------|
| `skills/backlog-implementer/SKILL.md` | Gate 1→script, Gate 3→integrated into Gate 2, Gate 4b→removed, fast path routing, escalation, MODEL RULES update |
| `skills/backlog-implementer/CLAUDE.md` | Model routing table, cost model v10.0, scripts list |
| `skills/backlog-implementer/templates/fast-path-agent.md` | Haiku for trivial, Haiku+Sonnet for simple, remove Gate 4b ref |
| `skills/backlog-implementer/templates/high-risk-review.md` | NEW — Sonnet 6-point high-risk checklist |
| `config/presets/default.json` | `escalationModel: "balanced"`, `frontierReview.enabled: false` |
| `scripts/implementer/plan_generator.py` | NEW — deterministic plan from ticket |
| `scripts/implementer/lint_fixer.py` | NEW — lint error parser with minimal context |
| `scripts/implementer/diff_pattern_scanner.py` | NEW — regex pattern scanner for high-risk detection |
