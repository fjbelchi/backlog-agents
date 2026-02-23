# Backlog Benchmark Skill — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a reusable benchmark skill with 3 modes: run (Opus baseline + quality comparison), report (LiteLLM cost dashboard), compare (diff two runs).

**Architecture:** New skill at `skills/backlog-benchmark/`, command at `commands/benchmark.md`, helper script at `scripts/ops/benchmark_capture.sh`. Queries LiteLLM Postgres directly for spend data.

**Tech Stack:** Markdown/prompt (SKILL.md), Bash (benchmark_capture.sh), SQL (Postgres queries)

**Design doc:** `docs/plans/2026-02-23-backlog-benchmark-design.md`

---

### Task 1: Create benchmark_capture.sh helper script

**Files:**
- Create: `scripts/ops/benchmark_capture.sh`

**Step 1: Write the script**

```bash
#!/usr/bin/env bash
# benchmark_capture.sh — Capture LiteLLM spend snapshot from Postgres
# Used by backlog-benchmark skill to measure cost deltas.
#
# Usage:
#   ./benchmark_capture.sh snapshot           → JSON snapshot to stdout
#   ./benchmark_capture.sh breakdown <row_offset> → Per-model breakdown since row_offset
#   ./benchmark_capture.sh top-expensive <N> <days> → Top N expensive requests
#   ./benchmark_capture.sh zero-cost <days>   → Zero-cost anomalies
#
# Environment:
#   POSTGRES_CONTAINER (default: backlog-postgres)
#   POSTGRES_USER      (default: litellm)
#   POSTGRES_DB        (default: litellm)

set -euo pipefail

CONTAINER="${POSTGRES_CONTAINER:-backlog-postgres}"
USER="${POSTGRES_USER:-litellm}"
DB="${POSTGRES_DB:-litellm}"

psql_query() {
  docker exec "$CONTAINER" psql -U "$USER" -d "$DB" -t -A -c "$1" 2>/dev/null
}

case "${1:-snapshot}" in
  snapshot)
    ROW=$(psql_query "
      SELECT json_build_object(
        'timestamp', NOW(),
        'total_spend', ROUND(SUM(spend)::numeric, 6),
        'total_requests', COUNT(*),
        'total_prompt', SUM(prompt_tokens),
        'total_completion', SUM(completion_tokens),
        'row_count', COUNT(*)
      ) FROM \"LiteLLM_SpendLogs\";")
    echo "$ROW"
    ;;
  breakdown)
    OFFSET="${2:-0}"
    psql_query "
      WITH numbered AS (
        SELECT *, ROW_NUMBER() OVER (ORDER BY \"startTime\") as rn
        FROM \"LiteLLM_SpendLogs\"
      )
      SELECT json_agg(row_to_json(t)) FROM (
        SELECT model, COUNT(*) as requests,
          ROUND(SUM(spend)::numeric, 6) as spend,
          SUM(prompt_tokens) as prompt_tokens,
          SUM(completion_tokens) as completion_tokens
        FROM numbered WHERE rn > $OFFSET
        GROUP BY model ORDER BY SUM(spend) DESC
      ) t;"
    ;;
  top-expensive)
    N="${2:-10}"; DAYS="${3:-7}"
    psql_query "
      SELECT json_agg(row_to_json(t)) FROM (
        SELECT model, ROUND(spend::numeric, 6) as spend,
          prompt_tokens, completion_tokens,
          to_char(\"startTime\", 'YYYY-MM-DD HH24:MI') as time
        FROM \"LiteLLM_SpendLogs\"
        WHERE \"startTime\" > NOW() - INTERVAL '${DAYS} days'
        ORDER BY spend DESC LIMIT $N
      ) t;"
    ;;
  zero-cost)
    DAYS="${2:-7}"
    psql_query "
      SELECT json_agg(row_to_json(t)) FROM (
        SELECT model, COUNT(*) as count, SUM(prompt_tokens) as prompt_tokens
        FROM \"LiteLLM_SpendLogs\"
        WHERE spend = 0 AND prompt_tokens > 1000
          AND \"startTime\" > NOW() - INTERVAL '${DAYS} days'
        GROUP BY model
      ) t;"
    ;;
  daily)
    DAYS="${2:-7}"
    psql_query "
      SELECT json_agg(row_to_json(t)) FROM (
        SELECT DATE(\"startTime\") as date,
          ROUND(SUM(spend)::numeric, 4) as spend,
          COUNT(*) as requests
        FROM \"LiteLLM_SpendLogs\"
        WHERE \"startTime\" > NOW() - INTERVAL '${DAYS} days'
        GROUP BY DATE(\"startTime\")
        ORDER BY DATE(\"startTime\")
      ) t;"
    ;;
  *)
    echo "Usage: $0 {snapshot|breakdown <offset>|top-expensive <N> <days>|zero-cost <days>|daily <days>}" >&2
    exit 1
    ;;
esac
```

