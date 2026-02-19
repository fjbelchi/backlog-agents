# Token Optimization Design

**Date:** 2026-02-19
**Status:** Draft
**Scope:** All 4 skills + infrastructure
**Estimated cost reduction:** 75-85%

## Context

Current cost breakdown from a representative session:

```
Haiku:   417k input,  16.9k output, 772k  cache read  → $0.75  (7%)
Sonnet:  918  input,  11.2k output, 1.9M  cache read  → $2.69  (27%)
Opus:    13.3k input, 36.4k output, 3.5M  cache read  → $6.65  (66%)
Total:                                                   $10.09
```

Key observations:
- **Opus generates 36k output tokens** — it is doing generation work, not just analysis
- **Opus cache reads are already 3.5M** — Claude Code CLI caching is working
- **Sonnet has 1.9M cache reads but only 918 fresh input** — near-perfect cache efficiency when used
- **Root cause:** Opus is used by default for full code generation across all tickets in an epic

Typical workflow: user runs `/backlog-toolkit:implement` on an entire epic (5-10 tickets at once). Currently each ticket goes through Opus synchronously.

---

## The 6 Levers

```
┌──────────────────────────────────────────────────────────┐
│  Palanca 0: Deterministic scripts                        │
│  init, indexing, lint, tests, validation → $0            │
├──────────────────────────────────────────────────────────┤
│  Palanca 4: Structural prompt caching                    │
│  Stable prefix → cache hits across entire epic           │
├──────────────────────────────────────────────────────────┤
│  Palanca 5: RAG context compression                      │
│  RAG query before LLM → -70% input tokens               │
├──────────────────────────────────────────────────────────┤
│  Palanca 1: Config-driven model tier routing             │
│  Sonnet default, Opus only for ARCH/SECURITY/escalation  │
├──────────────────────────────────────────────────────────┤
│  Palanca 3: Redis semantic cache                         │
│  Identical responses → free on 2nd invocation            │
├──────────────────────────────────────────────────────────┤
│  Palanca 2: Batch API as default (not interactive)       │
│  50% discount on all async work → default mode           │
└──────────────────────────────────────────────────────────┘
```

---

## Integration Architecture

```
/backlog-toolkit:implement EPIC-001 EPIC-002 EPIC-003
                      |
                      v
PHASE 1 - Deterministic pre-flight (scripts/ops/, no LLM)
  - Validate ticket format (regex)
  - Run real lint + tests (eslint, pytest, tsc, etc.)
  - Detect ARCH/SECURITY tags (grep on ticket content)
  - Determine: batch-eligible or --now?
                      |
                      v
PHASE 2 - RAG context compression (:8001)
  - Query RAG: "files relevant to [ticket description]"
  - Returns top-5 snippets (~800 tokens vs ~3k full files)
  - Build prompt structure:
      [stable context][cache_control breakpoint][RAG snippets][ticket]
                      |
          +-----------+-----------+
          |                       |
    --now flag               batch-eligible (DEFAULT)
    (urgent, explicit)       (epics, multiple tickets)
          |                       |
          v                       v
  LiteLLM :8000           batch_submit.py
  1. Redis cache?          -> Anthropic Batch API
     hit -> free           -> 50% cost reduction
  2. Model routing         -> async, up to 24h
     from backlog.config        |
     ARCH    -> frontier   batch_reconcile.py
     default -> balanced   -> poll for results
     lint    -> cheap      -> write code to disk
  3. Bedrock/Anthropic     -> update ticket state
     API call
          |
          v
PHASE 3 - Deterministic post-process
  - Write generated code to disk
  - Update cost ledger (.backlog-ops/usage-ledger.jsonl)
  - Move ticket: pending -> in-progress -> completed
  - Git commit if quality gates pass
```

**Integration glue — `backlog.config.json`:**
All scripts and skills read one file. No hardcoded models or paths anywhere.

**Hub — LiteLLM (:8000):**
Every synchronous LLM call passes through LiteLLM. Redis cache, model routing, budget controls, and spend logging are centralized there. Skills never call Anthropic directly.

---

## Lever Details

### Lever 0 — Deterministic Scripts (cost: $0)

Replace LLM calls with scripts wherever the output is deterministic.

**`backlog-init` — nearly all deterministic:**
```bash
# Stack detection -> grep, not LLM
[ -f package.json ]   && stack="typescript"
[ -f pyproject.toml ] && stack="python"
[ -f go.mod ]         && stack="go"
[ -f Cargo.toml ]     && stack="rust"

# Config generation -> template substitution, not LLM
cp config/presets/$stack.json backlog.config.json
sed -i "s/PROJECT_NAME/$(basename $PWD)/" backlog.config.json

# Directory structure -> mkdir, not LLM
mkdir -p backlog/data/{pending,in-progress,completed,archived}
```
LLM only needed for: customizing config when project has non-detectable particularities.

