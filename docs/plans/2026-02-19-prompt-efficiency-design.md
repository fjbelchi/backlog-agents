# Prompt Efficiency Optimization — Design Doc

**Date**: 2026-02-19
**Status**: Implemented
**Impact**: ~60-70% cost reduction per session

## Problem

Analysis of 1,009 LiteLLM requests revealed three major inefficiencies:

1. **Opus as default model**: 217 requests at $15.55 (84% of all spend), with 54% producing <200 output tokens
2. **79-107 tool definitions per request**: ~20K-26K tokens of overhead repeated in every API call
3. **claude-mem context injection**: 3 blocks of activity tables injected in 61% of requests, never queried via tools (0 tool calls)

## Root Causes

### Tool definition overhead
Claude Code sends ALL tool definitions from ALL enabled plugins in every request. With Atlassian (28 tools), Playwright (22 tools), claude-mem (4 tools), and core tools (25), each request carries ~20K tokens just in tool schemas. These are cached by Bedrock prompt caching (~80% hit rate), but the remaining 20% + cache read costs add up across 100+ requests per session.

### Global plugin loading
Plugins enabled in `~/.claude/settings.json` load for every project. Atlassian tools (Jira/Confluence) and mi-auditor-specific MCP servers (memory-bridge, luxito-memory) were loaded globally, adding overhead to coding sessions that never use them.

### Model selection
`ANTHROPIC_MODEL=global.anthropic.claude-opus-4-6-v1` was set in `~/.zshrc`, causing all Claude Code sessions and spawned subagents to use Opus ($5/$25 per MTok) for tasks where Sonnet ($3/$15 per MTok) produces equivalent results.

## Changes Implemented

### 1. Default model: Opus → Sonnet (40% cost reduction)

| File | Change |
|------|--------|
| `~/.zshrc` | `ANTHROPIC_MODEL='global.anthropic.claude-sonnet-4-6'` |
| `~/.claude/claude-model-switch.sh` | Bedrock mode defaults to Sonnet |

### 2. Plugin scoping: global → per-project (~7K tokens/request saved)

| File | Change |
|------|--------|
| `~/.claude/settings.json` | Disabled: `atlassian` (28 tools, 4,465 tok), `claude-mem` (4 tools + context injection) |
| `mi-auditor/.claude/settings.json` | Re-enabled `atlassian` and `claude-mem` at project level |
| `mi-auditor/.mcp.json` | Created — moved `memory-bridge` and `luxito-memory` MCP servers from global to project scope |

### 3. MCP server scoping: global → project-specific

Memory-bridge and luxito-memory MCP servers were mi-auditor-specific but loaded globally, adding tool definitions to every project session.

## Efficiency metrics (before)

| Model | Reqs | Avg Input | Avg Output | Output % | Total Spend | Cost/1K output |
|-------|------|-----------|------------|----------|-------------|----------------|
| Opus | 204 | 64K | 559 | 2.0% | $15.55 | $0.1364 |
| Sonnet | 378 | 89K | 686 | 3.5% | $2.18 | $0.0084 |
| Haiku | 407 | 4K | 57 | 8.2% | $0.79 | $0.0338 |

## Expected metrics (after)

| Model | Est. Reqs | Avg Input | Est. Spend | Reduction |
|-------|-----------|-----------|------------|-----------|
| Sonnet | ~580 | ~75K (-15K tools) | ~$6-8 | ~60-65% |
| Haiku | ~400 | ~4K | ~$0.79 | Same |
| Opus | ~10 (on-demand) | ~80K | ~$0.80 | -95% |

## Architecture: dynamic tool loading

Claude Code does not support per-task dynamic tool activation within a session. Tools are determined at session start from:

1. **Global settings** (`~/.claude/settings.json`) — minimal plugins
2. **Project settings** (`.claude/settings.json` in repo) — project-specific plugins
3. **MCP servers** (`.mcp.json` in repo) — project-specific servers

This layered approach is the right pattern: keep global config lean, add what each project needs at the project level.

---

## Phase 2: Prompt-Level Optimizations (Implemented)

### 4. Batch similar tickets (reduce subagent setup overhead)

Added batch grouping rule to Wave Selection in `skills/backlog-implementer/SKILL.md`:
- When 2+ tickets share same prefix, directory, and change pattern → group into one slot
- Implementer processes them sequentially (edit→commit→next), reusing context
- Avoids paying 26K tokens of subagent setup overhead per ticket

### 5. Compress SKILL.md prompts (~2K tokens saved per invocation)

| Metric | Before | After | Reduction |
|--------|--------|-------|-----------|
| Lines | 819 | 528 | 35% |
| Chars | 28,000 | 22,745 | 19% |
| Est. tokens | ~7,000 | ~5,700 | ~1,300 tokens |

Compressions applied:
- Priority table → inline notation
- State schema (37 lines JSON) → 1-line reference to `migrate-state.py`
- Phase 0.5 (37 lines) → 3 lines
- TDD table → inline: "Min 3 tests: 1 happy path + 1 error path + 1 edge case"
- Focus types table → inline
- Pricing table → inline
- Cost templates → compressed
- Co-Authored-By → generic `Claude` (not model-specific)
- Extracted state migration Python to `scripts/implementer/migrate-state.py`

### 6. Context management rules (prevent linear context growth)

Added to SKILL.md after Iron Laws — included in every implementer prompt:
- After file read >100 lines: extract only relevant lines
- After tests: keep only failures + summary count
- After grep/glob: max 20 matching lines
- Batch tickets: reuse file reads across tickets

### 7. Batch API scripts for Plan/Review gates (50% cost reduction)

Created `scripts/ops/batch_submit.py` and `scripts/ops/batch_reconcile.py`:
- Submit ticket markdown files as single-shot Batch API requests via LiteLLM
- 50% cost discount for non-interactive Plan and Review processing
- Limitation: no tool_use support — only single-shot messages
- State tracked in `.backlog-ops/batch-state.json`

## Combined impact estimate

| Optimization | Est. savings per session |
|-------------|------------------------|
| Opus → Sonnet default | ~$9 (60% of Opus spend) |
| Plugin scoping | ~$1-2 (7K tokens × 500 reqs × cache miss rate) |
| SKILL.md compression | ~$0.30 (1.3K tokens × ~40 invocations) |
| Context management | ~$1-3 (prevents 50K+ context bloat) |
| Batch tickets | ~$0.50 (saves 1-3 subagent setups per wave) |
| Batch API (Plan/Review) | ~$1-2 (50% off qualifying gates) |
| **Total** | **~$13-17 saved per session (~70-85%)** |

## Future considerations

- **Playwright conditional loading**: Move Playwright MCP server to project-level `.mcp.json` only for projects with E2E tests
- **claude-mem evaluation**: Monitor if re-enabling at project level actually provides value; consider removing entirely if tool call rate remains 0%
- **Subagent system prompt dedup**: Investigate if system prompt overhead can be reduced for subagents spawned within the same session
