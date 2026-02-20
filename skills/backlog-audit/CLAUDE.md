# Backlog Audit Skill

## Purpose

Full project health audit. Scans entire codebase across 6 dimensions using a cascading Haiku→Sonnet→Opus funnel.
Deterministic prescan catches 70-80% of findings at $0. Each LLM tier does real work and passes only suspect items up.
Creates validated backlog tickets for every finding.

## Key Features

1. **12-Check Deterministic Prescan**: secrets, TODOs, debug, mock data, long functions, dep vulns, coverage, dead code, complexity, duplicates, file size, type safety -- all at $0
2. **Haiku Full Sweep**: 4 mega-chunk agents read ALL source files, flag suspects for Sonnet
3. **Sonnet Deep Analysis**: Validates Haiku suspects in batch + discovers new issues on suspect files
4. **Opus Critical Review**: 6-point checklist on Sonnet escalations + own deep analysis
5. **RAG Deduplication**: Prevents duplicate tickets across audits
6. **Haiku Ticket Writer**: Batch writes multiple tickets per agent

## Invocation

```bash
/backlog-toolkit:audit
```

## Flow Overview

```
Phase 0:   audit_prescan.py   -> 12 deterministic checks, $0
Phase 0.5: RAG lookups         -> architecture rules, past findings, $0
Phase 1:   Haiku sweep         -> 4 mega-chunk agents, all files, ~$0.50
Phase 2:   Sonnet deep         -> 1-3 agents, suspects only, ~$0.30-0.80
Phase 3:   Opus critical       -> 0-1 agent, escalated only, ~$0-0.90
Phase 3.5: RAG dedup           -> skip existing tickets, $0
Phase 4:   Haiku tickets       -> 1-2 agents, batch write, ~$0.30
```

## Cost Model

```
Prescan (12 checks): $0.00
RAG context:         $0.00
Haiku sweep:         ~$0.50  (4 agents, all files)
Sonnet deep:         ~$0.30-0.80  (1-3 agents, suspects only)
Opus critical:       ~$0-0.90  (0-1 agent, escalated only)
Haiku tickets:       ~$0.30  (1-2 agents)
-----------------------------------------
Per audit (3000 files): ~$1.50-3.00
```

## Call Budget

15 API calls max. NEVER spawn one agent per finding. ALWAYS batch.

## Related Files

- `SKILL.md`: Full skill implementation
- `scripts/ops/audit_prescan.py`: 12-check deterministic prescan
- `docs/plans/2026-02-20-backlog-audit-design.md`: Design rationale
- `docs/plans/2026-02-20-backlog-audit-plan.md`: Implementation plan
