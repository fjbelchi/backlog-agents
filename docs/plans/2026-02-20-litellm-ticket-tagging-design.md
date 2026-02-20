# Design: LiteLLM Ticket Tagging

**Date:** 2026-02-20
**Status:** Approved
**Scope:** Inject ticket/gate/project/agent tags into every LiteLLM prompt log

---

## Context

LiteLLM logs every prompt to PostgreSQL and shows them in the UI dashboard. Currently there is no way to filter logs by ticket — all requests look identical regardless of which ticket or gate produced them.

This design adds automatic tag injection: every LLM call made while a skill is active gets tagged with the active ticket, gate, project, and agent type. Tags appear in the LiteLLM UI and are filterable.

---

## Architecture

```
Skill starts working on ticket
        ↓
writes ~/.backlog-toolkit/current-context.json
  AND  .backlog-ops/current-context.json (local audit copy)
        ↓
LiteLLM TicketTagger CustomLogger
  reads ~/.backlog-toolkit/current-context.json
  on every log_pre_api_call
        ↓
injects metadata.tags into the request
        ↓
LiteLLM UI: filterable by ticket:FEAT-001, gate:implement,
            project:my-api, agent:backend
```

---

## Context File

**`~/.backlog-toolkit/current-context.json`** — read by LiteLLM container (global, stable path):

```json
{
  "ticket_id": "FEAT-001",
  "gate": "implement",
  "project": "my-api",
  "agent_type": "backend",
  "skill": "backlog-implementer",
  "updated_at": "2026-02-20T10:30:00"
}
```

File is absent when no skill is active. The callback handles missing file gracefully (no tags injected).

Also written to `.backlog-ops/current-context.json` as a per-project audit copy (gitignored).

---

## Component 1: LiteLLM CustomLogger

**`config/litellm/callbacks/ticket_tagger.py`:**

```python
import json, os
from pathlib import Path
from litellm.integrations.custom_logger import CustomLogger

CONTEXT_FILE = Path(
    os.environ.get("BACKLOG_CONTEXT_FILE",
                   str(Path.home() / ".backlog-toolkit" / "current-context.json"))
)

class TicketTagger(CustomLogger):
    def _read_context(self) -> dict:
        try:
            if CONTEXT_FILE.exists():
                return json.loads(CONTEXT_FILE.read_text())
        except Exception:
            pass
        return {}

    def log_pre_api_call(self, model, messages, kwargs):
        ctx = self._read_context()
        if not ctx:
            return
        tags = []
        for key, prefix in [
            ("ticket_id", "ticket"),
            ("gate",      "gate"),
            ("project",   "project"),
            ("agent_type","agent"),
            ("skill",     "skill"),
        ]:
            val = ctx.get(key)
            if val:
                tags.append(f"{prefix}:{val}")
        if tags:
            kwargs.setdefault("metadata", {})
            kwargs["metadata"]["tags"] = tags
```

---

## Component 2: proxy-config.docker.yaml update

Add to `litellm_settings`:
```yaml
litellm_settings:
  callbacks: ["ticket_tagger.TicketTagger"]
```

---

## Component 3: docker-compose.yml update

Add to `litellm` service:
```yaml
volumes:
  - ./config/litellm/callbacks:/app/callbacks:ro      # new
  - ~/.backlog-toolkit:/root/.backlog-toolkit:ro       # new
environment:
  PYTHONPATH: /app/callbacks                           # new
```

---

## Component 4: scripts/ops/context.sh

Sourceable shell helper used by all skills:

```bash
#!/usr/bin/env bash
# Source this file to get set_backlog_context / clear_backlog_context

_CONTEXT_GLOBAL="${HOME}/.backlog-toolkit/current-context.json"
_CONTEXT_LOCAL=".backlog-ops/current-context.json"

set_backlog_context() {
    # Args: ticket_id gate agent_type [skill]
    local ticket="$1" gate="$2" agent="$3"
    local skill="${4:-${CURRENT_SKILL:-unknown}}"
    local project
    project="$(python3 -c "import json; print(json.load(open('backlog.config.json'))['project']['name'])" 2>/dev/null || basename "$(pwd)")"
    local ts
    ts="$(date -u +%Y-%m-%dT%H:%M:%S)"
    local json
    json="$(python3 -c "import json; print(json.dumps({
        'ticket_id': '$ticket', 'gate': '$gate', 'project': '$project',
        'agent_type': '$agent', 'skill': '$skill', 'updated_at': '$ts'
    }))")"
    mkdir -p "$(dirname "$_CONTEXT_GLOBAL")"
    echo "$json" > "$_CONTEXT_GLOBAL"
    mkdir -p .backlog-ops
    echo "$json" > "$_CONTEXT_LOCAL"
}

clear_backlog_context() {
    rm -f "$_CONTEXT_GLOBAL"
    rm -f "$_CONTEXT_LOCAL"
}

get_backlog_context() {
    cat "$_CONTEXT_GLOBAL" 2>/dev/null || echo "{}"
}
```

---

## Component 5: Skills integration

Each skill sources `scripts/ops/context.sh` and calls `set_backlog_context` before spawning LLM agents.

### backlog-implementer

| Gate | Call |
|---|---|
| Gate 1 PLAN | `set_backlog_context "$ticket_id" "plan" "$agent_type" "backlog-implementer"` |
| Gate 2 IMPLEMENT | `set_backlog_context "$ticket_id" "implement" "$agent_type" "backlog-implementer"` |
| Gate 3 LINT | `set_backlog_context "$ticket_id" "lint" "linter" "backlog-implementer"` |
| Gate 4 REVIEW | `set_backlog_context "$ticket_id" "review" "reviewer" "backlog-implementer"` |
| Gate 5 COMMIT | `clear_backlog_context` |

### backlog-sentinel

| Phase | Call |
|---|---|
| Phase 0 prescan | `set_backlog_context "" "prescan" "sentinel" "backlog-sentinel"` |
| Phase 1 LLM review | `set_backlog_context "" "review" "security-reviewer" "backlog-sentinel"` |
| Phase 2 ticket creation | `set_backlog_context "$finding_id" "ticket-create" "ticket" "backlog-sentinel"` |
| Phase 3 done | `clear_backlog_context` |

### backlog-ticket

```bash
set_backlog_context "$ticket_id" "generate" "ticket" "backlog-ticket"
# ... generate ticket ...
clear_backlog_context
```

### backlog-refinement

```bash
set_backlog_context "" "refine" "refinement" "backlog-refinement"
# ... run refinement ...
clear_backlog_context
```

---

## Files to Create

```
config/litellm/callbacks/ticket_tagger.py   ← CustomLogger
scripts/ops/context.sh                      ← shell helper
```

## Files to Modify

```
config/litellm/proxy-config.docker.yaml     ← add callbacks
docker-compose.yml                          ← add volumes + PYTHONPATH
skills/backlog-implementer/SKILL.md         ← context calls per gate
skills/backlog-sentinel/SKILL.md            ← context calls per phase (when created)
skills/backlog-ticket/SKILL.md              ← context on generate
skills/backlog-refinement/SKILL.md          ← context on run
.gitignore                                  ← add .backlog-ops/current-context.json
```

---

## Result in LiteLLM UI

Each prompt log entry shows tags like:
```
ticket:FEAT-001  gate:implement  project:my-api  agent:backend  skill:backlog-implementer
```

Filterable from the LiteLLM dashboard. Cost analysis per ticket becomes trivial.