**RAG indexing — fully deterministic:**
- Chunking by file: text splitting, no LLM
- Metadata extraction: AST parsing (Python `ast` module)
- Embeddings: sentence-transformers (deterministic, same input = same vector)
- Cost: $0

**Quality gate execution:**
```bash
# Lint gate -> run the actual linter, not ask LLM to lint
npx eslint . --format json

# Type check -> run the actual compiler
npx tsc --noEmit

# Tests -> run the actual test runner
npx vitest run --reporter=json
```
Only the analysis of results goes to LLM, not the execution itself.

**Ticket validation (backlog-refinement):**
```python
# Check required sections -> regex, not LLM
required = ["context", "description", "acceptanceCriteria"]
missing = [s for s in required if s not in ticket_content]
# Only tickets passing deterministic checks proceed to LLM
```

**Rule of thumb:** if the correct answer is always the same given the same input, it is deterministic. LLM enters only when judgment, creativity, or ambiguity is required.

---

### Lever 1 — Config-Driven Model Tier Routing

New `costOptimization` section in `backlog.config.json`:

```json
{
  "costOptimization": {
    "defaultGenerationModel": "balanced",
    "escalationRules": [
      { "condition": "ticket.tags.includes('ARCH')",     "model": "frontier" },
      { "condition": "ticket.tags.includes('SECURITY')", "model": "frontier" },
      { "condition": "qualityGateFails >= 2",            "model": "frontier" },
      { "condition": "ticket.complexity == 'high'",      "model": "frontier" }
    ],
    "reviewModel":   "cheap",
    "planningModel": "balanced",
    "lintModel":     "cheap"
  }
}
```

Gate model mapping (current vs proposed):
```
Gate       Current    Proposed
---------  ---------  ----------
Plan       frontier   balanced
TDD        frontier   balanced
Code gen   frontier   balanced   <- biggest saving
Lint       balanced   cheap
Review     frontier   balanced   (frontier only on 2nd fail)
Commit     cheap      cheap
```

Expected result: Opus drops from 66% to ~10-15% of total cost. ARCH/SECURITY tickets keep Opus. Escalation on repeated gate failure preserves quality.

---

### Lever 2 — Anthropic Batch API (default mode)

Current `batch_submit.py` is a local queue stub. It needs to call the real Batch API.

**Execution modes:**
```bash
# DEFAULT — batch mode (50% off, async, for epics)
/backlog-toolkit:implement EPIC-001 EPIC-002 EPIC-003

# EXPLICIT — synchronous (normal price, when result needed immediately)
/backlog-toolkit:implement --now FEAT-001
```

**New `batchApi` config section:**
```json
{
  "batchApi": {
    "enabled": true,
    "maxWaitHours": 24,
    "minTicketsForBatch": 1
  }
}
```

**`batch_submit.py` changes:**
- Call `client.messages.batches.create()` with tickets as independent requests
- Write batch job IDs to `.backlog-ops/batch-queue/active.jsonl`
- Each request in the batch uses the same model routing rules from `costOptimization`

**`batch_reconcile.py` changes:**
- Poll `client.messages.batches.results()` for each active job ID
- Write generated code to disk when results arrive
- Move tickets from `pending` to `completed`
- Update cost ledger with actual spend

**New `scripts/ops/batch_status.py`:**
- Show all in-flight batch jobs with estimated completion
- Show pending results ready to reconcile

**Best for:** backlog refinement runs, epic implementations, nightly quality gate checks, bulk ticket generation from ideas.

---

### Lever 3 — Redis Semantic Cache

Add Redis to `docker-compose.yml`:
```yaml
redis:
  image: redis:7-alpine
  container_name: backlog-redis
  ports: ["6379:6379"]
  volumes: [redisdata:/data]
  command: redis-server --save 60 1 --loglevel warning
  restart: unless-stopped
```

Add to volumes:
```yaml
volumes:
  pgdata:
  chromadata:
  memgraphdata:
  redisdata:       # new
```

Enable in `config/litellm/proxy-config.docker.yaml`:
```yaml
litellm_settings:
  cache: true
  cache_params:
    type: redis
    host: redis        # compose service name
    port: 6379
    ttl: 3600          # 1 hour for generation
    namespace: backlog
```

**Impact:** If the same ticket is analyzed twice in the same session (review + re-review after a fix), the second call is free. For iterative refinement workflows, savings accumulate quickly.

---

### Lever 4 — Structural Prompt Caching

Anthropic caches prompts when the stable prefix reaches 1024+ tokens (2048+ recommended). The key is separating stable from dynamic content:

