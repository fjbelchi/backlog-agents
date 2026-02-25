---
name: backlog-reflect
description: "Deep reflection on implementer waves. Analyzes playbook effectiveness, proposes delta updates, identifies patterns. ACE-inspired self-improvement. v1.0."
allowed-tools: Read, Glob, Grep, Bash, Write, Task
---

# Backlog Reflect v1.0 — ACE-Inspired Deep Reflection

## Role
**Analyst**: Evaluates implementer outcomes across multiple waves, identifies what strategies work, proposes playbook improvements. Does NOT implement code.

## MODEL RULES FOR TASK TOOL

```
model: "sonnet"  → Deep analysis agent (1 call)
model: "sonnet"  → Report writer (1 call), delta applicator (1 call)

BUDGET: Max 3 LLM calls per reflection.
```

## Parameters

Parse from command args:
- `--waves N` → analyze last N waves (default: 10)
- `--dry-run` → show proposed changes without applying

---

## Phase 1: Load Data

Gather all inputs for analysis:

```
1. Usage ledger: read last N entries from .backlog-ops/usage-ledger.jsonl
   Extract per-wave: tickets, gates passed/failed, models used, cost, escalations
2. Playbook: read .claude/playbook.md (parse with playbook_utils.py)
3. Sentinel patterns: read .backlog-ops/sentinel-patterns.json (if exists)
4. Cost history: read .claude/cost-history.json (if exists)
```

If playbook doesn't exist, create a default one:
```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/ops/playbook_utils.py" add \
  .claude/playbook.md "Strategies & Insights" "Initial playbook — will evolve through reflection"
```

## Phase 2: Deep Analysis

Spawn Sonnet analyst with all collected data:

```
Task(
  subagent_type: "general-purpose",
  model: "sonnet",
  prompt: """
You are analyzing implementer wave outcomes to improve the project's learning playbook.

## Current Playbook
{playbook_content_with_stats}

## Wave Outcomes (last {N} waves)
{usage_ledger_summary}

## Sentinel Patterns
{sentinel_patterns_or_"No patterns tracked yet"}

## Cost History
{cost_history_averages_or_"No history yet"}

## Analyze These Dimensions:

1. **Strategy effectiveness**: Which playbook bullets correlate with first-pass gate approval?
   For each bullet used in waves, check if tickets referencing it passed or failed.

2. **Failure patterns**: Are there recurring gate failures (lint, review, escalation) NOT yet in the playbook?
   Propose new bullets for each pattern found.

3. **Unused bullets**: Which bullets were never referenced in the last {N} waves?
   These are candidates for archival.

4. **Near-duplicates**: Are there bullets with very similar content that should be merged?

5. **Cost insights**: Are there cost patterns worth capturing?
   E.g., "type X tickets consistently cost $Y" or "fast-path success rate is Z%"

6. **Classifier accuracy**: If cost-history shows escalations, is the complexity classifier miscalibrating?

## Output Format (JSON):

{
  "bullet_tags": [{"id": "strat-00001", "tag": "helpful", "reason": "..."}],
  "new_bullets": [{"section": "Common Mistakes", "content": "..."}],
  "merge_candidates": [{"ids": ["strat-00001", "strat-00003"], "reason": "similar content"}],
  "archive_candidates": [{"id": "err-00002", "reason": "never used in 10 waves"}],
  "promotion_candidates": [{"id": "strat-00001", "reason": "helpful=15, harmful=0, proven effective"}],
  "cost_insights": ["Simple BUG tickets average $0.28 on fast-path"],
  "classifier_notes": "Classifier accuracy 92%, no action needed",
  "summary": "3 strategies effective, 1 harmful bullet found, 2 new patterns identified"
}
"""
)
```

## Phase 3: Apply Deltas

Parse Sonnet's JSON response and apply changes (skip if `--dry-run`):

```bash
# Update counters for tagged bullets
python3 -c "
from scripts.ops.playbook_utils import update_counters
tags = {bullet_tags_from_analysis}
updated = update_counters('.claude/playbook.md', tags)
print(f'Updated {updated} bullet counters')
"

# Add new bullets
python3 -c "
from scripts.ops.playbook_utils import add_bullet
for b in {new_bullets}:
    bid = add_bullet('.claude/playbook.md', b['section'], b['content'])
    print(f'Added {bid}: {b[\"content\"][:60]}...')
"

# Archive candidates
python3 -c "
from scripts.ops.playbook_utils import archive_bullet
for a in {archive_candidates}:
    archive_bullet('.claude/playbook.md', a['id'], a['reason'])
    print(f'Archived {a[\"id\"]}: {a[\"reason\"]}')
"

# Auto-prune harmful bullets
python3 -c "
from scripts.ops.playbook_utils import prune_playbook
pruned = prune_playbook('.claude/playbook.md')
if pruned: print(f'Auto-pruned {len(pruned)} harmful bullets: {pruned}')
"
```

## Phase 4: Generate Report

Spawn Sonnet write-agent:

```
Task(
  subagent_type: "general-purpose",
  model: "sonnet",
  prompt: """
Write a reflection report to .backlog-ops/reflections/reflect-{YYYY-MM-DD}.md

## Analysis Results
{sonnet_analysis_json}

## Changes Applied
- Counters updated: {N}
- Bullets added: {N}
- Bullets archived: {N}
- Bullets pruned: {N}

Format as markdown with:
1. ## Summary — key findings in 2-3 sentences
2. ## Strategy Effectiveness — table: id, content, helpful, harmful, verdict
3. ## New Patterns Found — list of added bullets with rationale
4. ## Archival & Pruning — what was removed and why
5. ## Cost Insights — trends from cost-history
6. ## Recommendations — top 3 actionable improvements
"""
)
```

Print summary banner:
```
═══ REFLECTION COMPLETE ═══
Waves analyzed: {N} | Bullets tagged: {tagged}
Added: {added} | Archived: {archived} | Pruned: {pruned}
Report: .backlog-ops/reflections/reflect-{date}.md
═══════════════════════════
```

---

## Constraints

**DO**: Read all data before analysis, use playbook_utils.py for all playbook operations, generate report, respect --dry-run.
**DO NOT**: Modify code, modify SKILL.md files, skip Phase 2 analysis, apply changes without analysis.

## Start

1. Parse args (--waves, --dry-run)
2. Resolve CLAUDE_PLUGIN_ROOT
3. Execute Phases 1-4 in order
