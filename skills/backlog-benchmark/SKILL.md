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
