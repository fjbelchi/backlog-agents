# Backlog Agents -- Reusable Backlog Toolkit for Claude Code

A set of 4 Claude Code skills for managing project backlogs. Stack-agnostic,
config-driven. Handles ticket creation, refinement, and implementation with
Agent Teams.

## Quick Start

```bash
# Install skills
./install.sh                    # global: ~/.claude/skills/
./install.sh --local            # project: .claude/skills/

# Initialize backlog in your project
/backlog-init

# Create a ticket
/backlog-ticket "Add user authentication"

# Refine existing tickets
/backlog-refinement

# Implement tickets
/backlog-implementer
```

## Skills Overview

| Skill | Purpose | Invocation |
|-------|---------|------------|
| backlog-init | Initialize backlog in any project | `/backlog-init` |
| backlog-ticket | Generate validated tickets with 6-check validation | `/backlog-ticket` |
| backlog-refinement | Refine and validate existing tickets | `/backlog-refinement` |
| backlog-implementer | Implement tickets with Agent Teams | `/backlog-implementer` |

### backlog-init

Detects your project stack (TypeScript, Python, Go, Rust, Swift, or generic),
creates the `backlog/` directory structure, writes ticket templates, and
generates `backlog.config.json` with quality gate commands for your stack.

### backlog-ticket

Generates high-quality tickets from a short description. Analyzes the codebase
for context, auto-assigns IDs, fills all template sections with real content,
and runs 6 validation checks: completeness, backlog coherence, inter-ticket
gaps, contract verification, impact analysis, and consistency.

### backlog-refinement

Processes all pending tickets to verify code references still exist, detect
duplicates, validate completeness, update severity, and generate a health
report with a 0-100 score. Moves obsolete tickets to `completed/`.

### backlog-implementer

Orchestrates Agent Teams to implement tickets in parallel waves. Each ticket
passes through 5 quality gates: Plan, TDD (tests first), Lint, Code Review,
and Commit. Enforces two Iron Laws: Commit-Before-Move and Zero-Hacks.

## Configuration

Running `/backlog-init` generates `backlog.config.json` at your project root.
The main sections are:

| Section | Description |
|---------|-------------|
| `project` | Project name and stack (e.g., typescript, python, go) |
| `backlog` | Data directory, templates directory, ticket prefixes, required sections |
| `qualityGates` | Commands for type checking, linting, testing, building |
| `codeRules` | Path to code rules file, hard gates, soft gates |
| `ticketValidation` | Flags for test strategy, affected files, dependency checks, min AC count |

Example (abbreviated):

```json
{
  "version": "1.0",
  "project": { "name": "my-app", "stack": "typescript" },
  "backlog": {
    "dataDir": "backlog/data",
    "templatesDir": "backlog/templates",
    "ticketPrefixes": ["FEAT", "BUG", "TASK", "IDEA"],
    "requiredSections": ["context", "description", "acceptanceCriteria",
                         "testStrategy", "affectedFiles", "dependencies"]
  },
  "qualityGates": {
    "typeCheckCommand": "npx tsc --noEmit",
    "lintCommand": "npx eslint .",
    "testCommand": "npx vitest run"
  },
  "codeRules": { "source": ".claude/code-rules.md", "hardGates": [], "softGates": [] },
  "ticketValidation": {
    "requireTestStrategy": true,
    "requireAffectedFiles": true,
    "requireDependencyCheck": true,
    "minAcceptanceCriteria": 3,
    "requireVerificationCommands": true
  }
}
```

## Ticket Format

Every ticket is a Markdown file with YAML frontmatter:

```yaml
---
id: FEAT-001
title: Add user authentication
status: pending
priority: high
created: 2026-02-17
updated: 2026-02-17
assignee: unassigned
blockers: []
depends_on: []
shared_files: []
related_docs: []
---
```

Required body sections: Context, Description, Affected Files, Acceptance
Criteria (min 3), Test Strategy, Dependencies.

Four ticket types are supported out of the box:

| Prefix | Purpose | Extra fields |
|--------|---------|--------------|
| TASK | General implementation work | -- |
| BUG | Defect reports and fixes | severity, environment |
| FEAT | New feature development | phase |
| IDEA | Exploratory ideas and experiments | type, ice_score, hypothesis |

## Install Options

```
./install.sh [OPTIONS]

Options:
  --local       Install to .claude/skills/ in the current project
  --skills      Install only skill files (skip config and templates)
  --force       Overwrite existing files without prompting
```

By default, skills are installed globally to `~/.claude/skills/`.

## License

MIT
