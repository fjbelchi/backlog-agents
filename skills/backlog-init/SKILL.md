---
name: backlog-init
description: "Initialize backlog system in any project. Creates directory structure, templates, config, and conventions. Stack-agnostic with auto-detection."
allowed-tools: Read, Write, Bash, Glob, Grep, AskUserQuestion, Task
---

# Backlog Init Skill

Initialize a backlog system in the current project. This skill detects the project stack, creates the directory structure, writes ticket templates, generates `backlog.config.json`, and optionally creates `.claude/code-rules.md`.

## MODEL RULES FOR TASK TOOL

```
model: "sonnet"  → write-agents: config generation, template writing, directory setup
no model:        → analysis agents — inherits parent
```

## OUTPUT DISCIPLINE

```
- Never output file content or config content inline in your response
- Max response length: ~20 lines
- Steps 3+4 (directory structure + config generation) → delegate to sonnet write-agent
- Parent prints compact 5-line summary after write-agent returns
```

---

## Step 1: Detect Project Context

Use **deterministic file checks** (no LLM calls) to detect the project stack:

1. Check for manifest files to detect stack (first match wins):
   - `package.json` + `tsconfig.json` → `typescript`
   - `package.json` (no tsconfig) → `javascript`
   - `pyproject.toml` or `setup.py` or `requirements.txt` → `python`
   - `go.mod` → `go`
   - `Cargo.toml` → `rust`
   - `Package.swift` → `swift`
   - Otherwise → `generic`

2. Try to extract the project name from the manifest (e.g., `name` field in `package.json`). Fall back to the current directory name via `basename $(pwd)`.

3. Check if `backlog/` directory already exists. If it does, warn the user and ask whether to overwrite or abort.

## Step 2: Ask User for Preferences

Use **AskUserQuestion** to confirm or adjust:

1. **Project name** — pre-fill with detected name.
2. **Stack** — pre-fill with detected stack. Options: typescript, python, go, rust, swift, generic.
3. **Ticket prefixes** — default all enabled: TASK, BUG, FEAT, IDEA. Ask which to keep.
4. **Create `.claude/code-rules.md`?** — yes/no, default yes.

## Step 3: Create Directory Structure + Step 4: Generate Config (delegated)

After confirming with user, spawn a sonnet write-agent that creates all files:

```
Task(
  subagent_type: "general-purpose",
  model: "sonnet",
  prompt: """
You are a write-agent. Create the full backlog directory structure and config file.
Do NOT output file content in your response.

Project details:
  name: {project_name}
  stack: {detected_stack}
  dataDir: backlog/data
  templatesDir: backlog/templates
  ticketPrefixes: {chosen_prefixes}
  qualityGates: {stack_commands}

Tasks:
1. Create backlog/data/pending/.gitkeep (empty file)
2. Create backlog/data/completed/.gitkeep (empty file)
3. Copy templates from ${CLAUDE_PLUGIN_ROOT}/templates/ to backlog/templates/
   (task-template.md, bug-template.md, feature-template.md, idea-template.md)
4. Write backlog.config.json at project root with all values above
   (use the full config schema from the skill — all sections: project, backlog, ticketValidation, qualityGates, llmOps, sentinel)

After writing all files, return ONLY:
{"files_created": N, "config": "backlog.config.json", "status": "ok", "summary": "Initialized backlog for {project_name} ({stack})"}
"""
)
```

Receive JSON, then print:

```
✓ Backlog initialized for {project_name}
  Stack: {stack} | Files created: {N}
  Config: backlog.config.json
  Next: /backlog-toolkit:ticket "your first ticket"
```

The directory structure created (reference for write-agent prompt):

```
backlog/
├── data/
│   ├── pending/          # .gitkeep
│   └── completed/        # .gitkeep
└── templates/
    ├── task-template.md
    ├── bug-template.md
    ├── feature-template.md
    └── idea-template.md
```

Create the `.gitkeep` files:
- `backlog/data/pending/.gitkeep` (empty)
- `backlog/data/completed/.gitkeep` (empty)

## Step 4: Generate `backlog.config.json` (reference schema for write-agent)

The write-agent from Step 3 handles this. Use the detected/chosen stack to pick quality gate commands from this table:

