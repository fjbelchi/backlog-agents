# batch-queue.jsonl Schema

## Purpose

Queue of deferred/non-interactive jobs eligible for batch execution.

## Location

`.backlog-ops/batch-queue.jsonl`

## Record Schema

```json
{
  "id": "job-20260218-0001",
  "workflow": "refinement",
  "phase": "bulk-validation",
  "payload_path": "tmp/refinement-input.jsonl",
  "provider": "anthropic",
  "model_alias": "cheap",
  "status": "queued",
  "attempts": 0,
  "created_at": "2026-02-18T00:00:00Z",
  "updated_at": "2026-02-18T00:00:00Z",
  "result_path": null,
  "error": null
}
```

## Status Values

- `queued`
- `submitted`
- `running`
- `completed`
- `failed`
