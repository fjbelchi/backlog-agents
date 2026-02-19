---
name: backlog-refinement
description: "Refine backlog tickets: verify code references, detect duplicates, validate completeness, update severity, generate report. Config-driven and stack-agnostic. v3.0."
allowed-tools: Read, Glob, Grep, Bash, Edit, Write, Task
---

# Backlog Refinement Skill v3.0

Refine existing backlog tickets by verifying code references, detecting duplicates, validating completeness, updating severity, and generating a health report.

This skill runs inside a target project that has been initialized with `backlog-init` (has `backlog.config.json` and `backlog/` directory).

---

## CRITICAL RULE: DO NOT PASS model: TO TASK TOOL

```
When invoking any Task tool subagent, NEVER pass the model: parameter.
The subagent inherits the parent's model automatically (always the latest version).

PROHIBITED:
  - model: "opus"
  - model: "sonnet"
  - model: "haiku"

REQUIRED:
  - Omit the model parameter entirely in every Task tool call
```

---

## Phase 1: Inventory

### 1.1 Read Configuration

Read `backlog.config.json` from the project root.

```
Required fields to extract:
- backlog.dataDir           -> where tickets live (e.g. "backlog/data")
- backlog.ticketPrefixes    -> allowed prefixes (e.g. ["FEAT","BUG","SEC","QUALITY"])
- backlog.requiredSections  -> sections every ticket must have
- ticketValidation.*        -> all validation flags and thresholds
- project.name              -> project name
- project.stack             -> technology stack
```

If the file is not found, stop immediately and tell the user:

> "No backlog.config.json found. Run /backlog-init first to set up the backlog system."

### 1.2 List All Pending Tickets

Use Glob to find all `.md` files in `{config.backlog.dataDir}/pending/`.

For each ticket file, parse the YAML frontmatter and extract:

| Field | Purpose |
|-------|---------|
| `id` | Ticket identification |
| `title` | Duplicate detection |
| `priority` | Processing order |
| `status` | Filter active tickets |

### 1.3 Count by Prefix Type

Count tickets by prefix using the prefixes from `config.backlog.ticketPrefixes`.

For each prefix in the config, count how many tickets match `{PREFIX}-*`.

### 1.4 Show Summary

Print an inventory summary:

```
Backlog Inventory
-----------------
Total pending tickets: N

By type:
  SEC-*:      N tickets
  BUG-*:      N tickets
  QUALITY-*:  N tickets
  FEAT-*:     N tickets
  ...

Processing will follow priority order: SEC -> BUG -> QUALITY -> FEAT -> remaining
```

---

## Phase 1.5: Deterministic Pre-Filter (No LLM)

Before any LLM calls, run deterministic checks using regex/grep only:

```
FOR EACH ticket:
  1. Check required sections present (grep for "## Context", "## Description", etc.)
  2. Validate frontmatter YAML structure (parse YAML, check required fields)
  3. Check file references exist (Glob check each path in Affected Files table)
  4. Count acceptance criteria lines matching "- [ ] AC-"
  5. Check `updated` date is plausible (not in future, not missing)

Mark each ticket: DETERMINISTIC_PASS or NEEDS_LLM_REVIEW
→ Tickets passing all deterministic checks: skip LLM, just validate VALID
→ Only tickets with structural issues proceed to full LLM analysis
```

This eliminates LLM calls for already-healthy tickets.

## Phase 1.6: Context Grouping for Cache Efficiency

Before sending tickets to LLM, group them by shared codebase context:

```
Group tickets that share files in their Affected Files sections.
Process each group consecutively so the stable system context is cached.
Within a group, the LLM's prompt prefix (project rules, config) is identical
→ cache hit on prefix for tickets 2..N in each group → near-free reuse.

Order: SEC → BUG → QUALITY → FEAT (within each type, group by shared files)
```

## Phase 2: Validation (Per Ticket)

For each ticket, run the following checks grouped by category.

### 2.0 Duplicate Detection (Before Other Checks)

