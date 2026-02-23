# ACE-Inspired Learning System — Design

**Goal:** Apply ACE (Agentic Context Engineering) patterns to make the backlog toolkit self-improving. Evolving playbook with helpful/harmful counters, dual-mode reflector, intelligent curator, and cost-history feedback loop.

**Inspiration:** ACE paper (arxiv 2510.04618, ICLR 2026) — +10.6% on agent benchmarks, 82-91% latency reduction, 75-83% cost reduction via structured incremental context evolution.

---

## 1. Playbook (`.claude/playbook.md`)

Committed to project repo. Shared via git. Per-project evolution.

### Format (ACE bullet structure)

```
## Strategies & Insights
[strat-00001] helpful=12 harmful=1 :: Always write failing test before implementation — catches spec misunderstandings early
[strat-00002] helpful=8 harmful=3 :: Pre-read all affected files before spawning implementer — reduces redundant file reads by 70%

## Common Mistakes
[err-00001] helpful=5 harmful=0 :: useRef hooks in React must reset on dependency changes — sentinel caught this 3x

## Cost Patterns
[cost-00001] helpful=7 harmful=0 :: Simple bug fixes (1-3 files) route to fast-path — 80% cheaper than full pipeline
[cost-00002] helpful=4 harmful=2 :: Batch similar tickets in same wave — saves context but increases blast radius

## Review Patterns
[rev-00001] helpful=6 harmful=0 :: Qwen3 pre-review catches 60% of lint issues — reduces Sonnet review tokens by 40%
```

### Counter Update Rules

```
helpful++ when:
  - Strategy referenced by agent AND gate passes (test/lint/review)
  - Pattern avoided AND no regression introduced
  - Cost pattern followed AND actual cost within 20% of estimate

harmful++ when:
  - Strategy referenced by agent AND gate fails
  - Pattern applied but caused regression or escalation
  - Cost pattern followed but actual cost exceeded estimate by >50%

Pruning threshold: harmful > helpful AND total_uses > 5 → archive
Promotion threshold: helpful >= 10 AND harmful <= 2 → inject into code-rules as soft gate
```

### Injection into Implementer Prompts

The leader selects top-K relevant bullets (K=10) by matching:
- Ticket tags against bullet sections
- Affected file patterns against bullet content
- Ticket type (BUG→Common Mistakes, FEAT→Strategies)

Injected after Code Rules, before Iron Laws in implementer prompt.

---

## 2. Reflector (Dual-Mode)

### 2a. Micro-Reflector (automatic, Phase 6, Haiku, ~$0.01)

Runs inside wave summary. Input: wave outcomes from usage-ledger.

```
Task(
  subagent_type: "general-purpose",
  model: "haiku",
  prompt: """
Analyze this wave's outcomes and tag playbook bullets.

## Wave Results
- Tickets: {completed}/{attempted}
- Gates failed: {gate_failures_with_reasons}
- Escalations: {fast_path_escalations}
- Models used: {model_breakdown}
- Cost: ${wave_cost}

## Current Playbook Bullets Used This Wave
{bullets_referenced_with_ids}

## Instructions
1. Tag each referenced bullet: helpful, harmful, or neutral
2. If a gate failed, identify root cause and propose 1 new bullet (ADD)
3. If fast-path escalated, explain why classifier was wrong
4. Max 3 tags + 1 new bullet per wave

Return JSON:
{"bullet_tags": [{"id": "strat-00001", "tag": "helpful"}],
 "new_bullets": [{"section": "Common Mistakes", "content": "..."}],
 "reasoning": "..."}
"""
)
```

### 2b. Deep Reflector (manual, `/backlog-toolkit:reflect`, Sonnet, ~$0.10)

Analyzes multiple waves. Cross-references patterns.

```
Input:
- Last N waves from usage-ledger.jsonl (default: 10)
- Current playbook.md
- Sentinel pattern ledger
- Cost-history.json

Analysis:
1. Which strategies correlate with first-pass review approval?
2. Which correlate with escalations or gate failures?
3. Are there recurring failure patterns not yet in playbook?
4. Are there unused bullets (never referenced in N waves)?
5. Are there near-duplicate bullets (semantic similarity >0.85)?

Output:
- Structured delta operations (ADD/MERGE/DELETE)
- Deduplication recommendations
- Pruning candidates (harmful > helpful)
- Promotion candidates (high helpful, low harmful)
- Report to .backlog-ops/reflections/reflect-{date}.md
```

---

## 3. Curator (integrated)

### Delta Operations

```
ADD:    New bullet with id auto-generated, counters at 0/0
MERGE:  Combine 2+ similar bullets, sum counters, LLM merges content
DELETE: Archive bullet (move to ## Archived section with reason)
UPDATE: Increment helpful/harmful counters (no LLM needed)
```

