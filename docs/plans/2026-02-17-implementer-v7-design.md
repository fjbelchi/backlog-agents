# Backlog Implementer v7.0 — Smart Agent Routing + Embedded Skill Catalog

## Goal

Upgrade backlog-implementer from v6.1 to v7.0 with intelligent agent selection per ticket, an embedded skill catalog with best practices per discipline, configurable multi-reviewer quality gates, and external plugin detection.

## Architecture

The implementer gains 4 new capabilities layered on top of the existing wave-based orchestration:

1. **Agent Router**: Config-driven rules map file patterns to agent types, with LLM override for ambiguous cases
2. **Embedded Skill Catalog**: Best practices for TDD, code review, debugging, security, architecture, frontend, and performance — extracted from superpowers, handbook, and Anthropic engineering blog
3. **Configurable Review Pipeline**: 2-4 parallel reviewers with confidence scoring (0-100) and false-positive filtering
4. **External Skill Detection**: Phase 0.5 detects installed plugins/skills and uses them when available

## 1. Agent Router

### Config Schema (`backlog.config.json`)

```json
{
  "agentRouting": {
    "rules": [
      { "pattern": "**/*.tsx,**/*.jsx,**/*.css,**/*.vue", "agent": "frontend", "label": "Frontend" },
      { "pattern": "**/*.ts,**/*.js", "agent": "backend", "label": "Backend TS" },
      { "pattern": "**/*.py", "agent": "backend", "label": "Backend Python" },
      { "pattern": "**/*.go", "agent": "backend", "label": "Backend Go" },
      { "pattern": "**/*.rs", "agent": "backend", "label": "Backend Rust" },
      { "pattern": "**/*.swift", "agent": "general-purpose", "label": "iOS/macOS" },
      { "pattern": "**/*.kt,**/*.java", "agent": "general-purpose", "label": "Android/JVM" },
      { "pattern": "**/Dockerfile,**/docker-compose*,**/*.yaml,**/*.tf", "agent": "devops", "label": "DevOps/Infra" },
      { "pattern": "**/*.ipynb,**/train*,**/model*", "agent": "ml-engineer", "label": "ML/AI" }
    ],
    "overrides": {
      "BUG": { "investigator": true },
      "SEC": { "reviewers": 4 }
    },
    "llmOverride": true
  }
}
```

### Routing Algorithm

1. Read `Affected Files` from ticket frontmatter
2. Match each file against `agentRouting.rules` (first match wins)
3. If multiple files match different agents, use majority rule
4. If `llmOverride: true` and ticket has clear signals (e.g., ML ticket with .py files), LLM can override
5. If no match, fall back to `general-purpose`
6. Apply `overrides` based on ticket prefix (BUG gets investigator, SEC gets 4 reviewers)

## 2. Embedded Skill Catalog

7 disciplines, each with extracted best practices:

| ID | Discipline | Source | Injected When |
|----|-----------|--------|---------------|
| CAT-TDD | Test-Driven Development | superpowers:test-driven-development, Anthropic best practices | Every implementer |
| CAT-REVIEW | Multi-Pass Code Review | code-review plugin (4 agents, confidence), superpowers:requesting-code-review | Every reviewer |
| CAT-DEBUG | Systematic Debugging | superpowers:systematic-debugging, handbook:root-cause-analyst | BUG tickets |
| CAT-SECURITY | Security Patterns | OWASP top 10, code review security lens | SEC tickets, all reviews |
| CAT-ARCH | Architecture Principles | handbook:backend-architect, handbook:system-architect | FEAT tickets |
| CAT-FRONTEND | Frontend Patterns | frontend-design plugin, handbook:frontend agent, a11y-first | Frontend-routed tickets |
| CAT-PERF | Performance & Efficiency | Anthropic multi-agent research, token efficiency | All (as guidelines) |

### Injection Logic

The leader selects disciplines based on:
- **Always**: CAT-TDD + CAT-PERF (for all implementers)
- **By ticket type**: BUG -> +CAT-DEBUG, FEAT -> +CAT-ARCH, SEC -> +CAT-SECURITY
- **By routing**: frontend agent -> +CAT-FRONTEND

## 3. Configurable Review Pipeline

### Config Schema

```json
{
  "reviewPipeline": {
    "reviewers": [
      { "name": "spec-compliance", "agent": "code-quality", "focus": "spec", "required": true },
      { "name": "code-quality", "agent": "code-quality", "focus": "quality", "required": true }
    ],
    "confidenceThreshold": 80,
    "maxReviewRounds": 3
  }
}
```

### Defaults

- 2 reviewers: spec-compliance + code-quality
- SEC tickets auto-add: security (investigator) + git-history (investigator)
- Confidence threshold: 80 (only report findings >= 80)
- Max 3 review rounds

### Review Flow

1. Spawn all configured reviewers in parallel as team members
2. Each reviewer analyzes changes from their focus perspective
3. Each finding scored 0-100 confidence
4. Filter: only findings >= confidenceThreshold reported
5. If any `required` reviewer has findings: implementer fixes -> re-review
6. Max rounds enforced, then `review-blocked`

## 4. External Skill Detection

### Phase 0.5: Detect Capabilities

After reading config (Phase 0), before wave selection (Phase 1):

1. Check for superpowers plugin in `~/.claude/plugins/`
2. Check for stack-specific plugins (pg-aiguide, AWS skills, etc.)
3. Check for configured MCP servers
4. Log available capabilities in banner

When an external skill is available for a discipline, prefer it over the embedded catalog version.

## 5. Team Composition (Updated)

```
LEADER (you) — coordinates, DOES NOT implement
├── implementer-1 ({routed_agent_type})
├── implementer-2 ({routed_agent_type})
├── implementer-3 (optional)
├── reviewer-1 (code-quality, focus: spec-compliance) [required]
├── reviewer-2 (code-quality, focus: quality) [required]
├── reviewer-3 (investigator, focus: security) [if configured/SEC]
├── reviewer-4 (investigator, focus: git-history) [if configured/SEC]
└── investigator (general-purpose) — unblocks complex tickets
```

## 6. Changes Summary

| Component | v6.1 | v7.0 |
|-----------|------|------|
| Agent selection | Manual (backend/frontend/general) | Smart Router (config + LLM override) |
| Implementer instructions | Code rules only | Code rules + Skill Catalog |
| Review gate | 1 reviewer | 2-4 configurable, confidence scoring |
| External plugins | None | Phase 0.5 detection + fallback |
| Stacks | Generic | Web, Python, Mobile, Infra |
| Iron Laws | 2 | 2 (unchanged) |
| State schema | v5.0 | v6.0 (adds routing stats) |

## 7. State Schema v6.0

Adds to v5.0:

```json
{
  "version": "6.0",
  "stats": {
    "...existing fields...",
    "agentRoutingStats": {
      "frontend": 0,
      "backend": 0,
      "devops": 0,
      "ml-engineer": 0,
      "general-purpose": 0,
      "llmOverrides": 0
    },
    "reviewStats": {
      "totalFindings": 0,
      "filteredByConfidence": 0,
      "avgConfidence": 0
    }
  }
}
```