**If MCP memory tools are available** (e.g., `mcp__memory-bridge__unified_search`), use semantic search:

```
Search for: ticket.title + key phrases from ticket.description
If any result has relevance_score > 0.7 -> mark as possible duplicate
```

**If MCP memory tools are NOT available**, fall back to keyword-based search:

```
FOR EACH other pending ticket:
  - Extract title keywords (remove stop words)
  - Compare keyword sets between current ticket and other ticket
  - If keyword overlap > 60% -> WARN: possible duplicate
  - Also Grep the pending/ directory for key phrases from the ticket description
```

### 2.1 Technical Validity (Critical)

| Check | What to verify | Action if fails |
|-------|----------------|-----------------|
| File exists | Files referenced in the ticket exist in the repo | Update path or mark OBSOLETE |
| Lines valid | Line numbers cited match current code | Update line numbers |
| Code matches | Snippets shown in the ticket match actual code | Update snippet or mark OBSOLETE |
| Issue persists | The problem described still exists in the code | Move to completed/ if resolved |
| Solution feasible | The proposed remediation is technically correct | Correct solution or flag for review |

#### RAG-Assisted Reference Check (if enabled)

If `llmOps.ragPolicy.enabled` and RAG server is reachable, supplement the file-existence check by querying the RAG index for function and class names mentioned in each ticket:

```python
# For each symbol name extracted from ticket affectedFiles and description:
rag = RagClient()
results = rag.search(symbol_name, n=3, filter={"type": "code"})
if not results.get("documents", [[]])[0]:
    flag_ticket(ticket_id, f"Code reference '{symbol_name}' not found in RAG index")
```

This is faster than grepping the full codebase and respects project isolation — it only searches the current project's index.

### 2.2 Completeness (High)

| Check | What to verify | Action if fails |
|-------|----------------|-----------------|
| Required sections | All sections from `config.backlog.requiredSections` are present | Add missing sections |
| Test Strategy | Has unit + integration tests specified | Add test specs |
| Affected Files | Table is populated with real file paths | Add file references |
| Dependencies | Section is accurate and references valid ticket IDs | Update dependencies |
| Description clear | The problem is understandable without additional context | Expand description |
| Acceptance Criteria | Has at least `config.ticketValidation.minAcceptanceCriteria` items | Add criteria |
| Verification Commands | Has actual runnable commands (if `config.ticketValidation.requireVerificationCommands`) | Add commands |

### 2.3 Classification (Medium)

| Check | What to verify | Action if fails |
|-------|----------------|-----------------|
| Severity correct | Severity matches the actual impact of the issue | Adjust severity |
| Correct prefix | Ticket type/prefix matches the nature of the issue | Reclassify if needed |
| Not a duplicate | No other ticket covers the same issue | Mark as DUP, reference original |
| Not obsolete | The code/feature still exists | Move to completed/ |
| Effort estimated | Has a `## Cost Estimate` section with token counts and USD costs | Run cost estimation (see 2.4) |

### 2.4 Cost Estimation

For any ticket missing a `## Cost Estimate` section, compute and add it.

#### Step 1: Count scope from ticket

From the ticket's Affected Files table and Test Strategy:
- `files_to_modify` = rows with existing files
- `files_to_create` = rows with new files
- `test_count` = number of test cases in Test Strategy

#### Step 2: Estimate tokens

Read `.claude/cost-history.json` if it exists (written by implementer after each ticket).

**With history** (use averages from matching ticket type):
```
input_tokens  = (files_to_modify * avg.input_tokens_per_file_modified)
              + (files_to_create * avg.input_tokens_per_file_created)
output_tokens = (files_to_modify * avg.output_tokens_per_file_modified)
              + (files_to_create * avg.output_tokens_per_file_created)
              + (test_count * avg.output_tokens_per_test)
total_tokens  = (input_tokens + output_tokens) * avg.overhead_multiplier
```

