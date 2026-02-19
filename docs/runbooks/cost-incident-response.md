# Runbook: Cost Incident Response

## Trigger

- Daily spend spikes above threshold.
- Unexpected frontier model usage.

## Response Target

Resolve within 10 minutes.

## Steps

1. Check latest ledger entries.
2. Identify top spend by workflow/phase.
3. Enforce temporary routing caps.
4. Disable non-essential frontier escalation.
5. Re-run workload in batch if applicable.

## Commands

```bash verify
./scripts/ops/cost_guard.py --ledger .backlog-ops/usage-ledger.jsonl --warn 0.70 --hard-stop 1.00
```

## Exit Criteria

- Spend returns below warning threshold.
- Escalation reasons are documented.