| Stack | typeCheckCommand | lintCommand | testCommand |
|-------|-----------------|-------------|-------------|
| typescript | `npx tsc --noEmit` | `npx eslint .` | `npx vitest run` |
| python | `mypy .` | `ruff check .` | `pytest` |
| go | `go vet ./...` | `golangci-lint run` | `go test ./...` |
| rust | `cargo check` | `cargo clippy -- -D warnings` | `cargo test` |
| swift | `swift build` | `swiftlint` | `swift test` |
| generic | _(omit)_ | _(omit)_ | `echo 'Configure testCommand in backlog.config.json'` |

The config structure must be:

```json
{
  "version": "1.0",
  "project": {
    "name": "<PROJECT_NAME>",
    "stack": "<STACK>"
  },
  "backlog": {
    "dataDir": "backlog/data",
    "templatesDir": "backlog/templates",
    "ticketPrefixes": ["<CHOSEN_PREFIXES>"],
    "requiredSections": [
      "context",
      "description",
      "acceptanceCriteria",
      "testStrategy",
      "affectedFiles",
      "dependencies"
    ]
  },
  "qualityGates": {
    "typeCheckCommand": "<from table>",
    "lintCommand": "<from table>",
    "testCommand": "<from table>"
  },
  "codeRules": {
    "source": ".claude/code-rules.md",
    "hardGates": [],
    "softGates": []
  },
  "ticketValidation": {
    "requireTestStrategy": true,
    "requireAffectedFiles": true,
    "requireDependencyCheck": true,
    "minAcceptanceCriteria": 3,
    "requireVerificationCommands": true
  },
  "llmOps": {
    "gateway": {
      "baseURL": "http://localhost:8000"
    },
    "routing": {
      "defaultGenerationModel": "balanced",
      "planningModel": "balanced",
      "reviewModel": "cheap",
      "lintModel": "cheap",
      "escalationRules": [
        { "condition": "ticket.tags.includes('ARCH')", "model": "frontier" },
        { "condition": "ticket.tags.includes('SECURITY')", "model": "frontier" },
        { "condition": "qualityGateFails >= 2", "model": "frontier" }
      ]
    },
    "batchPolicy": {
      "enabled": true,
      "forceBatchWhenQueueOver": 1,
      "maxWaitHours": 24,
      "eligiblePhases": ["ticket", "refinement", "implementation"]
    },
    "ragPolicy": {
      "enabled": true,
      "serverUrl": "http://localhost:8001",
      "vectorStore": "chromadb",
      "topK": 5,
      "embeddingModel": "all-MiniLM-L6-v2"
    },
    "cachePolicy": {
      "redisEnabled": true,
      "redisUrl": "redis://localhost:6379",
      "ttlSeconds": 3600
    }
  },
  "sentinel": {
    "enabled": true,
    "installGitHook": true,
    "prescan": {
      "runLinter": true,
      "runTests": true,
      "detectHardcoded": true,
      "maxFunctionLines": 80
    },
    "reviewers": {
      "security": true,
      "quality": true
    },
    "ragDeduplication": true,
    "ticketMapping": {
      "security": "SEC",
      "bug": "BUG",
      "techDebt": "TASK"
    },
    "patternThresholds": {
      "escalateToSoftGate": 3,
      "escalateToHardGate": 5
    }
  }
}
```

Only include `typeCheckCommand` and `lintCommand` keys when the stack provides them (omit for generic).

## Step 5: Create `backlog/CLAUDE.md`

Write the following file, replacing `<PROJECT_NAME>` with the chosen project name:

```markdown
# Backlog System

This directory contains the backlog management system for <PROJECT_NAME>.

## Directory Structure

```
backlog/
├── data/
│   ├── pending/      # Active tickets
│   └── completed/    # Finished tickets (moved here after completion)
└── templates/        # Ticket templates
```

## Ticket Format

Every ticket is a Markdown file with YAML frontmatter. Required frontmatter fields:

| Field | Description |
|-------|-------------|
| id | Ticket ID (e.g., TASK-001, BUG-042) |
| title | Short actionable description |
| status | pending, in_progress, completed |
| priority | low, medium, high, critical |
| created | ISO date (YYYY-MM-DD) |
| updated | ISO date (YYYY-MM-DD) |
| assignee | Who is working on it |
| blockers | List of blocking ticket IDs |
| depends_on | List of dependency ticket IDs |
| shared_files | Files shared with other tickets |
| related_docs | Links to related documentation |

### Required Sections

Every ticket body must include: Context, Description, Affected Files, Acceptance Criteria (min 3), Test Strategy, Dependencies.

## Ticket Prefixes

| Prefix | Purpose | Extra Fields |
|--------|---------|--------------|
| TASK | General implementation work | — |
| BUG | Defect reports and fixes | severity, environment |
| FEAT | New feature development | phase |
| IDEA | Exploratory ideas and experiments | type, ice_score, hypothesis |

## Severity SLAs (BUG tickets)

| Severity | Response Time | Resolution Target |
|----------|--------------|-------------------|
| critical | Immediate | Same day |
| high | Within 4 hours | 1-2 days |
| medium | Within 1 day | 3-5 days |
| low | Within 1 week | Best effort |

## Workflow

1. **Create** — Use the appropriate template from `backlog/templates/`
2. **Assign** — Set `assignee` and `status: in_progress`
3. **Implement** — Work on the ticket, update affected files
4. **Verify** — Run quality gates and verification commands
5. **Complete** — Set `status: completed`, move file to `backlog/data/completed/`
```

