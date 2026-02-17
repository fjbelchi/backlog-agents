# Backlog Toolkit — Design Document

**Date**: 2026-02-17
**Status**: Approved
**Author**: Claude Code + fbelchi

## Problem

The backlog management system built for mi-auditor (backlog-refinement v2.0, backlog-implementer v5.0) works well but has critical limitations:

1. **Hardcoded for one stack** — 28 code rules are TypeScript/React/Express specific
2. **No ticket writing skill** — Tickets are created manually or by audit agents without quality validation
3. **Gaps between tickets** — Missing dependency declarations, uncoordinated shared files, assumed contracts that don't exist
4. **Not reusable** — Can't be installed in other projects without heavy customization

## Solution

A reusable toolkit of 4 Claude Code skills with centralized configuration, installable in any project regardless of tech stack.

## Architecture

### Repository Structure

```
backlog-agents/
├── README.md
├── install.sh                         # Installs skills to ~/.claude/skills/ or .claude/skills/
├── skills/
│   ├── backlog-init/SKILL.md          # Scaffolds backlog in target project
│   ├── backlog-ticket/SKILL.md        # Generates + validates tickets
│   ├── backlog-refinement/SKILL.md    # Refines existing tickets
│   └── backlog-implementer/SKILL.md   # Implements tickets with Agent Teams
├── templates/
│   ├── task-template.md
│   ├── bug-template.md
│   ├── feature-template.md
│   └── idea-template.md
├── config/
│   ├── backlog.config.schema.json     # JSON Schema for config validation
│   └── presets/
│       └── default.json
├── tests/                             # Validation tests for skills
└── docs/plans/
```

### Centralized Configuration: `backlog.config.json`

Generated per-project by `backlog-init`. Makes the system stack-agnostic.

```json
{
  "version": "1.0",
  "project": {
    "name": "project-name",
    "stack": "typescript",
    "testRunner": "vitest",
    "linter": "eslint",
    "typeChecker": "tsc"
  },
  "backlog": {
    "dataDir": "backlog/data",
    "templatesDir": "backlog/templates",
    "ticketPrefixes": ["FEAT", "BUG", "SEC", "QUALITY", "REFACTOR", "TEST"],
    "requiredSections": [
      "context", "description", "acceptanceCriteria",
      "testStrategy", "affectedFiles", "dependencies"
    ]
  },
  "qualityGates": {
    "lintCommand": "npx eslint src/ --quiet",
    "typeCheckCommand": "npx tsc --noEmit",
    "testCommand": "npx vitest run",
    "buildCommand": "npm run build"
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
  }
}
```

## Skills Design

### Skill 1: `backlog-init`

**Purpose**: Initialize backlog system in any project.

**Flow**:
1. Ask project name and stack
2. Create `backlog/data/pending/`, `backlog/data/completed/`, `backlog/templates/`
3. Copy templates from toolkit
4. Generate `backlog.config.json` with stack-appropriate presets
5. Create `backlog/CLAUDE.md` with conventions
6. Optionally create `.claude/code-rules.md` with base rules

### Skill 2: `backlog-ticket` (NEW)

**Purpose**: Generate high-quality tickets with validation to prevent gaps.

**Flow**:
1. **Analysis**: Read config, scan existing tickets, analyze codebase
2. **Generation**: Create complete ticket with all required sections
3. **Validation**: Run 6 checks (see below)
4. **Output**: Write ticket or show warnings and ask user

**6 Validation Checks**:

| # | Check | What it verifies |
|---|-------|-----------------|
| 1 | Completeness | All required sections present, tests defined, files verified |
| 2 | Backlog coherence | No duplicates, dependencies resolved, no file conflicts |
| 3 | Inter-ticket gaps | No undocumented assumptions, shared files coordinated |
| 4 | Contract verification | Assumed types/interfaces/functions exist in codebase OR in prior ticket |
| 5 | Impact analysis | What other modules are affected by changes (reverse dependencies) |
| 6 | Consistency check | Naming, structure, patterns follow codebase conventions |

**Ticket Format**:
```markdown
---
id: TYPE-NNN
title: Actionable description
status: pending
priority: high
created: YYYY-MM-DD
assignee: unassigned
blockers: []
depends_on: []
shared_files: []
---

# TYPE-NNN: Title

## Context
Why this is needed and how it fits in the system.

## Description
What needs to be done with enough detail to implement.

## Affected Files
| File | Action | Description |
|------|--------|-------------|
| src/foo.ts | create | New module |
| src/bar.ts | modify | Add export |

## Acceptance Criteria
- [ ] AC-1: ...
- [ ] AC-2: ...
- [ ] AC-3: ...

## Test Strategy
### Unit Tests
- test: "should X when Y" -> verifies Z
- test: "should handle error when..." -> verifies error handling

### Integration Tests
- test: "X interacts with Y correctly" -> verifies full flow

### Verification Commands
\```bash
npm test -- --filter=foo
\```

## Dependencies
| Ticket | What it needs | Status |
|--------|---------------|--------|
| FEAT-002 | SessionConfig type exported | pending |

## Implementation Notes
Technical details, patterns to follow, constraints.
```

### Skill 3: `backlog-refinement` (adapted)

**Adapted from** mi-auditor v2.0.

**Changes**:
- Reads `backlog.config.json` for project-specific rules and commands
- Memory Bridge MCP is optional (works without it)
- Adds validation of Dependencies and Test Strategy sections
- Stack-agnostic validation phases

**Phases preserved**: Inventory -> Validation -> Workflow -> Actions -> Output

### Skill 4: `backlog-implementer` (adapted)

**Adapted from** mi-auditor v5.0.

**Changes**:
- Code rules read from `codeRules.source` in config (project-specific markdown file)
- Quality gate commands read from config (`qualityGates.*`)
- 2 Iron Laws preserved (universal, stack-independent)
- Agent Teams composition preserved (leader + implementers + reviewer + investigator)

**Preserved**: Wave selection, 5 quality gates (Plan -> TDD -> Lint -> Review -> Commit), antipattern scan, ticket enrichment.

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Stack-agnostic | Config-driven, no hardcoded rules | Reusable across projects |
| 4 separate skills | Not monolithic | Separation of concerns, independent usage |
| Centralized config | `backlog.config.json` | Single source of truth per project |
| Iron Laws universal | Not configurable | Commit-before-move and No-hacks apply to all stacks |
| 6 validation checks | In backlog-ticket | Addresses all gap types detected in practice |
| Ticket format with depends_on/shared_files | Explicit coordination | Prevents implicit dependency gaps |

## Future: Marketplace Distribution

The repository structure supports adding more skill categories beyond backlog:
- `skills/security/` — Security scanning skills
- `skills/testing/` — Testing automation skills
- `skills/deployment/` — Deployment skills

The `install.sh` script can be extended to install specific skill categories.
