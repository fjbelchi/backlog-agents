# Backlog Toolkit -- Reusable Backlog Management Plugin for Claude Code

A Claude Code plugin with 4 skills for managing project backlogs. Stack-agnostic,
config-driven. Handles ticket creation with gap detection, refinement, and
implementation with Agent Teams. Includes cost estimation and tracking.

## Prerequisites

- Claude Code CLI installed
- Bash 4.0+ and Python 3.10+
- Node.js 18+ (for Claude Code)
- Git 2.30+
- A project repository where `backlog/` and `backlog.config.json` can be created
- (Optional) LiteLLM proxy for multi-provider routing and cost optimization
- (Optional) Redis for response caching
- (Optional) Ollama for local models

**New to the toolkit?** → See [Complete Setup Guide](docs/tutorials/complete-setup-guide.md) for step-by-step installation from scratch.

## Cost Optimization Philosophy

This toolkit is designed around **aggressive token efficiency**. Every feature follows the cost pyramid:

1. **Script-first, LLM-second** — Deterministic scripts handle validation, dedup, impact analysis before any LLM call
2. **Cheapest model that passes quality gates** — Route 70% of calls to Haiku, 25% to Sonnet, 5% to Opus
3. **Multi-layer caching** — Anthropic prompt caching (90% discount) + response cache + semantic cache
4. **Batch for non-interactive work** — 50% cost reduction via Batch API
5. **RAG-augmented context** — Send only relevant code chunks, not entire files

See the [Token Optimization Playbook](docs/tutorials/token-optimization-playbook.md) for the complete guide.

## Quick Start (Automated Setup)

For first-time users, use the interactive setup wizard:

```bash
# Clone repository
git clone https://github.com/fjbelchi/backlog-agents.git
cd backlog-agents

# Run interactive setup
./scripts/setup/complete-setup.sh
```

The wizard will ask you:
- **Anthropic**: Use Anthropic API or AWS Bedrock?
- **OpenAI**: Add OpenAI models? (optional)
- **Ollama**: Use local models? (optional)
- **Model Selection**: Which specific models to enable?
- **Plugin Installation**: Install Claude Code plugin now? (automated)
- **Services**: Start LiteLLM and services now? (automated)

This automatically:
- ✓ Installs Python dependencies (LiteLLM, ChromaDB, etc.)
- ✓ Detects existing credentials (AWS CLI, Ollama)
- ✓ Generates LiteLLM config with your models
- ✓ **Installs Claude Code plugin**
- ✓ **Starts all services**
- ✓ **Verifies everything works**
- ✓ **Runs connectivity tests**

**See [Interactive Setup Guide](docs/tutorials/interactive-setup.md) for examples and [Complete Setup Guide](docs/tutorials/complete-setup-guide.md) for manual configuration.**

## Installation

### Via Marketplace (recommended)

Install directly from Claude Code without cloning anything:

```bash
# 1. Register the marketplace (one time only):
/plugin marketplace add fjbelchi/backlog-agents

# 2. Install the plugin:
/plugin install backlog-toolkit@backlog-agents
```

Skills are immediately available as `/backlog-toolkit:init`, `/backlog-toolkit:ticket`, etc.

### Via Plugin path (local clone)

```bash
git clone https://github.com/fjbelchi/backlog-agents.git

# Install permanently:
/plugin install --path /path/to/backlog-agents

# Or load for the current session only:
claude --plugin-dir /path/to/backlog-agents
```

### Via install.sh (manual, no plugin system)

```bash
./install.sh                    # global: ~/.claude/skills/
./install.sh --local            # project: .claude/skills/
```

## Setup (Recommended Path)

1. Install the plugin:

```bash
# Via marketplace (recommended):
/plugin marketplace add fjbelchi/backlog-agents
/plugin install backlog-toolkit@backlog-agents
# OR via local clone:
/plugin install --path /path/to/backlog-agents
```

2. Initialize backlog in your target project:

```bash
/backlog-toolkit:init
```

3. Validate base toolkit:

```bash
./tests/test-config-schema.sh
./tests/test-templates.sh
./tests/test-install.sh
```

4. Enable docs-as-code validation:

```bash
./scripts/docs/generate-config-reference.py
./scripts/docs/generate-model-table.sh
./scripts/docs/check-links.sh
./scripts/docs/verify-snippets.sh
./scripts/docs/check-doc-coverage.py
```

5. (Optional) Initialize cloud-first ops artifacts:

```bash
mkdir -p .backlog-ops
./scripts/ops/sync-model-registry.sh
: > .backlog-ops/usage-ledger.jsonl
./scripts/ops/cost_guard.py --ledger .backlog-ops/usage-ledger.jsonl
```

## LiteLLM Setup (Multi-Provider Routing)

LiteLLM provides unified access to multiple LLM providers with cost tracking, caching, and fallbacks.

### Automated Configuration

```bash
./scripts/setup/complete-setup.sh
```

