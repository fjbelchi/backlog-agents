# Runbook: Cache Optimization

## Goal

Increase cache hit rate to ≥60% and reduce duplicate token spend through multi-layer caching.

## Prerequisites

- Usage ledger active at `.backlog-ops/usage-ledger.jsonl`
- Prompt manifest at `.backlog-ops/prompt-manifest.json` (optional but recommended)
- `llmOps.cachePolicy` configured in `backlog.config.json`

## Step 1: Diagnose Current Cache Performance

```bash
# Check cache hit rate from ledger
echo "Cache hits:"
grep '"cache_hit":true' .backlog-ops/usage-ledger.jsonl | wc -l
echo "Cache misses:"
grep '"cache_hit":false' .backlog-ops/usage-ledger.jsonl | wc -l

# Full analytics
python scripts/ops/cost_report.py --ledger .backlog-ops/usage-ledger.jsonl --json | python -c "import sys,json;d=json.load(sys.stdin);print(f'Cache hit rate: {d[\"cache_hit_rate_pct\"]}%')"
```

## Step 2: Validate Prompt Prefix Consistency

Anthropic prompt caching requires byte-identical prefixes. Any variation breaks the cache.

```bash
./scripts/ops/prompt_prefix_lint.py --manifest .backlog-ops/prompt-manifest.json
```

**Common cache-breaking patterns**:
- Timestamps in system prompts
- Random order of included files
- Dynamic config values that change between calls
- Whitespace differences

**Fix**: Move all dynamic content AFTER the stable prefix (system instructions, code rules, Iron Laws).

## Step 3: Check Response Cache TTL

```yaml
# In litellm config
litellm_settings:
  cache_params:
    ttl: 3600    # 1 hour — increase for stable workflows
```

For long refactoring sessions, consider `ttl: 7200` (2 hours).

## Step 4: Tune Semantic Cache Threshold

If semantic cache is enabled:

```json
{
  "llmOps": {
    "cachePolicy": {
      "semanticCache": {
        "enabled": true,
        "threshold": 0.88
      }
    }
  }
}
```

- **0.92+**: Very conservative, few false positives, low hit rate
- **0.88**: Balanced (recommended starting point)
- **0.82**: Aggressive, more hits but risk of incorrect cached responses

## Step 5: Verify and Iterate

```bash
# Re-run a typical workflow and compare
/backlog-toolkit:refinement

# Check improvement
python scripts/ops/cost_report.py --ledger .backlog-ops/usage-ledger.jsonl --days 1
```

## KPI Targets

| Metric | Target | Action if Below |
|--------|--------|----------------|
| Prompt cache hit rate | ≥60% | Fix prefix consistency (Step 2) |
| Response cache useful hit rate | ≥20% | Increase TTL (Step 3) |
| Semantic cache useful hit rate | ≥10% | Lower threshold (Step 4) |
| Cached token ratio | ≥40% | Review which workflows bypass cache |

## Escalation

If cache hit rate stays below 40% after following all steps:
1. Check if LiteLLM Redis/cache backend is healthy
2. Verify prompt manifest covers all high-volume paths
3. Consider if the workload pattern is inherently low-repetition (implementation has lower cache rates than validation)
