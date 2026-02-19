# Command Reference

## Recommended Default Command

`/backlog-toolkit:orchestrator` is the recommended default interface.

## Active Commands (Current Repository)

| Command | Purpose | Status |
|---|---|---|
| `/backlog-toolkit:init` | Initialize backlog structure/configuration | Active |
| `/backlog-toolkit:ticket` | Create validated tickets | Active |
| `/backlog-toolkit:refinement` | Refine pending tickets | Active |
| `/backlog-toolkit:implementer` | Execute implementation workflow | Active |

## Planned Commands (Documented)

| Command | Purpose | Status |
|---|---|---|
| `/backlog-toolkit:orchestrator` | Single entrypoint orchestration | Planned |
| `/backlog-toolkit:cost-governor` | Cost policy and budget checks | Planned |
| `/backlog-toolkit:batch-operator` | Batch queue execution | Planned |
| `/backlog-toolkit:cache-optimizer` | Prompt/cache tuning workflow | Planned |

## Common Operator Flows

1. Create ticket.
2. Run refinement in bulk mode.
3. Implement selected ticket.
4. Run offline batch jobs.
5. Run aggressive cost control check.
