# Ticket Scope Gate Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a scope gate to the ticket and refinement skills: max 5 files, token estimation, auto-split, and Haiku write-agent for cost reduction.

**Architecture:** Insert Phase 0 before analysis in both skills. Parent does all codebase exploration upfront and passes a structured context map to Haiku (no tool calls in write-agent). Auto-split oversized requests into focused sub-tickets.

**Tech Stack:** Bash (test scripts), JSON (schema), Markdown (templates, SKILL.md)

---

## Task 1: Add failing tests for ticketConstraints in schema test

**Files:**
- Modify: `tests/test-config-schema.sh`

**Step 1: Add ticketConstraints section to test-config-schema.sh**

Find the `# ── Summary` comment near end of file and insert before it:

```bash
# ── ticketConstraints schema checks ──────────────────────────────────

echo "-- ticketConstraints schema --"

if python3 -c "
import json, sys
s = json.load(open(sys.argv[1]))
assert 'ticketConstraints' in s['properties']
" "$SCHEMA" 2>/dev/null; then
  pass "ticketConstraints section exists in schema"
else
  fail "ticketConstraints section missing from schema"
fi

if python3 -c "
import json, sys
s = json.load(open(sys.argv[1]))
tc = s['properties']['ticketConstraints']['properties']
assert 'maxAffectedFiles' in tc
assert 'maxEstimatedTokens' in tc
assert 'requireSingleResponsibility' in tc
" "$SCHEMA" 2>/dev/null; then
  pass "ticketConstraints has all 3 sub-properties"
else
  fail "ticketConstraints missing sub-properties"
fi

if python3 -c "
import json, sys
s = json.load(open(sys.argv[1]))
tc = s['properties']['ticketConstraints']['properties']
assert tc['maxAffectedFiles']['default'] == 5
assert tc['maxEstimatedTokens']['default'] == 100000
assert tc['requireSingleResponsibility']['default'] == True
" "$SCHEMA" 2>/dev/null; then
  pass "ticketConstraints default values correct"
else
  fail "ticketConstraints default values wrong"
fi

echo ""
```

**Step 2: Run test to verify it fails**

Run: `./tests/test-config-schema.sh 2>&1 | grep -A2 "ticketConstraints"`
Expected: `FAIL: ticketConstraints section missing from schema`

---

## Task 2: Add ticketConstraints to config schema

**Files:**
- Modify: `config/backlog.config.schema.json`

**Step 1: Locate the insertion point**

The schema ends with the `sentinel` property block, then closes `}` for `properties`, then `}` for the root object. Find the closing of the `sentinel` property (last `}` before the final two `}`).

The last lines of the file currently are:
```json
        }
      }
    }
  }
}
```

**Step 2: Add ticketConstraints property**

Insert before the last two closing braces (before `  }\n}`), after the `sentinel` block closes. Add a comma after the `sentinel` closing `}` and then add:

```json
    "ticketConstraints": {
      "type": "object",
      "description": "Constraints on ticket scope to ensure completability within context window.",
      "additionalProperties": false,
      "properties": {
        "maxAffectedFiles": {
          "type": "integer",
          "description": "Maximum number of files a single ticket may touch.",
          "default": 5,
          "minimum": 1
        },
        "maxEstimatedTokens": {
          "type": "integer",
          "description": "Maximum estimated tokens for implementer context. Tickets exceeding this are auto-split.",
          "default": 100000,
          "minimum": 10000
        },
        "requireSingleResponsibility": {
          "type": "boolean",
          "description": "Require all affected files to share a common path prefix (single scope boundary).",
          "default": true
        }
      }
    }
```

**Step 3: Verify JSON is valid**

Run: `python3 -c "import json; json.load(open('config/backlog.config.schema.json')); print('valid')"`
Expected: `valid`

**Step 4: Run schema test**

Run: `./tests/test-config-schema.sh 2>&1 | grep -E "(PASS|FAIL).*ticketConstraints"`
Expected: 3 PASS lines for ticketConstraints

**Step 5: Commit**

```bash
git add config/backlog.config.schema.json tests/test-config-schema.sh
git commit -m "feat(schema): add ticketConstraints block with maxAffectedFiles, maxEstimatedTokens, requireSingleResponsibility"
```

---

## Task 3: Add failing tests for new template frontmatter fields

**Files:**
- Modify: `tests/test-templates.sh`

**Step 1: Add estimated_tokens and scope_boundary to FRONTMATTER_FIELDS**

Find line:
```bash
FRONTMATTER_FIELDS=(id title status priority depends_on shared_files)
```