**Without history** (defaults):
```
input_tokens  = (files_to_modify * 8000) + (files_to_create * 3000)
output_tokens = (files_to_modify * 2500) + (files_to_create * 4000) + (test_count * 1200)
total_tokens  = (input_tokens + output_tokens) * 2.5
```

Split: ~60% input, ~40% output.

#### Step 3: Calculate cost

| Model | Input $/1M | Output $/1M |
|-------|-----------|------------|
| Claude Opus 4 | $15.00 | $75.00 |
| Claude Sonnet 4 | $3.00 | $15.00 |
| Claude Haiku 3.5 | $0.80 | $4.00 |

```
cost = (input_tokens / 1_000_000 * input_price) + (output_tokens / 1_000_000 * output_price)
```

#### Step 4: Add section to ticket

Insert after `## Dependencies`:

```markdown
## Cost Estimate

| Model | Input Tokens | Output Tokens | Est. Cost |
|-------|-------------|---------------|-----------|
| Opus 4 | ~{input} | ~{output} | ${cost} |
| Sonnet 4 | ~{input} | ~{output} | ${cost} |
| Haiku 3.5 | ~{input} | ~{output} | ${cost} |

**Basis**: {N} files to modify, {M} files to create, {K} tests defined
**Estimation source**: {historical (N samples) | default heuristics}
**Confidence**: {high (>10 samples) | medium (3-10) | low (<3 or defaults)}
```

Round token counts to nearest 1000. Round costs to 2 decimal places.

---

## Phase 3: Workflow

Process tickets in priority order based on prefix. The default priority order is:

1. **SEC-*** (Security) -- highest risk
2. **BUG-*** (Bugs) -- affect functionality
3. **QUALITY-*** (Code quality) -- technical debt
4. **FEAT-*** (Features) -- new functionality
5. **Remaining prefixes** -- alphabetical order

Within each prefix group, process by priority: critical > high > medium > low.

### Per-Ticket Workflow

For each ticket:

```
1. READ     - Read the full ticket content
2. VERIFY   - Check that referenced files exist using Glob
3. READ     - Read the actual source code referenced in the ticket
4. COMPARE  - Compare current code with what the ticket describes
5. EVALUATE - Determine if the issue still exists
6. DECIDE   - Choose an action:
               VALID     - Ticket is correct, minor improvements only
               UPDATED   - Ticket needs corrections to sections
               OBSOLETE  - Issue is resolved or code was removed
               DUPLICATE - Another ticket covers the same issue
7. EXECUTE  - Apply the decided action (see Phase 4)
```

For codebase scanning on large projects, use the **Task** tool to delegate file verification to a subagent. Do NOT pass model: to the Task tool.

---

## Phase 4: Actions

### Ticket VALID

Add a `## Refinement Status` section at the end of the ticket:

```markdown
## Refinement Status
- **Status**: Validated
- **Date**: YYYY-MM-DD
- **Code verified**: Yes -- all referenced files and line numbers confirmed
- **Sections complete**: Yes
```

### Ticket UPDATED

Update the affected sections with corrected information. Then add:

```markdown
## Refinement Status
- **Status**: Updated
- **Date**: YYYY-MM-DD
- **Changes**:
  - [list each change made, e.g. "Updated file path from X to Y"]
  - [e.g. "Added missing Test Strategy section"]
  - [e.g. "Updated line numbers for src/foo.ts (was 42-50, now 55-63)"]
```

### Ticket OBSOLETE

Move the ticket file from `{dataDir}/pending/` to `{dataDir}/completed/`.

Before moving, append a closure note:

```markdown
## Refinement Status
- **Status**: Obsolete
- **Date**: YYYY-MM-DD
- **Reason**: [why the ticket is no longer relevant]
  - e.g. "Referenced file was deleted in commit abc1234"
  - e.g. "Issue was resolved -- code no longer contains the bug"
```

Use Bash to move the file:

```bash
mv {dataDir}/pending/{filename} {dataDir}/completed/{filename}
```

### Ticket DUPLICATE

