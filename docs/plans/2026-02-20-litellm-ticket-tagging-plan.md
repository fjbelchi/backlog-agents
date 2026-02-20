# LiteLLM Ticket Tagging — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Inject ticket/gate/project/agent tags into every LiteLLM prompt log so requests are filterable by ticket in the UI.

**Architecture:** Skills write `~/.backlog-toolkit/current-context.json` before each LLM gate. A LiteLLM CustomLogger reads that file on every `log_pre_api_call` and injects `metadata.tags`. Docker mounts the callbacks dir and home toolkit dir.

**Tech Stack:** Python 3.11, LiteLLM CustomLogger API, bash, docker-compose

---

### Task 1: Create ticket_tagger.py CustomLogger

**Files:**
- Create: `config/litellm/callbacks/ticket_tagger.py`
- Create: `config/litellm/callbacks/__init__.py` (empty)
- Create: `tests/test_ticket_tagger.py`

**Step 1: Write failing test**

```python
# tests/test_ticket_tagger.py
import json, os, sys, pytest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, "config/litellm/callbacks")

def test_tags_injected_when_context_file_exists(tmp_path):
    ctx = {"ticket_id": "FEAT-001", "gate": "implement",
           "project": "my-api", "agent_type": "backend", "skill": "backlog-implementer"}
    ctx_file = tmp_path / "current-context.json"
    ctx_file.write_text(json.dumps(ctx))
    with patch.dict(os.environ, {"BACKLOG_CONTEXT_FILE": str(ctx_file)}):
        import importlib, ticket_tagger
        importlib.reload(ticket_tagger)
        tagger = ticket_tagger.TicketTagger()
        kwargs = {}
        tagger.log_pre_api_call("claude", [], kwargs)
    assert "metadata" in kwargs
    assert "ticket:FEAT-001" in kwargs["metadata"]["tags"]
    assert "gate:implement" in kwargs["metadata"]["tags"]
    assert "project:my-api" in kwargs["metadata"]["tags"]
    assert "agent:backend" in kwargs["metadata"]["tags"]

def test_no_tags_when_file_missing(tmp_path):
    with patch.dict(os.environ, {"BACKLOG_CONTEXT_FILE": str(tmp_path / "missing.json")}):
        import importlib, ticket_tagger
        importlib.reload(ticket_tagger)
        tagger = ticket_tagger.TicketTagger()
        kwargs = {}
        tagger.log_pre_api_call("claude", [], kwargs)
    assert "metadata" not in kwargs

def test_no_tags_when_file_empty(tmp_path):
    ctx_file = tmp_path / "current-context.json"
    ctx_file.write_text("{}")
    with patch.dict(os.environ, {"BACKLOG_CONTEXT_FILE": str(ctx_file)}):
        import importlib, ticket_tagger
        importlib.reload(ticket_tagger)
        tagger = ticket_tagger.TicketTagger()
        kwargs = {}
        tagger.log_pre_api_call("claude", [], kwargs)
    assert kwargs.get("metadata", {}).get("tags", []) == []
```

**Step 2: Verify they fail**

```bash
cd /Users/fbelchi/github/backlog-agents
python3 -m pytest tests/test_ticket_tagger.py -v
# Expected: ModuleNotFoundError: No module named 'ticket_tagger'
```

**Step 3: Implement ticket_tagger.py**

```python
# config/litellm/callbacks/ticket_tagger.py
import json
import os
from pathlib import Path

try:
    from litellm.integrations.custom_logger import CustomLogger
except ImportError:
    # Fallback for testing without LiteLLM installed
    class CustomLogger:
        pass

CONTEXT_FILE = Path(
    os.environ.get(
        "BACKLOG_CONTEXT_FILE",
        str(Path.home() / ".backlog-toolkit" / "current-context.json")
    )
)

class TicketTagger(CustomLogger):
    def _read_context(self) -> dict:
        try:
            path = Path(os.environ.get("BACKLOG_CONTEXT_FILE", str(CONTEXT_FILE)))
            if path.exists():
                return json.loads(path.read_text())
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

**Step 4: Run tests**

```bash
python3 -m pytest tests/test_ticket_tagger.py -v
# Expected: 3 passed
```

**Step 5: Commit**

```bash
touch config/litellm/callbacks/__init__.py
git add config/litellm/callbacks/ tests/test_ticket_tagger.py
git commit -m "feat(litellm): add TicketTagger CustomLogger for prompt tagging"
```

---

### Task 2: Create context.sh shell helper

**Files:**
- Create: `scripts/ops/context.sh`
- Create: `tests/test_context_sh.sh`

**Step 1: Create context.sh**

```bash
#!/usr/bin/env bash
# scripts/ops/context.sh — Sourceable helper to set/clear backlog context
# Usage: source scripts/ops/context.sh