### Deduplication (from ACE BulletpointAnalyzer)

After each curator cycle:
1. Encode all bullet contents via sentence similarity
2. Find pairs with similarity > 0.85
3. Merge: sum counters, use Haiku to combine content
4. Log compression ratio

### Pruning Rules

```
Archive when ALL true:
  - harmful > helpful
  - total_uses (helpful + harmful) > 5
  - age > 7 days (not a new bullet still being tested)

Never prune:
  - Bullets promoted to code-rules (managed by sentinel)
  - Bullets with helpful >= 10 (proven valuable)
```

### Integration Points

- **Sentinel**: When pattern crosses escalation threshold → curator ADDs to playbook
- **Micro-reflector**: After each wave → curator UPDATEs counters
- **Deep reflector**: On manual invoke → curator applies full delta set
- **Implementer Phase 0**: Reads playbook, selects relevant bullets

---

## 4. Cost-History Feedback Loop

### Storage: `.claude/cost-history.json`

```json
{
  "version": "1.0",
  "entries": [
    {
      "ticket_id": "BUG-001",
      "ticket_type": "BUG",
      "complexity": "simple",
      "pipeline": "fast",
      "files_modified": 2,
      "files_created": 0,
      "tests_added": 3,
      "total_tokens": 45000,
      "cost_usd": 0.28,
      "model_breakdown": {"sonnet": 1},
      "review_rounds": 1,
      "gates_passed_first_try": 5,
      "date": "2026-02-23"
    }
  ],
  "averages": {
    "by_type": {
      "BUG": {"avg_cost": 0.35, "avg_tokens": 52000, "avg_files": 2.1, "sample_size": 15},
      "FEAT": {"avg_cost": 1.20, "avg_tokens": 180000, "avg_files": 4.3, "sample_size": 8}
    },
    "by_complexity": {
      "trivial": {"avg_cost": 0.12, "sample_size": 5},
      "simple": {"avg_cost": 0.35, "sample_size": 20},
      "complex": {"avg_cost": 2.10, "sample_size": 7}
    },
    "by_pipeline": {
      "fast": {"avg_cost": 0.28, "success_rate": 0.92},
      "full": {"avg_cost": 1.85, "success_rate": 0.95}
    }
  }
}
```

### Feedback to backlog-ticket

When `backlog-ticket` estimates cost, it reads cost-history.json:
1. Match ticket type + estimated complexity
2. Use rolling average (last 20 matching tickets)
3. Adjust by file count ratio: `estimate = avg_cost * (files / avg_files)`
4. Add confidence interval from sample variance

### Feedback to implementer classifier

The complexity classifier uses cost-history to improve:
- If "simple" tickets consistently escalate to full-path → adjust heuristic thresholds
- If "complex" tickets consistently finish in fast-path → classifier is too conservative
- Log: `classifier_accuracy = 1 - escalations / total_classified`

---

## 5. Files

```
Create: scripts/ops/playbook_utils.py    — Parse/update/prune playbook bullets
Create: scripts/ops/reflector.py         — Deep reflector analysis logic
Modify: skills/backlog-implementer/SKILL.md — Phase 0 playbook load, Phase 6 micro-reflect
Create: skills/backlog-reflect/SKILL.md  — Deep reflector skill
Create: skills/backlog-reflect/CLAUDE.md — Skill documentation
Create: commands/reflect.md              — Command definition
Modify: .claude-plugin/plugin.json       — Register reflect command
Modify: skills/backlog-ticket/SKILL.md   — Cost-history feedback integration
Create: scripts/ops/cost_history.py      — Cost-history management
```

## 6. Cost Model

| Component | Model | Frequency | Cost |
|-----------|-------|-----------|------|
| Micro-reflector | Haiku | Every wave | ~$0.01 |
| Counter updates | No LLM | Every gate | $0.00 |
| Deep reflector | Sonnet | Manual | ~$0.10 |
| Curator dedup | Haiku | After deep reflect | ~$0.02 |
| Playbook injection | No LLM | Every implementer | $0.00 |
| Cost-history update | No LLM | Every ticket | $0.00 |

Total overhead per wave: ~$0.01. Per deep reflection: ~$0.12.

## 7. Verification

1. Run implementer on 5 tickets → playbook should grow with strategies
2. Introduce a known bad pattern → harmful counter should increase, bullet should get pruned
3. Run `/backlog-toolkit:reflect` → should identify unused bullets and propose merges
4. Check cost-history after 10 tickets → averages should stabilize
5. Verify backlog-ticket uses cost-history for estimates