This configures LiteLLM with support for:
- **Anthropic Claude** (Opus, Sonnet, Haiku)
- **OpenAI** (GPT-4, GPT-3.5)
- **AWS Bedrock** (Claude models)
- **Ollama** (local models)

### Manual Configuration

1. **Install LiteLLM**:
   ```bash
   pip install 'litellm[proxy]'
   ```

2. **Configure providers**:
   ```bash
   # Anthropic (required)
   export ANTHROPIC_API_KEY="sk-ant-api03-..."

   # OpenAI (optional)
   export OPENAI_API_KEY="sk-..."

   # AWS Bedrock (optional)
   export AWS_ACCESS_KEY_ID="AKIA..."
   export AWS_SECRET_ACCESS_KEY="..."
   export AWS_REGION="us-east-1"
   ```

3. **Create configuration**:
   ```bash
   cp config/litellm/proxy-config.template.yaml ~/.config/litellm/config.yaml
   # Edit configuration as needed
   ```

4. **Start proxy**:
   ```bash
   litellm --config ~/.config/litellm/config.yaml
   ```

**Detailed guide**: [Complete Setup Guide](docs/tutorials/complete-setup-guide.md)
**Configuration reference**: [LiteLLM Proxy Config](docs/reference/litellm-proxy-config.md)

## Service Management

The toolkit includes scripts to manage all required services (LiteLLM, RAG, etc.).

### Start All Services

```bash
# Start services manually
./scripts/services/start-services.sh

# Or start services and Claude Code together
./claude-with-services.sh
```

**Services started**:
- ✓ LiteLLM proxy (port 8000)
- ✓ RAG server (port 8001) - optional
- ✓ Redis (caching) - optional
- ✓ Ollama (local models) - optional

### Check Service Status

```bash
./scripts/services/status.sh
```

### Stop Services

```bash
./scripts/services/stop-services.sh
```

### Service Logs

```bash
# View logs
tail -f ~/.backlog-toolkit/services/logs/litellm.log
tail -f ~/.backlog-toolkit/services/logs/rag.log
```

**See [Service Management](scripts/services/README.md) for detailed documentation.**

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

## Documentation

Operational documentation is available under `docs/`:

### Getting Started
- [Quickstart (Cloud-First)](docs/tutorials/quickstart-cloud-only.md) — end-to-end setup in 15 min
- [Token Optimization Playbook](docs/tutorials/token-optimization-playbook.md) — 40-70% token savings
- [Daily Operator Flow](docs/tutorials/daily-flow.md) — structured daily workflow

### Reference
- [Command Reference](docs/reference/command-reference.md)
- [Config Schema v1.1](docs/reference/backlog-config-v1.1.md) — includes `llmOps` block
- [LiteLLM Proxy Config](docs/reference/litellm-proxy-config.md)
- [Model Registry](docs/reference/model-registry.md)
- [Scripts Catalog](docs/reference/scripts-catalog.md)

### Architecture
- [System Overview](docs/architecture/system-overview.md)
- [ADR-001: Orchestrator Entrypoint](docs/architecture/adr/ADR-001-orchestrator-entrypoint.md)
- [ADR-004: Multi-Layer Caching & Batch](docs/architecture/adr/ADR-004-multilayer-caching-and-batch.md)
- [ADR-005: RAG-Augmented Context](docs/architecture/adr/ADR-005-rag-augmented-context.md)

### Runbooks
- [Cost Incident Response](docs/runbooks/cost-incident-response.md)
- [Cache Optimization](docs/runbooks/cache-optimization.md)
- [Batch Operations](docs/runbooks/batch-operations.md)

### Validation

```bash
make validate    # or manually:
./scripts/docs/check-links.sh
./scripts/docs/check-doc-coverage.py
./scripts/docs/verify-snippets.sh
```

## Skills Overview

| Skill | Purpose | Command |
|-------|---------|---------|
| backlog-init | Initialize backlog in any project | `/backlog-toolkit:init` |
| backlog-ticket | Generate validated tickets with cost estimation | `/backlog-toolkit:ticket` |
| backlog-refinement | Refine and validate existing tickets | `/backlog-toolkit:refinement` |
| backlog-implementer | Implement tickets with cost tracking | `/backlog-toolkit:implementer` |

Skill details index:

- `docs/skills/README.md`

## Skills Playbook (How To Use)

### 1) backlog-init

Use when starting backlog tooling in a new repo.

```bash
/backlog-toolkit:init
```

Expected result: `backlog/` structure + `backlog.config.json` + templates.

### 2) backlog-ticket

Use when turning a request into a validated, actionable ticket.

```bash
/backlog-toolkit:ticket "Implement SSO login for admin users"
```

Expected result: new ticket in `backlog/data/pending/` with sections, ACs, tests, dependencies, and cost estimate.

### 3) backlog-refinement

Use periodically to keep backlog consistency and remove stale tickets.

```bash
/backlog-toolkit:refinement
```

Expected result: updated ticket quality + report in `backlog/`.

### 4) backlog-implementer

Use to execute pending tickets in quality-gated waves.