**Step 2: Make executable and commit**

```bash
chmod +x scripts/ops/benchmark_capture.sh
git add scripts/ops/benchmark_capture.sh
git commit -m "feat(benchmark): add benchmark_capture.sh for LiteLLM Postgres queries"
```

---

### Task 2: Create command file

**Files:**
- Create: `commands/benchmark.md`

**Step 1: Write the command definition**

```markdown
# Command: /backlog-toolkit:benchmark

Benchmark skill cost and quality against Opus baseline. Monitor LiteLLM spend.

## Syntax

```
/backlog-toolkit:benchmark run <ticket-id>       — Benchmark a ticket (Opus baseline + skill comparison)
/backlog-toolkit:benchmark start [name]           — Mark benchmark start (capture LiteLLM snapshot)
/backlog-toolkit:benchmark stop [name]            — Mark benchmark stop (capture + generate report)
/backlog-toolkit:benchmark report [--days N]      — Cost dashboard from LiteLLM logs (default: 7 days)
/backlog-toolkit:benchmark compare <run-a> <run-b> — Compare two benchmark runs
```

## Examples

### Full benchmark with Opus baseline
```
/backlog-toolkit:benchmark run BUG-20260220-003
```

### Manual markers (when skill runs in another session)
```
/backlog-toolkit:benchmark start my-test
# ... run skill in another session ...
/backlog-toolkit:benchmark stop my-test
```

### Cost dashboard
```
/backlog-toolkit:benchmark report --days 3
```

## Output

Reports written to `.backlog-ops/benchmarks/` with cost tables, model breakdowns,
quality scores, and recommendations.

## Related

- Skill: `skills/backlog-benchmark/SKILL.md`
- Design: `docs/plans/2026-02-23-backlog-benchmark-design.md`
```

**Step 2: Commit**

```bash
git add commands/benchmark.md
git commit -m "feat(benchmark): add benchmark command definition"
```

---

### Task 3: Register command in plugin.json

**Files:**
- Modify: `.claude-plugin/plugin.json`

**Step 1: Add benchmark command to commands array**

Add `"./commands/benchmark.md"` to the commands list (after audit.md).

**Step 2: Commit**

```bash
git add .claude-plugin/plugin.json
git commit -m "feat(benchmark): register benchmark command in plugin.json"
```

---

### Task 4: Create SKILL.md — frontmatter + model rules + report mode

**Files:**
- Create: `skills/backlog-benchmark/SKILL.md`

**Step 1: Write the first half of the skill (frontmatter through `report` mode)**

```markdown
---
name: backlog-benchmark
description: "Benchmark skill cost/quality against Opus baseline. Monitor LiteLLM spend, generate cost dashboards, compare runs. 3 modes: run, report, compare. v1.0."
allowed-tools: Read, Glob, Grep, Bash, Write, Task
---

# Backlog Benchmark v1.0 — Cost & Quality Benchmarking

## Role
**Analyst**: Captures LiteLLM spend data, manages Opus baselines, evaluates quality, generates reports. Does NOT implement code.

## MODEL RULES FOR TASK TOOL

```
model: "haiku"   → Report generation, checklist evaluation, formatting
model: "sonnet"  → Quality comparison evaluator (1 call per benchmark)
model: "opus"    → Baseline reference implementation (1 agent per `run`)

BUDGET: Max 5 LLM calls per benchmark operation.
```

## MODES

Parse the user's command to determine mode:
- Contains "run" + ticket ID → RUN mode
- Contains "start" → START marker mode
- Contains "stop" → STOP marker mode
- Contains "report" → REPORT mode
- Contains "compare" + two IDs → COMPARE mode

---

## Mode: REPORT (cost dashboard)

### Phase 1: Query LiteLLM

Extract --days N from args (default: 7). Run queries via helper script:

```bash
SCRIPT="${CLAUDE_PLUGIN_ROOT}/scripts/ops/benchmark_capture.sh"

# Get all data
BREAKDOWN=$(bash "$SCRIPT" breakdown 0)  # Not useful for report; use daily
DAILY=$(bash "$SCRIPT" daily "$DAYS")
TOP=$(bash "$SCRIPT" top-expensive 10 "$DAYS")
ZERO=$(bash "$SCRIPT" zero-cost "$DAYS")
SNAPSHOT=$(bash "$SCRIPT" snapshot)
```

### Phase 2: Generate Report

Spawn Haiku write-agent to format the report:

```
Task(
  subagent_type: "general-purpose",
  model: "haiku",
  prompt: """
Write a cost dashboard report to .backlog-ops/cost-report-{YYYY-MM-DD}.md

Data:
- Current snapshot: {SNAPSHOT}
- Daily spend: {DAILY}
- Top 10 expensive requests: {TOP}
- Zero-cost anomalies: {ZERO}

Format as markdown with:
1. ## Summary — total spend, requests, period
2. ## Daily Trend — table with date, spend, requests
3. ## Model Breakdown — table with model, requests, spend, prompt_tokens, completion_tokens
4. ## Top Expensive Requests — table with time, model, spend, tokens
5. ## Anomalies — any zero-cost entries with >1000 prompt tokens (pricing bug indicator)
6. ## Recommendations — if zero-cost anomalies found, suggest checking LiteLLM pricing config
"""
)
```

Print summary banner after report is written.
```

