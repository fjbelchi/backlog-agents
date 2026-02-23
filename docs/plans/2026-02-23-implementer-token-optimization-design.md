# Implementer v9.0 — Token Optimization Design

## Problem

SKILL.md is 1055 lines / 47KB / ~12,000 tokens. Every invocation loads the full prompt into context. Seven LLM calls per wave could be deterministic scripts.

**Goals:**
- Reduce SKILL.md to ~350 lines / ~3,500 tokens (~70% reduction)
- Replace 7 LLM calls with deterministic Python/bash scripts (0 tokens, 0 cost)
- Maintain all current behavior — same quality gates, same pipeline routing

## Architecture

### Two-Layer Optimization

**Layer 1 — Script Delegation:** Replace LLM calls with deterministic scripts.
**Layer 2 — Prompt Compression:** Extract templates, remove duplicates, aggressive rewrite.

### Script Layer (9 new scripts)

```
scripts/implementer/
├── startup.sh           # Phase 0 + 0.5 merged: config, Ollama, classify, playbook
├── classify.py          # ticket → trivial|simple|complex (heuristic)
├── wave_plan.py         # tickets → wave JSON (graph-based conflict detection)
├── commit_msg.py        # ticket metadata → conventional commit string
├── pre_review.py        # diff + test + lint → checklist JSON
├── micro_reflect.py     # wave results + bullets → tags JSON (rule-based)
├── enrich_ticket.py     # git log + metrics → enriched ticket md
├── wave_end.py          # Phase 4+6 merged: enrich, cost, move, summary, reflect
├── impact_graph.py      # (already exists)
└── migrate-state.py     # (already exists)
```

### Template Layer (4 new templates)

```
templates/
├── implementer-prefix.md    # (exists — 88 lines)
├── reviewer-prefix.md       # (exists — 81 lines)
├── fast-path-agent.md       # NEW: extracted fast-path prompt
├── wave-summary-agent.md    # NEW: fallback if wave_end.py fails
├── micro-reflector.md       # NEW: fallback if micro_reflect.py fails
└── pre-review.md            # NEW: fallback if pre_review.py fails
```

## Script Specifications

### startup.sh (Phase 0 + 0.5)

Replaces 114 lines of Phase 0/0.5 with single invocation.

**Input:** None (reads backlog.config.json, env vars)
**Output:** JSON to stdout:
```json
{
  "config": {"dataDir": "backlog/data", "testCommand": "npm test", ...},
  "tickets": [{"id": "BUG-001", "complexity": "simple", "files": 2, "tags": []}],
  "ollama_available": true,
  "plugin_root": "/path/to/backlog-agents",
  "playbook_stats": {"total": 15, "high_performing": 8, "problematic": 2},
  "cache_health": {"avg_hit_rate": 0.92, "warning": false},
  "litellm_url": "http://localhost:8000"
}
```

**Steps:**
1. Resolve CLAUDE_PLUGIN_ROOT (search common paths)
2. Read backlog.config.json
3. Set LITELLM_BASE_URL + LITELLM_MASTER_KEY defaults
4. Test Ollama via llm_call.sh --model free --user "Reply OK"
5. For each ticket in pending/: run classify.py, store result
6. Load playbook stats via playbook_utils.py
7. Cache health: read last 10 entries from usage-ledger.jsonl
8. Load state from implementer-state.json (run migrate if needed)
9. Output JSON

### classify.py

Promotes existing heuristic fallback to primary classifier.

**Input:** Ticket .md path
**Output:** `trivial`, `simple`, or `complex` (stdout)

**Rules:**
- `files <= 1 AND no ARCH/SEC tags AND no depends_on` → trivial
- `files <= 3 AND no ARCH/SEC tags AND no depends_on` → simple
- Else → complex
- Override: if ticket has explicit `complexity:` frontmatter, use that

### wave_plan.py

Graph-based conflict detection replaces LLM wave planning.

