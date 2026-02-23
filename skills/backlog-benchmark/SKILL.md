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
