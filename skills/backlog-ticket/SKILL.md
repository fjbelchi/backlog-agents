---
name: backlog-ticket
description: "Generate high-quality backlog tickets with 6-check validation. Detects gaps, verifies dependencies, validates contracts, analyzes impact, and ensures consistency. Ask clarifying questions when ambiguous."
allowed-tools: Read, Write, Bash, Glob, Grep, Edit, AskUserQuestion, Task
---

# Backlog Ticket Skill

Generate high-quality tickets and validate them with 6 checks that prevent gaps between tickets (missing dependencies, unspecified tests, uncoordinated shared files, assumed contracts).

This skill runs inside a target project that has been initialized with `backlog-init` (has `backlog.config.json` and `backlog/` directory).

---

## Phase 1: Analysis

### 1.1 Read Configuration

Read `backlog.config.json` from the project root.

```
Required fields to extract:
- backlog.dataDir           → where tickets live (e.g. "backlog/data")
- backlog.templatesDir      → where templates live (e.g. "backlog/templates")
- backlog.ticketPrefixes    → allowed prefixes (e.g. ["FEAT","BUG","TASK","IDEA"])
- backlog.requiredSections  → sections every ticket must have
- ticketValidation.*        → all validation flags and thresholds
- project.name              → project name
- project.stack             → technology stack
- qualityGates.*            → test/lint/build commands
```

If the file is not found, stop immediately and tell the user:

> "No backlog.config.json found. Run /backlog-init first to set up the backlog system."

### 1.2 Scan Existing Backlog

Read all `.md` files in `{dataDir}/pending/` using Glob.

For each ticket file, parse the YAML frontmatter and extract:

| Field | Purpose |
|-------|---------|
| `id` | Build ID registry for auto-increment |
| `title` | Duplicate detection |
| `depends_on` | Dependency graph |
| `shared_files` | File ownership map |
| `status` | Filter active tickets |

Build two data structures in memory:

1. **Dependency graph** — map of ticket ID to its `depends_on` list
2. **File ownership map** — map of file path to list of ticket IDs that touch it (from Affected Files tables)

To build the file ownership map, scan each ticket's body for the `## Affected Files` table and parse the file paths and actions from it.

### 1.3 Understand User Request

Parse the user's description for what the ticket should cover.

If the request is ambiguous or missing critical information, ask the user using **AskUserQuestion**. Rules:

- Ask **one question at a time**
- Use **multiple choice** when possible
- Essential questions to resolve:
  1. **Ticket type** — if not obvious: "What type of ticket? (FEAT / BUG / TASK / IDEA)"
  2. **Priority** — if not stated: "What priority? (low / medium / high / critical)"
  3. **Scope ambiguity** — if description could mean multiple things, ask for clarification
  4. **BUG-specific** — severity, environment, steps to reproduce
  5. **IDEA-specific** — hypothesis, ICE scores

Do NOT ask about information you can infer from the codebase or the user's description.

### 1.4 Analyze Codebase Context

Use Glob and Grep to understand the relevant parts of the codebase:

1. Find files mentioned or implied by the user's description
2. Check if those files exist — note which are "modify" vs "create"
3. Detect naming conventions (kebab-case, camelCase, snake_case) by examining existing files in the same directories
4. Detect directory structure patterns (where tests live, where source lives)
5. Identify imports, exports, types, and interfaces relevant to the ticket

For large projects, use the **Task** tool to delegate codebase scanning to a subagent.

---

## Phase 2: Generation

### 2.1 Auto-Assign Ticket ID

From the existing tickets scanned in Phase 1:

1. Filter tickets matching the chosen prefix (e.g. `FEAT-*`)
2. Find the highest numeric ID
3. Increment by 1, zero-padded to 3 digits: `FEAT-001` -> `FEAT-002`
4. If no existing tickets for this prefix, start at `001`

### 2.2 Select Template

Choose the template from `{templatesDir}/` based on ticket type:

| Prefix | Template |
|--------|----------|
| FEAT | `feature-template.md` |
| BUG | `bug-template.md` |
| TASK | `task-template.md` |
| IDEA | `idea-template.md` |

Read the template to get the exact structure. If the template file is missing, fall back to the feature template structure.

### 2.3 Generate Ticket Content

Fill in the template with real content. Every section must contain **substantive content**, never placeholders or HTML comments.

#### Frontmatter

```yaml
---
id: {PREFIX}-{NNN}
title: {Actionable description derived from user request}
status: pending
priority: {from user or inferred}
created: {today's date YYYY-MM-DD}
updated: {today's date YYYY-MM-DD}
assignee: unassigned
blockers: []
depends_on: [{list of ticket IDs this depends on}]
shared_files: [{list of files shared with other tickets}]
related_docs: []
---
```

