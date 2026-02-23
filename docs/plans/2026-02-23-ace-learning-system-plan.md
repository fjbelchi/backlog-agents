# ACE-Inspired Learning System — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Self-improving toolkit with evolving playbook, dual-mode reflector, curator, and cost-history feedback.

**Architecture:** Playbook in `.claude/playbook.md` (committed to repo), micro-reflector in implementer Phase 6, deep reflector as new skill, cost-history in `.claude/cost-history.json`.

**Tech Stack:** Python (playbook_utils.py, cost_history.py), Markdown/prompt (SKILL.md), Shell integration

**Design doc:** `docs/plans/2026-02-23-ace-learning-system-design.md`

---

### Task 1: Create playbook_utils.py

**Files:**
- Create: `scripts/ops/playbook_utils.py`

**Step 1: Write the script**

Python module with these functions:
- `parse_playbook(path)` → list of dicts `{id, section, helpful, harmful, content, raw_line}`
- `parse_bullet(line)` → dict or None. Regex: `\[([^\]]+)\]\s*helpful=(\d+)\s*harmful=(\d+)\s*::\s*(.*)`
- `update_counters(path, tags)` → tags is `[{id, tag}]` where tag is helpful/harmful/neutral. Reads file, increments counters, writes back.
- `add_bullet(path, section, content)` → auto-generates next ID for section prefix, appends bullet with helpful=0 harmful=0
- `archive_bullet(path, bullet_id, reason)` → moves bullet to `## Archived` section with reason
- `prune_playbook(path)` → archives bullets where harmful > helpful AND total > 5 AND age > 7 days
- `get_stats(path)` → dict with total_bullets, high_performing (helpful>5, harmful<2), problematic (harmful>=helpful), unused (both=0)
- `select_relevant(path, ticket_type, tags, affected_files, k=10)` → returns top-K bullets by section matching

**Step 2: Commit**

```bash
git add scripts/ops/playbook_utils.py
git commit -m "feat(ace): add playbook_utils.py for bullet parsing and curation"
```

---

### Task 2: Create cost_history.py

**Files:**
- Create: `scripts/ops/cost_history.py`

**Step 1: Write the script**

Python module:
- `load_history(path=".claude/cost-history.json")` → dict (creates default if missing)
- `add_entry(path, entry_dict)` → appends entry, recalculates averages
- `recalculate_averages(data)` → rolling averages by_type, by_complexity, by_pipeline (last 20 per category)
- `estimate_cost(path, ticket_type, complexity, file_count)` → returns `{estimate, confidence, sample_size}` using historical averages
- `get_classifier_accuracy(path)` → returns `1 - escalations / total` from pipeline field

**Step 2: Commit**

```bash
git add scripts/ops/cost_history.py
git commit -m "feat(ace): add cost_history.py for feedback loop"
```

---

### Task 3: Create reflect skill (SKILL.md + CLAUDE.md + command)

**Files:**
- Create: `skills/backlog-reflect/SKILL.md`
- Create: `skills/backlog-reflect/CLAUDE.md`
- Create: `commands/reflect.md`

**Step 1: Write SKILL.md**

Frontmatter: name=backlog-reflect, description="Deep reflection on implementer waves. Analyzes playbook effectiveness, proposes delta updates, identifies patterns. ACE-inspired. v1.0.", allowed-tools=Read,Glob,Grep,Bash,Write,Task

Content:
- Role: Analyst. Does NOT implement code.
- MODEL RULES: model "sonnet" for analysis (1 call), model "haiku" for report writing (1 call). Budget: 3 max.
- Phase 1: Load data (usage-ledger last N waves, playbook.md, sentinel-patterns.json, cost-history.json)
- Phase 2: Spawn Sonnet analyst with all data, analyze correlations, output structured JSON with bullet_tags, new_bullets, merge_candidates, prune_candidates, promotion_candidates
- Phase 3: Apply deltas via playbook_utils.py (python3 calls)
- Phase 4: Generate report via Haiku write-agent to .backlog-ops/reflections/reflect-{date}.md
- Constraints: DO read all data before analysis, DO NOT modify code, DO NOT modify SKILL.md files

**Step 2: Write CLAUDE.md**

Purpose, modes, cost model ($0.10-0.15 per invocation), dependencies.

**Step 3: Write commands/reflect.md**

Command `/backlog-toolkit:reflect [--waves N]`, delegates to skill.

**Step 4: Commit**

```bash
git add skills/backlog-reflect/ commands/reflect.md
git commit -m "feat(ace): create reflect skill with deep analysis mode"
```

---

### Task 4: Register reflect command in plugin.json

**Files:**
- Modify: `.claude-plugin/plugin.json`

**Step 1:** Add `"./commands/reflect.md"` to commands array.

**Step 2: Commit**

```bash
git add .claude-plugin/plugin.json
git commit -m "feat(ace): register reflect command in plugin.json"
```

---

### Task 5: Add micro-reflector to implementer Phase 6

**Files:**
- Modify: `skills/backlog-implementer/SKILL.md` — Phase 6 section

**Step 1: Add micro-reflection after wave summary write-agent**

