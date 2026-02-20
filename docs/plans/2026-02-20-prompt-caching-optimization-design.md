# Prompt Caching Optimization Design

**Status**: Implemented
**Date**: 2026-02-20
**Goal**: Maximize Anthropic prompt cache hit rate (target: >90%) by restructuring prompts, adding cache monitoring, and preventing cache-breaking patterns.

## Context

Analysis of @trq212's post "Lessons from Building Claude Code: Prompt Caching Is Everything" revealed 6 internal engineering patterns from the Claude Code team. Mapped to the backlog-agents toolkit, 4 improvements were identified.

Current cache hit rate: ~98% on Sonnet calls (already high due to stable SKILL.md). These changes formalize the pattern and add monitoring to prevent regression.

## Changes

### 1. Restructure SKILL.md — Static Prefix, Dynamic at Runtime

**Problem**: The Configuration section mixed static reference data with a "read at startup" instruction, creating a semi-dynamic prefix.

**Fix**:
- Added `## Prompt Caching Strategy` section at the top of SKILL.md explaining the static/dynamic split
- Renamed `## Configuration` to `## Configuration Reference` — pure reference, no runtime actions
- Moved all config reading to Phase 0 with explicit "Dynamic Context Loading" label
- Added `cachePolicy` fields to config reference

### 2. Wave-per-Session Pattern (Compaction Avoidance)

**Problem**: Long implementer sessions (>5 waves, 50+ tickets) trigger context compaction, which rebuilds the cache prefix and drops hit rate.

**Fix**:
- Added `sessionMaxWaves` config (default: 5) to `llmOps.cachePolicy`
- Updated MAIN LOOP with session limit check: `wavesThisSession < sessionMaxWaves`
- Added session limit logic in Phase 6: save state → print resume instructions → exit
- State continuity guaranteed via `implementer-state.json`

### 3. Cache Metrics in Usage Ledger

**Problem**: No visibility into prompt cache health. Cache-breaking changes could go undetected.

**Fix**:
- Extended `usage-ledger.jsonl` format with: `cache_read_tokens`, `cache_creation_tokens`, `cache_hit_rate`, `cost_usd`
- Added Phase 0 cache health check: reads last 10 ledger entries, warns if avg hit rate < `warnBelowHitRate` (default: 0.80)
- Added cache hit rate to wave summary banner

### 4. Subagent Prompt Templates

**Problem**: Each subagent prompt was constructed inline by the leader, with no shared prefix. Implementers and reviewers in the same wave couldn't benefit from Anthropic's prompt caching across calls.

**Fix**:
- Created `templates/implementer-prefix.md` — static prefix with role, TDD protocol, context rules, Iron Laws
- Created `templates/reviewer-prefix.md` — static prefix with role, review protocol, focus types, scoring
- Updated Gate 2 (IMPLEMENT) to use template-based prompt construction: static prefix → dynamic suffix
- Updated Gate 4 (REVIEW) to use template-based prompt construction
- SKILL.md Iron Laws and Context Management sections now reference templates as canonical source

## Cache Savings Model

| Scenario | Cache Hit Rate | Effective Input Cost |
|----------|---------------|---------------------|
| No caching | 0% | 100% of list price |
| Current (stable SKILL.md) | ~98% | ~12% of list price |
| With templates (wave of 3 implementers) | ~98% on prefix | ~10% of list price |
| With session limits (no compaction) | Sustained ~98% | ~12% of list price |

The main value is **preventing regression**: without monitoring and session limits, a single prompt change could silently drop from 98% to 0% cache hits, tripling costs.

## Verification

- 44 schema tests pass (including 2 new cachePolicy tests)
- 49 Python tests pass
- JSON validation passes for schema and preset
