# ADR-001: Orchestrator as Single Entrypoint

## Status
Accepted

## Decision
`backlog-orchestrator` is the default and recommended entrypoint for all workflows.

## Rationale

- Reduces operator decision overhead.
- Centralizes policy enforcement.
- Improves consistency in cost and quality controls.

## Consequences

- Other skills remain callable but are treated as internal workflow components.
- Command reference must prioritize orchestrator usage.
