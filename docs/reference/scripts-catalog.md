# Scripts Catalog (Deterministic First)

Each script is designed to reduce avoidable LLM usage.

## Core Operational Scripts

| Script | Purpose | Input | Output | Fallback if fails |
|---|---|---|---|---|
| `scripts/ops/sync-model-registry.sh` | Refresh model aliases | Provider APIs | `model-registry.json` | Keep last known good registry |
| `scripts/ops/cost_guard.py` | Budget policy checks | Usage ledger | Cost alert report | Hard-stop expensive routes |
| `scripts/ops/cost_report.py` | Detailed cost analytics | Usage ledger | KPI report + breakdown | Fall back to cost_guard |
| `scripts/ops/prompt_prefix_lint.py` | Enforce cache-friendly prompts | Prompt manifest | Lint findings | Auto-normalize prefixes |
| `scripts/ops/batch_submit.py` | Submit batch jobs | Queue file | Provider job ids | Retry with backoff |
| `scripts/ops/batch_reconcile.py` | Reconcile batch results | Queue file + responses | Updated queue statuses | Mark failed and escalate |
| `scripts/ops/rag_index.py` | Build/query RAG code index | Source files | Chunk index (JSONL) | Fall back to glob/grep |

## Ticket Scripts

| Script | Purpose | Input | Output | Fallback if fails |
|---|---|---|---|---|
| `scripts/ticket/preflight_context_pack.py` | Build compact context pack | Ticket intent + repo | JSON context pack | Escalate to minimal LLM context scan |
| `scripts/ticket/validate_ticket.py` | Validate ticket structure/content | Ticket file | Validation report | Re-run with strict mode off |
| `scripts/ticket/detect_duplicates.py` | Detect likely duplicates | Ticket + backlog dir | Similarity matches | Flag for human review |

## Implementer Scripts

| Script | Purpose | Input | Output | Fallback if fails |
|---|---|---|---|---|
| `scripts/implementer/impact_graph.py` | Build blast radius graph | File set | Dependency impact map | Use grep-based fallback |

## Init Scripts

| Script | Purpose | Input | Output | Fallback if fails |
|---|---|---|---|---|
| `scripts/init/backlog_init.py` | Deterministic project initialization | Project root + flags | backlog/ structure + config | Fall back to LLM skill |

## Refinement Scripts

| Script | Purpose | Input | Output | Fallback if fails |
|---|---|---|---|---|
| `scripts/refinement/bulk_refine_plan.py` | Classify refinement queue | Pending tickets | Work buckets | Send all to cheap model |

## Example CLI Calls

```bash
# Ops
./scripts/ops/sync-model-registry.sh --output tmp/model-registry.json
./scripts/ops/cost_guard.py --ledger .backlog-ops/usage-ledger.jsonl
python scripts/ops/cost_report.py --ledger .backlog-ops/usage-ledger.jsonl --days 7
python scripts/ops/rag_index.py --rebuild
python scripts/ops/rag_index.py --query "authentication middleware" --json

# Tickets
./scripts/ticket/validate_ticket.py templates/feature-template.md
./scripts/ticket/detect_duplicates.py backlog/data/pending/FEAT-001.md

# Init (zero tokens — replaces LLM-based init)
python scripts/init/backlog_init.py --yes --llmops
python scripts/init/backlog_init.py --name my-app --stack python --dry-run

# Implementer
./scripts/implementer/impact_graph.py src/auth.ts src/middleware.ts

# Refinement
python scripts/refinement/bulk_refine_plan.py
```
