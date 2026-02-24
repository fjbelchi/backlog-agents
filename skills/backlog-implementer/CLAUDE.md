# Backlog Implementer Skill v10.0

## Purpose

Orchestrates ticket implementation with adaptive pipeline, script delegation, quality gates, and smart agent routing. v10.0 eliminates Opus, scripts Gate 1, and routes trivial/simple tickets to Haiku for significant cost reduction.

## Architecture

### v10.0 Changes (from previous version)

- **Frontier model eliminated**: Selective high-risk gate removed, replaced by `diff_pattern_scanner.py` (regex) + Sonnet `high-risk-review.md`
- **Gate 1 scripted**: `plan_generator.py` replaces Ollama/Haiku LLM call ($0, deterministic)
- **Gate 3 integrated**: `lint_fixer.py` integrates lint into Gate 2, passes only error lines to Haiku (70% token reduction)
- **Fast path Haiku**: Trivial tickets use Haiku (was Sonnet); simple use Haiku+Sonnet-review
- **3 LLM gates**: Down from 5 (was: Plan+Impl+Lint+Review+Frontier → now: Impl+Lint(conditional)+Review)

### Adaptive Pipeline

Tickets classified by `classify.py` (deterministic heuristic, was Qwen3 LLM). Routes:

- **Fast Path** (trivial): Single Haiku agent, all 4 gates inline. $0.03-0.08/ticket.
- **Fast Path** (simple): Haiku impl + Sonnet Gate 4 review. $0.10-0.20/ticket.
- **Full Path** (complex): Team-based with Haiku implementers, Sonnet reviewers, optional Opus frontier. $1.50-3.00/ticket.

### Quality Gates

5 sequential gates: Plan → TDD → Lint → Review → Commit

### Script Layer

| Script | Replaces | Cost |
|--------|----------|------|
| `scripts/implementer/startup.sh` | Phase 0+0.5 (114 lines bash) | $0 |
| `scripts/implementer/classify.py` | Qwen3 complexity classifier | $0 |
| `scripts/implementer/wave_plan.py` | Qwen3/Haiku wave planning | $0 |
| `scripts/implementer/commit_msg.py` | Qwen3 commit message gen | $0 |
| `scripts/implementer/pre_review.py` | Qwen3 pre-review checklist | $0 |
| `scripts/implementer/micro_reflect.py` | Haiku micro-reflector tagging | $0 |
| `scripts/implementer/wave_end.py` | Phase 4+6 (150 lines) | $0 |
| `scripts/implementer/enrich_ticket.py` | Leader inline enrichment | $0 |
| `scripts/implementer/plan_generator.py` | Gate 1 plan generation | $0 |
| `scripts/implementer/lint_fixer.py` | Gate 3 lint error parsing | $0 |
| `scripts/implementer/diff_pattern_scanner.py` | High-risk pattern detection | $0 |

### Template Layer

| Template | Purpose | Loaded When |
|----------|---------|-------------|
| `templates/implementer-prefix.md` | Iron Laws, TDD, context rules | Every Gate 2 |
| `templates/reviewer-prefix.md` | Review protocol, scoring | Every Gate 4 |
| `templates/fast-path-agent.md` | Single Sonnet agent prompt | Fast path tickets |
| `templates/wave-summary-agent.md` | Fallback if wave_end.py fails | Error fallback |
| `templates/micro-reflector.md` | Fallback if micro_reflect.py fails | Error fallback |
| `templates/pre-review.md` | Fallback if pre_review.py fails | Error fallback |
| `templates/high-risk-review.md` | Sonnet 6-point high-risk checklist | When patterns detected |

### Model Routing

| Tier | Model | Usage |
|------|-------|-------|
| free | Ollama qwen3-coder | Wave plan, pre-review, commit msg (via llm_call.sh) |
| cheap | Haiku | Implementers, investigators, fast-path trivial |
| balanced | Sonnet | Fast-path simple review, Gate 4 reviewers, escalation |

### High-Risk Pattern Detection (replaces Opus frontier gate)

`diff_pattern_scanner.py` scans git diff with regex for: AUTH (jwt, bcrypt, session, token), DB_SCHEMA (createIndex, migration, ALTER TABLE), SERIALIZATION (JSON.parse, Buffer.from), ERROR_HANDLING (Promise.all, retry), EXTERNAL_API (fetch, axios), CONCURRENCY (worker_threads, mutex). If any detected → Gate 4 uses `high-risk-review.md` instead of `reviewer-prefix.md`. Cost: $0.

### Escalation Rules

- ARCH or SECURITY tag → sonnet (balanced)
- qualityGateFails ≥ 2 → sonnet (balanced)
- complex ticket + gateFails ≥ 1 → sonnet (balanced)
- Fast path: 2 fails → escalate to full path

## Key Files

- `SKILL.md` — Compressed leader prompt (288 lines)
- `catalog/` — 7 discipline catalogs (TDD, debug, arch, security, perf, frontend, review)
- `templates/` — 6 cache-optimized prompt templates
- `scripts/implementer/` — 9 deterministic scripts

## Cost Model

| Ticket Type | Pipeline | Before Cost | After Cost | Savings |
|-------------|----------|-----------|-----------|---------|
| trivial | fast path Haiku | $0.08-0.20 | $0.03-0.08 | ~60% |
| simple | fast path Haiku+Sonnet | $0.20-0.40 | $0.10-0.20 | ~50% |
| complex | full path no Opus | $1.20-2.50 | $0.70-1.50 | ~40% |

Token savings: ~12,000 → ~3,500 tokens per invocation (71% reduction in prompt size).

## State

Schema v6.3. Persists to `.claude/implementer-state.json`. Keys: version, stats (tickets, tests, commits, waves, cost, agentRouting, reviewStats, localModelStats, fastPathTickets, fullPathTickets, fastPathEscalations), investigationQueue, failedTickets, completedThisSession.

## Dependencies

- `backlog.config.json` — Project configuration
- LiteLLM proxy — Model routing (optional for fast-path)
- Docker (optional) — For Ollama/Postgres access
- Python 3 — For all script delegation

<claude-mem-context>
# Recent Activity

<!-- This section is auto-generated by claude-mem. Edit content outside the tags. -->

### Feb 19, 2026

| ID | Time | T | Title | Read |
|----|------|---|-------|------|
| #8306 | 8:39 PM | 🔵 | Model Tier Routing Strategy in Backlog Implementer | ~327 |
| #8269 | 7:51 PM | 🟣 | Implementer Skill Updated with Write-Agent Pattern | ~296 |
| #8268 | " | 🔄 | Implementer Skill Refactored for Delegated Wave Planning | ~312 |
| #8266 | " | 🟣 | Implementer Skill Updated with Write-Agent Pattern | ~326 |

### Feb 23, 2026

| ID | Time | T | Title | Read |
|----|------|---|-------|------|
| #8745 | 11:20 AM | 🟣 | Implementer v8.0 Model Routing Updated for Fast Path | ~295 |
</claude-mem-context>