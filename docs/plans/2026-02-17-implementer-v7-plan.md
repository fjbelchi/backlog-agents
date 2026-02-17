# Implementer v7.0 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Upgrade backlog-implementer SKILL.md from v6.1 to v7.0 with smart agent routing, embedded skill catalog, configurable review pipeline, and external skill detection.

**Architecture:** Modify the existing SKILL.md in-place. Add new config schema properties. Update templates and tests.

**Tech Stack:** Markdown (SKILL.md), JSON Schema, Bash (tests)

---

### Task 1: Update Config Schema — Add agentRouting and reviewPipeline

**Files:**
- Modify: `config/backlog.config.schema.json`
- Modify: `config/presets/default.json`

**Step 1: Add agentRouting to schema**

Add `agentRouting` property to the JSON Schema with:
- `rules` array: objects with `pattern` (string), `agent` (string), `label` (string)
- `overrides` object: keyed by ticket prefix, values with optional `investigator` (boolean), `reviewers` (number)
- `llmOverride` boolean, default true

**Step 2: Add reviewPipeline to schema**

Add `reviewPipeline` property with:
- `reviewers` array: objects with `name`, `agent`, `focus`, `required` (boolean)
- `confidenceThreshold` number (0-100, default 80)
- `maxReviewRounds` number (default 3)

**Step 3: Update default preset**

Add default values for both new sections to `config/presets/default.json`.

**Step 4: Run schema validation tests**

Run: `bash tests/test-config-schema.sh`
Expected: All checks pass including new properties.

**Step 5: Commit**

```bash
git add config/backlog.config.schema.json config/presets/default.json
git commit -m "feat(config): add agentRouting and reviewPipeline schema"
```

---

### Task 2: Write Embedded Skill Catalog Section

**Files:**
- Create: `skills/backlog-implementer/catalog/CAT-TDD.md`
- Create: `skills/backlog-implementer/catalog/CAT-REVIEW.md`
- Create: `skills/backlog-implementer/catalog/CAT-DEBUG.md`
- Create: `skills/backlog-implementer/catalog/CAT-SECURITY.md`
- Create: `skills/backlog-implementer/catalog/CAT-ARCH.md`
- Create: `skills/backlog-implementer/catalog/CAT-FRONTEND.md`
- Create: `skills/backlog-implementer/catalog/CAT-PERF.md`

**Step 1: Write CAT-TDD.md**

Extract TDD best practices from superpowers:test-driven-development skill. Include:
- Failing test first (red-green-refactor)
- 3 test types (happy/error/edge)
- Verification before completion
- Stack-specific test commands per language

**Step 2: Write CAT-REVIEW.md**

Extract multi-pass review from code-review plugin. Include:
- 3-pass review (compliance, bugs, coverage)
- Confidence scoring 0-100
- Only report >= threshold
- False positive awareness

**Step 3: Write CAT-DEBUG.md**

Extract from superpowers:systematic-debugging. Include:
- Hypothesis-driven investigation
- Evidence collection before fixes
- Root cause analysis
- Git history mining

**Step 4: Write CAT-SECURITY.md**

OWASP patterns + security review lens. Include:
- Input validation at boundaries
- Injection prevention
- Auth/authz verification
- Secret detection

**Step 5: Write CAT-ARCH.md**

Extract from handbook agents. Include:
- Layered architecture enforcement
- Data integrity first
- Fault tolerance patterns
- API design principles

**Step 6: Write CAT-FRONTEND.md**

Extract from frontend-design plugin + handbook:frontend. Include:
- Component decomposition
- Accessibility-first
- Behavior-driven testing
- TypeScript strict mode

**Step 7: Write CAT-PERF.md**

Extract from Anthropic engineering blog. Include:
- Token efficiency guidelines
- Parallelization patterns
- Effort scaling heuristics
- Tool selection optimization

**Step 8: Commit**

```bash
git add skills/backlog-implementer/catalog/
git commit -m "feat(catalog): add 7 embedded skill disciplines"
```

---

### Task 3: Rewrite SKILL.md Phase 0 — Add Startup + Detection

