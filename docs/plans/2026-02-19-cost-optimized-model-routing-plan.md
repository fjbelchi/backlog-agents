# Cost-Optimized Model Routing Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reduce per-ticket cost 33-51% by routing dev tasks to Ollama/Haiku and review to Sonnet.

**Architecture:** Update config schema, preset defaults, and SKILL.md routing rules. No new files — all edits to existing files.

**Tech Stack:** JSON Schema, JSON presets, Markdown skill files, Bash tests

---

### Task 1: Add entryModelPlan to config schema

**Files:**
- Modify: `config/backlog.config.schema.json:320-352` (llmOps.routing.properties)

**Step 1: Add the new property**

In `config/backlog.config.schema.json`, inside `llmOps.routing.properties` (after `entryModelDraft` at ~line 330), add:

```json
"entryModelPlan": {
  "type": "string",
  "description": "Model alias for planning gates (text-only, no tool_use). Supports Ollama/local models.",
  "default": "free"
},
```

**Step 2: Validate JSON**

Run: `python3 -c "import json; json.load(open('config/backlog.config.schema.json'))"`
Expected: No output (valid JSON)

**Step 3: Run existing tests**

Run: `bash tests/test-config-schema.sh`
Expected: All tests PASS

**Step 4: Commit**

```bash
git add config/backlog.config.schema.json
git commit -m "feat(schema): add entryModelPlan for Ollama routing"
```

---

### Task 2: Update default preset routing values

**Files:**
- Modify: `config/presets/default.json:85-92` (llmOps.routing)

**Step 1: Update routing values**

Replace the routing block in `config/presets/default.json`:

```json
"routing": {
  "entryModelClassify": "free",
  "entryModelPlan": "free",
  "entryModelDraft": "free",
  "entryModelImplement": "cheap",
  "entryModelReview": "balanced",
  "escalationModel": "frontier",
  "maxEscalationsPerTicket": 1
},
```

Changes from current:
- `entryModelClassify`: "cheap" → "free"
- `entryModelPlan`: NEW, set to "free"
- `entryModelDraft`: "cheap" → "free"
- `entryModelImplement`: "balanced" → "cheap"
- `entryModelReview`: "cheap" → "balanced"

**Step 2: Validate JSON**

Run: `python3 -c "import json; json.load(open('config/presets/default.json'))"`
Expected: No output (valid JSON)

**Step 3: Run existing tests**

Run: `bash tests/test-config-schema.sh`
Expected: All tests PASS

**Step 4: Commit**

```bash
git add config/presets/default.json
git commit -m "feat(preset): update routing defaults for cost optimization"
```

---

### Task 3: Add schema test for entryModelPlan

**Files:**
- Modify: `tests/test-config-schema.sh` (add test section after reviewPipeline checks)

**Step 1: Add routing schema tests**

After the `-- reviewPipeline preset sub-keys --` section (~line 278), add:

```bash
# ── llmOps.routing sub-keys ──────────────────────────────────────────

echo "-- llmOps.routing sub-keys --"

ROUTING_KEYS=(entryModelClassify entryModelPlan entryModelDraft entryModelImplement entryModelReview escalationModel)

for key in "${ROUTING_KEYS[@]}"; do
  if python3 -c "
import json, sys
d = json.load(open(sys.argv[1]))
assert sys.argv[2] in d['llmOps']['routing']
" "$PRESET" "$key" 2>/dev/null; then
    pass "llmOps.routing.${key} present"
  else
    fail "llmOps.routing.${key} missing"
  fi
done

echo ""
```

**Step 2: Run tests**

Run: `bash tests/test-config-schema.sh`
Expected: All tests PASS including new `llmOps.routing.entryModelPlan present`

**Step 3: Commit**

```bash
git add tests/test-config-schema.sh
git commit -m "test: add routing schema validation for entryModelPlan"
```

---

### Task 4: Update SKILL.md MODEL RULES and gate defaults

**Files:**
- Modify: `skills/backlog-implementer/SKILL.md:12-88`

**Step 1: Update MODEL RULES block (lines 12-25)**

Replace the MODEL RULES block with:

