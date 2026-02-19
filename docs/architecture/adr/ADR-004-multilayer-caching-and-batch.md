# ADR-004: Multi-Layer Caching and Batch

## Status
Accepted

## Decision
Use provider prompt caching + response/semantic cache + batch offloading for non-interactive workloads.

## Rationale

- Maximizes token reuse.
- Lowers per-request cost.
- Improves throughput for background tasks.

## Consequences

- Prompt prefix consistency becomes a hard requirement.
- Batch reconciliation runbook is required for production operations.
