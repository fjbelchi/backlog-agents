# Backlog Sentinel Skill

## Purpose

One-shot code review on HEAD commit. Runs deterministic prescan (lint+tests+grep at $0)
then 2 parallel LLM reviewers for findings requiring judgment.
Creates validated backlog tickets for every finding.
Updates pattern ledger for continuous learning.

## Key Features

1. **Deterministic Prescan**: lint, tests, grep — no LLM, no cost
2. **RAG Context Compression**: snippets not full files, deduplication against backlog
3. **2 Parallel Reviewers**: security-engineer + code-quality, config-driven model tiers
4. **Ticket Integration**: every finding → proper BUG/SEC/TASK ticket via backlog-ticket logic
5. **Pattern Ledger**: tracks recurring errors, auto-escalates to codeRules
6. **Git Hook**: installs pre-push hook on first run

## Invocation

```bash
/backlog-toolkit:sentinel          # on HEAD commit
/backlog-toolkit:sentinel --now    # force synchronous ticket creation
```

## Flow Overview

```
Phase 0:   sentinel_prescan.py   → deterministic findings, $0
Phase 0.5: RAG lookups           → compress context, deduplicate, $0
Phase 1:   2 parallel reviewers  → security + quality LLM analysis
Phase 2:   Ticket creation       → BUG/SEC/TASK via backlog-ticket logic
Phase 3:   Pattern ledger update → continuous learning
Phase 3.5: Git hook install      → future automation
```

## Related Files

- `SKILL.md`: Full skill implementation
- `scripts/ops/sentinel_prescan.py`: Deterministic prescan ($0)
- `scripts/ops/sentinel_patterns.py`: Pattern ledger management
- `.backlog-ops/sentinel-patterns.json`: Pattern ledger (auto-created, commit to share with team)
- `docs/plans/2026-02-19-backlog-sentinel-design.md`: Design rationale

## Cost Model

```
Prescan:          $0.00  (grep, lint, tests)
RAG:              $0.00  (vector search)
security-reviewer ~$0.04 (Sonnet, focused context)
quality-reviewer  ~$0.02 (Haiku, focused context)
ticket creation   ~$0.03 (Haiku, validation)
────────────────────────
Per commit:       ~$0.09
```