Replace with:
```bash
FRONTMATTER_FIELDS=(id title status priority depends_on shared_files estimated_tokens scope_boundary)
```

**Step 2: Run template test to verify it fails**

Run: `./tests/test-templates.sh 2>&1 | grep -E "FAIL.*estimated_tokens|FAIL.*scope_boundary"`
Expected: 8 FAIL lines (2 fields × 4 templates)

---

## Task 4: Update all 4 templates with new frontmatter fields

**Files:**
- Modify: `templates/task-template.md`
- Modify: `templates/bug-template.md`
- Modify: `templates/feature-template.md`
- Modify: `templates/idea-template.md`

### task-template.md

**Step 1: Add fields to frontmatter**

Find in `templates/task-template.md`:
```yaml
shared_files: []
related_docs: []
```

Replace with:
```yaml
shared_files: []
related_docs: []
estimated_tokens: 0        # calculated in Phase 1, never set manually
scope_boundary: ""         # module prefix, e.g. "src/auth/"
```

**Step 2: Add MAX 5 comment to Affected Files section**

Find:
```markdown
## Affected Files
| File | Action | Description |
|------|--------|-------------|
| path/to/file | create/modify/delete | What changes |
```

Replace with:
```markdown
## Affected Files
<!-- MAX 5 files — tickets exceeding this will be auto-split by the scope gate -->
| File | Action | Description |
|------|--------|-------------|
| path/to/file | create/modify/delete | What changes |
```

### bug-template.md

Apply the same two changes (add fields after `related_docs: []`, add MAX 5 comment).

### feature-template.md

Apply the same two changes.

### idea-template.md

Apply the same two changes.

**Step 3: Run template test to verify it passes**

Run: `./tests/test-templates.sh`
Expected: All PASS, exit 0

**Step 4: Commit**

```bash
git add templates/task-template.md templates/bug-template.md templates/feature-template.md templates/idea-template.md tests/test-templates.sh
git commit -m "feat(templates): add estimated_tokens and scope_boundary frontmatter fields, MAX 5 files comment"
```

---

## Task 5: Add Phase 0 Scope Gate to ticket SKILL.md

**Files:**
- Modify: `skills/backlog-ticket/SKILL.md`

**Step 1: Insert Phase 0 section before Phase 1**

Find in `skills/backlog-ticket/SKILL.md`:
```
## Phase 1: Analysis
```

Insert the entire Phase 0 block immediately before it:

```markdown
## Phase 0: Scope Gate

Run before Phase 1. Exits early if constraints are met; auto-splits if not.

### 0.1 Read Constraints

Read `ticketConstraints` from `backlog.config.json`. If absent, use defaults:

```
maxAffectedFiles: 5
maxEstimatedTokens: 100000
requireSingleResponsibility: true
```

### 0.2 Identify Candidate Files

Use Glob/Grep to find files mentioned or implied by the user request — **without reading content**.

```bash
# Count lines without reading file content
wc -l path/to/file1 path/to/file2 ...
```

### 0.3 Estimate Tokens

```
estimated_tokens = Σ(lines_per_file × 4)   # code to read
                 + 2,000                     # ticket content
                 + 10,000                    # implementation overhead
```

### 0.4 Detect Scope Boundary

```
scope_boundary = longest common path prefix of all candidate files
Example: ["src/auth/login.ts", "src/auth/session.ts"] → "src/auth/"
```

### 0.5 Check Constraints

```
CHECK A: len(candidate_files) <= maxAffectedFiles
CHECK B: estimated_tokens <= maxEstimatedTokens
CHECK C: requireSingleResponsibility → all files share scope_boundary
```

If **all pass** → proceed to Phase 1 with `estimated_tokens` and `scope_boundary` already computed.

If **any fail** → run Auto-Split (§0.6) and loop Phase 1–4 for each sub-ticket instead.

### 0.6 Auto-Split

When constraints are exceeded:

1. **Detect split points**: module boundaries, architectural layers (frontend/backend/DB), dependency order
2. **Generate N sub-requests**: each satisfying all constraints independently
3. **Inherit naming**: if original request had a name prefix, sub-tickets use it: `AUTH-001`, `AUTH-002`
4. **Order by dependency**: blocking sub-tickets first
5. **Each sub-ticket** runs through its own Phase 0 gate before proceeding

Inform the user:

```
Request exceeds scope constraints (N files, ~X tokens).
Auto-splitting into {M} sub-tickets:
  1. {description of sub-ticket 1} (~{files} files, ~{tokens} tokens)
  2. {description of sub-ticket 2} ...
