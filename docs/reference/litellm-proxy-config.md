# LiteLLM Production Configuration

This page documents the production-ready settings used by the cloud-first plan.
See also: [ADR-004: Multi-Layer Caching & Batch](../architecture/adr/ADR-004-multilayer-caching-and-batch.md)

## Model Aliases

Skills reference **aliases only** (cheap/balanced/frontier), never raw model IDs.
This decouples workflows from provider model changes.

```yaml
model_list:
  # CHEAP — 70% of calls: classify, triage, review, lint, drafts
  - model_name: cheap
    litellm_params:
      model: anthropic/claude-haiku-4-5
      api_key: os.environ/ANTHROPIC_API_KEY

  # BALANCED — 25% of calls: implementation, code generation
  - model_name: balanced
    litellm_params:
      model: anthropic/claude-sonnet-4-6
      api_key: os.environ/ANTHROPIC_API_KEY

  # FRONTIER — 5% of calls: complex architecture, security, escalation
  - model_name: frontier
    litellm_params:
      model: anthropic/claude-opus-4
      api_key: os.environ/ANTHROPIC_API_KEY
```

## Routing and Fallbacks

```yaml
router_settings:
  routing_strategy: simple-shuffle
  fallbacks:
    - cheap: [balanced, frontier]
    - balanced: [frontier]
  context_window_fallbacks:
    - cheap: [balanced]
    - balanced: [frontier]
  content_policy_fallbacks:
    - cheap: [balanced]
  allowed_fails: 3
  cooldown_time: 60
```

## Budgets

```yaml
litellm_settings:
  budget_duration: monthly
  max_budget: 1200

model_max_budget:
  frontier: 300
  balanced: 600
  cheap: 300

provider_budget_config:
  anthropic:
    budget_limit: 1000
    time_period: 1m
  openai:
    budget_limit: 200
    time_period: 1m
```

## Tag Routing

Skills can tag requests for routing decisions:

```yaml
general_settings:
  enable_tag_filtering: true

model_list:
  - model_name: cheap
    model_info:
      supported_environments: ["interactive", "offline"]
  - model_name: frontier
    model_info:
      supported_environments: ["critical"]
```

## Timeouts, Retries, Cooldown

```yaml
litellm_settings:
  request_timeout: 30
  num_retries: 2

router_settings:
  allowed_fails: 3
  cooldown_time: 60
```

## Caching (3 Layers)

### Layer 1: Anthropic Prompt Caching (provider-native)

- 90% discount on cached input tokens
- Minimum prefix: 1024 tokens (2048+ recommended)
- Prefix must be byte-identical across requests
- Cache TTL: 5 minutes, refreshed on each hit
- No LiteLLM config needed — handled by provider

**What to cache**: System instructions, code rules, Iron Laws, config.
**What NOT to cache**: Ticket content, dynamic file contents, timestamps.

### Layer 2: Response Cache (LiteLLM gateway)

Caches identical API call responses:

```yaml
litellm_settings:
  cache: true
  cache_params:
    type: redis           # or s3, local
    ttl: 3600             # 1 hour
    namespace: backlog    # isolate from other apps
```

### Layer 3: Semantic Cache (optional)

Near-duplicate prompt matching via vector similarity:

```yaml
# Configured in backlog.config.json -> llmOps.cachePolicy.semanticCache
# Requires a vector backend (qdrant, redis-vss, chromadb)
```

## Guardrails, Callbacks, Metrics

- Configure guardrails via proxy guardrail settings
- Enable callbacks for logging/spend telemetry
- Scrape `/metrics` for Prometheus-based alerting

## Fallback Management API

- `GET /fallback` — list current fallback routes
- `POST /fallback` — add/update fallback route
- `DELETE /fallback/{fallback_name}` — remove fallback

## Mapping to backlog.config.json

| LiteLLM Setting | backlog.config.json Path |
|-----------------|-------------------------|
| Model aliases | `llmOps.routing.*` |
| Budget enforcement | `llmOps.gateway.baseURL` + proxy config |
| Response cache | `llmOps.cachePolicy.responseCache` |
| Prompt caching | `llmOps.cachePolicy.providerPromptCaching` |
| Semantic cache | `llmOps.cachePolicy.semanticCache` |
| Escalation policy | `llmOps.routing.maxEscalationsPerTicket` |