Insert between the wave summary write-agent and the banner print. Add:

```
### Micro-Reflection (v8.0 — ACE-inspired)

After the write-agent completes, if `.claude/playbook.md` exists, run micro-reflection:

1. Collect wave outcomes: completed/failed tickets, gate failures, escalations, cost
2. Read playbook bullets that were injected this wave (tracked in wave context)
3. Spawn Haiku reflector:

Task(
  subagent_type: "general-purpose",
  model: "haiku",
  prompt: """...(micro-reflector prompt from design doc)..."""
)

4. Parse JSON response
5. Apply counter updates: python3 scripts/ops/playbook_utils.py update_counters
6. Apply new bullets: python3 scripts/ops/playbook_utils.py add_bullet
7. Log: "Micro-reflection: tagged {N} bullets, added {M} new insights"

If playbook.md doesn't exist or reflector fails: skip silently (non-blocking).
```

**Step 2: Commit**

```bash
git add skills/backlog-implementer/SKILL.md
git commit -m "feat(ace): add micro-reflector to implementer Phase 6"
```

---

### Task 6: Add playbook loading to implementer Phase 0

**Files:**
- Modify: `skills/backlog-implementer/SKILL.md` — Phase 0 section

**Step 1: Add playbook loading after step 8 (show banner)**

Insert new step before banner:

```
8. **Load playbook** (if `.claude/playbook.md` exists):
   Parse with playbook_utils. Get stats. Log: "Playbook: {total} bullets ({high_performing} high, {problematic} problematic)".
   Auto-prune: run prune_playbook() to archive harmful bullets.
```

**Step 2: Add playbook injection to Gate 2 prompt construction**

In the implementer prompt construction (dynamic suffix section), add after Code Rules and before Catalog Disciplines:

```
b2. PLAYBOOK CONTEXT (ACE-inspired learning)
    Select relevant bullets: python3 scripts/ops/playbook_utils.py select_relevant
    Inject top-K (K=10) bullets matching ticket type, tags, affected files.
    Format: "## Learned Strategies\n{selected_bullets}"
```

**Step 3: Commit**

```bash
git add skills/backlog-implementer/SKILL.md
git commit -m "feat(ace): add playbook loading and injection to implementer"
```

---

### Task 7: Add cost-history integration to implementer Phase 4

**Files:**
- Modify: `skills/backlog-implementer/SKILL.md` — Phase 4 section

**Step 1: Add cost-history update in Phase 4.3**

In the "Update Cost History" subsection, replace the current description with integration using cost_history.py:

```
### 4.3 Update Cost History (ACE feedback loop)

After computing actual cost, update cost-history.json:
python3 -c "
from scripts.ops.cost_history import add_entry
add_entry('.claude/cost-history.json', {
  'ticket_id': '{ticket_id}', 'ticket_type': '{type}',
  'complexity': '{computed_complexity}', 'pipeline': '{fast|full}',
  'files_modified': {N}, 'files_created': {N}, 'tests_added': {N},
  'total_tokens': {N}, 'cost_usd': {cost}, 'review_rounds': {N},
  'gates_passed_first_try': {N}, 'date': '{date}'
})"

This auto-recalculates rolling averages by type, complexity, and pipeline.
```

**Step 2: Commit**

```bash
git add skills/backlog-implementer/SKILL.md
git commit -m "feat(ace): integrate cost-history feedback in implementer Phase 4"
```

---

### Task 8: Add cost-history feedback to backlog-ticket

**Files:**
- Modify: `skills/backlog-ticket/SKILL.md`

**Step 1: Add cost estimation from history**

In the cost estimation section of backlog-ticket, add:

```
### Historical Cost Estimation (ACE feedback loop)

If `.claude/cost-history.json` exists, use historical data for estimation:

python3 -c "
from scripts.ops.cost_history import estimate_cost
result = estimate_cost('.claude/cost-history.json', '{ticket_type}', '{complexity}', {file_count})
print(f'Historical estimate: ${result[\"estimate\"]:.2f} (confidence: {result[\"confidence\"]:.0%}, n={result[\"sample_size\"]})')
"

If history available AND sample_size >= 5: use historical estimate as primary.
If history unavailable or sample_size < 5: use model-based estimate (current behavior).
Show both when available: "Estimated: $X.XX (model) / $Y.YY (historical, n=N)"
```

**Step 2: Commit**

```bash
git add skills/backlog-ticket/SKILL.md
git commit -m "feat(ace): add cost-history feedback to backlog-ticket"
```

---

## Verification

1. `python3 -c "from scripts.ops.playbook_utils import parse_playbook; print('OK')"` → imports clean
2. `python3 -c "from scripts.ops.cost_history import load_history; print('OK')"` → imports clean
3. Run implementer on 1 ticket → Phase 0 loads playbook, Phase 4 updates cost-history, Phase 6 runs micro-reflection
4. Run `/backlog-toolkit:reflect --waves 5` → generates reflection report
5. Check `.claude/playbook.md` has updated counters after wave
6. Check `.claude/cost-history.json` has entry after ticket completion
