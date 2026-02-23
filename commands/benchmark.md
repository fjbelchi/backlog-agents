# Command: /backlog-toolkit:benchmark

Benchmark skill cost and quality against Opus baseline. Monitor LiteLLM spend.

## Syntax

```
/backlog-toolkit:benchmark run <ticket-id>       — Benchmark a ticket (Opus baseline + skill comparison)
/backlog-toolkit:benchmark start [name]           — Mark benchmark start (capture LiteLLM snapshot)
/backlog-toolkit:benchmark stop [name]            — Mark benchmark stop (capture + generate report)
/backlog-toolkit:benchmark report [--days N]      — Cost dashboard from LiteLLM logs (default: 7 days)
/backlog-toolkit:benchmark compare <run-a> <run-b> — Compare two benchmark runs
```

## Examples

### Full benchmark with Opus baseline
```
/backlog-toolkit:benchmark run BUG-20260220-003
```

### Manual markers (when skill runs in another session)
```
/backlog-toolkit:benchmark start my-test
# ... run skill in another session ...
/backlog-toolkit:benchmark stop my-test
```

### Cost dashboard
```
/backlog-toolkit:benchmark report --days 3
```

## Output

Reports written to `.backlog-ops/benchmarks/` with cost tables, model breakdowns,
quality scores, and recommendations.

## Related

- Skill: `skills/backlog-benchmark/SKILL.md`
- Design: `docs/plans/2026-02-23-backlog-benchmark-design.md`