Proceeding with sub-ticket 1...
```

---
```

**Step 2: Verify the section was inserted correctly**

Run: `grep -n "## Phase 0" skills/backlog-ticket/SKILL.md`
Expected: one match, with line number lower than `## Phase 1`

**Step 3: Commit**

```bash
git add skills/backlog-ticket/SKILL.md
git commit -m "feat(ticket): add Phase 0 scope gate with token estimation and auto-split"
```

---

## Task 6: Modify Phase 1 to build context map for Haiku write-agent

**Files:**
- Modify: `skills/backlog-ticket/SKILL.md`

**Step 1: Update MODEL RULES section at top of file**

Find:
```
model: "sonnet"  → write-agents: ticket file creation, cost section generation
model: "haiku"   → analysis agents: codebase scanning, gap detection, duplicate check
```

Replace with:
```
model: "haiku"   → write-agents: ticket file creation (receives pre-digested context map)
model: "haiku"   → analysis agents: codebase scanning, gap detection, duplicate check
NOTE: write-agent is now Haiku (not Sonnet) because parent pre-digests all context.
```

**Step 2: Add context map building to Phase 1 analysis**

Find at the end of `### 1.5 Analyze Codebase Context`:
```
For large projects, use the **Task** tool to delegate codebase scanning to a subagent.
```

Add after it:

```markdown
### 1.6 Build Context Map

After completing 1.1–1.5, assemble a context map. This is the **only input** the Haiku write-agent will receive — it must contain everything needed to write the ticket without tool calls.

```
<context_map>
  affected_files:
    - path: src/auth/login.ts
      line_count: 142
      relevant_snippets: |
        // lines 1-20: imports and types
        export interface LoginRequest { ... }
        // lines 45-67: main handler
        export async function login(req, res) { ... }
    - path: src/auth/session.ts
      line_count: 89
      relevant_snippets: |
        export function createSession(userId: string): Session { ... }
  patterns:
    naming: camelCase for functions, PascalCase for types
    error_handling: throw AppError with status code
    test_style: vitest, describe/it blocks, vi.mock() for dependencies
  dependencies: []
  scope_boundary: "src/auth/"
  estimated_tokens: 42000
  existing_tickets_summary: "FEAT-001 (pending): Add OAuth. TASK-003 (pending): Rate limiting."
</context_map>
```

**Snippet extraction rule**: Max 20 lines per file. Include function signatures, exported types, and any code directly relevant to the ticket. Omit implementation bodies.
```

**Step 3: Verify changes**

Run: `grep -n "context_map" skills/backlog-ticket/SKILL.md | head -5`
Expected: lines containing `context_map` in Phase 1 section

**Step 4: Commit**

```bash
git add skills/backlog-ticket/SKILL.md
git commit -m "feat(ticket): Phase 1 builds context map for Haiku write-agent pre-digestion"
```

---

## Task 7: Switch Phase 2 write-agent from Sonnet → Haiku

**Files:**
- Modify: `skills/backlog-ticket/SKILL.md`

**Step 1: Update the Phase 4 write-agent Task call**

Find in `## Phase 4: Output` → `### All 6 Checks Pass`:

```
Task(
  subagent_type: "general-purpose",
  model: "sonnet",
  prompt: """
You are a write-agent. Your only job is to create a ticket file using the Write tool.
Do NOT output file content in your response.
```

Replace `model: "sonnet"` with `model: "haiku"` and update the prompt to include the context map:

```
Task(
  subagent_type: "general-purpose",
  model: "haiku",
  prompt: """
You are a write-agent. Your ONLY job is to create a ticket file using the Write tool.
Do NOT use any other tools. Do NOT explore the codebase. Do NOT output file content inline.
All context you need is provided below.

{context_map}

Write to: {dataDir}/pending/{PREFIX}-{NNN}-{slug}.md

Template structure: [paste the full template content here]
Section content decisions:
  frontmatter: [all frontmatter fields and values, including estimated_tokens and scope_boundary]
  context: [context section content]
  description: [description section content]
  affected_files: [affected files table — max 5 rows]
  acceptance_criteria: [AC list]
  test_strategy: [test strategy content]
  dependencies: [dependencies list]
  cost_estimate: [cost table with calculated values]

After writing, return ONLY this JSON:
{"file": "{path}", "lines": N, "status": "ok", "summary": "{PREFIX}-{NNN}: {title}"}
"""
)
```

**Step 2: Verify model changed**