## Step 6: Write Templates

Write the following four template files exactly as shown.

### `backlog/templates/task-template.md`

```markdown
---
id: TASK-NNN
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

# TASK-NNN: Title

## Context
<!-- Why this task is needed and how it fits in the system -->

## Description
<!-- What needs to be done with enough detail to implement -->

## Affected Files
| File | Action | Description |
|------|--------|-------------|
| path/to/file | create/modify/delete | What changes |

## Acceptance Criteria
- [ ] AC-1: ...
- [ ] AC-2: ...
- [ ] AC-3: ...

## Test Strategy
### Unit Tests
- test: "should X when Y" → verifies Z

### Integration Tests
- test: "X interacts with Y correctly" → verifies flow

### Verification Commands
```bash
# Commands to verify the implementation
```

## Dependencies
| Ticket | What it needs | Status |
|--------|---------------|--------|
| (none) | — | — |

## Implementation Notes
<!-- Technical details, patterns, constraints -->

## History
| Date | Change | Author |
|------|--------|--------|
| YYYY-MM-DD | Created | claude-code |
```

### `backlog/templates/bug-template.md`

```markdown
---
id: BUG-NNN
title: Actionable description
status: pending
priority: medium
severity: medium
environment: all
created: YYYY-MM-DD
updated: YYYY-MM-DD
assignee: unassigned
blockers: []
depends_on: []
shared_files: []
related_docs: []
---

# BUG-NNN: Title

## Context
<!-- Why this bug matters and how it affects the system -->

## Description
<!-- What is broken, with enough detail to reproduce and fix -->

## Steps to Reproduce
1. Step one
2. Step two
3. Step three

## Expected Behavior
<!-- What should happen -->

## Actual Behavior
<!-- What happens instead -->

## Affected Files
| File | Action | Description |
|------|--------|-------------|
| path/to/file | create/modify/delete | What changes |

## Acceptance Criteria
- [ ] AC-1: Bug no longer reproducible following the steps above
- [ ] AC-2: Regression test added covering this scenario
- [ ] AC-3: ...

## Test Strategy
### Regression Tests
- test: "should not reproduce BUG-NNN when Y" → verifies the fix holds
- test: "should handle edge case Z" → verifies related paths

### Unit Tests
- test: "should X when Y" → verifies Z

### Integration Tests
- test: "X interacts with Y correctly" → verifies flow

### Verification Commands
```bash
# Commands to verify the fix
```

## Dependencies
| Ticket | What it needs | Status |
|--------|---------------|--------|
| (none) | — | — |

## Implementation Notes
<!-- Root cause analysis, patterns, constraints -->

## History
| Date | Change | Author |
|------|--------|--------|
| YYYY-MM-DD | Created | claude-code |
```

### `backlog/templates/feature-template.md`

```markdown
---
id: FEAT-NNN
title: Actionable description
status: pending
priority: medium
phase: planning
created: YYYY-MM-DD
updated: YYYY-MM-DD
assignee: unassigned
blockers: []
depends_on: []
shared_files: []
related_docs: []
---

# FEAT-NNN: Title

## Context
<!-- Why this feature is needed and how it fits in the system -->

## Description
<!-- What needs to be built with enough detail to implement -->

## Affected Files
| File | Action | Description |
|------|--------|-------------|
| path/to/file | create/modify/delete | What changes |

## Acceptance Criteria
- [ ] AC-1: ...
- [ ] AC-2: ...
- [ ] AC-3: ...

## Test Strategy
### Unit Tests
- test: "should X when Y" → verifies Z

### Integration Tests
- test: "X interacts with Y correctly" → verifies flow

### E2E Tests
- test: "user can complete workflow Z" → verifies end-to-end behavior

### Verification Commands
```bash
# Commands to verify the implementation
```

## Dependencies
| Ticket | What it needs | Status |
|--------|---------------|--------|
| (none) | — | — |

## Implementation Notes
<!-- Technical details, patterns, constraints -->

## History
| Date | Change | Author |
|------|--------|--------|
| YYYY-MM-DD | Created | claude-code |
```

