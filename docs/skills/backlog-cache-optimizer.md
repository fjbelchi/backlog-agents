# backlog-cache-optimizer

## Purpose

Improve cache efficiency through prompt-prefix normalization and cache policy tuning.

## Inputs

- Prompt manifest
- Usage ledger cache fields
- Cache policy settings

## Outputs

- Cache findings report
- Prompt lint violations
- Suggested prefix/TTL adjustments

## Internal Flow

1. Parse prompt manifests and usage logs.
2. Detect cache-breaking prompt variation.
3. Recommend standardization and policy updates.

## Expected Cost

Very low; deterministic analysis with optional cheap-model summary.

## Frequent Errors

- Missing prompt manifest.
- Inconsistent prompt versioning.