Add type-specific frontmatter fields:
- **BUG**: `severity`, `environment`
- **FEAT**: `phase: planning`
- **IDEA**: `type`, `ice_score`

#### Section-by-Section Generation

**Context**: Synthesize from the user's description plus codebase analysis. Explain WHY this work is needed and how it fits in the system.

**Description**: Detailed enough to implement without additional questions. Include specific technical details drawn from the codebase analysis.

**Affected Files**: Table with three columns. For each file:
- Action `modify` — file MUST exist in the codebase (verify with Glob)
- Action `create` — file MUST NOT exist yet (verify with Glob)
- Action `delete` — file MUST exist in the codebase

**Acceptance Criteria**: Minimum count from `config.ticketValidation.minAcceptanceCriteria`. Each criterion must be specific and testable, formatted as `- [ ] AC-N: {criterion}`.

**Test Strategy**: Write specific test cases, not generic ones.
- At least 1 unit test with format: `test: "should X when Y" -> verifies Z`
- At least 1 integration test with format: `test: "X interacts with Y correctly" -> verifies flow`
- For FEAT tickets: include E2E tests
- For BUG tickets: include regression tests
- **Verification Commands**: actual runnable commands using the project's `qualityGates.testCommand` and other configured commands

**Dependencies**: Cross-reference with existing pending tickets. For each dependency:
- Verify the referenced ticket ID exists in `{dataDir}/pending/`
- Note what this ticket needs from it and its current status

**Implementation Notes**: Include relevant patterns from the codebase, naming conventions, architectural constraints, and any technical decisions.

**History**: Single row with today's date, "Created", and "claude-code".

---

## Phase 3: Validation (6 Checks)

Run all 6 checks against the generated ticket. Track results as PASS, WARN, or ERROR.

### Check 1: Completeness

Verify every required section exists and has real content.

```
FOR EACH section IN config.backlog.requiredSections:
  - Section heading exists in ticket body        → ERROR if missing
  - Section body is not empty or placeholder      → ERROR if empty

IF config.ticketValidation.requireTestStrategy:
  - "Unit Tests" subsection has >= 1 test         → ERROR if missing
  - "Integration Tests" subsection has >= 1 test  → ERROR if missing

IF config.ticketValidation.requireVerificationCommands:
  - "Verification Commands" has actual commands    → ERROR if only comments

IF config.ticketValidation.requireAffectedFiles:
  - Affected Files table has >= 1 data row        → ERROR if empty
  - Each "modify" file exists (Glob check)        → ERROR if not found
  - Each "create" file does NOT exist yet          → ERROR if already exists

IF config.ticketValidation.minAcceptanceCriteria:
  - Count lines matching "- [ ] AC-"
  - Count >= config value                          → ERROR if fewer
```

### Check 2: Backlog Coherence

Detect duplicates and verify dependency references.

```
FOR EACH existing pending ticket:
  - Compare title keywords with new ticket title
  - If keyword overlap > 60%                      → WARN: possible duplicate

FOR EACH id IN new ticket's depends_on:
  - Verify file exists in {dataDir}/pending/
    matching that ID                               → ERROR if not found

FOR EACH file IN new ticket's shared_files:
  - Find the other ticket(s) that touch this file
  - Verify those tickets also list it in
    their shared_files                             → WARN if not acknowledged
```

### Check 3: Inter-Ticket Gaps

Detect file conflicts and missing cross-references.

```
FOR EACH file with action "modify" IN Affected Files:
  - Check file ownership map from Phase 1
  - If another pending ticket also modifies it     → WARN: coordination needed
    Add to shared_files if not already there

FOR EACH file with action "create" IN Affected Files:
  - Check file ownership map from Phase 1
  - If another pending ticket also creates it      → ERROR: file conflict

FOR EACH type/function/module referenced in Description or Implementation Notes:
  - If created by another pending ticket
    AND that ticket is NOT in depends_on            → WARN: missing dependency
```

### Check 4: Contract Verification

Ensure all assumed imports, types, and interfaces exist or are accounted for.

```
FOR EACH import/type/interface/function the ticket references:
  1. Grep the codebase for its definition
  2. If NOT found in codebase:
     a. Check if a depends_on ticket creates it
     b. If neither                                  → WARN: assumed contract
        "This ticket assumes {X} exists but it
         doesn't. Either add it to this ticket's
         scope or create a dependency ticket."

FOR EACH export this ticket will create:
  - Check if other pending tickets reference it
  - If yes AND those tickets don't have this
    ticket in their depends_on                      → WARN: missing reverse dependency
```

### Check 5: Impact Analysis

