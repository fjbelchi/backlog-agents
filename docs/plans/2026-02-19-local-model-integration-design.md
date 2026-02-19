# Local Model Integration — Design Doc

**Date**: 2026-02-19
**Status**: Implemented
**Impact**: Additional ~$0.50-2.50/session savings on top of prompt efficiency optimizations

## Problem

After optimizing model selection (Opus→Sonnet) and plugin scoping (~70-85% cost reduction), the remaining costs are:
- Sonnet: ~$2-6/session for implementation, review, analysis
- Haiku: ~$0.79/session for 407 classification/triage requests

The user has Ollama installed with qwen3-coder:30b (18GB, Q4_K_M). Can local models replace some cloud API calls without quality degradation?

## Benchmarks

### qwen3-coder:30b Performance (on user's laptop)

| Task | Output tokens | Speed | Total time | Quality |
|---|---|---|---|---|
| Classification (short) | 2 | 136 tok/s | 0.8s | Correct |
| Code generation (circuit breaker) | 2,704 | 63 tok/s | 46.3s | 83% type hints, 96% docstrings |
| Code review (6 findings) | 80 | 70 tok/s | 2.0s | All valid findings |
| Tool use (function call) | 23 | 71 tok/s | 3.2s | Correct |
| Large context (1K tokens) | 2 | 132 tok/s | 4.0s | Correct |

### Code Quality Comparison (3 senior-level tests)

| Test | Criteria met | Type hints | Docstrings | Issues found |
|---|---|---|---|---|
| Resilient HTTP Client | 7/9 | 83% | 96% | Missing discriminated union, bare pass |
| LRU Cache + TTL | 11/11 | 92% | 100% | async def without await, bare pass |
| Event Bus + Middleware | 11/11 | 89% | 71% | time.sleep in async, 2 Any despite constraint |

### Assessment

- **Quality**: ~80-85% of Sonnet on isolated tasks. Gap is in constraint adherence and subtle bugs.
- **Speed**: 57-70 tok/s generation, 2-4s prompt eval. Acceptable for non-interactive tasks.
- **Strengths**: Correct architecture, good type hints, follows instructions well.
- **Weaknesses**: Bare pass in exceptions (3/3 tests), subtle async bugs, doesn't self-correct.

## Why NOT gpt-5.2-codex

Investigated as alternative. Raw pricing ($1.75/$14) looks 40% cheaper than Sonnet ($3/$15), but Bedrock prompt caching (85% hit rate, 90% discount) makes effective Sonnet cost much lower:

| Model | With caching | Without caching |
|---|---|---|
| Sonnet (Bedrock) | $27.61/session | N/A (always cached) |
| gpt-5.2-codex (OpenAI) | $24.97 (10% savings) | $62.50 (126% MORE) |

Not worth adding a second cloud provider for 10% savings with cache-miss risk.

## Architecture

### 4-tier model routing (via LiteLLM)

```
free     (qwen3-coder local)  → $0/MTok
cheap    (Haiku 4.5 Bedrock)  → $1/$5/MTok
balanced (Sonnet 4.6 Bedrock) → $3/$15/MTok
frontier (Opus 4.6 Bedrock)   → $5/$25/MTok
```

### Routing via LiteLLM tag-based routing

Requests tagged `"local"` route to Ollama. Untagged requests route to Bedrock (default). Fallback: `free → cheap → balanced`.

```yaml
# proxy-config.docker.yaml additions
model_list:
  - model_name: free
    litellm_params:
      model: ollama/qwen3-coder:30b
      api_base: http://host.docker.internal:11434
      tags: ["local"]
      input_cost_per_token: 0
      output_cost_per_token: 0

router_settings:
  enable_tag_filtering: true
  fallbacks:
    - free: [cheap, balanced]
    - cheap: [balanced, frontier]
    - balanced: [frontier]
```

### Phase 1: Tasks routed to local (safe, no quality risk)

| Task | Current tier | Why local works |
|---|---|---|
| Ticket classification | Haiku | 2-token output, classification is reliable |
| File pattern analysis | Haiku | Simple pattern matching |
| Ticket format validation | Haiku | Structural checks |
| Wave summary log writing | Sonnet (write-agent) | Templated markdown output |
| Wave planning (JSON) | Sonnet (subagent) | Structured output, tested at 100% accuracy |

### Phase 2: Simple implementation with sentinel (quality-gated)

Route simple tickets (single-file edits, test additions) to local. Existing quality gates act as sentinel:

1. **Gate 3 (Lint/Typecheck)**: Catches syntax errors, type violations
2. **Gate 4 (Review by Sonnet)**: Catches constraint violations, subtle bugs
3. **Escalation**: If gate fails after 2 rounds, re-route ticket to Sonnet with `"local-failed"` tag

### Escalation flow

```
qwen3-coder generates code
         │
    Lint passes? ──No──→ Fix attempt (max 2)
         │                     │
        Yes              Still fails?
         │                     │
  Review passes? ──No──→ Fix attempt (max 2) ──→ ESCALATE to Sonnet
         │
        Yes
         │
  Commit + log "local-success"
```

### Performance tracking

Add to implementer state:
```json
{
  "localModelStats": {
    "totalAttempts": 0,
    "successCount": 0,
    "escalatedToCloud": 0,
    "failuresByType": {},
    "avgQualityScore": 0
  }
}
```

Auto-disable local routing if `escalatedToCloud / totalAttempts > 30%`.

## Changes Required

### Config (Phase 1 — no skill changes)
1. `config/litellm/proxy-config.docker.yaml` — add `free` tier with Ollama
2. `docker-compose.yml` — ensure Ollama accessibility from Docker network
3. `scripts/services/start-services.sh` — verify Ollama running before LiteLLM

### Skills (Phase 2 — "junior programmer" routing)
4. `skills/backlog-implementer/SKILL.md` — add local-first routing for simple tickets
5. `scripts/implementer/migrate-state.py` — add `localModelStats` to schema

## Cost Impact Estimate

| Phase | Tasks routed locally | Est. savings/session |
|---|---|---|
| Phase 1: Classification + planning | ~400-500 requests | $0.50-0.80 |
| Phase 2: Simple implementation | ~50-100 requests | $0.50-1.50 |
| **Combined** | **~500-600 requests** | **$1.00-2.30** |

On top of previous optimizations (~$13-17 savings), total cost reduction reaches ~75-90%.

## Constraints

- **Claude Code main agent cannot use Ollama** — always requires Anthropic API
- **Ollama must be running** — not guaranteed on all machines; fallback to Haiku is essential
- **Context window**: qwen3-coder has 262K context but quality degrades above ~32K tokens
- **No prompt caching**: Ollama doesn't cache prompts like Bedrock; each request reprocesses the full context
- **Latency**: 40-60s for complex generation; not suitable for interactive chains

## Verification Plan

1. Add Ollama tier to LiteLLM config
2. Test routing: `curl -X POST .../chat/completions -d '{"model":"free","tags":["local"],...}'`
3. Test fallback: stop Ollama, verify request falls back to Haiku
4. Run 10 classification tasks through local, compare results with Haiku
5. Run 3 simple implementation tasks, verify quality gates catch issues
6. Monitor `localModelStats` for escalation rate