```
## MODEL RULES FOR TASK TOOL

\```
model: "haiku"   → DEFAULT for implementers, investigators, write-agents,
                   wave planning subagents. Cost-optimized tier.

model: "sonnet"  → REVIEWERS ONLY. All Gate 4 review subagents use Sonnet
                   for higher-quality defect detection.

ESCALATION to parent model (omit model: parameter):
  - Ticket tagged ARCH or SECURITY
  - qualityGateFails >= 2 for a ticket
  - ticket.complexity == "high"
  In these cases, the subagent inherits the parent model.

OLLAMA (free tier, via llm_call.sh):
  - Wave planning JSON generation
  - Gate 1 PLAN text generation
  - Gate 5 COMMIT message generation
  - Classification/triage
  These use llm_call.sh --model free. If Ollama fails → fallback to
  Task(model: "haiku") subagent.
\```
```

**Step 2: Update gate defaults table (lines 74-88)**

Replace the gate default block with:

```
1. Check ticket tags: ARCH or SECURITY tag → "frontier"
2. Check gate fail count: qualityGateFails >= 2 → "frontier"
3. Check ticket.complexity == "high" → "frontier"
4. Use gate default:
   Wave Plan  → config.llmOps.routing.entryModelPlan      (default: "free" via llm_call.sh)
   Gate 1 PLAN      → config.llmOps.routing.entryModelPlan (default: "free" via llm_call.sh)
   Gate 2 IMPLEMENT → config.llmOps.routing.entryModelImplement  (default: "cheap")
   Gate 3 LINT      → always "cheap" (runs tools, LLM analyzes output)
   Gate 4 REVIEW    → config.llmOps.routing.entryModelReview     (default: "balanced")
   Gate 5 COMMIT    → "free" via llm_call.sh (template fallback if Ollama unavailable)
```

**Step 3: Update OUTPUT DISCIPLINE block (lines 27-34)**

Change `sonnet` references to `haiku`:

```
- Wave planning → delegate to haiku subagent (returns JSON), or llm_call.sh --model free
- Wave summary → delegate to haiku write-agent (writes log, returns JSON)
```

**Step 4: Commit**

```bash
git add skills/backlog-implementer/SKILL.md
git commit -m "feat(implementer): update model rules for cost-optimized routing"
```

---

### Task 5: Update SKILL.md Wave Planning and Team Creation

**Files:**
- Modify: `skills/backlog-implementer/SKILL.md:190-261`

**Step 1: Update Phase 1 Wave Planning (lines 194-231)**

Replace the Task() call with Ollama-first logic:

```
Delegate wave planning to Ollama first, Haiku subagent fallback:

\```
# Try Ollama first (free)
WAVE_JSON=$(bash "${CLAUDE_PLUGIN_ROOT}/scripts/ops/llm_call.sh" --model free \
  --system "You analyze tickets and return wave plans as JSON. No explanations." \
  --user "Tickets: {ticket_metadata_list}

Rules:
- Group into 2-3 slots WITHOUT file conflicts
- Never parallelize: same file, depends_on, create-then-import
- Select subagent_type per ticket based on file patterns

Return ONLY JSON: {\"waves\":[{\"wave\":1,\"tickets\":[{\"id\":\"BUG-001\",\"subagent_type\":\"backend\",\"rationale\":\"auth\"}]}],\"skipped\":[]}")

# Validate JSON response
if ! echo "$WAVE_JSON" | python3 -c "import json,sys; json.load(sys.stdin)" 2>/dev/null; then
  # Fallback to Haiku subagent
  Task(subagent_type: "general-purpose", model: "haiku", prompt: "...same prompt...")
fi
\```
```

**Step 2: Update Phase 2 Team Creation (lines 240-261)**

Change all `model: "sonnet"` to `model: "haiku"` for implementers and investigator. Change reviewer to `model: "sonnet"`:

```
Spawn teammates via Task tool:

1. implementer-1:
   model: "haiku"  (omit if ARCH/SECURITY/escalation → inherits parent)

2. code-reviewer:
   model: "sonnet"

3. investigator:
   model: "haiku"
```

**Step 3: Commit**

```bash
git add skills/backlog-implementer/SKILL.md
git commit -m "feat(implementer): wave planning via Ollama, team uses Haiku/Sonnet split"
```

---

### Task 6: Update SKILL.md Gates 1, 2, 4, 5 and Phase 6

**Files:**
- Modify: `skills/backlog-implementer/SKILL.md:267-418`

