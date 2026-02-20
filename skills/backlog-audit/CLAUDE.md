# Backlog Audit Skill

## Purpose

Full project health audit. Scans entire codebase across 6 dimensions using a 5-phase tiered model funnel.
Deterministic prescan catches 70-80% of findings at $0. LLM phases use Haiku -> Sonnet -> Opus progression.
Creates validated backlog tickets for every finding.

## Key Features

1. **12-Check Deterministic Prescan**: secrets, TODOs, debug, mock data, long functions, dep vulns, coverage, dead code, complexity, duplicates, file size, type safety -- all at $0
2. **Haiku Sweep**: Semantic analysis of every module for architecture, security, bugs, performance, threading, test quality
3. **Sonnet Deep Analysis**: Validates and enriches high-severity findings with root cause and fix
4. **Opus Critical Review**: 6-point checklist for security/serialization/auth/concurrency patterns
5. **RAG Deduplication**: Prevents duplicate tickets across audits
6. **Ticket Integration**: Every finding -> validated ticket via backlog-ticket logic

## Invocation

```bash
/backlog-toolkit:audit
```

## Flow Overview

```
Phase 0:   audit_prescan.py   -> 12 deterministic checks, $0
Phase 0.5: RAG lookups         -> architecture rules, past findings, $0
Phase 1:   Haiku sweep         -> parallel module analysis, ~$0.10
Phase 2:   Sonnet deep         -> validate high-severity findings, ~$0.50
Phase 3:   Opus critical       -> 6-point checklist for critical only, ~$0.30
Phase 3.5: RAG dedup           -> skip existing tickets, $0
Phase 4:   Ticket creation     -> backlog tickets + summary report
```

## Cost Model

```
Prescan (12 checks): $0.00
RAG context:         $0.00
Haiku sweep:         ~$0.10  (parallel, cheap)
Sonnet deep:         ~$0.50  (medium+ severity only)
Opus critical:       ~$0.30  (critical/security only)
Ticket creation:     ~$0.05  (Sonnet write-agents)
-----------------------------------------
Per audit (50 files): ~$0.95-2.50
```

## Related Files

- `SKILL.md`: Full skill implementation
- `scripts/ops/audit_prescan.py`: 12-check deterministic prescan
- `docs/plans/2026-02-20-backlog-audit-design.md`: Design rationale
- `docs/plans/2026-02-20-backlog-audit-plan.md`: Implementation plan