### `backlog/templates/idea-template.md`

```markdown
---
id: IDEA-NNN
title: Actionable description
status: pending
priority: medium
type: feature | business-line | experiment
ice_score: 0
created: YYYY-MM-DD
updated: YYYY-MM-DD
assignee: unassigned
blockers: []
depends_on: []
shared_files: []
related_docs: []
---

# IDEA-NNN: Title

## Context
<!-- Why this idea is worth exploring and how it fits in the system -->

## Description
<!-- What the idea is about with enough detail to evaluate -->

## Hypothesis
<!-- If we do X, then Y will happen, because Z -->

## ICE Score
| Dimension | Score (1-10) | Rationale |
|-----------|:------------:|-----------|
| Impact | 0 | How much will this move the needle? |
| Confidence | 0 | How sure are we this will work? |
| Ease | 0 | How easy is this to implement? |
| **Total** | **0** | |

## Validation Required
<!-- What needs to be true for this idea to be worth pursuing -->
- [ ] Validation 1: ...
- [ ] Validation 2: ...

## Metrics of Success
<!-- How we will measure whether this idea worked -->
| Metric | Current | Target | How to measure |
|--------|---------|--------|----------------|
| metric_name | baseline | goal | measurement method |

## Affected Files
| File | Action | Description |
|------|--------|-------------|
| path/to/file | create/modify/delete | What changes |

## Acceptance Criteria
- [ ] AC-1: ...
- [ ] AC-2: ...
- [ ] AC-3: ...

## Test Strategy
<!-- Ideas are exploratory; full test specs are deferred until the idea is promoted to a feature -->
### Validation Tests
- test: "hypothesis holds when X" → verifies core assumption

### Verification Commands
```bash
# Commands to verify the prototype or experiment
```

## Dependencies
| Ticket | What it needs | Status |
|--------|---------------|--------|
| (none) | — | — |

## Implementation Notes
<!-- Technical details, patterns, constraints -->

## History
| Date | Change | Author |
|------|--------|--------|
| YYYY-MM-DD | Created | claude-code |
```

## Step 7: Optionally Create `.claude/code-rules.md`

If the user chose yes, create `.claude/code-rules.md` with:

```markdown
# Code Rules for <PROJECT_NAME>

## Hard Gates (must pass, block commit)
- [ ] Define your hard gate rules here

## Soft Gates (should review, can override with justification)
- [ ] Define your soft gate rules here
```

Create the `.claude/` directory first if it does not exist.

## Step 6: Initialize RAG Index

Check if `llmOps.ragPolicy.enabled` is `true` in the generated `backlog.config.json`.

If enabled:
1. Check RAG server health: `curl -sf http://localhost:8001/health`
2. If reachable, run initial index:
   ```bash
   source "${CLAUDE_PLUGIN_ROOT}/scripts/rag/client.sh"
   rag_index_dir .
   # Also index any existing tickets
   [ -d backlog/data ] && rag_index_dir backlog/data
   ```
3. Log: `"✓ RAG index initialized for project {project.name}"`

If RAG server is unreachable: log a warning and continue without error:
> "⚠ RAG server not reachable — skipping initial index. Run 'make rag-index' when services are up."

## Step 8: Print Summary

After all files are created, print a summary like:

```
Backlog system initialized for <PROJECT_NAME> (<STACK>)

Created:
  - backlog/data/pending/.gitkeep
  - backlog/data/completed/.gitkeep
  - backlog/templates/task-template.md
  - backlog/templates/bug-template.md
  - backlog/templates/feature-template.md
  - backlog/templates/idea-template.md
  - backlog/CLAUDE.md
  - backlog.config.json
  - .claude/code-rules.md  (if created)

Ticket prefixes enabled: TASK, BUG, FEAT, IDEA
Quality gates configured for: <STACK>
Sentinel: enabled (pre-push hook will auto-install on first /backlog-toolkit:sentinel run)

Next steps:
  1. Review backlog.config.json and adjust quality gate commands
  2. Add rules to .claude/code-rules.md
  3. Create your first ticket with /backlog-ticket
  4. Run /backlog-toolkit:sentinel after your first commit to activate code review
```