**Input:** `--tickets-dir pending/ --max-slots 3`
**Output:** Wave JSON (same format as current LLM output)

**Algorithm:**
1. Build file-overlap graph: edge between tickets sharing affected files
2. Topological sort on `depends_on` relationships
3. Greedy bin-packing: assign tickets to slots, skip if file conflict
4. Sort by priority within slots
5. Include `subagent_type` from file-extension routing rules

### commit_msg.py

Template-based conventional commit generation.

**Input:** `--type feat --area auth --ticket FEAT-042 --summary "Add OAuth2 flow"`
**Output:** Conventional commit message string

**Template:** `{type}({area}): implement {ticket_id} — {summary}`

### pre_review.py

Grep/diff-based pre-review checklist.

**Input:** `--diff-file diff.txt --test-output test.log --lint-output lint.log`
**Output:** Checklist JSON:
```json
{
  "imports_ok": true,
  "lint_clean": true,
  "tests_pass": true,
  "no_debug": false,
  "format_ok": true,
  "issues": ["TODO found at src/foo.ts:42"]
}
```

**Checks:**
1. Unused imports: added imports not used in diff
2. Debug artifacts: console.log, print(), TODO, FIXME, HACK, debugger
3. Lint clean: parse lint output for 0 warnings
4. Tests pass: parse test output for 0 failures
5. Format: tab/space consistency in diff

### micro_reflect.py

Rule-based playbook bullet tagging.

**Input:** `--wave-results wave.json --bullets-used bullets.json --playbook .claude/playbook.md`
**Output:** Tags JSON (same format as current Haiku reflector)

**Rules:**
- Ticket completed, gates passed first try → all injected bullets → `helpful`
- Ticket failed a gate → bullets matching that gate's section → `harmful`
- Ticket completed after retry → `neutral`
- New bullet generation: deferred to `/backlog-toolkit:reflect` deep mode

### enrich_ticket.py

Git + filesystem metrics collection.

**Input:** `--ticket ticket.md --commit-hash abc123 --review-rounds 1 --tests-added 3`
**Output:** Writes enrichment sections to ticket .md (status, dates, metrics, cost)

**Steps:**
1. `git log -1 --format=%H,%an,%ai` for commit info
2. `git diff --stat HEAD~1` for files changed
3. Update frontmatter: status, completed date, implemented_by, review_rounds, tests_added
4. Add ## Actual Cost section with model breakdown

### wave_end.py (Phase 4 + 6 merged)

Orchestrates all post-wave operations.

**Input:** JSON stdin with wave data:
```json
{
  "wave": 1,
  "tickets": [{"id": "BUG-001", "status": "completed", "commit": "abc123", ...}],
  "models_used": {"free": 3, "haiku": 8, "sonnet": 4},
  "cost": 0.25,
  "session_total_cost": 1.50,
  "waves_this_session": 2,
  "max_waves": 5,
  "bullets_used": [{"id": "strat-00001"}]
}
```

**Output:** JSON:
```json
{
  "enriched_count": 3,
  "wave_log_written": true,
  "micro_reflect": {"tags": 2, "new_bullets": 0},
  "session_limit_reached": false,
  "pending_remaining": 5
}
```

**Steps:**
1. For each completed ticket: call `enrich_ticket.py`
2. Call `cost_history.py add` for each ticket
3. Move tickets: `mv pending/ → completed/`
4. Write wave summary to wave-log.md
5. Run micro_reflect.py
6. Apply playbook updates via playbook_utils.py
7. Check session limit
8. Output results JSON

## SKILL.md Compressed Structure (~350 lines)

