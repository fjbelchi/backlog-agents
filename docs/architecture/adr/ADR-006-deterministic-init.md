# ADR-006: Deterministic Init — Script vs Skill

## Status
Proposed

## Context

The `backlog-init` skill currently runs as an LLM-powered skill that detects the project stack, asks user preferences, and scaffolds the backlog directory. The question is: **does init need an LLM at all?**

## Analysis: Init Step-by-Step

| Step | What it does | Deterministic? | LLM value-add |
|------|-------------|----------------|---------------|
| 1. Detect stack | Glob for `package.json`, `pyproject.toml`, `go.mod`, etc. | **Yes** — file existence checks | None |
| 2. User preferences | Ask project name, stack, prefixes, code-rules | **Yes with CLI flags** | None (just a prompt) |
| 3. Create directories | `mkdir -p backlog/data/{pending,completed}` | **Yes** | None |
| 4. Generate config | Table lookup: stack → quality gate commands | **Yes** — static mapping | None |
| 5. Create CLAUDE.md | Template with `<PROJECT_NAME>` substitution | **Yes** | None |
| 6. Write templates | Copy 4 static markdown files | **Yes** | None |
| 7. Create code-rules | Static template with project name | **Yes** | None |
| 8. Print summary | List created files | **Yes** | None |

**Verdict: 8/8 steps are deterministic. The LLM adds zero value.**

## Token Cost of Current Init

Running `backlog-init` as a skill:

| Component | Tokens | Cost (Sonnet) |
|-----------|--------|---------------|
| SKILL.md (system prompt) | ~4,000 | $0.012 |
| Template content (4 templates) | ~3,500 | $0.010 |
| Config generation | ~800 | $0.002 |
| LLM reasoning + output | ~2,000 | $0.030 |
| **Total** | **~10,300** | **$0.054** |

Running `backlog-init` as a script: **$0.00**

Over 100 project initializations, the skill costs ~$5.40 for zero benefit vs the script.

## Decision

**Extract `backlog-init` into a deterministic script** (`scripts/init/backlog_init.py`).

Retain the skill as an optional wrapper that:
1. Calls the script with auto-detected defaults
2. Only invokes the LLM if the user asks for non-standard customization (e.g., "initialize with a monorepo structure for 3 services")

### Script Interface

```bash
# Auto-detect everything (zero tokens)
python scripts/init/backlog_init.py

# Explicit flags (zero tokens)  
python scripts/init/backlog_init.py \
  --name my-project \
  --stack typescript \
  --prefixes TASK,BUG,FEAT,IDEA \
  --code-rules \
  --llmops          # Include v1.1 llmOps block in config

# Non-interactive (CI/CD friendly)
python scripts/init/backlog_init.py --yes
```

### What Remains in the Skill

The skill becomes a thin orchestrator:

```
User: /backlog-toolkit:init
  → Script detects stack, generates all files
  → Skill only activates if:
     a) User gives a complex natural-language request
     b) Auto-detection is ambiguous (multiple manifests)
     c) User explicitly asks for customization
```

## Consequences

### Positive
- **100% token savings** for init (most common case)
- **Faster execution**: no LLM round-trip latency
- **CI/CD compatible**: script runs in pipelines without API keys
- **Reproducible**: same input → same output, always
- **Testable**: unit tests for stack detection and template generation
- **Offline capable**: works without network access

### Negative
- Lose the "magic" of conversational init (user says "set up backlog for my TypeScript monorepo" and gets a custom result)
- Must maintain two code paths (script + skill wrapper)
- Script needs its own flag parsing and validation

### Mitigation
- Keep the skill for edge cases where LLM reasoning adds value
- Script covers 95%+ of init invocations
- Add `--help` with comprehensive examples

## Applicability to Other Skills

This analysis applies to init because it's pure scaffolding. Other skills do NOT qualify:

| Skill | Deterministic? | Why / Why not |
|-------|---------------|---------------|
| `backlog-init` | **Yes** | Pure scaffolding: detect → lookup → copy |
| `backlog-ticket` | **No** | Requires LLM to analyze codebase and generate descriptions |
| `backlog-refinement` | **Partial** | Scripts handle 80% (dedup, validation), LLM for quality review |
| `backlog-implementer` | **No** | Core LLM task: code generation, review, architecture |

## Implementation

See `scripts/init/backlog_init.py` for the complete deterministic implementation.

## Related

- [ADR-002: Script-First, LLM-Second](ADR-002-script-first-llm-second.md) — This ADR is a direct application of that principle
- [Token Optimization Playbook](../../tutorials/token-optimization-playbook.md) — Layer 1: Script-First
- [backlog-init SKILL.md](../../../skills/backlog-init/SKILL.md) — Current LLM-based implementation