Run: `grep -n 'model: "haiku"' skills/backlog-ticket/SKILL.md`
Expected: at least 2 matches (MODEL RULES section + Phase 4 Task call)

Run: `grep -c 'model: "sonnet"' skills/backlog-ticket/SKILL.md`
Expected: 0 (no Sonnet references remain)

**Step 3: Commit**

```bash
git add skills/backlog-ticket/SKILL.md
git commit -m "feat(ticket): switch Phase 2 write-agent from Sonnet to Haiku, inject context map"
```

---

## Task 8: Add Check #7 (scope_gate) to Phase 3 validation

**Files:**
- Modify: `skills/backlog-ticket/SKILL.md`

**Step 1: Add Check #7 after Check #6 in Phase 3**

Find in `## Phase 3: Validation (6 Checks)` at the end of `### Check 6: Consistency`:

```markdown
### Check 6: Consistency
```

After the entire Check 6 block (after its closing content, before `---`), add:

```markdown
### Check 7: Scope Gate

Final verification that the ticket satisfies implementer constraints.

```
READ ticketConstraints from config (defaults: maxAffectedFiles=5, maxEstimatedTokens=100000)

CHECK files_count <= maxAffectedFiles:
  - Count rows in Affected Files table           → ERROR if > max

CHECK estimated_tokens <= maxEstimatedTokens:
  - Use value computed in Phase 0/1.6            → ERROR if > max

CHECK scope_boundary (if requireSingleResponsibility=true):
  - All files in Affected Files must share       → ERROR if different prefixes
    the scope_boundary prefix

IF any check fails → trigger auto-split (Phase 0.6) and regenerate
```

**Note:** Check #7 runs in Phase 3 as final verification. It should rarely trigger because Phase 0 already gated the request — this catches edge cases where analysis revealed additional files.
```

**Step 2: Update the Phase 3 header to say "7 Checks"**

Find:
```markdown
## Phase 3: Validation (6 Checks)
```

Replace with:
```markdown
## Phase 3: Validation (7 Checks)
```

**Step 3: Update the skill description in frontmatter**

Find at top of file:
```yaml
description: "Generate high-quality backlog tickets with 6-check validation and cost estimation...
```

Replace with:
```yaml
description: "Generate high-quality backlog tickets with 7-check validation, scope gate (max 5 files, 100k tokens), auto-split, and Haiku write-agent. Detects gaps, verifies dependencies, validates contracts, analyzes impact, ensures consistency, and estimates implementation cost.
```

**Step 4: Verify Check #7 exists**

Run: `grep -n "Check 7\|scope_gate\|7 Checks" skills/backlog-ticket/SKILL.md`
Expected: 3 matches

**Step 5: Commit**

```bash
git add skills/backlog-ticket/SKILL.md
git commit -m "feat(ticket): add Check #7 scope gate to Phase 3 validation"
```

---

## Task 9: Add Phase 0 Scope Gate to refinement SKILL.md

**Files:**
- Modify: `skills/backlog-refinement/SKILL.md`

**Step 1: Insert Phase 0 section before Phase 1**

Find in `skills/backlog-refinement/SKILL.md`:
```markdown
## Phase 1: Inventory
```

Insert the entire Phase 0 block immediately before it:

```markdown
## Phase 0: Scope Audit

Runs before Phase 1. Scans all pending tickets for scope violations and flags candidates for split.

### 0.1 Read Constraints

Read `ticketConstraints` from `backlog.config.json`. Defaults:
```
maxAffectedFiles: 5
maxEstimatedTokens: 100000
requireSingleResponsibility: true
```

### 0.2 Scan All Pending Tickets

For each `.md` file in `{dataDir}/pending/`:

1. Parse frontmatter YAML
2. Count rows in `## Affected Files` table (no content read needed — count `|` separated rows)
3. For each file in Affected Files, run `wc -l` to get line count
4. Calculate: `estimated_tokens = Σ(lines × 4) + 2000 + 10000`
5. Extract all file paths → compute `scope_boundary` (longest common prefix)

### 0.3 Classify Each Ticket

```
SCOPE_OK:      files ≤ max AND tokens ≤ max AND single boundary
SCOPE_SPLIT:   any constraint violated → mark for auto-split
```

### 0.4 Report Scope Violations

Print summary before proceeding:

```
Scope Audit
-----------
Total pending: N
Scope-OK:      M  (proceed to Phase 1.5 as normal)
Needs split:   K  (will be auto-split before refinement)

Tickets to split:
  FEAT-007: 8 files (max 5), ~142k tokens (max 100k) → will split into 2
  TASK-012: mixed scope (src/auth/ + src/billing/) → will split into 2
```

