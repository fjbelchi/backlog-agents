# usage-ledger.jsonl Schema

## Purpose

Append-only operational cost telemetry per request.

## Location

`.backlog-ops/usage-ledger.jsonl`

## Record Schema

```json
{
  "timestamp": "2026-02-18T00:00:00Z",
  "workflow": "ticket",
  "phase": "generate",
  "ticket_id": "FEAT-001",
  "model_alias": "balanced",
  "provider": "anthropic",
  "model": "claude-sonnet-4-6",
  "input_tokens": 1200,
  "output_tokens": 430,
  "cached_input_tokens": 800,
  "cost_usd": 0.0231,
  "cache_hit": true,
  "batch_job_id": null,
  "escalation_reason": null,
  "status": "ok"
}
```

## Notes

- One JSON object per line.
- Do not rewrite historical entries.