```
+---------------------------------------+  <- STABLE (cached after 1st call)
|  System context                       |    - Project rules
|  backlog.config.json summary          |    - Templates
|  Codebase conventions                 |    - Quality gate definitions
|  Skill-specific instructions          |
+---------------------------------------+  <- cache_control breakpoint
|  Ticket-specific content              |  <- DYNAMIC (never cached)
|  RAG snippets for this ticket         |    - Changes every request
|  Current file state                   |
+---------------------------------------+
```

For an epic of 10 tickets:
- Ticket 1: pays for the stable prefix (~2k tokens)
- Tickets 2-10: read the stable prefix from cache (~$0 for that part)
- Only pay for the dynamic part of each ticket

**`prompt_prefix_lint.py` role:** Already exists. Run it on all 4 skills to detect dynamic content placed before the breakpoint. Fix flagged skills to move dynamic content after the breakpoint. This should be part of CI validation.

**Rule:** Anything that changes per-ticket goes after the breakpoint. Anything that is the same across an entire project session goes before it.

---

### Lever 5 — RAG Context Compression

The RAG server runs at `:8001` but no skill queries it before calling the LLM. Current pattern:

```
Skill -> "here are all potentially relevant files" -> LLM (large input)
```

Optimized pattern:

```
Skill -> RAG query: "files relevant to [ticket description]"
      -> top-5 snippets (~800 tokens)
      -> LLM (minimal, focused input)
```

**Helper available to all skills:**
```python
import requests

def get_context_for_ticket(ticket_description: str, n_results: int = 5) -> list:
    """Query RAG server for relevant code context before LLM call."""
    response = requests.post("http://localhost:8001/search", json={
        "query": ticket_description,
        "n_results": n_results
    })
    return response.json()["results"]["documents"][0]
```

**Expected reduction:** ~70-80% fewer input tokens on any call that currently includes code context. Instead of 3 full files (3,000 tokens), 5 surgical snippets (~800 tokens).

**Prerequisite:** RAG index must be current. `scripts/ops/rag_index.py` should run on project open or after significant code changes. Can be triggered deterministically from `claude-with-services.sh`.

---

## Changes Required Per Skill

### `backlog-init`
- Replace LLM-based stack detection with bash/grep scripts
- Replace LLM-based config generation with template substitution
- Add `costOptimization` and `batchApi` to generated `backlog.config.json` by default
- Keep LLM only for project-specific customization that cannot be detected

### `backlog-ticket`
- Tag tickets `ARCH` or `SECURITY` explicitly based on description keywords
- Set `batchEligible: true/false` on each ticket
- Group ticket suggestions by shared codebase context (for cache efficiency)
- Use `cheap` model for ticket format validation, `balanced` for content generation

### `backlog-refinement`
- Run format/section checks deterministically (no LLM)
- Group tickets by shared context before sending to LLM (maximize prompt cache hits)
- Order tickets so those sharing context are processed consecutively
- Use `cheap` for classification, `balanced` for detailed analysis
- Default to batch mode for full backlog scans

### `backlog-implementer`
- Read `costOptimization` from `backlog.config.json` for every gate
- Evaluate escalation rules before each LLM call (ARCH tag, gate fail count)
- Query RAG before loading files manually into context
- Default to batch mode; accept `--now` flag for synchronous execution
- Log model used and tokens spent per gate to cost ledger

---

## Implementation Order

Ordered by impact/effort ratio:

1. **`backlog.config.json` schema** — add `costOptimization` and `batchApi` sections
2. **`backlog-implementer` routing** — read config, apply escalation rules
3. **Redis in docker-compose** — enable LiteLLM cache
4. **`batch_submit.py` real implementation** — call Anthropic Batch API
5. **`batch_reconcile.py` real implementation** — poll and write results
6. **`backlog-init` deterministic scripts** — replace LLM calls
7. **RAG integration helper** — add to all skills
8. **Prompt structure audit** — run `prompt_prefix_lint.py`, fix all skills
9. **`backlog-refinement` batching** — group by context, default batch mode
10. **`batch_status.py`** — new script for monitoring in-flight jobs

---

## Expected Cost Impact

```
Current:  $10.09 / session
          Opus 66%, Sonnet 27%, Haiku 7%

After Lever 0+1 (routing + deterministic):
          Opus ~12%, Sonnet 65%, Haiku 23%
          Estimated: ~$3.50 / session  (-65%)

After all levers:
          Batch default (50% off most work)
          Redis cache hits for repeated queries
          RAG compression on input tokens
          Estimated: ~$1.50-2.00 / session  (-80%)
```

Reduction is multiplicative, not additive. The levers compound.
