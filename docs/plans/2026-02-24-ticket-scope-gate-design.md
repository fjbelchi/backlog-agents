# Ticket Scope Gate Design

**Date:** 2026-02-24
**Status:** Approved
**Scope:** `skills/backlog-ticket/`, `skills/backlog-refinement/`, `templates/`, `config/schema.json`

## Problem

Current tickets are too large for the implementer to complete within 50% of the context window (100k tokens of a 200k context). Two root causes:

1. **Scope too broad** — tickets span multiple modules or too many files, forcing the implementer to read excessive context before writing code
2. **Excessive exploration** — the write-agent (Sonnet) explores the codebase itself, consuming tokens and time
3. **Cost** — Sonnet write-agent costs ~$0.04/ticket; Haiku can do it for ~$0.005 with a pre-digested context map

## Goals

- Tickets completable within 50% context window (~100k tokens)
- Max 5 affected files per ticket
- Single responsibility: all affected files within one scope boundary
- Auto-split oversized requests into N focused sub-tickets
- Switch write-agent from Sonnet → Haiku without quality loss
- Apply same constraints to refinement skill (split existing oversized tickets)

## Architecture

### Phase 0: Scope Gate (NEW)

Inserted before Phase 1 in both ticket and refinement skills.

```
Request
   │
   ▼
Phase 0: Scope Gate
   ├─ Glob/Grep candidate files (no content read yet)
   ├─ wc -l each file → estimate tokens = Σ(lines × 4) + 12,000 overhead
   ├─ Check: files ≤ maxAffectedFiles (default: 5)
   ├─ Check: estimated_tokens ≤ maxEstimatedTokens (default: 100,000)
   ├─ Check: all files share scope_boundary (same module/path prefix)
   └─ if any check fails → Auto-Split Plan
          ├─ Identify split points: by module, by layer, by dependency order
          ├─ Generate N sub-ticket requests, each satisfying all constraints
          └─ Loop Phase 1-4 for each sub-ticket
```

### Phase 1: Analysis (MODIFIED)

Parent skill (Haiku) does ALL exploration upfront before delegating:

1. Read affected files — extract only relevant snippets (functions, exports, types) — max 20 lines per file
2. Detect patterns: naming conventions, error handling style, test structure
3. Calculate `estimated_tokens` precisely
4. Identify `scope_boundary` (common path prefix)
5. Build **context map** to pass to Haiku write-agent

### Phase 2: Generation (MODIFIED — Haiku write-agent)

Haiku receives a structured context map and fills the template. No tool calls, no exploration.

**Context map structure:**
```
<context_map>
  affected_files: [{path, relevant_snippets, line_count}]
  patterns: {naming, error_handling, test_style}
  dependencies: [blocking_ticket_ids]
  scope_boundary: "src/payments/"
  estimated_tokens: 42000
</context_map>
```

**Haiku prompt structure:** `<context>`, `<template>`, `<instructions>` — fully specified, no open-ended inference required.

**Cost comparison:**

| Phase | Model | Cost |
|---|---|---|
| Phase 0-1 analysis | Haiku | ~$0.002 |
| Phase 2 write-agent | Haiku | ~$0.003 |
| **Total** | | **~$0.005** (was ~$0.04 with Sonnet) |

### Phase 3: Validation (MODIFIED — adds Check #7)

New check added to the existing 6:

| Check | Rule | Behavior |
|---|---|---|
| #7 scope_gate | `files ≤ max` AND `tokens ≤ max` AND single `scope_boundary` | ERROR → auto-split |

Check #7 also runs in Phase 0 (early exit) and again in Phase 3 (final verification).

## Token Estimation Formula

```
estimated_tokens = Σ(lines_per_file × 4)   # code to read
                 + 2,000                     # ticket content
                 + 10,000                    # implementation overhead
```

Lines counted with a cheap `wc -l` before any content is read. Target: `estimated_tokens < 100,000`.

## Template Changes

Two fields added to frontmatter YAML across all 4 templates (TASK, BUG, FEAT, IDEA):

```yaml
estimated_tokens: 0        # calculated in Phase 1, never set manually
scope_boundary: ""         # module prefix, e.g. "src/auth/"
```

Comment added to `affected_files` section: `# MAX 5 files`.

No sections removed — template remains equally rich in content.

## Auto-Split Strategy

When a request exceeds constraints:

1. Detect natural split points: module boundaries, architectural layers (frontend/backend/DB), dependency order
2. Generate N sub-requests, each satisfying all constraints
3. If original request had a name, sub-tickets inherit prefix: `AUTH-001`, `AUTH-002`
4. Sub-tickets are ordered by dependency (blocking tickets first)
5. Each sub-ticket runs through its own Phase 0 gate before generation

## Refinement Skill Changes

New Phase 0 in refinement:

1. Read all backlog tickets
2. For each ticket: count `affected_files`, recalculate `estimated_tokens`
3. Flag violations → mark as candidates for split
4. Auto-split: same algorithm as ticket skill
5. Original ticket archived with `status: split`, references new IDs
6. New tickets written with updated frontmatter

## Config Schema Changes

New `ticketConstraints` block in `backlog.config.json`:

```json
"ticketConstraints": {
  "maxAffectedFiles": 5,
  "maxEstimatedTokens": 100000,
  "requireSingleResponsibility": true
}
```

Default values apply if block is absent (backwards compatible).

## Files Affected

| File | Change |
|---|---|
| `skills/backlog-ticket/SKILL.md` | Add Phase 0, modify Phase 1 (context map), switch to Haiku write-agent, add Check #7 |
| `skills/backlog-refinement/SKILL.md` | Add Phase 0 scope gate, add auto-split logic |
| `templates/task-template.md` | Add `estimated_tokens`, `scope_boundary` fields + MAX 5 comment |
| `templates/bug-template.md` | Same |
| `templates/feature-template.md` | Same |
| `templates/idea-template.md` | Same |
| `config/schema.json` | Add `ticketConstraints` block with defaults |