_CTX_GLOBAL="${HOME}/.backlog-toolkit/current-context.json"
_CTX_LOCAL=".backlog-ops/current-context.json"

set_backlog_context() {
    # Args: ticket_id gate agent_type [skill]
    local ticket="${1:-}" gate="${2:-}" agent="${3:-}"
    local skill="${4:-${CURRENT_SKILL:-unknown}}"
    local project
    project="$(python3 -c "
import json, sys
try:
    print(json.load(open('backlog.config.json'))['project']['name'])
except Exception:
    import os; print(os.path.basename(os.getcwd()))
" 2>/dev/null)"
    local ts
    ts="$(date -u +%Y-%m-%dT%H:%M:%S)"
    local json
    json="$(python3 -c "
import json, sys
print(json.dumps({
    'ticket_id': sys.argv[1], 'gate': sys.argv[2],
    'project': sys.argv[3], 'agent_type': sys.argv[4],
    'skill': sys.argv[5], 'updated_at': sys.argv[6]
}))" "$ticket" "$gate" "$project" "$agent" "$skill" "$ts")"
    mkdir -p "$(dirname "$_CTX_GLOBAL")"
    echo "$json" > "$_CTX_GLOBAL"
    mkdir -p .backlog-ops
    echo "$json" > "$_CTX_LOCAL"
}

clear_backlog_context() {
    rm -f "$_CTX_GLOBAL"
    rm -f "$_CTX_LOCAL"
}

get_backlog_context() {
    cat "$_CTX_GLOBAL" 2>/dev/null || echo "{}"
}
```

**Step 2: Write bash test**

```bash
#!/usr/bin/env bash
# tests/test_context_sh.sh
set -euo pipefail
PASS=0; FAIL=0

pass() { echo "  PASS: $1"; ((PASS++)); }
fail() { echo "  FAIL: $1"; ((FAIL++)); }

TMPDIR_TEST="$(mktemp -d)"
ORIG_HOME="$HOME"
export HOME="$TMPDIR_TEST"

# Temporarily cd into a dir with backlog.config.json
mkdir -p "$TMPDIR_TEST/proj"
echo '{"project":{"name":"test-proj"}}' > "$TMPDIR_TEST/proj/backlog.config.json"
cd "$TMPDIR_TEST/proj"

source "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/scripts/ops/context.sh"

# Test 1: set_backlog_context writes global file
set_backlog_context "FEAT-001" "plan" "backend" "backlog-implementer"
if [ -f "$HOME/.backlog-toolkit/current-context.json" ]; then
    pass "global context file created"
else
    fail "global context file missing"
fi

# Test 2: ticket_id present in file
if grep -q "FEAT-001" "$HOME/.backlog-toolkit/current-context.json"; then
    pass "ticket_id in context"
else
    fail "ticket_id missing from context"
fi

# Test 3: local file written
if [ -f ".backlog-ops/current-context.json" ]; then
    pass "local context file created"
else
    fail "local context file missing"
fi

# Test 4: clear removes files
clear_backlog_context
if [ ! -f "$HOME/.backlog-toolkit/current-context.json" ]; then
    pass "global context cleared"
else
    fail "global context not cleared"
fi

# Cleanup
cd /
rm -rf "$TMPDIR_TEST"
export HOME="$ORIG_HOME"

