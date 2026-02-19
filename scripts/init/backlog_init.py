#!/usr/bin/env python3
"""Deterministic backlog-init: scaffolds backlog structure with zero LLM tokens.

Replaces the LLM-powered backlog-init skill for the common case where
stack detection and scaffolding are fully deterministic.

Usage:
    # Auto-detect everything
    python scripts/init/backlog_init.py

    # Explicit flags
    python scripts/init/backlog_init.py --name my-app --stack typescript

    # Non-interactive (CI/CD)
    python scripts/init/backlog_init.py --yes

    # Include v1.1 llmOps block
    python scripts/init/backlog_init.py --llmops
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

# ──────────────────────────────────────────────
# Stack detection: manifest file → stack name
# ──────────────────────────────────────────────

STACK_INDICATORS: list[tuple[list[str], str]] = [
    # Order matters: first match wins
    (["package.json", "tsconfig.json"], "typescript"),
    (["package.json"], "javascript"),
    (["pyproject.toml"], "python"),
    (["setup.py"], "python"),
    (["requirements.txt"], "python"),
    (["go.mod"], "go"),
    (["Cargo.toml"], "rust"),
    (["Package.swift"], "swift"),
]

# Quality gate commands per stack (from SKILL.md table)
QUALITY_GATES: dict[str, dict[str, str]] = {
    "typescript": {
        "typeCheckCommand": "npx tsc --noEmit",
        "lintCommand": "npx eslint .",
        "testCommand": "npx vitest run",
    },
    "javascript": {
        "lintCommand": "npx eslint .",
        "testCommand": "npx vitest run",
    },
    "python": {
        "typeCheckCommand": "mypy .",
        "lintCommand": "ruff check .",
        "testCommand": "pytest",
    },
    "go": {
        "typeCheckCommand": "go vet ./...",
        "lintCommand": "golangci-lint run",
        "testCommand": "go test ./...",
    },
    "rust": {
        "typeCheckCommand": "cargo check",
        "lintCommand": "cargo clippy -- -D warnings",
        "testCommand": "cargo test",
    },
    "swift": {
        "typeCheckCommand": "swift build",
        "lintCommand": "swiftlint",
        "testCommand": "swift test",
    },
    "generic": {
        "testCommand": "echo 'Configure testCommand in backlog.config.json'",
    },
}

# ──────────────────────────────────────────────
# Stack detection
# ──────────────────────────────────────────────


def detect_stack(root: Path) -> str:
    """Detect project stack from manifest files. Returns stack name."""
    for indicators, stack in STACK_INDICATORS:
        if all((root / f).exists() for f in indicators):
            return stack
    return "generic"


def detect_project_name(root: Path, stack: str) -> str:
    """Attempt to extract project name from manifest. Fall back to dir name."""
    try:
        if stack in ("typescript", "javascript"):
            pkg = json.loads((root / "package.json").read_text(encoding="utf-8"))
            name = pkg.get("name", "")
            if name:
                return name
        elif stack == "python":
            for manifest in ("pyproject.toml",):
                p = root / manifest
                if p.exists():
                    text = p.read_text(encoding="utf-8")
                    for line in text.splitlines():
                        if line.strip().startswith("name"):
                            # Basic TOML name extraction
                            parts = line.split("=", 1)
                            if len(parts) == 2:
                                return parts[1].strip().strip('"').strip("'")
        elif stack == "go":
            mod = root / "go.mod"
            if mod.exists():
                first_line = mod.read_text(encoding="utf-8").splitlines()[0]
                # "module github.com/user/repo" → "repo"
                parts = first_line.split()
                if len(parts) >= 2:
                    return parts[1].rsplit("/", 1)[-1]
        elif stack == "rust":
            cargo = root / "Cargo.toml"
            if cargo.exists():
                for line in cargo.read_text(encoding="utf-8").splitlines():
                    if line.strip().startswith("name"):
                        parts = line.split("=", 1)
                        if len(parts) == 2:
                            return parts[1].strip().strip('"').strip("'")
    except (OSError, json.JSONDecodeError, IndexError):
        pass

    return root.resolve().name


# ──────────────────────────────────────────────
# Config generation
# ──────────────────────────────────────────────


def build_config(
    name: str,
    stack: str,
    prefixes: list[str],
    include_llmops: bool,
) -> dict:
    """Build backlog.config.json content deterministically."""
    gates = QUALITY_GATES.get(stack, QUALITY_GATES["generic"])
    version = "1.1" if include_llmops else "1.0"

    config: dict = {
        "version": version,
        "project": {
            "name": name,
            "stack": stack,
        },
        "backlog": {
            "dataDir": "backlog/data",
            "templatesDir": "backlog/templates",
            "ticketPrefixes": prefixes,
            "requiredSections": [
                "context",
                "description",
                "acceptanceCriteria",
                "testStrategy",
                "affectedFiles",
                "dependencies",
            ],
        },
        "qualityGates": gates,
        "codeRules": {
            "source": ".claude/code-rules.md",
            "hardGates": [],
            "softGates": [],
        },
        "ticketValidation": {
            "requireTestStrategy": True,
            "requireAffectedFiles": True,
            "requireDependencyCheck": True,
            "minAcceptanceCriteria": 3,
            "requireVerificationCommands": True,
        },
    }

    if include_llmops:
        config["llmOps"] = {
            "registry": {
                "path": ".backlog-ops/model-registry.json",
                "refreshCommand": "scripts/ops/sync-model-registry.sh",
            },
            "gateway": {
                "baseURL": "",
                "apiKeyEnv": "LITELLM_API_KEY",
            },
            "routing": {
                "entryModelClassify": "cheap",
                "entryModelDraft": "cheap",
                "entryModelImplement": "balanced",
                "entryModelReview": "cheap",
                "escalationModel": "frontier",
                "maxEscalationsPerTicket": 1,
            },
            "tokenPolicy": {
                "maxInputByPhase": {
                    "classify": 4000,
                    "draft": 8000,
                    "implement": 32000,
                    "review": 16000,
                },
                "maxOutputByPhase": {
                    "classify": 500,
                    "draft": 2000,
                    "implement": 8000,
                    "review": 4000,
                },
            },
            "cachePolicy": {
                "providerPromptCaching": True,
                "stablePrefixMinTokens": 2048,
                "responseCache": {
                    "enabled": True,
                    "ttlSeconds": 3600,
                    "backend": "redis",
                },
                "semanticCache": {
                    "enabled": False,
                    "backend": "qdrant",
                    "threshold": 0.88,
                },
            },
            "batchPolicy": {
                "enabled": True,
                "eligiblePhases": [
                    "refinement",
                    "bulk-ticket-validation",
                    "cost-report",
                    "duplicate-detection",
                ],
                "forceBatchWhenQueueOver": 25,
                "retryPolicy": {
                    "maxRetries": 3,
                    "backoffMultiplier": 2.0,
                },
            },
            "ragPolicy": {
                "enabled": False,
                "embeddingModel": "text-embedding-3-small",
                "vectorStore": "local-faiss",
                "indexPath": ".backlog-ops/rag-index",
                "chunkSize": 512,
                "topK": 10,
                "reindexCommand": "python scripts/ops/rag_index.py --rebuild",
            },
        }

    return config


# ──────────────────────────────────────────────
# Template content (identical to SKILL.md Step 6)
# ──────────────────────────────────────────────

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates"


def get_template_content(template_name: str) -> str:
    """Read template from the plugin's templates/ directory."""
    # Map internal names to actual template files
    mapping = {
        "task-template.md": "task-template.md",
        "bug-template.md": "bug-template.md",
        "feature-template.md": "feature-template.md",
        "idea-template.md": "idea-template.md",
    }
    source = TEMPLATES_DIR / mapping.get(template_name, template_name)
    if source.exists():
        return source.read_text(encoding="utf-8")
    # Fallback: generate minimal template
    prefix = template_name.replace("-template.md", "").upper()
    return f"""---
id: {prefix}-NNN
title: Actionable description
status: pending
priority: medium
created: YYYY-MM-DD
updated: YYYY-MM-DD
assignee: unassigned
blockers: []
depends_on: []
shared_files: []
related_docs: []
---

# {prefix}-NNN: Title

## Context
<!-- Why this is needed -->

## Description
<!-- What needs to be done -->

## Affected Files
| File | Action | Description |
|------|--------|-------------|

## Acceptance Criteria
- [ ] AC-1: ...
- [ ] AC-2: ...
- [ ] AC-3: ...

## Test Strategy
### Verification Commands
```bash
# Commands to verify
```

## Dependencies
| Ticket | What it needs | Status |
|--------|---------------|--------|
"""


