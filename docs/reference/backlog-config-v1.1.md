# backlog.config.json v1.1 (Contract)

This document defines the official documentation contract for v1.1.

## Top-Level Structure

```json
{
  "version": "1.1",
  "project": {},
  "backlog": {},
  "qualityGates": {},
  "codeRules": {},
  "ticketValidation": {},
  "agentRouting": {},
  "reviewPipeline": {},
  "llmOps": {}
}
```

## Required Blocks

- `version` (now accepts `"1.0"` or `"1.1"`)
- `project`
- `backlog`
- `qualityGates`
- `codeRules`
- `ticketValidation`

## Optional/Extended Blocks

- `agentRouting`
- `reviewPipeline`
- `llmOps` (cloud routing, caching, budgets, batch policy, RAG)

## llmOps Block (v1.1 Extension)

### registry

```json
{
  "registry": {
    "source": ".backlog-ops/model-registry.json",
    "refreshCommand": "bash scripts/ops/sync-model-registry.sh",
    "strictMode": true
  }
}
```

When `strictMode` is true, skills can only use aliases defined in the registry. Prevents accidental use of raw model IDs.

### gateway

```json
{
  "gateway": {
    "baseURL": "http://localhost:4000",
    "apiKeyEnv": "LITELLM_MASTER_KEY",
    "requireEscalationReason": true
  }
}
```

When `requireEscalationReason` is true, any escalation to frontier model must log a reason in the usage ledger.

### routing

```json
{
  "routing": {
    "entryModelClassify": "cheap",
    "entryModelDraft": "cheap",
    "entryModelImplement": "balanced",
    "entryModelReview": "cheap",
    "escalationModel": "frontier",
    "maxEscalationsPerTicket": 1
  }
}
```

Maps workflow phases to model aliases. The cost pyramid: 70% cheap, 25% balanced, 5% frontier.

### tokenPolicy

```json
{
  "tokenPolicy": {
    "maxInputByPhase": {
      "classify": 4000,
      "draft": 8000,
      "implement": 32000,
      "review": 16000,
      "refine": 12000
    },
    "maxOutputByPhase": {
      "classify": 1000,
      "draft": 4000,
      "implement": 16000,
      "review": 4000,
      "refine": 8000
    },
    "contextWindowStrategy": "summarize"
  }
}
```

`contextWindowStrategy` options:
- `truncate-oldest` — drop oldest context
- `summarize` — LLM-summarize older context
- `rag-augment` — use RAG index for context retrieval

### cachePolicy

```json
{
  "cachePolicy": {
    "providerPromptCaching": true,
    "stablePrefixMinTokens": 2048,
    "responseCache": {
      "enabled": true,
      "ttlSeconds": 3600,
      "backend": "redis"
    },
    "semanticCache": {
      "enabled": false,
      "backend": "qdrant",
      "threshold": 0.88
    }
  }
}
```

Three caching layers:
1. **Provider prompt caching** — Anthropic native, 90% input discount
2. **Response cache** — LiteLLM gateway, identical request dedup
3. **Semantic cache** — Vector similarity for near-duplicate prompts

### batchPolicy

```json
{
  "batchPolicy": {
    "enabled": true,
    "eligiblePhases": ["refinement", "bulk-ticket-validation", "cost-report", "duplicate-detection"],
    "forceBatchWhenQueueOver": 25,
    "maxConcurrentBatchJobs": 10,
    "retryPolicy": {
      "maxRetries": 3,
      "backoffMultiplier": 2.0
    }
  }
}
```

Batch API gives 50% cost reduction for non-interactive workloads.

### ragPolicy

```json
{
  "ragPolicy": {
    "enabled": false,
    "embeddingModel": "text-embedding-3-small",
    "vectorStore": "local-faiss",
    "indexPath": ".backlog-ops/rag-index",
    "chunkSize": 512,
    "topK": 10,
    "reindexCommand": "python scripts/ops/rag_index.py --rebuild"
  }
}
```

RAG reduces input tokens by 60-80% for large codebases by retrieving only relevant code chunks. See [ADR-005](../architecture/adr/ADR-005-rag-augmented-context.md).

## Compatibility Notes

- Config with `version: "1.0"` still works — `llmOps` block is optional
- Schema file (`config/backlog.config.schema.json`) now accepts both versions
- Default preset (`config/presets/default.json`) ships with v1.1 and full `llmOps`
- Skills should check for `llmOps` presence before using cloud features
