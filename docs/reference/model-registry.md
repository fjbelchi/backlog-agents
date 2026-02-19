# model-registry.json Contract

## Purpose

Map stable aliases to current provider model IDs without hardcoding model names in skills.

## Location

`.backlog-ops/model-registry.json`

## Schema

```json
{
  "version": "1.0",
  "generated_at": "2026-02-18T00:00:00Z",
  "aliases": {
    "cheap": [{"provider": "anthropic", "model": "claude-haiku-4-5"}],
    "balanced": [{"provider": "anthropic", "model": "claude-sonnet-4-6"}],
    "frontier": [{"provider": "openai", "model": "gpt-5.2"}],
    "code_frontier": [{"provider": "openai", "model": "gpt-5-codex"}]
  },
  "raw_catalog": {
    "anthropic": [],
    "openai": [],
    "google": []
  }
}
```

## Rules

1. Skills reference aliases only.
2. Registry is refreshed by `scripts/ops/sync-model-registry.sh`.
3. Documentation model table is generated from this file.