**Files:**
- Modify: `skills/backlog-implementer/SKILL.md`

**Step 1: Update header to v7.0**

Change version in frontmatter and title.

**Step 2: Add Phase 0.5: Detect Capabilities**

After config load, before wave selection:
- Check for superpowers plugin
- Check for stack-specific plugins
- Check for MCP servers
- Log capabilities banner

**Step 3: Update Configuration table**

Add agentRouting and reviewPipeline config paths.

**Step 4: Commit**

```bash
git add skills/backlog-implementer/SKILL.md
git commit -m "feat(implementer): add Phase 0.5 external skill detection"
```

---

### Task 4: Rewrite SKILL.md Phase 2 — Smart Agent Router

**Files:**
- Modify: `skills/backlog-implementer/SKILL.md`

**Step 1: Replace static team composition with router**

Replace the current "Team Composition" section with the Agent Router algorithm:
1. Read Affected Files from ticket
2. Match against agentRouting.rules
3. Apply LLM override if enabled
4. Apply ticket-type overrides

**Step 2: Update team spawn logic**

Update Phase 2 to spawn implementers with routed agent types.

**Step 3: Add catalog injection to implementer prompts**

Each implementer receives:
- Code rules (existing)
- Relevant catalog disciplines (new)
- Iron Laws (existing, unchanged)

**Step 4: Commit**

```bash
git add skills/backlog-implementer/SKILL.md
git commit -m "feat(implementer): add smart agent routing in Phase 2"
```

---

### Task 5: Rewrite SKILL.md Gate 4 — Configurable Review Pipeline

**Files:**
- Modify: `skills/backlog-implementer/SKILL.md`

**Step 1: Replace single reviewer with configurable pipeline**

Update Gate 4 (REVIEW) to:
- Read reviewPipeline config
- Spawn N reviewers in parallel
- Each reviewer uses CAT-REVIEW catalog + their focus
- Confidence scoring and filtering

**Step 2: Add SEC ticket auto-escalation**

When ticket is SEC-*, auto-add security and git-history reviewers.

**Step 3: Update review consolidation**

Leader consolidates findings from all reviewers, filters by confidence threshold.

**Step 4: Commit**

```bash
git add skills/backlog-implementer/SKILL.md
git commit -m "feat(implementer): configurable multi-reviewer pipeline in Gate 4"
```

---

### Task 6: Update State Schema to v6.0

**Files:**
- Modify: `skills/backlog-implementer/SKILL.md`

**Step 1: Add agentRoutingStats and reviewStats**

Update the State Schema section from v5.0 to v6.0.

**Step 2: Update Phase 6 Wave Summary**

Add routing stats and review stats to the wave summary output.

**Step 3: Add migration logic**

If state.version != "6.0": migrate by adding new stats fields.

**Step 4: Commit**

```bash
git add skills/backlog-implementer/SKILL.md
git commit -m "feat(implementer): update state schema to v6.0"
```

---

### Task 7: Update Tests

**Files:**
- Modify: `tests/test-config-schema.sh`

**Step 1: Add schema validation for agentRouting**

Test that the schema validates agentRouting rules correctly.

**Step 2: Add schema validation for reviewPipeline**

Test reviewPipeline with valid and invalid configs.

**Step 3: Run all tests**

Run: `bash tests/test-config-schema.sh && bash tests/test-templates.sh`
Expected: All tests pass.

**Step 4: Commit**

```bash
git add tests/
git commit -m "test: add schema validation for agentRouting and reviewPipeline"
```

---

### Task 8: Update README

**Files:**
- Modify: `README.md`

**Step 1: Update backlog-implementer description**

Mention v7.0 features: smart routing, skill catalog, configurable reviews.

**Step 2: Add Agent Routing section**

Document the agentRouting config with examples.

**Step 3: Add Review Pipeline section**

Document the reviewPipeline config.

**Step 4: Commit**

```bash
git add README.md
git commit -m "docs: update README for implementer v7.0 features"
```

---

### Task 9: Push to GitHub

**Step 1: Push all commits**

```bash
git push origin main
```
