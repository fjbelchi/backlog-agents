# Token Optimization Playbook

Practical checklist to reduce Claude Code token spend by 40-70% without losing quality.

## The Cost Pyramid

```
         ┌─────────────┐
         │  FRONTIER    │ ← 5% of calls, 40% of cost
         │  (Opus 4)    │   Only for: complex architecture, security audit
         ├─────────────────┤
         │   BALANCED      │ ← 25% of calls, 40% of cost
         │ (Sonnet 4)      │   For: implementation, code generation
         ├─────────────────────┤
         │     CHEAP            │ ← 70% of calls, 20% of cost
         │   (Haiku 3.5)        │   For: classify, triage, review, lint
         └──────────────────────┘
```

## 7 Optimization Layers (apply in order)

### Layer 1: Script-First, LLM-Second

Every time you reach for the LLM, ask: **can a deterministic script do this?**

| Task | Script Alternative | Token Savings |
|------|-------------------|---------------|
| **Project init** | `scripts/init/backlog_init.py` | **100%** |
| Ticket validation | `scripts/ticket/validate_ticket.py` | 100% |
| Duplicate detection | `scripts/ticket/detect_duplicates.py` | 100% |
| Impact analysis | `scripts/implementer/impact_graph.py` | 100% |
| Refinement triage | `scripts/refinement/bulk_refine_plan.py` | 80-100% |
| Cost checks | `scripts/ops/cost_guard.py` | 100% |
| Prompt lint | `scripts/ops/prompt_prefix_lint.py` | 100% |

```bash
# Init a project deterministically (replaces the LLM skill)
python scripts/init/backlog_init.py --yes --llmops

# Run ALL scripts before any LLM call
./scripts/ticket/validate_ticket.py backlog/data/pending/FEAT-001.md
./scripts/ticket/detect_duplicates.py backlog/data/pending/FEAT-001.md
./scripts/implementer/impact_graph.py src/auth.ts src/middleware.ts
./scripts/refinement/bulk_refine_plan.py
```

### Layer 2: Model Routing by Phase

Don't use Opus for everything. Route by phase via `llmOps.routing`:

```json
{
  "llmOps": {
    "routing": {
      "entryModelClassify": "cheap",
      "entryModelDraft": "cheap",
      "entryModelImplement": "balanced",
      "entryModelReview": "cheap",
      "escalationModel": "frontier",
      "maxEscalationsPerTicket": 1
    }
  }
}
```

**Cost per 1M tokens comparison:**

| Model | Input | Output | Relative Cost |
|-------|-------|--------|---------------|
| Haiku 3.5 | $0.80 | $4.00 | 1x |
| Sonnet 4 | $3.00 | $15.00 | ~4x |
| Opus 4 | $15.00 | $75.00 | ~19x |

**Rule**: Start cheap → escalate only when quality drops below threshold.

### Layer 3: Prompt Caching (Anthropic)

Anthropic's prompt caching gives **90% discount** on cached input tokens and is the single most impactful optimization.

**How it works**: Mark stable system prompt content with `cache_control: { type: "ephemeral" }`. After the first call, subsequent calls with identical prefix pay only 10% of input cost.

**Requirements**:
- Minimum 1024 tokens in the cacheable prefix (2048+ recommended)
- Prefix must be byte-identical across requests
- Cache TTL: 5 minutes (refreshed on hit)

**What to put in the stable prefix**:
1. System instructions (SKILL.md content)
2. Code rules (`.claude/code-rules.md`)
3. Project config (`backlog.config.json`)
4. Iron Laws (always identical)

**What NOT to put in the prefix**:
- Ticket-specific content (changes per request)
- File contents being analyzed (changes per request)
- Timestamps or dynamic values

**Verify cache is working**:
```bash
# Check prompt prefix consistency
./scripts/ops/prompt_prefix_lint.py --manifest .backlog-ops/prompt-manifest.json

# Look for cached_input_tokens in usage ledger
grep '"cache_hit":true' .backlog-ops/usage-ledger.jsonl | wc -l
```

**Target**: >=60% cache hit rate for repetitive workflows (refinement, validation, review).

### Layer 4: Response Caching (LiteLLM)

Cache identical API responses at the gateway level.

```yaml
# In litellm config
litellm_settings:
  cache: true
  cache_params:
    type: redis           # or s3, local
    ttl: 3600             # 1 hour -- enough for session work
    namespace: backlog    # separate from other apps
```

**Best candidates for response caching**:
- Classification/triage (same ticket → same classification)
- Validation checks (same code → same lint suggestions)
- Template expansion (stable inputs → stable outputs)

**Config in backlog.config.json**:
```json
{
  "llmOps": {
    "cachePolicy": {
      "responseCache": {
        "enabled": true,
        "ttlSeconds": 3600,
        "backend": "redis"
      }
    }
  }
}
```

### Layer 5: Semantic Caching

For **near-duplicate** prompts (different wording, same intent), semantic cache uses vector similarity to avoid re-computation.

