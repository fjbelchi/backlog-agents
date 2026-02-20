# Wave 1 Audit & Quality Improvements Design

## Context

AUDIT-PERF Wave 1 delivered 4 tickets at **$0.65/ticket** (75% savings vs $2.58/ticket with Opus leader). Code quality scored **8.0/10** but the review found a critical Date deserialization bug and 4 important gaps that Opus would likely have caught. The quality gap comes from edge-case awareness, not core logic.

**Goal**: Close the quality gap from 75% to 90%+ of Opus level without significantly increasing cost.

## Findings Summary

| Phase | Cost | % | Issue |
|-------|-----:|--:|-------|
| Planning + read | $0.83 | 33% | RAG disabled, Haiku reads raw files. 88 calls. |
| Implementation | $0.83 | 33% | Correct — Haiku implements, well-distributed |
| Review | $0.74 | 29% | Sonnet catches real bugs but misses edge cases |
| Overhead | $0.18 | 7% | Init + pricing bug session restart |

Critical bug found: `JSON.parse` doesn't revive `Date` objects in Redis L2 cache round-trip.

## Approach: 4 Changes + Selective Opus Escalation

### Change 1: Enable RAG for Planning Phase

**Problem**: 88 calls ($0.83) just reading files. RAG server is running but `ragPolicy.enabled: false`.

**Fix**: Enable RAG in mi-auditor's `backlog.config.json`:
```json
{
  "llmOps": {
    "ragPolicy": {
      "enabled": true,
      "serverUrl": "http://localhost:5100"
    }
  }
}
```

The implementer skill already has RAG integration (Phase 1 context, Phase 3a plan context). When enabled, it queries RAG for ~800 tokens of context instead of reading full files (~3K+ tokens each). This reduces both call count and token volume in the planning phase.

**Estimated savings**: $0.83 → ~$0.35 planning cost (-58%)

### Change 2: Selective Opus Review (Quality Gate Enhancement)

**Problem**: Sonnet reviews miss edge cases that Opus would catch (Date serialization, error paths, semantic dead weight, migration needs). But Opus for ALL reviews would erase cost savings.

**Fix**: Add a risk-based Opus escalation rule to Gate 4 REVIEW in the implementer skill:

```
REVIEW ESCALATION (new rule for SKILL.md Gate 4):

After Sonnet review APPROVES, check if changes touch HIGH-RISK patterns:
  - Serialization/deserialization (JSON.parse, JSON.stringify, Redis, cache)
  - Database schema (indexes, migrations, model changes)
  - Authentication/authorization
  - External service integration (new imports, API clients)
  - Error handling patterns (try/catch, Promise.all, fallback logic)

If HIGH-RISK pattern detected:
  1. Spawn ONE frontier/Opus review subagent (model: "opus")
  2. Prompt: "Review ONLY the high-risk patterns in this diff: {patterns_found}.
     Check for: type preservation across serialization boundaries,
     error propagation, missing migration steps, defensive edge cases."
  3. If Opus finds Critical/Important issues → CHANGES_REQUESTED
  4. Cost: ~$0.05-0.15 per ticket (1 focused call, not full review)

If NO high-risk pattern: skip Opus review (saves cost on simple changes)
```

This would have caught:
- Date deserialization bug (serialization pattern)
- Missing index migration (database schema pattern)
- Promise.all error propagation (error handling pattern)

**Estimated cost**: +$0.05-0.15/ticket (only for tickets with high-risk patterns)
**Quality impact**: 75% → 90%+ Opus quality match

### Change 3: Fix Ollama/Free Tier

**Problem**: 0 free-tier calls. Phase 0.5 Ollama detection runs but the wave planning and commit messages aren't reaching `llm_call.sh`.

**Root cause investigation needed**: The implementer skill says Gate 1 PLAN and Gate 5 COMMIT should use `free` via `llm_call.sh`, but the LiteLLM logs show 0 `free` model calls from the session. Possible causes:
1. `CLAUDE_PLUGIN_ROOT` not set correctly in the Claude Code session
2. `llm_call.sh` path not found by the skill
3. The skill falls back to template generation without calling llm_call.sh

**Fix**: Add explicit diagnostic logging to Phase 0.5 and verify `CLAUDE_PLUGIN_ROOT` is set. If the script path issue persists, embed `llm_call.sh` as a bash command in the skill prompt rather than referencing a file path.

**Estimated savings**: $0.05-0.10/ticket for plan + commit gates

### Change 4: Fix Critical Date Deserialization Bug

**Problem**: In `publicTariff.service.ts:148`, `JSON.parse(raw) as T` doesn't revive Date objects. After Redis L2 cache hit, `PublicTariff.validFrom` is a string, not a Date.

**Fix** (in mi-auditor repo):
```typescript
// In getCachedWithL2, add Date reviver:
const parsed = JSON.parse(raw, (key, value) => {
  // Revive ISO date strings back to Date objects
  if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T/.test(value)) {
    const d = new Date(value);
    if (!isNaN(d.getTime())) return d;
  }
  return value;
}) as T;
```

Also fix the redundant Redis write: when warming L1 from L2, skip the L2 write-back.

**Also needed**:
- Add test: verify Date type preservation through L2 round-trip
- Add test: Promise.all partial failure in analytics repository
- Clean up: remove unused `import type { Types }` in test file
- Document: index migration runbook for PERF-002

## Projected Impact

| Metric | Current | Projected | Change |
|--------|---------|-----------|--------|
| Cost/ticket | $0.65 | $0.45-0.55 | -23% to -31% |
| Quality score | 8.0/10 | 9.0+/10 | +12% |
| Critical bugs missed | 1 | 0 (target) | -100% |
| Planning cost | $0.21/ticket | $0.09/ticket | -57% |
| Opus cost | $0/ticket | $0.05-0.15/ticket | controlled |
| Savings vs Opus baseline | 75% | 79-83% | better |

## Implementation Order

1. Fix Date bug in mi-auditor (critical, immediate)
2. Enable RAG in mi-auditor config (quick, high savings)
3. Update implementer SKILL.md with Opus escalation rule (quality improvement)
4. Debug Ollama/free tier path (investigation + fix)
5. Run another AUDIT-PERF wave to validate improvements
