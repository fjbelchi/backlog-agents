# Command: /backlog-toolkit:audit

Full project health audit with 5-phase tiered model funnel.
Scans entire codebase across 6 dimensions (architecture, security, bugs, performance, tests, hygiene).
Creates validated backlog tickets for every finding.

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
2. **Haiku sweep** (LLM, ~$0.10): semantic analysis of every module across 6 dimensions
3. **Sonnet deep** (LLM, ~$0.50): validates high-severity findings, adds root cause + fix
4. **Opus critical** (LLM, ~$0.30): 6-point checklist for critical/security patterns only
5. **RAG dedup** ($0): skips findings that already have tickets
6. **Tickets**: every validated finding -> backlog ticket with cost estimate

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
