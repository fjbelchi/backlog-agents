# Backlog Benchmark Skill — Design

**Goal:** Reusable skill for benchmarking skill cost/quality, monitoring LiteLLM spend, and optimizing toolkit processes. Uses Opus as quality baseline reference.

**Architecture:** Three modes — `run` (benchmark puntual with Opus baseline + quality comparison), `report` (cost dashboard from LiteLLM Postgres), `compare` (diff two benchmark runs). Capture via manual markers (`start`/`stop`) and LiteLLM tag filtering.

**Motivation:** Manual benchmark of implementer v7.0 vs Opus on ticket AUDIT-BUG-20260220-003 revealed 6.8x cost difference ($2.04 vs $0.30) with equivalent quality. This process was ad-hoc (custom monitor.sh, manual Postgres queries, manual diff). A skill automates it for iterative optimization.

---

## 1. Skill Modes

### 1a. `benchmark run <ticket-id> [--variant <name>]`

Benchmarks a ticket implementation against Opus baseline.

```
Phase 1: CAPTURE BASELINE
  - Query LiteLLM Postgres: SUM(spend), COUNT(*), SUM(prompt_tokens), SUM(completion_tokens)
  - Save to .backlog-ops/benchmarks/{run-id}/start.json
  - {run-id} = {ticket-id}-{YYYYMMDD-HHmm}[-{variant}]

Phase 2: OPUS REFERENCE (quality baseline)
  - Spawn 1 Opus agent via Task tool:
    - Reads ticket, implements fix, writes tests
    - Solution saved to .backlog-ops/benchmarks/{run-id}/opus-baseline/
  - Capture post-Opus LiteLLM snapshot
  - Calculate Opus cost delta

Phase 3: AWAIT SKILL EXECUTION
  - Print: "Opus baseline captured ($X.XX). Now run the skill under test."
  - Print: "When done, run: /backlog-toolkit:benchmark stop {run-id}"
  - The user runs the skill in another session (or same session)
  - All LiteLLM requests auto-tagged via TicketTagger callback

Phase 4: STOP & MEASURE
  - Triggered by /benchmark stop {run-id}
  - Capture final LiteLLM snapshot
  - Calculate skill deltas (total, per-model breakdown)
  - Query per-model breakdown from Postgres:
    SELECT model, COUNT(*), ROUND(SUM(spend)::numeric, 6),
           SUM(prompt_tokens), SUM(completion_tokens)
    FROM "LiteLLM_SpendLogs"
    WHERE row_number > {baseline_row_count}
    GROUP BY model ORDER BY SUM(spend) DESC;

Phase 5: QUALITY COMPARISON
  - Find skill output files (modified since benchmark start)
  - Diff against Opus baseline
  - Automated checks:
    - Tests pass? (run testCommand)
    - Lint clean? (run lintCommand)
    - ACs covered? (parse ticket acceptance criteria)
  - Sonnet evaluator: structured comparison
    Input: Opus code + skill code + ticket ACs
    Output: quality rubric scores (0-100 per dimension)

Phase 6: GENERATE REPORT
  - Write .backlog-ops/benchmarks/{run-id}/report.md
  - Content: cost table, model mix, quality scores, recommendation
```

### 1b. `benchmark report [--days N]`

Cost dashboard from LiteLLM logs.

```
Phase 1: QUERY LITELLM POSTGRES
  Queries (via docker exec backlog-postgres psql):

  a) Spend by model (last N days):
     SELECT model, COUNT(*), SUM(spend), SUM(prompt_tokens), SUM(completion_tokens)
     FROM "LiteLLM_SpendLogs"
     WHERE "startTime" > NOW() - INTERVAL '{N} days'
     GROUP BY model ORDER BY SUM(spend) DESC;

  b) Spend by day:
     SELECT DATE("startTime"), SUM(spend), COUNT(*)
     FROM "LiteLLM_SpendLogs"
     WHERE "startTime" > NOW() - INTERVAL '{N} days'
     GROUP BY DATE("startTime") ORDER BY DATE("startTime");

  c) Top 10 most expensive requests:
     SELECT model, spend, prompt_tokens, completion_tokens, "startTime"
     FROM "LiteLLM_SpendLogs"
     WHERE "startTime" > NOW() - INTERVAL '{N} days'
     ORDER BY spend DESC LIMIT 10;

  d) Zero-cost anomalies (pricing bugs):
     SELECT model, COUNT(*), SUM(prompt_tokens)
     FROM "LiteLLM_SpendLogs"
     WHERE spend = 0 AND prompt_tokens > 1000
       AND "startTime" > NOW() - INTERVAL '{N} days'
     GROUP BY model;

Phase 2: GENERATE REPORT
  Write .backlog-ops/cost-report-{date}.md with:
  - Total spend and request count
  - Per-model breakdown table
  - Daily trend table
  - Top expensive requests
  - Zero-cost anomaly warnings
  - Cache efficiency (if usage-ledger data available)
  - Comparison with previous period (if prior report exists)
```

