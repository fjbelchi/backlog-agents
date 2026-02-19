.PHONY: help setup validate test refresh cost ops clean docker-up docker-down docker-logs docker-ps rag-status rag-index rag-search rag-clear

SHELL := /bin/bash
LEDGER ?= .backlog-ops/usage-ledger.jsonl
REGISTRY ?= .backlog-ops/model-registry.json
BUDGET ?= 1000

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ─── Setup ──────────────────────────────────────────────────────────

setup: ## First-time setup: create ops directories and initialize artifacts
	@mkdir -p .backlog-ops tmp
	@chmod +x scripts/ops/*.py scripts/ops/*.sh scripts/services/*.sh scripts/docs/*.py scripts/docs/*.sh 2>/dev/null || true
	@./scripts/ops/sync-model-registry.sh --output $(REGISTRY)
	@touch $(LEDGER)
	@echo "✓ .backlog-ops/ initialized"

# ─── Validation ─────────────────────────────────────────────────────

validate: validate-docs validate-config ## Run ALL validation checks
	@echo "✓ All validations passed"

validate-docs: ## Validate documentation (links, coverage, snippets)
	@./scripts/docs/check-links.sh
	@./scripts/docs/check-doc-coverage.py
	@./scripts/docs/verify-snippets.sh
	@echo "✓ Docs validated"

validate-config: ## Validate config schema and templates
	@./tests/test-config-schema.sh
	@./tests/test-templates.sh
	@echo "✓ Config validated"

# ─── Test ───────────────────────────────────────────────────────────

test: ## Run all tests
	@./tests/test-config-schema.sh
	@./tests/test-templates.sh
	@./tests/test-install.sh
	@echo "✓ All tests passed"

# ─── Refresh ────────────────────────────────────────────────────────

refresh: refresh-registry refresh-docs ## Refresh all generated artifacts
	@echo "✓ All artifacts refreshed"

refresh-registry: ## Refresh model registry
	@./scripts/ops/sync-model-registry.sh --output $(REGISTRY)

refresh-docs: ## Regenerate documentation references
	@./scripts/docs/generate-config-reference.py
	@./scripts/docs/generate-model-table.sh
	@echo "✓ Docs refreshed"

# ─── Cost & Ops ─────────────────────────────────────────────────────

cost: ## Check current cost posture
	@./scripts/ops/cost_guard.py --ledger $(LEDGER) --budget $(BUDGET)

cost-warn: ## Cost check with warning threshold
	@./scripts/ops/cost_guard.py --ledger $(LEDGER) --budget $(BUDGET) --warn 0.70 --hard-stop 1.00

ops: cost cache-lint ## Full ops health check
	@echo "✓ Ops check complete"

cache-lint: ## Lint prompt prefixes for cache compatibility
	@test -f .backlog-ops/prompt-manifest.json && \
		./scripts/ops/prompt_prefix_lint.py --manifest .backlog-ops/prompt-manifest.json || \
		echo "⚠ No prompt manifest found. Create .backlog-ops/prompt-manifest.json first."

# ─── Batch ──────────────────────────────────────────────────────────

batch-submit: ## Submit queued batch jobs
	@./scripts/ops/batch_submit.py

batch-reconcile: ## Reconcile batch job results
	@./scripts/ops/batch_reconcile.py

batch-cycle: batch-submit batch-reconcile ## Full batch submit + reconcile cycle
	@echo "✓ Batch cycle complete"

# ─── Refinement ─────────────────────────────────────────────────────

refine-plan: ## Triage pending tickets into cost buckets (no-llm/cheap/frontier)
	@python scripts/refinement/bulk_refine_plan.py

# ─── Clean ──────────────────────────────────────────────────────────

clean: ## Remove temporary files
	@rm -rf tmp/*
	@echo "✓ tmp/ cleaned"

# ─── Docker ────────────────────────────────────────────────────────

docker-up: ## Start infrastructure (Docker)
	@test -f .env.docker.local || (echo "Creating .env.docker.local from template..." && cp .env.docker .env.docker.local)
	docker compose --env-file .env.docker.local up -d --build

docker-down: ## Stop infrastructure (Docker)
	docker compose --env-file .env.docker.local down

docker-logs: ## Tail Docker logs
	docker compose --env-file .env.docker.local logs -f

docker-ps: ## Show Docker service status
	docker compose --env-file .env.docker.local ps

# ─── RAG ────────────────────────────────────────────────────────────

rag-status: ## Show RAG index stats for current project
	@source scripts/rag/client.sh && rag_status | python3 -m json.tool

rag-index: ## Index project files into RAG (make rag-index DIR=./src)
	@source scripts/rag/client.sh && rag_index_dir "$(or $(DIR),.)"

rag-search: ## Search RAG index (make rag-search QUERY="auth logic")
	@test -n "$(QUERY)" || (echo "Usage: make rag-search QUERY=\"auth logic\"" && exit 1)
	@source scripts/rag/client.sh && rag_search "$(QUERY)" | python3 -m json.tool

rag-clear: ## Clear RAG index for current project (make rag-clear [PROJECT=name])
	@source scripts/rag/client.sh && rag_clear "$(PROJECT)"
