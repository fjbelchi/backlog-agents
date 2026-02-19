# Quick Diagnosis

## Symptoms → Actions

### 1. High cost spike

```bash
# Check budget status
./scripts/ops/cost_guard.py --ledger .backlog-ops/usage-ledger.jsonl --warn 0.70 --hard-stop 1.00

# Detailed breakdown: which model/workflow is burning money?
python scripts/ops/cost_report.py --ledger .backlog-ops/usage-ledger.jsonl --days 1

# Check for frontier escalations (should be <5%)
grep '"escalation_reason"' .backlog-ops/usage-ledger.jsonl | grep -v null | tail -10
```

**Fix**: If frontier ratio is high, check `llmOps.routing.maxEscalationsPerTicket` and reduce. Switch bulk work to batch mode.

### 2. Low cache hit rate (<60%)

```bash
# Check cache stats
grep '"cache_hit"' .backlog-ops/usage-ledger.jsonl | sort | uniq -c

# Lint prompt prefixes for inconsistencies
./scripts/ops/prompt_prefix_lint.py --manifest .backlog-ops/prompt-manifest.json
```

**Fix**: Ensure system prompt prefix is byte-identical across calls. Move dynamic content (ticket data, file contents) after the stable prefix. See [Cache Optimization Runbook](../runbooks/cache-optimization.md).

### 3. Batch backlog not draining

```bash
# Check queue status
cat tmp/batch-queue.jsonl | python -c "import sys,json;[print(json.loads(l).get('status','?')) for l in sys.stdin]" | sort | uniq -c

# Force reconcile
./scripts/ops/batch_reconcile.py --queue tmp/batch-queue.jsonl
```

**Fix**: Check provider batch API status. Verify API keys are valid. Check `batchPolicy.retryPolicy.maxRetries`.

### 4. Docs validation failure

```bash
./scripts/docs/check-links.sh
./scripts/docs/check-doc-coverage.py
```

**Fix**: Update broken links. Add missing doc coverage for new scripts/skills.

### 5. Config schema validation failure

```bash
./tests/test-config-schema.sh
```

**Fix**: If migrating from v1.0 to v1.1, update `"version": "1.1"` and add `llmOps` block. Use `config/presets/default.json` as reference.

### 6. RAG index stale or missing

```bash
# Check index age
python scripts/ops/rag_index.py --stats

# Rebuild
python scripts/ops/rag_index.py --rebuild
```

**Fix**: Add reindex to your CI/CD pipeline or run weekly. Set `ragPolicy.reindexCommand` in config.

## Fast Command Set

```bash
# Full health check in 30 seconds
make ops                    # cost + cache lint
make validate               # docs + config
./tests/test-config-schema.sh
./tests/test-templates.sh
```