### 1c. `benchmark compare <run-a> <run-b>`

Diff two benchmark runs side by side.

```
Phase 1: READ REPORTS
  - Load .backlog-ops/benchmarks/{run-a}/report.md
  - Load .backlog-ops/benchmarks/{run-b}/report.md

Phase 2: GENERATE COMPARISON
  - Side-by-side cost table
  - Quality score delta
  - Model mix comparison
  - Recommendation: which variant is better (cost-adjusted quality)
  - Write .backlog-ops/benchmarks/compare-{a}-vs-{b}.md
```

## 2. Data Capture

### Manual Markers

```
/backlog-toolkit:benchmark start [name]
  → Captures LiteLLM snapshot to .backlog-ops/benchmarks/{name}/start.json
  → Format: {"timestamp", "total_spend", "total_requests", "total_prompt", "total_completion"}

/backlog-toolkit:benchmark stop [name]
  → Captures end snapshot to .backlog-ops/benchmarks/{name}/stop.json
  → Calculates deltas, per-model breakdown
  → Triggers report generation
```

### Tag-Based (via TicketTagger callback)

When the TicketTagger callback is active in LiteLLM, requests are tagged with `ticket_id`. The benchmark skill can filter by tag:

```sql
SELECT model, SUM(spend), COUNT(*)
FROM "LiteLLM_SpendLogs"
WHERE metadata::jsonb->>'ticket_id' = '{ticket_id}'
GROUP BY model;
```

This isolates costs per ticket without needing manual markers.

## 3. Quality Evaluation

Opus output serves as the quality reference. The Sonnet evaluator uses this rubric:

```
DIMENSIONS (0-100 each):
  1. Correctness: Does the code fix the issue described in the ticket?
  2. Test coverage: Are all ACs covered by tests? Edge cases?
  3. Code style: Consistent with codebase patterns? Clean?
  4. Completeness: Nothing missing vs the ticket requirements?
  5. No regressions: Does the fix introduce new issues?

SCORING:
  >= 90: Excellent (matches or exceeds Opus quality)
  70-89: Good (minor differences, production-ready)
  50-69: Acceptable (works but has gaps)
  < 50: Needs improvement
```

## 4. Model Rules

```
Haiku  → Postgres queries, report formatting, checklist evaluation
Sonnet → Quality comparison evaluator (1 call per benchmark)
Opus   → Baseline reference implementation (1 agent per benchmark run)

Cost per operation:
  benchmark run:     $0.20-0.60 (Opus baseline + Sonnet eval + Haiku report)
  benchmark report:  $0.01-0.03 (Haiku only, mostly SQL)
  benchmark compare: $0.01      (Haiku formatting)
```

## 5. Files

```
Create: skills/backlog-benchmark/SKILL.md      — Skill prompt with 3 modes
Create: skills/backlog-benchmark/CLAUDE.md      — Skill documentation
Create: commands/benchmark.md                   — Command definition
Modify: .claude-plugin/plugin.json              — Register command
Create: scripts/ops/benchmark_capture.sh        — LiteLLM snapshot helper

Output directory: .backlog-ops/benchmarks/
  {run-id}/
    start.json        — Baseline snapshot
    stop.json         — Final snapshot
    opus-baseline/    — Opus reference files
    report.md         — Full benchmark report
  cost-report-{date}.md — Dashboard reports
  compare-{a}-vs-{b}.md — Comparison reports
```

## 6. Verification

1. Run `benchmark run` on AUDIT-BUG-20260220-003 → should produce same data as manual benchmark
2. Run `benchmark report --days 3` → should show model breakdown matching Postgres
3. Run `benchmark compare` on two runs → should produce side-by-side comparison
4. Verify zero-cost anomaly detection catches the Sonnet $0 pricing bug we found