Assess the blast radius of changes.

```
FOR EACH file being MODIFIED:
  - Grep for files that import/require it
  - List all affected downstream modules
  - If any downstream module is touched by
    another pending ticket                          → WARN: overlapping impact

FOR EACH file being CREATED:
  - Verify target directory exists
  - Verify file naming matches project conventions

PRODUCE SUMMARY:
  "This ticket affects N files directly, M files indirectly"
```

### Check 6: Consistency

Verify the ticket follows project conventions.

```
FILE NAMING:
  - Detect naming pattern from existing files in same directory
    (kebab-case, camelCase, snake_case, PascalCase)
  - Verify new file paths follow the same pattern   → WARN if mismatch

DIRECTORY STRUCTURE:
  - Verify new files go in expected directories
    (tests in test dir, source in src dir, etc.)     → WARN if unexpected

TICKET ID:
  - Verify prefix is in config.backlog.ticketPrefixes → ERROR if invalid
  - Verify numeric part is sequential                 → WARN if gap

PRIORITY ALIGNMENT:
  - If description mentions "critical"/"urgent"/"blocker"
    but priority is low/medium                        → WARN: priority mismatch
  - If BUG severity is critical but priority is not
    high/critical                                     → WARN: severity/priority mismatch
```

---

## Phase 4: Output

### All 6 Checks Pass

Write the ticket to `{dataDir}/pending/{PREFIX}-{NNN}-{slug}.md` where `{slug}` is the title in kebab-case, truncated to 50 characters.

Print a summary:

```
Ticket created: {PREFIX}-{NNN}
  Title:        {title}
  File:         {dataDir}/pending/{filename}
  Priority:     {priority}
  Affected:     {N} files ({M} modify, {K} create)
  Dependencies: {count} tickets
  Tests:        {unit_count} unit, {integration_count} integration
  AC count:     {count}
```

### Warnings Found

Group warnings by check number and display them:

```
VALIDATION WARNINGS
-------------------
Check 2 - Backlog Coherence:
  - WARN: Possible duplicate of FEAT-003 (72% keyword overlap)

Check 3 - Inter-Ticket Gaps:
  - WARN: src/utils/helpers.ts also modified by TASK-012. Coordination needed.

Check 5 - Impact Analysis:
  - WARN: src/api/router.ts is imported by 8 other modules.
```

Then ask the user using AskUserQuestion with these options:

1. **Fix automatically** — adjust the ticket to resolve warnings (add shared_files entries, update depends_on, fix naming, etc.)
2. **Accept with warnings** — write the ticket as-is
3. **Cancel and revise** — discard and let the user refine their description

If the user chooses option 1, apply fixes and re-run validation. If warnings persist after auto-fix, show remaining warnings and offer options 2 and 3.

If the user asks to generate additional tickets for gaps (e.g., a missing dependency ticket), generate those tickets using the same 4-phase flow recursively.

### Errors Found

Display errors grouped by check number:

```
VALIDATION ERRORS (must fix before saving)
------------------------------------------
Check 1 - Completeness:
  - ERROR: Affected file src/missing.ts does not exist (action: modify)

Check 3 - Inter-Ticket Gaps:
  - ERROR: TASK-015 also creates src/new-module.ts. File conflict.
```

Do NOT write the ticket. Offer to:

1. **Fix automatically** — adjust affected files, resolve conflicts
2. **Create missing dependency tickets** — generate tickets for unmet dependencies
3. **Cancel** — discard entirely

---

## Template-Specific Behavior

### BUG Tickets

Additional required sections beyond the standard set:
- **Steps to Reproduce** — numbered steps
- **Expected Behavior** — what should happen
- **Actual Behavior** — what happens instead

Test Strategy must include a **Regression Tests** subsection.

### IDEA Tickets

Additional required sections:
- **Hypothesis** — "If we do X, then Y will happen, because Z"
- **ICE Score** — table with Impact, Confidence, Ease scores (1-10)
- **Validation Required** — checklist of what must be true
- **Metrics of Success** — table with metric, current, target, measurement

Test Strategy is lighter: only **Validation Tests** required.

### FEAT Tickets

Additional frontmatter: `phase: planning`

Test Strategy must include **E2E Tests** subsection.

---

## Error Handling

| Situation | Action |
|-----------|--------|
| `backlog.config.json` not found | Stop. Tell user to run `/backlog-init` |
| Template file missing | Fall back to feature-template structure |
| `{dataDir}/pending/` directory missing | Create it with `mkdir -p` |
| User description is empty | Ask for description via AskUserQuestion |
| Codebase file access fails | Log warning, continue with available info |
| Ticket ID collision | Increment until unique |
