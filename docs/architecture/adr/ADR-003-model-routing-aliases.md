# ADR-003: Routing by Model Aliases

## Status
Accepted

## Decision
Use aliases (`cheap`, `balanced`, `frontier`) resolved from model registry at runtime.

## Rationale

- Prevents hardcoded stale model IDs.
- Enables dynamic provider/model swaps.
- Simplifies policy rules in skills.

## Consequences

- Registry sync script is mandatory.
- Routing policy references aliases, never raw model IDs.