def generate_claude_md(project_name: str) -> str:
    """Generate backlog/CLAUDE.md content."""
    return f"""# Backlog System

This directory contains the backlog management system for {project_name}.

## Directory Structure

```
backlog/
├── data/
│   ├── pending/      # Active tickets
│   └── completed/    # Finished tickets
└── templates/        # Ticket templates
```

## Ticket Prefixes

| Prefix | Purpose |
|--------|---------|
| TASK | General implementation work |
| BUG | Defect reports and fixes |
| FEAT | New feature development |
| IDEA | Exploratory ideas and experiments |

## Workflow

1. Create ticket from template → `backlog/data/pending/`
2. Implement with quality gates
3. Move completed ticket → `backlog/data/completed/`
"""


def generate_code_rules(project_name: str) -> str:
    """Generate .claude/code-rules.md content."""
    return f"""# Code Rules for {project_name}

## Hard Gates (must pass, block commit)
- [ ] Define your hard gate rules here

## Soft Gates (should review, can override with justification)
- [ ] Define your soft gate rules here
"""


# ──────────────────────────────────────────────
# Main scaffolding logic
# ──────────────────────────────────────────────


def scaffold(
    root: Path,
    name: str,
    stack: str,
    prefixes: list[str],
    code_rules: bool,
    include_llmops: bool,
    force: bool,
) -> list[str]:
    """Create all backlog files. Returns list of created file paths."""
    created: list[str] = []

    backlog_dir = root / "backlog"
    if backlog_dir.exists() and not force:
        print(f"⚠ backlog/ already exists at {root}. Use --force to overwrite.", file=sys.stderr)
        return []

    # 1. Directories
    for d in ["backlog/data/pending", "backlog/data/completed", "backlog/templates"]:
        (root / d).mkdir(parents=True, exist_ok=True)

    # 2. .gitkeep files
    for gk in ["backlog/data/pending/.gitkeep", "backlog/data/completed/.gitkeep"]:
        p = root / gk
        if not p.exists():
            p.touch()
            created.append(gk)

    # 3. Templates
    prefix_to_template = {
        "TASK": "task-template.md",
        "BUG": "bug-template.md",
        "FEAT": "feature-template.md",
        "IDEA": "idea-template.md",
    }
    for prefix in prefixes:
        tpl_name = prefix_to_template.get(prefix)
        if tpl_name:
            dest = root / "backlog" / "templates" / tpl_name
            dest.write_text(get_template_content(tpl_name), encoding="utf-8")
            created.append(f"backlog/templates/{tpl_name}")

    # 4. backlog/CLAUDE.md
    claude_md = root / "backlog" / "CLAUDE.md"
    claude_md.write_text(generate_claude_md(name), encoding="utf-8")
    created.append("backlog/CLAUDE.md")

    # 5. backlog.config.json
    config = build_config(name, stack, prefixes, include_llmops)
    config_path = root / "backlog.config.json"
    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    created.append("backlog.config.json")

    # 6. .claude/code-rules.md (optional)
    if code_rules:
        rules_dir = root / ".claude"
        rules_dir.mkdir(exist_ok=True)
        rules_path = rules_dir / "code-rules.md"
        rules_path.write_text(generate_code_rules(name), encoding="utf-8")
        created.append(".claude/code-rules.md")

    return created


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Initialize backlog structure deterministically (zero LLM tokens)."
    )
    parser.add_argument("--root", default=".", help="Project root (default: current directory)")
    parser.add_argument("--name", default="", help="Project name (default: auto-detect)")
    parser.add_argument("--stack", default="", help="Stack: typescript|python|go|rust|swift|generic (default: auto-detect)")
    parser.add_argument("--prefixes", default="TASK,BUG,FEAT,IDEA", help="Ticket prefixes (comma-separated)")
    parser.add_argument("--code-rules", action="store_true", default=True, help="Create .claude/code-rules.md (default: yes)")
    parser.add_argument("--no-code-rules", action="store_false", dest="code_rules")
    parser.add_argument("--llmops", action="store_true", help="Include v1.1 llmOps block in config")
    parser.add_argument("--force", action="store_true", help="Overwrite existing backlog/ directory")
    parser.add_argument("--yes", "-y", action="store_true", help="Non-interactive mode (accept all defaults)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be created without writing")
    args = parser.parse_args()

    root = Path(args.root).resolve()

    # Auto-detect
    stack = args.stack or detect_stack(root)
    name = args.name or detect_project_name(root, stack)
    prefixes = [p.strip().upper() for p in args.prefixes.split(",") if p.strip()]

    # Confirm (unless --yes)
    if not args.yes and not args.dry_run:
        print(f"Project:  {name}")
        print(f"Stack:    {stack}")
        print(f"Prefixes: {', '.join(prefixes)}")
        print(f"llmOps:   {'yes' if args.llmops else 'no'}")
        print(f"Root:     {root}")
        print()
        answer = input("Proceed? [Y/n] ").strip().lower()
        if answer and answer != "y":
            print("Aborted.")
            return 0

    if args.dry_run:
        print(f"[dry-run] Would initialize backlog for '{name}' ({stack})")
        print(f"[dry-run] Prefixes: {', '.join(prefixes)}")
        print(f"[dry-run] Config version: {'1.1 (with llmOps)' if args.llmops else '1.0'}")
        return 0

    created = scaffold(root, name, stack, prefixes, args.code_rules, args.llmops, args.force)
    if not created:
        return 1

    # Summary
    print(f"\nBacklog initialized for {name} ({stack})")
    print()
    print("Created:")
    for f in created:
        print(f"  - {f}")
    print()
    print(f"Config version: {'1.1 (with llmOps)' if args.llmops else '1.0'}")
    print()
    print("Next steps:")
    print("  1. Review backlog.config.json")
    print("  2. Add rules to .claude/code-rules.md")
    print("  3. Create first ticket: /backlog-toolkit:ticket \"description\"")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
