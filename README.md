# Backlog Toolkit -- Reusable Backlog Management Plugin for Claude Code

A Claude Code plugin with 4 skills for managing project backlogs. Stack-agnostic,
config-driven. Handles ticket creation with gap detection, refinement, and
implementation with Agent Teams. Includes cost estimation and tracking.

## Installation

### Via Plugin (recommended)

```bash
# If this repo is in a marketplace:
/plugin install backlog-toolkit@marketplace-name

# Or install directly from local path:
/plugin install --path /path/to/backlog-agents

# Or test locally during development:
claude --plugin-dir /path/to/backlog-agents
```

### Via install.sh (manual)

```bash
./install.sh                    # global: ~/.claude/skills/
./install.sh --local            # project: .claude/skills/
```

## Quick Start

```bash
# Initialize backlog in your project
/backlog-toolkit:init

# Create a ticket (with cost estimation)
/backlog-toolkit:ticket "Add user authentication"

# Refine existing tickets
/backlog-toolkit:refinement

# Implement tickets (with cost tracking)
/backlog-toolkit:implementer
```

## Skills Overview

| Skill | Purpose | Command |
|-------|---------|---------|
| backlog-init | Initialize backlog in any project | `/backlog-toolkit:init` |
| backlog-ticket | Generate validated tickets with cost estimation | `/backlog-toolkit:ticket` |
| backlog-refinement | Refine and validate existing tickets | `/backlog-toolkit:refinement` |
| backlog-implementer | Implement tickets with cost tracking | `/backlog-toolkit:implementer` |

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

v7.0 additions:
- **Smart agent routing** -- selects the optimal agent type per ticket based on affected files
- **Embedded skill catalog** -- 7 disciplines: TDD, code review, debugging, security, architecture, frontend, performance
- **Configurable review pipeline** -- 2-4 parallel reviewers with confidence scoring
- **External plugin detection** -- discovers and loads third-party skill plugins

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
| `agentRouting` | File-pattern rules mapping to agent types, LLM override toggle |
| `reviewPipeline` | Reviewer definitions, confidence threshold, max review rounds |

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

## Agent Routing

The implementer automatically selects the best agent type for each ticket based
on the files it will modify. Configure rules in `backlog.config.json`:

| File Pattern | Default Agent | Use Case |
|-------------|--------------|----------|
| *.tsx, *.jsx, *.vue | frontend | UI components, pages |
| *.py | backend | APIs, services |
| *.go, *.rs | backend | Systems programming |
| Dockerfile, *.tf | devops | Infrastructure |
| *.ipynb | ml-engineer | ML pipelines |

Set `agentRouting.llmOverride: true` (default) to allow the implementer to
override routing when ticket context suggests a better agent.

## Review Pipeline

Quality gates use configurable parallel reviewers with confidence-based filtering.
Default: 2 reviewers (spec-compliance + code-quality). SEC tickets auto-escalate to 4.

Each finding is scored 0-100 confidence. Only findings above the threshold
(default: 80) are reported, eliminating false positives.

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

### Plugin install (recommended)

```bash
# User scope (available everywhere)
/plugin install backlog-toolkit --scope user

# Project scope (shared with team via .claude/settings.json)
/plugin install backlog-toolkit --scope project
```

### Manual install.sh

```
./install.sh [OPTIONS]

Options:
  --local       Install to .claude/skills/ in current project
  --skills      Comma-separated list of skills to install
  --force       Overwrite existing files without prompting
```

## Plugin Structure

```
backlog-agents/
├── .claude-plugin/
│   └── plugin.json           # Plugin manifest
├── commands/                  # Slash commands (/backlog-toolkit:*)
│   ├── init.md
│   ├── ticket.md
│   ├── refinement.md
│   └── implementer.md
├── skills/                    # Agent skills (full specifications)
│   ├── backlog-init/SKILL.md
│   ├── backlog-ticket/SKILL.md
│   ├── backlog-refinement/SKILL.md
│   └── backlog-implementer/SKILL.md
├── templates/                 # Ticket templates
├── config/                    # Config schema and presets
├── tests/                     # Validation tests
└── install.sh                 # Manual install script
```

## Cost Tracking

Tickets created with `/backlog-toolkit:ticket` include a **Cost Estimate** section
showing estimated tokens and USD cost for Opus, Sonnet, and Haiku models.

When implemented via `/backlog-toolkit:implementer`, actual costs are tracked and
saved to `.claude/cost-history.json`. This data feeds back to improve future
ticket estimates, creating a learning loop.

## License

MIT