```json
{
  "llmOps": {
    "cachePolicy": {
      "semanticCache": {
        "enabled": true,
        "backend": "qdrant",
        "threshold": 0.88
      }
    }
  }
}
```

**Best candidates**:
- Refinement passes on similar tickets
- Repeated validation queries
- FAQ-like developer questions

**Threshold tuning**: Start at 0.88 (conservative). Lower to 0.82 for more hits, raise to 0.92 for higher precision.

### Layer 6: Batch API (50% discount)

Anthropic and OpenAI offer 50% cost reduction for non-interactive requests with ≤24h SLA.

**Eligible workflows**:
- Bulk refinement (all pending tickets)
- Duplicate detection across backlog
- Cost reporting and analytics
- Ticket validation sweeps

```json
{
  "llmOps": {
    "batchPolicy": {
      "enabled": true,
      "eligiblePhases": ["refinement", "bulk-ticket-validation", "cost-report", "duplicate-detection"],
      "forceBatchWhenQueueOver": 25
    }
  }
}
```

**Workflow**:
```bash
# 1. Build queue
./scripts/refinement/bulk_refine_plan.py > tmp/batch-queue.jsonl

# 2. Submit batch
./scripts/ops/batch_submit.py --queue tmp/batch-queue.jsonl

# 3. Wait and reconcile (can take minutes to hours)
./scripts/ops/batch_reconcile.py --queue tmp/batch-queue.jsonl
```

### Layer 7: RAG-Augmented Context (reduce input tokens)

Instead of dumping entire files into context, use RAG to retrieve only relevant chunks.

> **Full reference**: See [RAG Pipeline Reference](../reference/rag-pipeline.md) for architecture, scoring algorithm, limitations, and operations guide.

**Problem**: A 2000-line file uses ~20K tokens. With RAG, you send only the 3-5 relevant functions (~2-4K tokens).

**Current implementation**: TF-based token overlap scoring (zero cost, fully offline). Semantic embedding support is planned but not yet wired.

**Typical savings**: 68% input token reduction. At Sonnet 4 pricing, ~$32/month for 2K calls/month.

```bash
# Build index (one-time, takes seconds)
python scripts/ops/rag_index.py --rebuild

# Query before LLM calls
python scripts/ops/rag_index.py --query "authentication middleware" --json

# Check index health
python scripts/ops/rag_index.py --stats
```

```json
{
  "llmOps": {
    "ragPolicy": {
      "enabled": true,
      "vectorStore": "local-faiss",
      "indexPath": ".backlog-ops/rag-index",
      "chunkSize": 512,
      "topK": 10,
      "reindexCommand": "python scripts/ops/rag_index.py --rebuild"
    }
  }
}
```

**When to use RAG**:
- Large codebases (>500 files)
- Ticket generation (need relevant context, not all code)
- Implementation planning (find related patterns)

**When NOT to use RAG**:
- Small projects (<50 files) — just read everything
- Bug fixes where you know the exact file
- Template/config generation

## Quick Wins Checklist

Apply these today for immediate savings:

- [ ] **Route all classification/triage to Haiku** (`entryModelClassify: "cheap"`)
- [ ] **Run scripts before LLM calls** (validate, dedup, impact graph)
- [ ] **Enable prompt caching** (`cachePolicy.providerPromptCaching: true`)
- [ ] **Enable response caching** (`cachePolicy.responseCache.enabled: true`)
- [ ] **Set token limits** (`tokenPolicy.maxInputByPhase` / `maxOutputByPhase`)
- [ ] **Batch non-interactive work** (`batchPolicy.enabled: true`)
- [ ] **Track costs daily** (`scripts/ops/cost_guard.py --ledger ...`)
- [ ] **Audit escalations weekly** (check `escalation_reason` in ledger)

## Measuring Progress

### KPIs

| Metric | Target | Check Command |
|--------|--------|---------------|
| Prompt cache hit rate | ≥60% | `grep cache_hit .backlog-ops/usage-ledger.jsonl \| jq .cache_hit \| sort \| uniq -c` |
| Cheap model ratio | ≥70% | `grep model_alias .backlog-ops/usage-ledger.jsonl \| jq .model_alias \| sort \| uniq -c` |
| Batch vs interactive ratio | ≥30% batch | `grep batch_job_id .backlog-ops/usage-ledger.jsonl \| grep -v null \| wc -l` |
| Frontier escalation rate | <5% | `grep escalation_reason .backlog-ops/usage-ledger.jsonl \| grep -v null \| wc -l` |
| Cost per ticket (avg) | <$2 with Sonnet | Average from `.claude/cost-history.json` |
| Estimate accuracy | ≥70% | Compare actual vs estimated in completed tickets |

### Weekly Cost Review

```bash
# Full cost posture check
./scripts/ops/cost_guard.py --ledger .backlog-ops/usage-ledger.jsonl --warn 0.70 --hard-stop 1.00
./scripts/ops/prompt_prefix_lint.py --manifest .backlog-ops/prompt-manifest.json
./scripts/docs/check-doc-coverage.py
```
