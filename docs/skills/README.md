# Skills Guide

This page is the operational index for all backlog toolkit skills.

## Active Skills

| Skill | Trigger Command | When to Use | Input | Output |
|---|---|---|---|---|
| `backlog-init` | `/backlog-toolkit:init` | New project setup | Project context + preferences | Backlog structure + config + templates |
| `backlog-ticket` | `/backlog-toolkit:ticket "..."` | Convert request into an implementable ticket | User request + repo context | Validated ticket in `backlog/data/pending/` |
| `backlog-refinement` | `/backlog-toolkit:refinement` | Backlog hygiene and consistency checks | Pending tickets + codebase | Updated tickets + refinement report |
| `backlog-implementer` | `/backlog-toolkit:implementer` | Execute tickets with quality gates | Pending tickets + config | Code changes + completed tickets + cost trail |

## Planned Skills (Documented Design)

| Skill | Intended Command | Role |
|---|---|---|
| `backlog-orchestrator` | `/backlog-toolkit:orchestrator` | Single entrypoint to route workflows |
| `backlog-cost-governor` | `/backlog-toolkit:cost-governor` | Spend policy checks and budget actions |
| `backlog-batch-operator` | `/backlog-toolkit:batch-operator` | Batch submission and reconciliation |
| `backlog-cache-optimizer` | `/backlog-toolkit:cache-optimizer` | Prompt/cache policy tuning |

## Skill Playbooks

- [backlog-orchestrator](backlog-orchestrator.md)
- [backlog-init](backlog-init.md)
- [backlog-ticket](backlog-ticket.md)
- [backlog-refinement](backlog-refinement.md)
- [backlog-implementer](backlog-implementer.md)
- [backlog-cost-governor](backlog-cost-governor.md)
- [backlog-batch-operator](backlog-batch-operator.md)
- [backlog-cache-optimizer](backlog-cache-optimizer.md)

## Recommended Usage Pattern

1. Initialize once with `backlog-init`.
2. Create/clarify work with `backlog-ticket`.
3. Keep queue healthy with `backlog-refinement`.
4. Execute implementation with `backlog-implementer`.
5. (Planned) move to single-entry orchestration with `backlog-orchestrator`.