### 0.5 Auto-Split Oversized Tickets

For each `SCOPE_SPLIT` ticket:

1. Read the ticket content
2. Apply auto-split algorithm (same as ticket skill Phase 0.6):
   - Detect split points: module boundaries, layers, dependency order
   - Generate N sub-ticket contents, each satisfying constraints
   - Sub-tickets inherit prefix: `FEAT-007` → `FEAT-007a`, `FEAT-007b`
3. Archive original with `status: split` and add note:
   ```yaml
   status: split
   split_into: [FEAT-007a, FEAT-007b]
   ```
4. Write new sub-ticket files using Haiku write-agent
5. Each sub-ticket gets `estimated_tokens` and `scope_boundary` populated

After split, the sub-tickets enter Phase 1 as normal.

---
```

**Step 2: Update refinement skill description in frontmatter**

Find at top:
```yaml
description: "Refine backlog tickets: verify code references, detect duplicates, validate completeness, update severity, generate report. Config-driven and stack-agnostic. v3.0."
```

Replace with:
```yaml
description: "Refine backlog tickets: scope audit + auto-split, verify code references, detect duplicates, validate completeness, update severity, generate report. Config-driven and stack-agnostic. v4.0."
```

**Step 3: Verify Phase 0 was inserted**

Run: `grep -n "## Phase 0\|## Phase 1" skills/backlog-refinement/SKILL.md | head -4`
Expected: Phase 0 line number lower than Phase 1

**Step 4: Commit**

```bash
git add skills/backlog-refinement/SKILL.md
git commit -m "feat(refinement): add Phase 0 scope audit — scans tickets for violations and auto-splits oversized ones"
```

---

## Task 10: Switch refinement write-agent from Sonnet → Haiku

**Files:**
- Modify: `skills/backlog-refinement/SKILL.md`

**Step 1: Update MODEL RULES at top of file**

Find:
```
model: "sonnet"  → write-agents: report generation, ticket file updates
model: "haiku"   → analysis agents: code verification, duplicate detection
```

Replace with:
```
model: "haiku"   → write-agents: sub-ticket file creation (receives pre-digested context map)
model: "haiku"   → analysis agents: code verification, duplicate detection
model: "sonnet"  → write-agents: health report generation only (complex multi-section doc)
NOTE: split ticket write-agents use Haiku; report write-agent stays Sonnet (complexity).
```

**Step 2: Verify changes**

Run: `grep -n 'model:' skills/backlog-refinement/SKILL.md | head -10`
Expected: Haiku for ticket writes, Sonnet only for report

**Step 3: Run all tests to confirm nothing broken**

Run: `./tests/test-config-schema.sh && ./tests/test-templates.sh`
Expected: All PASS, both exit 0

**Step 4: Final commit**

```bash
git add skills/backlog-refinement/SKILL.md
git commit -m "feat(refinement): switch split-ticket write-agents from Sonnet to Haiku"
```

---

## Summary

| Task | File | Change | Test |
|------|------|--------|------|
| 1 | `tests/test-config-schema.sh` | Add ticketConstraints checks | Run → expect FAIL |
| 2 | `config/backlog.config.schema.json` | Add ticketConstraints block | Run → expect PASS |
| 3 | `tests/test-templates.sh` | Add estimated_tokens, scope_boundary to FRONTMATTER_FIELDS | Run → expect FAIL |
| 4 | `templates/*.md` (×4) | Add 2 frontmatter fields + MAX 5 comment | Run → expect PASS |
| 5 | `skills/backlog-ticket/SKILL.md` | Add Phase 0 scope gate + auto-split | grep check |
| 6 | `skills/backlog-ticket/SKILL.md` | Phase 1 builds context map | grep check |
| 7 | `skills/backlog-ticket/SKILL.md` | Phase 2 write-agent: Sonnet → Haiku | grep check |
| 8 | `skills/backlog-ticket/SKILL.md` | Add Check #7, update description | grep check |
| 9 | `skills/backlog-refinement/SKILL.md` | Add Phase 0 scope audit + auto-split | grep check |
| 10 | `skills/backlog-refinement/SKILL.md` | Switch split write-agents Sonnet → Haiku | grep check |

**Expected savings:** $0.04 → $0.005 per ticket (8× cost reduction). Tickets bounded to ≤5 files and ≤100k tokens, completable within 50% of the 200k context window.
