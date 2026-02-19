# Command: /backlog-toolkit:sentinel

Analyze HEAD commit with deterministic prescan + 2 parallel LLM reviewers.
Creates validated backlog tickets for every finding (bugs, security, tech debt).
Installs pre-push git hook on first run for automatic future analysis.
Tracks recurring patterns for continuous learning.

## Syntax

```
/backlog-toolkit:sentinel [--now]
```

## Parameters

- `--now`: Force synchronous ticket creation (default: batch-eligible)

## Examples

### On-demand analysis of HEAD commit
```
/backlog-toolkit:sentinel
```

### Synchronous mode (immediate tickets, no batch queue)
```
/backlog-toolkit:sentinel --now
```

## What it does

1. **Prescan** (deterministic, $0): runs lint, tests, grep on changed files — catches ~50% of findings before any LLM call
2. **RAG** ($0): compresses context to snippets, deduplicates against existing backlog
3. **Reviewers** (LLM): security + quality analysis with focused context only
4. **Tickets**: every finding → validated BUG/SEC/TASK ticket with proper ID, ACs, cost estimate
5. **Learning**: updates `.backlog-ops/sentinel-patterns.json`, proposes codeRules updates when patterns recur 3+ times

## Git Hook

On first run, installs `.git/hooks/pre-push` so sentinel runs automatically before every `git push`.

To disable: set `sentinel.installGitHook: false` in `backlog.config.json`.

## Configuration

```json
{
  "sentinel": {
    "enabled": true,
    "installGitHook": true,
    "prescan": {
      "runLinter": true,
      "runTests": true,
      "detectHardcoded": true,
      "maxFunctionLines": 80
    },
    "reviewers": { "security": true, "quality": true },
    "patternThresholds": { "escalateToSoftGate": 3 }
  }
}
```

## Related

- Skill: `skills/backlog-sentinel/SKILL.md`
- Prescan: `scripts/ops/sentinel_prescan.py`
- Patterns: `scripts/ops/sentinel_patterns.py`
- Design: `docs/plans/2026-02-19-backlog-sentinel-design.md`
