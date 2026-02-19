# ADR-002: Script-First, LLM-Second

## Status
Accepted

## Decision
All deterministic tasks must execute via scripts before LLM invocation.

## Rationale

- Lower cost.
- Lower latency for repetitive tasks.
- Better reproducibility.

## Consequences

- Script catalog is mandatory and versioned.
- LLM calls need traceable justification when deterministic alternatives exist.