**Step 1: Update Gate 1 PLAN (line 269)**

Change model line to:
```
**Model**: apply escalation rules. Default: `entryModelPlan` (free via llm_call.sh).
If Ollama unavailable or response invalid → fallback to Task(model: "haiku").
```

**Step 2: Update Gate 2 IMPLEMENT (line 291)**

Change model line to:
```
**Model**: apply escalation rules. Default: `entryModelImplement` (cheap/Haiku). Escalate to balanced if qualityGateFails >= 1, frontier if ARCH/SECURITY tag or qualityGateFails >= 2.
```

**Step 3: Update Gate 4 REVIEW (line 322)**

Change model line to:
```
**Model**: `entryModelReview` (balanced/Sonnet). Sonnet provides higher-quality defect detection.
Escalate to frontier after 2nd review failure.
```

**Step 4: Update Gate 5 COMMIT (lines 337-350)**

Add Ollama commit message generation before the git commands:
```
Generate commit message via Ollama (free), template fallback:

\```bash
COMMIT_MSG=$(bash "${CLAUDE_PLUGIN_ROOT}/scripts/ops/llm_call.sh" --model free \
  --system "Generate a git commit message in Conventional Commits format. Return ONLY the message." \
  --user "Type: {type}, Area: {area}, Ticket: {ticket_id}, Changes: {summary}")

# Fallback to template if Ollama fails
if [ -z "$COMMIT_MSG" ]; then
  COMMIT_MSG="{type}({area}): implement {ticket_id}"
fi
\```
```

**Step 5: Update Phase 6 Wave Summary (lines 396-417)**

Change model from "sonnet" to "haiku" in the Task() call:
```
Task(
  subagent_type: "general-purpose",
  model: "haiku",
  prompt: """You are a write-agent..."""
)
```

**Step 6: Commit**

```bash
git add skills/backlog-implementer/SKILL.md
git commit -m "feat(implementer): gates use Ollama/Haiku/Sonnet cost-optimized routing"
```

---

### Task 7: Update SKILL.md escalation logic

**Files:**
- Modify: `skills/backlog-implementer/SKILL.md:96-118` (Local Model Routing section)

**Step 1: Expand escalation rules**

Update the escalation section to cover Haiku→Sonnet escalation (not just Ollama→Cloud):

```
ESCALATION RULES:
  Gate 2 (IMPLEMENT via Haiku) fails Gate 3/4 once:
    → Re-run Gate 2 with Task(model: "sonnet")
    → stats.localModelStats.escalatedToCloud++
    → stats.localModelStats.failuresByType[gate]++
    → Message: "Haiku failed on {id} at {gate}. Escalated to Sonnet."

  Gate 1 (PLAN via Ollama) returns empty/invalid:
    → Fallback to Task(model: "haiku")
    → No stats increment (expected behavior)

  Gate 5 (COMMIT via Ollama) returns empty:
    → Use template: "{type}({area}): implement {ticket_id}"
    → No stats increment (expected behavior)
```

**Step 2: Run all Python tests**

Run: `python3 -m pytest tests/ -v`
Expected: All tests PASS

**Step 3: Commit**

```bash
git add skills/backlog-implementer/SKILL.md
git commit -m "feat(implementer): add Haiku→Sonnet escalation rules"
```

---

### Task 8: Verify proxy fallbacks and run full validation

**Files:**
- Read-only: `config/litellm/proxy-config.docker.yaml` (verify, no changes needed)

**Step 1: Verify proxy fallback chain includes free→cheap**

Check that `proxy-config.docker.yaml` has:
```yaml
fallbacks:
  - free: [cheap, balanced]
```
This was added in the local model integration. Confirm it exists.

**Step 2: Run all validation**

```bash
bash tests/test-config-schema.sh
python3 -m pytest tests/ -v
python3 -c "import yaml; yaml.safe_load(open('config/litellm/proxy-config.docker.yaml'))"
```

Expected: All pass.

**Step 3: Final commit with design doc status update**

Update `docs/plans/2026-02-19-cost-optimized-model-routing-design.md` line 2:
Change `**Status**: Approved` to `**Status**: Implemented`

```bash
git add docs/plans/2026-02-19-cost-optimized-model-routing-design.md
git commit -m "docs: mark cost-optimized routing design as implemented"
```
