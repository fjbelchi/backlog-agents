# backlog-implementer

## Purpose

Execute ticket implementation with quality gates and traceable completion metadata.

## Inputs

- Ticket file(s)
- Config quality gates
- Code rules and review settings

## Outputs

- Code/test changes
- Enriched completed ticket
- Cost and review metadata

## Internal Flow

1. Plan from ticket and affected files.
2. Implement with TDD and lint/test gates.
3. Review and fix cycles.
4. Commit, enrich ticket, and move to completed.

## Expected Cost

Highest among core skills; controlled with model alias routing and escalation caps.

## Frequent Errors

- Unclear ticket scope.
- Repeated review loops.
- Gate command failures.
