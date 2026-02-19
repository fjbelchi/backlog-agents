# System Overview

## Topology

`user -> backlog-orchestrator -> deterministic scripts -> LiteLLM proxy -> cloud providers -> usage ledger`

## Components

1. **User Interface**: CLI commands and skills.
2. **Orchestrator**: Selects workflow, enforces policy, tracks escalations.
3. **Scripts Layer**: Performs deterministic tasks to avoid unnecessary LLM calls.
4. **LiteLLM Gateway**: Routing, budgets, fallbacks, caching, and metrics.
5. **Providers**: Anthropic/OpenAI/Gemini (and optional additional providers).
6. **Ledger**: Persistent usage and cost telemetry.

## Key Design Rules

1. Script-first, LLM-second.
2. Cheapest model class that passes quality gates.
3. Batch for non-interactive tasks.
4. Documented contracts are mandatory.

## Data Contracts

- [Backlog Config v1.1](../reference/backlog-config-v1.1.md)
- [Model Registry](../reference/model-registry.md)
- [Usage Ledger Schema](../reference/usage-ledger-schema.md)
- [Batch Queue Schema](../reference/batch-queue-schema.md)