Add at the top of the ticket body (after frontmatter):

```markdown
> **DUPLICATE**: This ticket duplicates [{original-id}]({relative-path-to-original}). See the original for the canonical description.
```

Then add:

```markdown
## Refinement Status
- **Status**: Duplicate
- **Date**: YYYY-MM-DD
- **Duplicates**: {original-ticket-id}
- **Reason**: [explanation of why this is a duplicate]
```

Do NOT delete the ticket. Leave it in pending/ with the duplicate marker so a human can confirm.

---

## Phase 5: Output

Generate a report at `backlog/REFINEMENT-REPORT-{YYYY-MM-DD}.md`.

If a report for today already exists, append a timestamp: `REFINEMENT-REPORT-{YYYY-MM-DD}-{HHmm}.md`.

### Report Structure

```markdown
# Refinement Report {YYYY-MM-DD}

## Summary
- Tickets processed: X
- Validated: X | Updated: X | Obsolete: X | Duplicates: X

## By Type
| Prefix | Total | Validated | Updated | Obsolete | Duplicate |
|--------|-------|-----------|---------|----------|-----------|
| SEC | N | N | N | N | N |
| BUG | N | N | N | N | N |
| QUALITY | N | N | N | N | N |
| FEAT | N | N | N | N | N |
| ... | ... | ... | ... | ... | ... |

## Issues Found
- [{ticket-id}]: {brief description of what was wrong or changed}
- [{ticket-id}]: {brief description}

## Tickets Requiring Human Review
- [{ticket-id}]: {reason human review is needed}

## Backlog Health Score: X/100

Health score calculation:
- Base: 100 points
- Deduct 5 points per obsolete ticket found
- Deduct 3 points per ticket missing required sections
- Deduct 10 points per duplicate found
- Deduct 2 points per ticket without test strategy
- Deduct 2 points per ticket without dependencies documented
- Minimum score: 0

Breakdown:
- Valid tickets: X% (X/Y)
- Tickets with test strategy: X% (X/Y)
- Tickets with dependencies documented: X% (X/Y)
- Tickets with affected files: X% (X/Y)
- Duplicates detected: X
- Obsolete tickets removed: X
```

### Optional: Save Learnings (MCP Memory)

If MCP memory tools are available (e.g., `mcp__memory-bridge__save_learning`), save refinement patterns:

```
Save a learning with:
  category: "refinement_pattern"
  content: Summary of tickets processed, duplicates found, common issues detected
  context: "backlog-refinement-v3"
```

If MCP memory tools are not available, skip this step without error.

---

## Restrictions

- ALWAYS verify that referenced code exists before marking a ticket as valid
- ALWAYS update tickets with correct information when discrepancies are found
- ALWAYS move obsolete tickets to completed/ (never delete without moving)
- NEVER delete tickets without moving them to completed/ first
- NEVER change the essence of the issue -- only improve clarity, accuracy, and completeness
- NEVER pass model: parameter to Task tool subagents

---

## Error Handling

| Situation | Action |
|-----------|--------|
| `backlog.config.json` not found | Stop. Tell user to run `/backlog-init` |
| `{dataDir}/pending/` directory missing | Create it with `mkdir -p` |
| `{dataDir}/completed/` directory missing | Create it with `mkdir -p` |
| No tickets found in pending/ | Report "No pending tickets to refine" and exit |
| Referenced file cannot be read | Log warning, mark check as inconclusive |
| Ticket has no frontmatter | Log error, skip ticket, note in report |
| Move to completed/ fails | Log error, note in report, continue to next ticket |

---

## Startup

**Run a complete refinement of the backlog. Verify each referenced file against the actual codebase. Document all changes in the report.**

Read `backlog.config.json` at startup. If `llmOps.batchPolicy.enabled` is true and ticket count >= `llmOps.batchPolicy.forceBatchWhenQueueOver`, and `--now` was NOT passed, submit refinement as a batch job and exit with instructions to run `scripts/ops/batch_reconcile.py` when complete.
