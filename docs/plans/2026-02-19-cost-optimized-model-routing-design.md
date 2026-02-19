# Cost-Optimized Model Routing Design

**Status**: Approved
**Date**: 2026-02-19
**Goal**: Reduce per-ticket implementation cost by 33–51% by routing development tasks to Ollama/Haiku and reserving Sonnet exclusively for code review.

## Context

Analysis of a 15-minute LiteLLM session (199 calls, $6.11) revealed:

- **Sonnet**: 129 calls, $6.02 (98.5% of spend) — large context, short output
- **Haiku**: 70 calls, $0.09 (1.5%) — small, efficient calls
- **Ollama (free)**: 0 calls — completely unused despite being configured
- Prompt caching is active (98–100% hit rate on Sonnet), already saving ~89% on input costs

The implementer skill currently routes **implementation to Sonnet** and **review to Haiku**. This is backwards from a cost-efficiency standpoint: the most expensive model is used for the most token-heavy gate (IMPLEMENT), while the cheapest model handles the quality-critical gate (REVIEW).

## Design

Invert the model routing: cheap/free models write code, expensive models review it.

### Routing Table

| Gate | Current Model | Proposed Model | Mechanism |
|------|--------------|----------------|-----------|
| Wave Planning | Sonnet (subagent) | **Ollama** → Haiku fallback | `llm_call.sh --model free` → Task(model: "haiku") |
| Gate 1 PLAN | balanced (Sonnet) | **Ollama** → Haiku fallback | `llm_call.sh --model free` → Task(model: "haiku") |
| Gate 2 IMPLEMENT | balanced (Sonnet) | **Haiku** | Task(model: "haiku") — needs tool_use |
| Gate 3 LINT | cheap (Haiku) | cheap (Haiku) | Unchanged |
| Gate 4 REVIEW | cheap (Haiku) | **Sonnet** | Task(model: "sonnet") |
| Gate 5 COMMIT | cheap (Haiku) | **Ollama** → static template | `llm_call.sh --model free` → template fallback |
| Write-agents | Sonnet | **Haiku** | Task(model: "haiku") |
| Classification | N/A | **Ollama** | `llm_call.sh --model free` |

### Technical Constraints

- **Ollama cannot do tool_use**: Gate 2 IMPLEMENT requires Read/Edit/Write/Bash through Claude Code subagents. Ollama is accessed via `llm_call.sh` (simple request-response), so it can only handle text-in/text-out tasks (planning, classification, commit messages).
- **Haiku is the cheapest tool_use-capable model**: At $1/$5 per MTok (in/out), it's 3x cheaper than Sonnet.
- **Sonnet excels at review**: Detecting subtle bugs, security issues, and architectural problems. This is where quality investment pays off.

### Escalation Safety Net

If Haiku fails Gate 3 (LINT) or Gate 4 (REVIEW) more than once on a ticket:

1. Increment `localModelStats.escalatedToCloud`
2. Re-route that ticket's IMPLEMENT to Sonnet
3. Log: "Haiku failed on {ticket_id} at {gate}. Escalated to Sonnet."

This prevents runaway review loops from erasing the cost savings.

### Cost Estimates Per Ticket

| Scenario | Cost/ticket | 50 tickets | Savings |
|----------|------------|------------|---------|
| Current | $0.432 | $21.60 | — |
| Proposed (optimistic) | $0.212 | $10.60 | 51% |
| Proposed (conservative) | $0.290 | $14.50 | 33% |

### Cost Breakdown — Proposed (Optimistic)

| Gate | Model | Input tok | Output tok | Cost |
|------|-------|-----------|------------|------|
| Wave plan (÷3) | Ollama | ~700 | ~330 | $0.000 |
| PLAN | Ollama→Haiku | ~5,000 | ~2,000 | $0.003 |
| IMPLEMENT (×2 rounds) | Haiku | ~30,000 | ~5,000 | $0.110 |
| LINT | Haiku | ~2,000 | ~500 | $0.005 |
| REVIEW (×2 reviewers) | Sonnet | ~10,000 | ~1,000 | $0.090 |
| COMMIT | Ollama | ~1,000 | ~200 | $0.000 |
| Write-agent (÷3) | Haiku | ~1,000 | ~670 | $0.004 |
| **Total** | | | | **$0.212** |

## Changes Required

### 1. Config schema (`config/backlog.config.schema.json`)

Add `entryModelPlan` to `llmOps.routing`:

```json
"entryModelPlan": {
  "type": "string",
  "description": "Model alias for planning gates (text-only, no tool_use).",
  "default": "free"
}
```

### 2. Default preset (`config/presets/default.json`)

Update routing defaults:

```json
"routing": {
  "entryModelClassify": "free",
  "entryModelPlan": "free",
  "entryModelDraft": "free",
  "entryModelImplement": "cheap",
  "entryModelReview": "balanced",
  "escalationModel": "frontier"
}
```

### 3. Implementer skill (`skills/backlog-implementer/SKILL.md`)

- Update MODEL RULES: default subagents to `haiku`, reviewers to `sonnet`
- Wave Planning: use `llm_call.sh --model free` instead of Task(model: "sonnet")
- Gate 1 PLAN: use `llm_call.sh --model free` with Haiku fallback
- Gate 2 IMPLEMENT: change Task model from `sonnet` to `haiku`
- Gate 4 REVIEW: change Task model from `cheap`/`haiku` to `sonnet`
- Gate 5 COMMIT: use `llm_call.sh --model free` for commit message, template fallback
- Write-agents: change model from `sonnet` to `haiku`
- Update escalation logic to track Haiku→Sonnet escalations

### 4. Proxy config (`config/litellm/proxy-config.docker.yaml`)

Ensure fallback chain: `free → [cheap, balanced]` (already configured).

## Risks

1. **Haiku code quality**: May produce more bugs, requiring more review rounds. Mitigated by escalation safety net.
2. **Ollama availability**: Local model may be unavailable. Mitigated by automatic fallback to Haiku.
3. **Ollama latency**: Local inference may be slower than API calls. Acceptable for non-interactive gates.
4. **Review cost increase**: Sonnet review is 3x more expensive than Haiku review. Offset by 3x cheaper implementation.

## Verification

After implementation, run the implementer on 3–5 tickets and compare:
- Actual cost per ticket vs estimates
- Review round count (Haiku implement vs Sonnet implement)
- Escalation frequency
- Code quality (test pass rate, lint errors)