```bash
/backlog-toolkit:implementer
```

Expected result: code and test changes, review/lint/test gates applied, completed tickets moved to `backlog/data/completed/`.

### Recommended sequence

1. `/backlog-toolkit:init` (once per project)
2. `/backlog-toolkit:ticket` (for each new work item)
3. `/backlog-toolkit:refinement` (periodic backlog hygiene)
4. `/backlog-toolkit:implementer` (execution loop)

### Full Agent Matrix (Active + Planned)

| Agent/Skill | Status | Primary Use |
|---|---|---|
| backlog-init | Active | Project bootstrap and backlog scaffolding |
| backlog-ticket | Active | Ticket generation and validation |
| backlog-refinement | Active | Backlog hygiene and ticket updates |
| backlog-implementer | Active | Implementation orchestration and quality gates |
| backlog-orchestrator | Planned (documented) | Single entrypoint to coordinate workflows |
| backlog-cost-governor | Planned (documented) | Budget/cost policy and alerts |
| backlog-batch-operator | Planned (documented) | Non-interactive batch queue execution |
| backlog-cache-optimizer | Planned (documented) | Prompt/cache optimization |

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

## Agent Management

This section describes how to operate the agent system in day-to-day usage.

### Agent Roles

| Role | Where configured | Responsibility |
|---|---|---|
| Leader/Coordinator | `skills/backlog-implementer/SKILL.md` | Selects wave, enforces gates, tracks completion |
| Implementer | `agentRouting.rules` | Executes code/test changes for ticket scope |
| Reviewer | `reviewPipeline.reviewers` | Performs quality/spec/security review passes |
| Investigator | Routing/overrides | Handles unclear tickets and deep diagnosis |

### Routing Strategy

Use `backlog.config.json -> agentRouting.rules` to map file patterns to agent types.

Best practice:

1. Keep rules simple and deterministic.
2. Use `llmOverride: true` only when needed for ambiguous tickets.
3. Add ticket-type overrides for `BUG`/`SEC`.

### Review Strategy

Use `reviewPipeline` to control review cost vs quality:

1. Start with 2 reviewers (`spec-compliance`, `code-quality`).
2. Auto-escalate only for sensitive tickets (security, auth, payments).
3. Keep `confidenceThreshold` high to reduce noisy findings.
4. Limit `maxReviewRounds` to avoid loops.

### Day-to-Day Operator Workflow

```bash
# 1) Create work item
/backlog-toolkit:ticket "Implement X"

# 2) Keep backlog healthy
/backlog-toolkit:refinement

# 3) Execute implementation waves
/backlog-toolkit:implementer

# 4) Run cost and docs controls
./scripts/ops/cost_guard.py --ledger .backlog-ops/usage-ledger.jsonl
./scripts/docs/check-doc-coverage.py
```

### Planned Unified Orchestration

The repository now includes full documentation for a single-entry orchestration model
(`backlog-orchestrator`) in `docs/skills/backlog-orchestrator.md`, plus supporting
ops skills (`cost-governor`, `batch-operator`, `cache-optimizer`).

Current plugin commands remain the 4 active commands listed in this README.

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

## Cost Tracking & Optimization

Tickets include a **Cost Estimate** section showing estimated tokens and USD per model.
After implementation, actual costs are tracked in `.claude/cost-history.json`, creating
a feedback loop that improves future estimates.

### Operational Cost Controls

```bash
# Cost posture check
make cost

# Detailed analytics report
python scripts/ops/cost_report.py --ledger .backlog-ops/usage-ledger.jsonl

# Prompt cache lint
make cache-lint

# Full ops health
make ops
```

### Key Scripts

| Script | Purpose |
|--------|--------|
| `scripts/ops/cost_guard.py` | Budget threshold checks (warn/hard-stop) |
| `scripts/ops/cost_report.py` | Detailed cost analytics and KPI tracking |
| `scripts/ops/prompt_prefix_lint.py` | Validate prompt prefixes for cache compatibility |
| `scripts/ops/batch_submit.py` | Submit non-interactive jobs (50% cheaper) |
| `scripts/ops/batch_reconcile.py` | Reconcile batch job results |
| `scripts/ops/rag_index.py` | Build/query RAG index for context reduction |
| `scripts/ops/sync-model-registry.sh` | Refresh model alias registry |

### KPI Targets

| Metric | Target |
|--------|--------|
| Prompt cache hit rate | ≥60% |
| Cheap model usage ratio | ≥70% |
| Batch vs interactive ratio | ≥30% batch |
| Frontier escalation rate | <5% |
| Cost per ticket (Sonnet) | <$2 avg |

## Makefile

Common operations are available via `make`:

```bash
make help          # Show all targets
make setup         # First-time ops initialization
make validate      # Run all validation checks
make test          # Run all tests
make refresh       # Regenerate all artifacts
make cost          # Check cost posture
make ops           # Full ops health check
make batch-cycle   # Submit + reconcile batch jobs
make clean         # Remove temp files
```

## License

MIT