```
--- frontmatter (3 lines) ---

# Implementer v9.0 (1 line)
## Role (1 line)

## RULES
MODEL RULES (table, 8 lines)
OUTPUT DISCIPLINE (3 lines)
CHUNKING (3 lines)
CACHE STRATEGY (3 lines)

## CONFIG (table, 8 lines)

## ROUTING (single merged table, 10 lines)
  All model routing: gate defaults + escalation + batch + local + RAG

## TEAM (table, 6 lines)

## MAIN LOOP (18 lines — unchanged logic, tighter formatting)

## STARTUP
  STARTUP_JSON=$(bash startup.sh) (8 lines total with error handling)

## WAVE SELECT
  WAVE_JSON=$(python3 wave_plan.py ...) (6 lines with fallback)

## CREATE TEAM (8 lines)

## GATES
  Gate 1 PLAN (6 lines: context track + RAG + plan)
  Catalog injection (2 lines: reference to catalog/)
  Gate 2 IMPL (10 lines: TDD protocol + prompt construction ref)
  Gate 3 LINT (4 lines: run commands, 3 retries)
  Gate 4 REVIEW (12 lines: pre_review.py → reviewer spawn → consolidate)
  Gate 4b FRONTIER (8 lines: trigger list + spawn + outcome)
  Gate 5 COMMIT (4 lines: commit_msg.py → git commit)

## FAST PATH (12 lines: Read templates/fast-path-agent.md + escalation)

## WAVE END
  RESULT=$(python3 wave_end.py <<< "$WAVE_JSON") (6 lines)
  Print banner (6 lines)

## CLEANUP (2 lines: shutdown + TeamDelete)

## SESSION CHECK (3 lines: limit → save → exit)

## IRON LAWS → See templates/implementer-prefix.md (1 line)
## STATE → See migrate-state.py, schema v6.2 (1 line)
## CONSTRAINTS (4 lines: compressed DO/DON'T)
## START (4 lines)
```

**Total: ~350 lines / ~3,500 tokens**

## LLM Call Elimination Summary

| Call | Before (v8.0) | After (v9.0) | Savings |
|------|---------------|-------------|---------|
| Complexity classify | Qwen3 (1 call/ticket) | classify.py ($0) | 100% |
| Wave planning | Qwen3 (1 call/wave) | wave_plan.py ($0) | 100% |
| Gate 1 PLAN text | Qwen3 (1 call/ticket) | Still LLM (needs NLP) | 0% |
| Gate 5 commit msg | Qwen3 (1 call/ticket) | commit_msg.py ($0) | 100% |
| Pre-review checklist | Qwen3 (1 call/ticket) | pre_review.py ($0) | 100% |
| Wave summary write | Haiku (1 call/wave) | wave_end.py ($0) | 100% |
| Micro-reflector | Haiku (1 call/wave) | micro_reflect.py ($0) | 100% |
| Ticket enrichment | Leader inline | enrich_ticket.py ($0) | 100% (context) |

**Calls eliminated per wave (3 tickets):** ~9 calls → 0 deterministic
**Remaining LLM calls:** Gate 1 PLAN, Gate 2 IMPL, Gate 3 LINT analysis, Gate 4 REVIEW, Gate 4b optional — these genuinely need language understanding.

## Token Savings Summary

| Component | Before (tokens) | After (tokens) | Reduction |
|-----------|-----------------|----------------|-----------|
| SKILL.md static prompt | ~12,000 | ~3,500 | 71% |
| Inline prompts → templates | (in above) | loaded on-demand | — |
| LLM calls eliminated (per wave) | ~5,000 | 0 | 100% |
| **Total per invocation** | **~17,000** | **~3,500** | **79%** |

## Migration

- Bump version: v8.0 → v9.0
- CLAUDE.md: rewrite as human-readable reference (all "why" commentary moves here)
- State schema: v6.2 → v6.3 (add `scriptDelegation: true` flag)
- Backward compat: if scripts missing, fall back to LLM calls (current behavior)

## Verification

1. Run all existing tests: `python3 -m pytest tests/ -v`
2. Each new script: TDD with min 5 tests
3. Benchmark: run implementer on test ticket, compare cost vs v8.0
4. SKILL.md: `wc -l` ≤ 400, token count ≤ 4,000