**Step 2: Commit**

```bash
git add skills/backlog-benchmark/SKILL.md
git commit -m "feat(benchmark): create SKILL.md with report mode"
```

---

### Task 5: Add RUN mode and START/STOP markers to SKILL.md

**Files:**
- Modify: `skills/backlog-benchmark/SKILL.md` — append after REPORT mode

**Step 1: Add START/STOP marker modes**

Append after the REPORT section:

```markdown
---

## Mode: START (mark benchmark beginning)

1. Parse benchmark name from args (default: timestamp-based ID)
2. Create directory: `.backlog-ops/benchmarks/{name}/`
3. Capture snapshot:
   ```bash
   bash "${CLAUDE_PLUGIN_ROOT}/scripts/ops/benchmark_capture.sh" snapshot \
     > .backlog-ops/benchmarks/{name}/start.json
   ```
4. Print: `"Benchmark '{name}' started. Baseline: $X spend, N requests."`
5. Print: `"Run your skill now. When done: /backlog-toolkit:benchmark stop {name}"`

---

## Mode: STOP (mark benchmark end + generate report)

1. Parse benchmark name from args
2. Read `.backlog-ops/benchmarks/{name}/start.json`
3. Capture end snapshot:
   ```bash
   bash "${CLAUDE_PLUGIN_ROOT}/scripts/ops/benchmark_capture.sh" snapshot \
     > .backlog-ops/benchmarks/{name}/stop.json
   ```
4. Calculate deltas: end - start for spend, requests, tokens
5. Get per-model breakdown for the delta:
   ```bash
   bash "${CLAUDE_PLUGIN_ROOT}/scripts/ops/benchmark_capture.sh" \
     breakdown {start_row_count} > .backlog-ops/benchmarks/{name}/breakdown.json
   ```
6. Generate report via Haiku write-agent with delta data
7. Write to `.backlog-ops/benchmarks/{name}/report.md`
8. Print summary banner with cost, requests, model mix

---

## Mode: RUN (full benchmark with Opus baseline)

### Phase 1: Setup
1. Parse ticket ID from args
2. Read ticket from `{dataDir}/pending/{ticket_id}.md` or `{dataDir}/completed/{ticket_id}.md`
3. Create benchmark dir: `.backlog-ops/benchmarks/{ticket_id}-{YYYYMMDD-HHmm}/`
4. Capture start snapshot (same as START mode)

### Phase 2: Opus Baseline
Spawn one Opus agent to solve the ticket as quality reference:

```
Task(
  subagent_type: "general-purpose",
  model: "opus",
  prompt: """
You are creating a REFERENCE SOLUTION for benchmarking purposes.

## Ticket
{full_ticket_markdown}

## Instructions
1. Read all affected files listed in the ticket
2. Implement the fix/feature described
3. Write tests (min 3: happy path + error + edge)
4. Do NOT commit — write your solution files to:
   .backlog-ops/benchmarks/{run_id}/opus-baseline/
   Use the same relative paths as the original files.

Write the implementation files and test files only. No other output needed.
"""
)
```

Capture post-Opus snapshot. Calculate Opus cost = post_opus - start.

### Phase 3: Await Skill Execution
Print: `"Opus baseline captured (${opus_cost}). Now run the skill under test."`
Print: `"When done: /backlog-toolkit:benchmark stop {run_id}"`

The STOP command will handle Phase 4-6 when the user triggers it.
When STOP is called for a RUN benchmark (detected by presence of opus-baseline/):

### Phase 4: Quality Comparison
After STOP captures the skill's cost delta, compare quality:

1. Find files modified since benchmark start in the project
2. Diff against Opus baseline files
3. Run automated checks:
   - `{testCommand}` → tests pass?
   - `{lintCommand}` → lint clean?
   - Parse ticket ACs → covered?

4. Spawn Sonnet evaluator:

```
Task(
  subagent_type: "code-quality",
  model: "sonnet",
  prompt: """
Compare two implementations of the same ticket.

## Ticket
{ticket_summary_and_ACs}

## Implementation A (Opus Baseline)
{opus_files_content}

## Implementation B (Skill Under Test)
{skill_files_content}

## Evaluate on these dimensions (score 0-100 each):
1. Correctness: Does the code fix the issue?
2. Test coverage: ACs covered? Edge cases?
3. Code style: Consistent with codebase? Clean?
4. Completeness: Nothing missing?
5. No regressions: Any new issues introduced?

Also note: specific differences between A and B, which is better and why.
Output as structured markdown with scores table.
"""
)
```

### Phase 5: Final Report
Combine cost data + quality scores into final report:
`.backlog-ops/benchmarks/{run_id}/report.md`
```

