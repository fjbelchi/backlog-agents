# Backlog Audit — Full Project Health Audit with Tiered Model Funnel

**Date:** 2026-02-20
**Status:** Approved

## Goal

On-demand full-project health audit (`/backlog-toolkit:audit`) that scans the entire codebase across 6 dimensions, using a tiered model funnel to keep costs 85-90% lower than all-Opus.

## Cost Target

$0.95-2.50 per audit (50-file project) vs $10-15 all-Opus.

## Architecture

5-phase pipeline where each phase filters for the next:

```
Phase 0  ($0.00) → Deterministic prescan (12 checks, ~70-80% of findings)
Phase 1  ($0.05) → Haiku sweep (all modules, semantic analysis)
Phase 2  ($0.30) → Sonnet deep analysis (medium+ severity only)
Phase 3  ($0.50) → Opus critical review (critical/security only)
Phase 3.5 ($0.00) → RAG deduplication (skip existing tickets)
Phase 4  ($0.10) → Ticket creation via backlog-ticket
```

## Dimensions

1. **Architecture & tech debt** — God classes, coupling, SOLID violations, missing abstractions
2. **Security & secrets** — Injection, auth bypass, data exposure, unsafe crypto
3. **Bugs & deficiencies** — Null dereferences, race conditions, wrong assumptions, mock data
4. **Performance & scalability** — N+1 queries, missing caching, unoptimized loops, memory leaks
5. **Test health** — Coverage gaps, mocks hiding bugs, missing edge cases, untested error paths
6. **Code hygiene** — TODOs, FIXMEs, debug leftovers, hardcoded values, dead code, type safety gaps

## Phase 0: Deterministic Prescan ($0)

**Script:** `scripts/ops/audit_prescan.py`

12 checks, all deterministic:

| # | Check | Method |
|---|-------|--------|
| 1 | Secrets detection | Regex (password=, api_key=, token=) |
| 2 | TODOs/FIXMEs | Grep TODO\|FIXME\|HACK\|XXX |
| 3 | Debug leftovers | Grep console.log\|print(\|debugger |
| 4 | Mock/hardcoded data | Regex (mock, fake, stub, hardcoded IPs/URLs/ports) |
| 5 | Long functions | Line counting per function |
| 6 | Dependency vulns | npm audit --json / pip audit |
| 7 | Test coverage gaps | Parse istanbul/pytest-cov report |
| 8 | Dead code | Unused imports, unreferenced exports |
| 9 | Cyclomatic complexity | AST parsing, flag >10 |
| 10 | Duplicate code blocks | Token-based comparison |
| 11 | File size / circular deps | Import graph analysis |
| 12 | Type safety gaps | Grep `any`, `as T`, `!.` patterns |

**Output:** JSON with findings array, each with severity, dimension, file, line, description.

**Config:**
```json
"audit": {
  "prescan": {
    "extensions": [".ts", ".tsx", ".js", ".py"],
    "excludeDirs": ["node_modules", "dist", "coverage", ".next"],
    "maxFunctionLines": 80,
    "coverageThreshold": 70,
    "complexityThreshold": 10
  }
}
```

## Phase 1: Haiku Sweep (~$0.05-0.15)

Break project into module chunks by directory. Each chunk gets ONE Haiku call covering all 6 dimensions.

**Input per chunk:** code files + Phase 0 findings for that module + RAG context.

**Haiku scans for:** architecture smells, threading/async bugs, wrong assumptions, logic errors, security patterns, test quality issues — things grep can't catch.

**Output per finding:** severity, dimension, file, line, description, `needs_deep_review` boolean.

**Key:** `needs_deep_review: true` only for findings Haiku is NOT confident about. This gates Phase 2.

All chunks run in **parallel** via Task tool with `model: "haiku"`.

## Phase 2: Sonnet Deep Analysis (~$0.20-0.80)

Only findings with `needs_deep_review: true` OR severity `high+` from Phase 1.

**Sonnet validates or rejects** each Haiku finding (false-positive filter). For valid findings: root cause, fix recommendation, affected files, confidence score 0-100.

**Gates Opus:** only `needs_opus: true` findings proceed to Phase 3.

**Groups related findings** — if 3 Haiku findings share a root cause, Sonnet merges them into 1 ticket.

Each flagged area reviewed independently via Task with `model: "sonnet"`.

Expected: ~40-60% of Haiku flags survive Sonnet validation.

## Phase 3: Opus Critical Review (~$0.15-0.50)

Triggers: `needs_opus: true` from Sonnet, OR HIGH_RISK_PATTERNS match (serialization, db_schema, auth, error_handling, external_api, concurrency), OR severity `critical` / ticket type `SEC`.

**6-point checklist (same as Gate 4b):**
- TYPE SAFETY: Do types survive serialization round-trips?
- ERROR PROPAGATION: Does error handling cover all failure modes?
- PRODUCTION READINESS: Are migrations/rollback plans needed?
- SEMANTIC CORRECTNESS: Are field names accurate? Dead fields?
- RESOURCE MANAGEMENT: Connections/handles properly cleaned up?
- BACKWARD COMPATIBILITY: Does this break existing consumers?

Expected: 2-5 findings per audit.

## Phase 3.5: RAG Deduplication ($0)

Before ticket creation, check RAG for existing tickets:
- Similarity > 0.85 → SKIP (duplicate)
- Similarity 0.60-0.85 → Flag as "possibly related to TICKET-ID"
- Similarity < 0.60 → New finding, create ticket

Prevents re-auditing from generating duplicates.

## Phase 4: Ticket Creation + Report

All validated findings → backlog tickets via `backlog-ticket` skill.

**Ticket prefix:** `AUDIT-{DIMENSION}-{DATE}-{SEQ}` (e.g., `AUDIT-SEC-20260220-001`)

Each ticket includes: finding, root cause, fix, affected files, detection phase, cost estimate.

**Console summary:**
```
═══════════════════════════════════════════════════
  PROJECT AUDIT: {project} | {date}
═══════════════════════════════════════════════════
  Scanned: N files | 12 deterministic checks
  Findings by phase:
    Phase 0 (prescan):  NN ($0.00)
    Phase 1 (Haiku):    NN ($X.XX)
    Phase 2 (Sonnet):   NN ($X.XX)
    Phase 3 (Opus):     NN ($X.XX)
  Duplicates skipped: NN
  Total: NN findings → NN tickets created
  Cost: $X.XX
═══════════════════════════════════════════════════
```

## Integration Points

- **RAG:** Phase 0.5 queries RAG for architecture rules and past findings. Phase 3.5 deduplicates. Phase 4 indexes new tickets.
- **Sentinel:** Shares `sentinel_prescan.py` patterns. Audit prescan extends them to full-project scope.
- **Implementer:** Audit tickets feed directly into implementation waves.
- **Config:** `audit` section in `backlog.config.json` controls all thresholds and enabled checks.
