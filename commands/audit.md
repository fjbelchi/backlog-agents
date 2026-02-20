# Command: /backlog-toolkit:audit

Full project health audit with cascading Haiku→Sonnet→Opus funnel.
Scans entire codebase across 6 dimensions (architecture, security, bugs, performance, tests, hygiene).
Creates validated backlog tickets for every finding. 15-call budget, $1.50-3.00 for ~3000 files.

## Syntax

```
/backlog-toolkit:audit
```

## Examples

### Full audit
```
/backlog-toolkit:audit
```

## What it does

1. **Prescan** (deterministic, $0): 12 checks on all project files -- catches 70-80% of findings
2. **Haiku sweep** (4 agents, ~$0.50): reads ALL source files in mega-chunks, flags suspects
3. **Sonnet deep** (1-3 agents, ~$0.30-0.80): validates suspects in batch + discovers new issues
4. **Opus critical** (0-1 agent, ~$0-0.90): 6-point checklist on escalated findings only
5. **RAG dedup** ($0): skips findings that already have tickets
6. **Haiku tickets** (1-2 agents, ~$0.30): batch writes multiple ticket files per agent

## Configuration

```json
{
  "audit": {
    "enabled": true,
    "prescan": {
      "extensions": [".ts", ".tsx", ".js", ".jsx", ".py"],
      "excludeDirs": ["node_modules", "dist", "coverage"],
      "maxFunctionLines": 80,
      "coverageThreshold": 70,
      "complexityThreshold": 10
    },
    "dimensions": ["architecture", "security", "bugs", "performance", "tests", "hygiene"],
    "ragDeduplication": true,
    "ticketMapping": { "security": "SEC", "bugs": "BUG" }
  }
}
```

## Related

- Skill: `skills/backlog-audit/SKILL.md`
- Prescan: `scripts/ops/audit_prescan.py`
- Design: `docs/plans/2026-02-20-backlog-audit-design.md`