**Step 2: Commit**

```bash
git add skills/backlog-benchmark/SKILL.md
git commit -m "feat(benchmark): add run/start/stop modes to SKILL.md"
```

---

### Task 6: Add COMPARE mode and finish SKILL.md

**Files:**
- Modify: `skills/backlog-benchmark/SKILL.md` — append COMPARE mode and constraints

**Step 1: Add COMPARE mode and constraints**

Append:

```markdown
---

## Mode: COMPARE (side-by-side two runs)

1. Parse two run IDs from args
2. Read both reports:
   - `.backlog-ops/benchmarks/{run-a}/report.md`
   - `.backlog-ops/benchmarks/{run-b}/report.md`
3. Spawn Haiku to generate comparison:

```
Task(
  subagent_type: "general-purpose",
  model: "haiku",
  prompt: """
Generate a side-by-side comparison of two benchmark runs.

## Run A: {run_a_id}
{report_a_content}

## Run B: {run_b_id}
{report_b_content}

Write comparison to .backlog-ops/benchmarks/compare-{a}-vs-{b}.md with:
1. ## Cost Comparison — side-by-side table
2. ## Quality Comparison — scores delta (if available)
3. ## Model Mix — which used more/less of each model
4. ## Recommendation — which variant is better (cost-adjusted quality)
"""
)
```

---

## Constraints

**DO**: Query Postgres via benchmark_capture.sh, save all data to .backlog-ops/benchmarks/, use Opus only for baseline, Sonnet only for quality eval, Haiku for everything else.
**DO NOT**: Implement code directly, modify the project under test, run benchmarks without capturing start snapshot, skip the Opus baseline in RUN mode.

## Start

1. Parse mode from command args
2. Resolve CLAUDE_PLUGIN_ROOT (same as implementer Phase 0.5)
3. Verify Postgres is reachable: `bash benchmark_capture.sh snapshot`
4. Execute the appropriate mode
```

**Step 2: Commit**

```bash
git add skills/backlog-benchmark/SKILL.md
git commit -m "feat(benchmark): add compare mode and constraints to SKILL.md"
```

---

### Task 7: Create CLAUDE.md

**Files:**
- Create: `skills/backlog-benchmark/CLAUDE.md`

**Step 1: Write skill documentation**

```markdown
# Backlog Benchmark Skill

## Purpose

Benchmark toolkit skills for cost and quality optimization using LiteLLM spend data and Opus as quality reference.

## Modes

### `benchmark run <ticket-id>`
Full benchmark: captures Opus baseline, user runs skill under test, generates cost + quality comparison report.

### `benchmark start/stop [name]`
Manual markers for benchmarking skills that run in separate sessions. Captures LiteLLM snapshots and calculates deltas.

### `benchmark report [--days N]`
Cost dashboard from LiteLLM Postgres. Shows model breakdown, daily trends, expensive requests, zero-cost anomalies.

### `benchmark compare <a> <b>`
Side-by-side comparison of two benchmark runs.

## Cost Model

| Operation | Model | Calls | Cost |
|-----------|-------|-------|------|
| run (Opus baseline) | Opus | 1 | $0.15-0.50 |
| run (quality eval) | Sonnet | 1 | $0.05-0.10 |
| run (report) | Haiku | 1 | $0.01 |
| report | Haiku | 1 | $0.01-0.03 |
| compare | Haiku | 1 | $0.01 |

## Data

All output in `.backlog-ops/benchmarks/`. Snapshots are JSON, reports are markdown.

## Dependencies

- Docker (for Postgres access via `docker exec`)
- LiteLLM with Postgres backend (spend logs)
- `scripts/ops/benchmark_capture.sh`
```

**Step 2: Commit**

```bash
git add skills/backlog-benchmark/CLAUDE.md
git commit -m "docs(benchmark): create CLAUDE.md for benchmark skill"
```

---

## Verification

1. Run `bash scripts/ops/benchmark_capture.sh snapshot` → should return JSON with spend data
2. Run `bash scripts/ops/benchmark_capture.sh daily 3` → should return daily breakdown
3. Run `/backlog-toolkit:benchmark report --days 3` → should generate cost-report markdown
4. Run `/backlog-toolkit:benchmark start test1`, wait, then `stop test1` → should generate delta report
5. Run `/backlog-toolkit:benchmark run` on a known ticket → should create Opus baseline + await skill
