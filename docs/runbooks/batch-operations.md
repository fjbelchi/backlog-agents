# Runbook: Batch Operations

## Scope

Operational procedure for non-interactive batch jobs. Batch API provides **50% cost reduction** over interactive requests with ≤24h SLA.

## When to Use Batch

| Workflow | Interactive? | Batch Eligible? | Cost Savings |
|----------|-------------|----------------|-------------|
| Ticket creation | Yes (needs user input) | No | - |
| Ticket validation | No | **Yes** | 50% |
| Bulk refinement | No | **Yes** | 50% |
| Duplicate detection | No | **Yes** | 50% |
| Cost reporting | No | **Yes** | 50% |
| Implementation | Yes (needs quality gates) | No | - |
| Code review | Partially | Partially | 25% |

## Steps

### 1. Triage Pending Work into Buckets

```bash
# Classify tickets by LLM cost requirement (zero tokens)
python scripts/refinement/bulk_refine_plan.py
```

Output: `{"no-llm": [...], "cheap-llm": [...], "requires-frontier": [...]}`

### 2. Build Batch Queue

Items in `cheap-llm` bucket are ideal for batch execution.

Queue format (`.backlog-ops/batch-queue.jsonl`):
```json
{"id": "job-20260218-0001", "workflow": "refinement", "phase": "bulk-validation", "payload_path": "tmp/refinement-input.jsonl", "provider": "anthropic", "model_alias": "cheap", "status": "queued", "attempts": 0, "created_at": "2026-02-18T00:00:00Z", "updated_at": "2026-02-18T00:00:00Z", "result_path": null, "error": null}
```

### 3. Submit Batch Jobs

```bash
./scripts/ops/batch_submit.py --queue tmp/batch-queue.jsonl
```

### 4. Poll and Reconcile

```bash
# Can be run periodically until all jobs complete
./scripts/ops/batch_reconcile.py --queue tmp/batch-queue.jsonl
```

### 5. Full Cycle (Shortcut)

```bash
make batch-cycle
```

## Configuration

In `backlog.config.json`:
```json
{
  "llmOps": {
    "batchPolicy": {
      "enabled": true,
      "eligiblePhases": ["refinement", "bulk-ticket-validation", "cost-report", "duplicate-detection"],
      "forceBatchWhenQueueOver": 25,
      "maxConcurrentBatchJobs": 10,
      "retryPolicy": {
        "maxRetries": 3,
        "backoffMultiplier": 2.0
      }
    }
  }
}
```

## Failure Policy

| Failure Type | Action | Max Retries |
|-------------|--------|-------------|
| Transient (timeout, 429) | Retry with exponential backoff | 3 |
| Persistent (400, 422) | Mark failed, fix payload | 1 |
| Provider outage | Pause queue, alert operator | 0 |

## Exit Criteria

- All queued items reach `completed` or `failed` status
- Failed items are documented with error details
- Cost savings logged in usage ledger
