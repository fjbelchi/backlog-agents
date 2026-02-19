# Quickstart: Cloud-First Setup

End-to-end guide to get the backlog toolkit running with cost-optimized cloud LLM usage in **under 15 minutes**.

## Prerequisites

- Claude Code installed and working
- Python 3.10+, Bash
- An Anthropic API key (minimum), optionally OpenAI
- (Optional) Docker for running LiteLLM proxy locally

## Step 1: Install the Plugin

```bash
# Recommended: install as plugin
/plugin install --path /path/to/backlog-agents

# Alternative: install skills manually
cd /path/to/backlog-agents
./install.sh --local --force
```

## Step 2: Initialize Your Project

```bash
# In your target project directory
/backlog-toolkit:init
```

This creates:
- `backlog/` directory with `data/pending/`, `data/completed/`, and `templates/`
- `backlog.config.json` auto-configured for your detected stack

## Step 3: Set Up Cost Controls

```bash
# Copy environment template
cp /path/to/backlog-agents/.env.example .env
# Edit .env with your API keys (NEVER commit this file)

# Create ops directory and initialize artifacts
mkdir -p .backlog-ops
/path/to/backlog-agents/scripts/ops/sync-model-registry.sh
touch .backlog-ops/usage-ledger.jsonl
```

## Step 4: Configure LLM Optimization (backlog.config.json)

Add the `llmOps` block to your `backlog.config.json`:

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
    },
    "cachePolicy": {
      "providerPromptCaching": true,
      "stablePrefixMinTokens": 2048,
      "responseCache": { "enabled": true, "ttlSeconds": 3600 }
    },
    "batchPolicy": {
      "enabled": true,
      "eligiblePhases": ["refinement", "bulk-ticket-validation"],
      "forceBatchWhenQueueOver": 25
    }
  }
}
```

## Step 5: (Optional) Start LiteLLM Proxy

For gateway-level routing, caching, and budget enforcement:

```bash
# Copy template
cp /path/to/backlog-agents/config/litellm/proxy-config.template.yaml litellm-config.yaml

# Export keys
export ANTHROPIC_API_KEY="sk-ant-..."
export LITELLM_MASTER_KEY="sk-litellm-..."

# Run proxy (Docker)
docker run -d \
  -p 4000:4000 \
  -v $(pwd)/litellm-config.yaml:/app/config.yaml \
  -e ANTHROPIC_API_KEY \
  -e LITELLM_MASTER_KEY \
  ghcr.io/berriai/litellm:main-latest \
  --config /app/config.yaml

# Verify
curl http://localhost:4000/health
```

Then set `llmOps.gateway.baseURL` in your `backlog.config.json`:
```json
{ "llmOps": { "gateway": { "baseURL": "http://localhost:4000" } } }
```

## Step 6: Create Your First Ticket

```bash
/backlog-toolkit:ticket "Add user authentication with JWT tokens"
```

Check the generated ticket in `backlog/data/pending/`. It includes:
- Full spec with acceptance criteria
- Affected files analysis
- Cost estimate per model

## Step 7: Verify Everything Works

```bash
# Validate toolkit health
make validate   # or run manually:
./tests/test-config-schema.sh
./tests/test-templates.sh
./scripts/docs/check-links.sh
```

## Next Steps

1. Read the [Token Optimization Playbook](token-optimization-playbook.md) for 40-70% cost savings
2. Review [Daily Operator Flow](daily-flow.md) for routine operations
3. Try implementation: `/backlog-toolkit:implementer`
4. Set up cost monitoring: `./scripts/ops/cost_guard.py --ledger .backlog-ops/usage-ledger.jsonl`