echo "=== $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ]
```

**Step 3: Run tests**

```bash
chmod +x tests/test_context_sh.sh
bash tests/test_context_sh.sh
# Expected: 4 passed, 0 failed
```

**Step 4: Commit**

```bash
chmod +x scripts/ops/context.sh
git add scripts/ops/context.sh tests/test_context_sh.sh
git commit -m "feat(ops): add context.sh shell helper for backlog context tracking"
```

---

### Task 3: Update proxy-config and docker-compose

**Files:**
- Modify: `config/litellm/proxy-config.docker.yaml`
- Modify: `docker-compose.yml`

**Step 1: Read current files**

Read `config/litellm/proxy-config.docker.yaml` to find the `litellm_settings` section.
Read `docker-compose.yml` to find the `litellm` service volumes and environment.

**Step 2: Update proxy-config.docker.yaml**

Find `litellm_settings:` block and add the callbacks line:

```yaml
litellm_settings:
  callbacks: ["ticket_tagger.TicketTagger"]
  # ... existing settings remain unchanged
```

**Step 3: Update docker-compose.yml litellm service**

Add to `litellm.volumes`:
```yaml
- ./config/litellm/callbacks:/app/callbacks:ro
- ${HOME}/.backlog-toolkit:/root/.backlog-toolkit:ro
```

Add to `litellm.environment`:
```yaml
PYTHONPATH: /app/callbacks
```

**Step 4: Verify syntax**

```bash
python3 -c "import yaml; yaml.safe_load(open('config/litellm/proxy-config.docker.yaml'))" && echo "YAML OK"
python3 -c "import yaml; yaml.safe_load(open('docker-compose.yml'))" && echo "docker-compose OK"
```

**Step 5: Commit**

```bash
git add config/litellm/proxy-config.docker.yaml docker-compose.yml
git commit -m "feat(litellm): mount ticket tagger callback + home toolkit dir in Docker"
```

---

### Task 4: Integrate context calls into skills

**Files:**
- Modify: `skills/backlog-implementer/SKILL.md`
- Modify: `skills/backlog-ticket/SKILL.md`
- Modify: `skills/backlog-refinement/SKILL.md`
- Modify: `.gitignore`

**Step 1: Update backlog-implementer/SKILL.md**

Find Gate 1 PLAN section. Add at the start of the Gate 1 description:

```markdown
**Context tracking**: Before spawning the planning agent, set the backlog context:
```bash
source scripts/ops/context.sh
set_backlog_context "$ticket_id" "plan" "$routed_agent_type" "backlog-implementer"
```
Update gate name as work progresses: `"plan"` → `"implement"` → `"lint"` → `"review"`.
Call `clear_backlog_context` after Gate 5 COMMIT completes.
```

**Step 2: Update backlog-ticket/SKILL.md**

Find Phase 1 Analysis. Add before phase begins:

```markdown
**Context tracking**: At start of ticket generation:
```bash
source scripts/ops/context.sh
set_backlog_context "" "generate" "ticket" "backlog-ticket"
```
Call `clear_backlog_context` after the ticket file is saved.
```

**Step 3: Update backlog-refinement/SKILL.md**

Find Phase 1 Inventory. Add:

```markdown
**Context tracking**: At start of refinement run:
```bash
source scripts/ops/context.sh
set_backlog_context "" "refine" "refinement" "backlog-refinement"
```
Call `clear_backlog_context` after the health report is generated.
```

**Step 4: Update .gitignore**

Add entry so the local context file is not committed:

```
.backlog-ops/current-context.json
```

**Step 5: Verify**

```bash
grep -c "set_backlog_context" skills/backlog-implementer/SKILL.md
grep -c "set_backlog_context" skills/backlog-ticket/SKILL.md
grep -c "set_backlog_context" skills/backlog-refinement/SKILL.md
grep -c "current-context.json" .gitignore
# Expected: 1 each
```

**Step 6: Commit**

```bash
git add skills/backlog-implementer/SKILL.md skills/backlog-ticket/SKILL.md \
        skills/backlog-refinement/SKILL.md .gitignore
git commit -m "feat(skills): add backlog context tracking to all four skills"
```

---

## Verification Checklist

```bash
# 1. Unit tests pass
python3 -m pytest tests/test_ticket_tagger.py -v
bash tests/test_context_sh.sh

# 2. Docker config valid
python3 -c "import yaml; yaml.safe_load(open('docker-compose.yml'))" && echo OK

# 3. Manual end-to-end (after docker compose up)
source scripts/ops/context.sh
set_backlog_context "FEAT-001" "implement" "backend" "backlog-implementer"
# Make any LLM call through LiteLLM proxy
# Open http://localhost:8000/ui/logs and verify tags appear
clear_backlog_context
```
