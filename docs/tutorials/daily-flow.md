# Daily Operator Flow

Structured daily workflow for efficient Claude Code usage with the backlog toolkit.

## Morning Preflight (2 min)

Run deterministic checks before any LLM call:

```bash
# 1. Refresh model registry (keeps aliases current)
./scripts/ops/sync-model-registry.sh

# 2. Check cost posture
./scripts/ops/cost_guard.py --ledger .backlog-ops/usage-ledger.jsonl

# 3. Quick doc validation
./scripts/docs/check-links.sh
```

**Decision gate**: If cost_guard returns `"state": "warning"`, switch all work to cheap model or batch mode.

## Working Session

### Creating Tickets

```bash
# Run scripts FIRST to minimize LLM tokens
./scripts/ticket/detect_duplicates.py backlog/data/pending/NEW-TICKET.md

# Then create via skill (uses codebase context efficiently)
/backlog-toolkit:ticket "Add password reset flow"
```

**Token-saving tip**: Provide detailed descriptions up front. A 50-word request saves ~30% tokens vs a vague 5-word request that requires back-and-forth.

### Refining the Backlog

```bash
# 1. Triage into cost buckets (deterministic, zero tokens)
python scripts/refinement/bulk_refine_plan.py

# 2. Run refinement skill (only on tickets needing LLM review)
/backlog-toolkit:refinement
```

### Implementing Tickets

```bash
# 1. Build impact graph before implementation (zero tokens)
./scripts/implementer/impact_graph.py src/auth.ts src/middleware.ts

# 2. Run implementer (uses routing: balanced model for code, cheap for review)
/backlog-toolkit:implementer
```

### Batch Operations (non-interactive work)

For bulk validation, dedup checks, and refinement:

```bash
# 1. Prepare batch queue
./scripts/refinement/bulk_refine_plan.py > tmp/batch-queue.jsonl

# 2. Submit (50% cheaper than interactive)
./scripts/ops/batch_submit.py --queue tmp/batch-queue.jsonl

# 3. Reconcile later
./scripts/ops/batch_reconcile.py --queue tmp/batch-queue.jsonl
```

## End of Day (2 min)

```bash
# 1. Cost report
./scripts/ops/cost_guard.py --ledger .backlog-ops/usage-ledger.jsonl

# 2. Cache health
./scripts/ops/prompt_prefix_lint.py --manifest .backlog-ops/prompt-manifest.json

# 3. Doc coverage (catch any drift)
./scripts/docs/check-doc-coverage.py
```

## Weekly Review

```bash
# Full validation suite
make validate

# Refresh all artifacts
make refresh

# Review frontier escalations (should be <5%)
grep '"escalation_reason"' .backlog-ops/usage-ledger.jsonl | grep -v null | wc -l

# Review cache hit rate (target ≥60%)
grep '"cache_hit":true' .backlog-ops/usage-ledger.jsonl | wc -l
grep '"cache_hit":false' .backlog-ops/usage-ledger.jsonl | wc -l
```

## Quick Reference: Script-First Checklist

Before each LLM call, ask: **can a script do this?**

| Before This LLM Call... | Run This Script First |
|--------------------------|----------------------|
| Creating a ticket | `detect_duplicates.py` + `preflight_context_pack.py` |
| Refining backlog | `bulk_refine_plan.py` |
| Implementing ticket | `impact_graph.py` |
| Checking costs | `cost_guard.py` |
| Validating prompts | `prompt_prefix_lint.py` |
| Validating tickets | `validate_ticket.py` |
