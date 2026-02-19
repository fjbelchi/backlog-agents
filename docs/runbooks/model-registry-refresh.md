# Runbook: Model Registry Refresh

## Goal

Keep model aliases current without manual hardcoding.

## Steps

1. Refresh provider model catalogs.
2. Regenerate local registry aliases.
3. Regenerate model table docs.
4. Validate docs links and coverage.

## Commands

```bash verify
mkdir -p tmp
./scripts/ops/sync-model-registry.sh --output tmp/model-registry.json
./scripts/docs/generate-model-table.sh
./scripts/docs/check-links.sh
```

## Frequency

- Daily for active environments.
- Mandatory before releases.
