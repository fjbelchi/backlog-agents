# Write-Agent Pattern Design

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:writing-plans to create the implementation plan from this design.

**Goal:** Eliminate output token limit errors across all skills by delegating file-writing and report-generation to haiku subagents, keeping the parent skill focused on short orchestration responses.

**Architecture:** Each skill splits work into two roles — the parent handles reasoning/orchestration (< 30 lines output), haiku write-agents handle all file creation and structured output. Subagents return compact JSON summaries, never file content.

---

## Problem

The 4096-token output limit in Claude Code CLI affects all skills equally. Skills currently mix reasoning (short) with file generation (long) in the same response, causing truncation. This happens in:
- `backlog-ticket`: outputting full ticket content inline
- `backlog-refinement`: per-ticket analysis × N tickets + report
- `backlog-implementer`: wave plan analysis, wave summary
- `backlog-sentinel`: creating N tickets from findings inline
- `backlog-init`: outputting config + structure inline

## Solution: Write-Agent Pattern

### Core Pattern

```
Parent skill (orchestrates, reasons):
  1. Analyzes context → makes decisions (< 30 lines output)
  2. Spawns Task(subagent_type: "general-purpose", model: "haiku")
  3. Receives compact JSON: {"file": "path", "lines": N, "status": "ok"}
  4. Continues to next step

Haiku write-agent (generates, writes files):
  1. Receives full context + template in prompt
  2. Generates content
  3. Writes file with Write tool
  4. Returns ONLY JSON summary
  5. Never outputs file content in response text
```

### Standard Write-Agent Prompt Block

```
You are a write-agent. Your only job is to create files using the Write tool.
Do NOT output file content in your response.

[task-specific context and template]

After writing, return ONLY this JSON:
{"file": "<path>", "lines": <N>, "status": "ok|error", "summary": "<one line description>"}
```

### Updated Model Rules (replaces "NEVER pass model:")

```
Model rules for Task tool subagents:
- model: "sonnet" → write-agents: file creation, report generation,
                     ticket writing, config generation, summaries
- no model:       → analysis agents: code review, security analysis,
                     architecture decisions, implementation — inherits parent
```

Note: haiku was evaluated but found unreliable for complex template-following.
Sonnet is the recommended model for write-agents.

### Output Discipline Rule (add to all skills)

```
OUTPUT DISCIPLINE:
- Never output file content inline in your response
- Max response length: ~30 lines of text
- Use Write tool directly for files < 50 lines
- Use haiku write-agent subagent for files > 50 lines or batches of files
```

---

## Per-Skill Changes

### backlog-ticket

**Current:** Outputs full ticket content (100-150 lines) inline, then writes file.

**Change:**
- Parent decides ticket structure, type, ID, validation — outputs < 10 lines
- Delegates ticket writing + cost estimation to haiku write-agent
- Write-agent receives: template, context, all section content
- Parent receives: `{"file": "backlog/data/pending/BUG-042.md", "lines": 87, "status": "ok"}`
- Parent outputs: `✓ Ticket BUG-042 created (87 lines) — estimated cost: $0.08 Opus / $0.02 Sonnet`

### backlog-refinement

**Current:** Processes each ticket in the main thread (read + analyze + update × N), then generates report.

**Change:**
- Phase 1 (inventory) stays in parent — just counting, no large output
- Phase 2-4 (per-ticket processing): group by Phase 1.6 context groups, spawn up to 5 parallel haiku write-agents, each handling one group
  - Each write-agent: reads tickets, runs checks, applies updates, returns `{processed: N, updated: M, obsolete: K}`
- Phase 5 (report): haiku write-agent generates and writes `REFINEMENT-REPORT-YYYY-MM-DD.md`
  - Parent receives: `{"file": "backlog/REFINEMENT-REPORT-2026-02-19.md", "lines": 120, "status": "ok"}`

### backlog-implementer

**Current:** Phase 1 (wave selection) outputs long analysis of all tickets inline. Phase 6 (wave summary) outputs long summary.

**Change:**
- Phase 1: delegate wave planning to haiku subagent
  - Input: all ticket IDs + metadata (no full content)
  - Output: `{"waves": [{"wave": 1, "tickets": [{"id": "BUG-001", "subagent_type": "backend", "rationale": "auth service"}]}]}`
  - Parent uses this JSON to create team and assign tasks
- Phase 6: delegate wave summary to haiku write-agent
  - Write-agent generates summary markdown, appends to `.backlog-ops/wave-log.md`
  - Parent outputs: 5-line banner with key numbers only

### backlog-sentinel

**Current:** Phase 2 creates N tickets sequentially in the main thread.

**Change:**
- Phase 2: for each finding, spawn haiku write-agent (parallel, max 5 at once)
  - Each write-agent creates one ticket using backlog-ticket template logic
  - Returns: `{"file": "backlog/data/pending/BUG-003.md", "ticket_id": "BUG-003", "status": "ok"}`
- Phase 3 summary: parent outputs compact summary (already short), no change needed

### backlog-init

**Current:** Generates backlog.config.json and directory structure, outputs summary inline.

**Change:**
- Parent reads project + detects stack (short, no output change)
- Delegates to haiku write-agent:
  - Creates `backlog.config.json`
  - Creates directory structure (backlog/data/pending, etc.)
  - Copies templates
  - Returns: `{"files_created": 8, "config": "backlog.config.json", "status": "ok"}`
- Parent outputs: compact 5-line summary

---

## Files to Modify

| File | Change |
|------|--------|
| `skills/backlog-ticket/SKILL.md` | Add OUTPUT DISCIPLINE rule + haiku write-agent for ticket creation |
| `skills/backlog-refinement/SKILL.md` | Add OUTPUT DISCIPLINE + parallel haiku write-agents for ticket processing + report |
| `skills/backlog-implementer/SKILL.md` | Add OUTPUT DISCIPLINE + haiku for wave planning (Phase 1) + wave summary (Phase 6) |
| `skills/backlog-sentinel/SKILL.md` | Add OUTPUT DISCIPLINE + parallel haiku write-agents for ticket creation (Phase 2) |
| `skills/backlog-init/SKILL.md` | Add OUTPUT DISCIPLINE + haiku write-agent for file generation |

No changes to scripts, config schema, or commands.

---

## Testing

For each skill, verify:
1. Run skill on a project with 5+ tickets
2. No "output token limit" error appears
3. Files are created correctly (content identical to before)
4. Parent responses stay under 30 lines
5. Haiku subagent JSON summaries are returned correctly
