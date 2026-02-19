#!/usr/bin/env python3
"""Validate required documentation files and skill doc section coverage."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"

REQUIRED_FILES = [
    "README.md",
    "tutorials/quickstart-cloud-only.md",
    "tutorials/daily-flow.md",
    "architecture/system-overview.md",
    "architecture/adr/ADR-001-orchestrator-entrypoint.md",
    "architecture/adr/ADR-002-script-first-llm-second.md",
    "architecture/adr/ADR-003-model-routing-aliases.md",
    "architecture/adr/ADR-004-multilayer-caching-and-batch.md",
    "architecture/adr/ADR-005-rag-augmented-context.md",
    "architecture/adr/ADR-006-deterministic-init.md",
    "skills/backlog-orchestrator.md",
    "skills/backlog-init.md",
    "skills/backlog-ticket.md",
    "skills/backlog-refinement.md",
    "skills/backlog-implementer.md",
    "skills/backlog-cost-governor.md",
    "skills/backlog-batch-operator.md",
    "skills/backlog-cache-optimizer.md",
    "reference/backlog-config-v1.1.md",
    "reference/model-registry.md",
    "reference/usage-ledger-schema.md",
    "reference/batch-queue-schema.md",
    "reference/litellm-proxy-config.md",
    "reference/rag-pipeline.md",
    "reference/scripts-catalog.md",
    "reference/command-reference.md",
    "runbooks/cost-incident-response.md",
    "runbooks/batch-operations.md",
    "runbooks/cache-optimization.md",
    "runbooks/model-registry-refresh.md",
    "runbooks/litellm-fallback-hotfix.md",
    "troubleshooting/quick-diagnosis.md",
    "contributing/documentation-standards.md",
]

SKILL_HEADERS = [
    "## Purpose",
    "## Inputs",
    "## Outputs",
    "## Internal Flow",
    "## Expected Cost",
    "## Frequent Errors",
]

SCRIPT_PATHS = [
    "scripts/ops/sync-model-registry.sh",
    "scripts/ticket/preflight_context_pack.py",
    "scripts/ticket/validate_ticket.py",
    "scripts/ticket/detect_duplicates.py",
    "scripts/refinement/bulk_refine_plan.py",
    "scripts/implementer/impact_graph.py",
    "scripts/ops/batch_submit.py",
    "scripts/ops/batch_reconcile.py",
    "scripts/ops/cost_guard.py",
    "scripts/ops/prompt_prefix_lint.py",
    "scripts/docs/generate-config-reference.py",
    "scripts/docs/generate-model-table.sh",
    "scripts/docs/check-links.sh",
    "scripts/docs/verify-snippets.sh",
    "scripts/docs/check-doc-coverage.py",
]


def fail(msg: str) -> None:
    raise SystemExit(msg)


for rel in REQUIRED_FILES:
    p = DOCS / rel
    if not p.exists():
        fail(f"Missing required doc file: {p}")

for skill_doc in (DOCS / "skills").glob("*.md"):
    if skill_doc.name == "README.md":
        continue
    text = skill_doc.read_text(encoding="utf-8")
    for header in SKILL_HEADERS:
        if header not in text:
            fail(f"Skill doc missing header '{header}': {skill_doc}")

for rel in SCRIPT_PATHS:
    p = ROOT / rel
    if not p.exists():
        fail(f"Missing required script: {p}")

schema_path = ROOT / "config" / "backlog.config.schema.json"
doc_path = DOCS / "reference" / "backlog-config-v1.1.md"
schema = json.loads(schema_path.read_text(encoding="utf-8"))
doc_text = doc_path.read_text(encoding="utf-8")

for top_key in schema.get("properties", {}).keys():
    token = f"`{top_key}`"
    if token not in doc_text:
        fail(
            "Schema key not documented in backlog-config-v1.1.md: "
            f"{top_key}"
        )

print("Documentation coverage checks passed.")
