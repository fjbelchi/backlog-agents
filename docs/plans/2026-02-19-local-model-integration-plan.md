# Local Model Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add qwen3-coder as a free local model tier in LiteLLM with tag-based routing, automatic fallback to Haiku, and quality-gated escalation for simple implementation tasks.

**Architecture:** LiteLLM tag-based routing sends `"local"` tagged requests to Ollama (qwen3-coder:30b). Untagged requests go to Bedrock (default). Fallback chain: free → cheap → balanced. The implementer skill treats local model as a "junior programmer" — quality gates (lint + review) act as sentinel, escalating to Sonnet on failure.

**Tech Stack:** LiteLLM proxy (YAML config), Ollama, Docker networking, Python (migrate-state.py), Markdown (SKILL.md)

**Design doc:** `docs/plans/2026-02-19-local-model-integration-design.md`

---

## Phase 1: LiteLLM Config (no skill changes)

### Task 1: Add free tier to LiteLLM proxy config

**Files:**
- Modify: `config/litellm/proxy-config.docker.yaml:19` (insert before cheap model)

**Step 1: Add the free model entry**

Insert before line 20 (`# CHEAP`):

```yaml
  # FREE — local model: classification, triage, wave planning, write-agents
  # Requires Ollama running on host with qwen3-coder:30b
  # Falls back to cheap (Haiku) if Ollama is unavailable
  - model_name: free
    litellm_params:
      model: ollama/qwen3-coder:30b
      api_base: http://host.docker.internal:11434
      tags: ["local"]
      input_cost_per_token: 0
      output_cost_per_token: 0
      request_timeout: 120

```

**Step 2: Add free tier fallback to router_settings**

In `router_settings.fallbacks` (line 122), add as the first entry:

```yaml
    - free: [cheap, balanced]
```

Add to `context_window_fallbacks` (line 129):

```yaml
    - free: [cheap]
```

**Step 3: Add free tier budget**

In `model_max_budget` (line 182), add:

```yaml
  free: 0                  # Local model, no cloud cost
```

**Step 4: Verify YAML is valid**

Run: `python3 -c "import yaml; yaml.safe_load(open('config/litellm/proxy-config.docker.yaml'))"`
Expected: No output (success)

**Step 5: Commit**

```bash
git add config/litellm/proxy-config.docker.yaml
git commit -m "feat(litellm): add free tier with Ollama qwen3-coder for local model routing"
```

---

### Task 2: Ensure Ollama is accessible from Docker

**Files:**
- Modify: `docker-compose.yml:40` (litellm environment section)

**Step 1: Add OLLAMA_HOST env var to litellm service**

In the `litellm` service `environment` section (after line 48, AWS_DEFAULT_REGION), add:

```yaml
      # Ollama host for local model routing (host.docker.internal resolves to host machine)
      OLLAMA_HOST: ${OLLAMA_HOST:-http://host.docker.internal:11434}
```

No other docker-compose changes needed — `host.docker.internal` is resolved automatically on Docker Desktop for Mac.

**Step 2: Verify docker-compose syntax**

Run: `docker compose --env-file .env.docker.local config --quiet`
Expected: No output (valid)

**Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "feat(docker): add OLLAMA_HOST env var for local model routing"
```

---

### Task 3: Add Ollama health check to start-services.sh

**Files:**
- Modify: `scripts/services/start-services.sh:1042-1046` (start_ollama function)

**Step 1: Enhance Ollama startup with model verification**

Replace the success check block (lines 1042-1046) with:

```bash
    if curl -s http://localhost:11434/api/tags &> /dev/null; then
        # Verify qwen3-coder model is available
        if ollama list 2>/dev/null | grep -q "qwen3-coder"; then
            log_success "Ollama started (qwen3-coder available)"
        else
            log_warning "Ollama running but qwen3-coder not found. Run: ollama pull qwen3-coder:30b"
        fi
    else
        log_warning "Ollama failed to start (optional — LiteLLM will fall back to Haiku)"
    fi
```

**Step 2: Verify script syntax**

Run: `bash -n scripts/services/start-services.sh`
Expected: No output (valid)

**Step 3: Commit**

```bash
git add scripts/services/start-services.sh
git commit -m "feat(services): add qwen3-coder model check to Ollama startup"
```

---

### Task 4: Write integration test for local model routing

**Files:**
- Create: `tests/test_local_model_routing.sh`

**Step 1: Write the test script**

```bash
#!/usr/bin/env bash
# Test local model routing through LiteLLM proxy
# Requires: Ollama running with qwen3-coder:30b, LiteLLM proxy on port 8000
set -euo pipefail

LITELLM_URL="${LITELLM_BASE_URL:-http://localhost:8000}"
API_KEY="${LITELLM_MASTER_KEY:-sk-litellm-changeme}"
PASS=0; FAIL=0

check() {
    local name="$1" expected="$2" actual="$3"
    if echo "$actual" | grep -q "$expected"; then
        echo "  ✅ $name"
        ((PASS++))
    else
        echo "  ❌ $name (expected: $expected, got: $actual)"
        ((FAIL++))
    fi
}

echo "=== Local Model Routing Tests ==="

# Test 1: Free tier routes to Ollama
echo "Test 1: Free tier request"
RESP=$(curl -s "$LITELLM_URL/v1/chat/completions" \
    -H "Authorization: Bearer $API_KEY" \
    -H "Content-Type: application/json" \
    -d '{"model":"free","messages":[{"role":"user","content":"Reply with only: OK"}],"max_tokens":5}' 2>&1)
check "Free tier responds" "choices" "$RESP"

# Test 2: Model list includes free
echo "Test 2: Model list"
MODELS=$(curl -s "$LITELLM_URL/v1/models" -H "Authorization: Bearer $API_KEY" 2>&1)
check "Free model listed" "free" "$MODELS"

# Test 3: Fallback works (stop Ollama temporarily if running test in isolation)
echo "Test 3: Classification task"
RESP=$(curl -s "$LITELLM_URL/v1/chat/completions" \
    -H "Authorization: Bearer $API_KEY" \
    -H "Content-Type: application/json" \
    -d '{"model":"free","messages":[{"role":"user","content":"Classify: BUG, FEAT, or TASK? \"Add login button\". Reply with ONE word."}],"max_tokens":10}' 2>&1)
check "Classification returns category" "FEAT" "$RESP"

echo ""
echo "Results: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
```

**Step 2: Make executable and run**

Run: `chmod +x tests/test_local_model_routing.sh`
Run: `./tests/test_local_model_routing.sh` (only if services are running)

**Step 3: Commit**

```bash
git add tests/test_local_model_routing.sh
git commit -m "test: add integration tests for local model routing via LiteLLM"
```

---

### Task 5: Create LiteLLM proxy helper script

**Files:**
- Create: `scripts/ops/llm_call.sh`
- Create: `tests/test_llm_call.sh`

**Step 1: Write the helper script**

This script lets the implementer skill call LiteLLM directly (bypassing Claude Code subagents), enabling `free` tier routing to Ollama.

```bash
#!/usr/bin/env bash
# llm_call.sh — Call LiteLLM proxy for single-shot LLM tasks
# Used by implementer skill to route gates through the proxy (including free/local tier)
#
# Usage:
#   echo "Classify this ticket: ..." | ./scripts/ops/llm_call.sh --model free
#   ./scripts/ops/llm_call.sh --model free --system "You are a classifier" --user "Classify: BUG or FEAT?"
#   ./scripts/ops/llm_call.sh --model free --file ticket.md --system "Write an implementation plan"
#
# Environment:
#   LITELLM_BASE_URL   (default: http://localhost:8000)
#   LITELLM_MASTER_KEY  (default: sk-litellm-changeme)

set -euo pipefail

# Defaults
MODEL="free"
SYSTEM_MSG=""
USER_MSG=""
FILE_PATH=""
MAX_TOKENS=4096
TEMPERATURE=0.2
BASE_URL="${LITELLM_BASE_URL:-http://localhost:8000}"
API_KEY="${LITELLM_MASTER_KEY:-sk-litellm-changeme}"

# Parse args
while [[ $# -gt 0 ]]; do
    case "$1" in
        --model)    MODEL="$2"; shift 2;;
        --system)   SYSTEM_MSG="$2"; shift 2;;
        --user)     USER_MSG="$2"; shift 2;;
        --file)     FILE_PATH="$2"; shift 2;;
        --max-tokens) MAX_TOKENS="$2"; shift 2;;
        --temperature) TEMPERATURE="$2"; shift 2;;
        *) echo "Unknown arg: $1" >&2; exit 1;;
    esac
done

# Build user message: --user takes priority, then --file, then stdin
if [ -z "$USER_MSG" ]; then
    if [ -n "$FILE_PATH" ] && [ -f "$FILE_PATH" ]; then
        USER_MSG=$(cat "$FILE_PATH")
    elif [ ! -t 0 ]; then
        USER_MSG=$(cat)
    else
        echo "Error: provide --user, --file, or pipe stdin" >&2
        exit 1
    fi
fi

# Build messages array
MESSAGES="[]"
if [ -n "$SYSTEM_MSG" ]; then
    MESSAGES=$(python3 -c "
import json, sys
msgs = [{'role':'system','content':sys.argv[1]},{'role':'user','content':sys.argv[2]}]
print(json.dumps(msgs))
" "$SYSTEM_MSG" "$USER_MSG")
else
    MESSAGES=$(python3 -c "
import json, sys
msgs = [{'role':'user','content':sys.argv[1]}]
print(json.dumps(msgs))
" "$USER_MSG")
fi

# Build request body
BODY=$(python3 -c "
import json, sys
body = {
    'model': sys.argv[1],
    'messages': json.loads(sys.argv[2]),
    'max_tokens': int(sys.argv[3]),
    'temperature': float(sys.argv[4])
}
print(json.dumps(body))
" "$MODEL" "$MESSAGES" "$MAX_TOKENS" "$TEMPERATURE")

# Call LiteLLM proxy
RESPONSE=$(curl -s -w "\n%{http_code}" "$BASE_URL/v1/chat/completions" \
    -H "Authorization: Bearer $API_KEY" \
    -H "Content-Type: application/json" \
    -d "$BODY" 2>&1)

HTTP_CODE=$(echo "$RESPONSE" | tail -1)
RESP_BODY=$(echo "$RESPONSE" | head -n -1)

if [ "$HTTP_CODE" -ge 200 ] && [ "$HTTP_CODE" -lt 300 ]; then
    # Extract content from response
    python3 -c "
import json, sys
r = json.loads(sys.argv[1])
content = r.get('choices',[{}])[0].get('message',{}).get('content','')
print(content)
" "$RESP_BODY"
else
    echo "Error: HTTP $HTTP_CODE" >&2
    echo "$RESP_BODY" >&2
    exit 1
fi
```

**Step 2: Write tests**

```bash
#!/usr/bin/env bash
# Test llm_call.sh helper
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PASS=0; FAIL=0

check() {
    local name="$1"; shift
    if "$@" >/dev/null 2>&1; then
        echo "  ✅ $name"; ((PASS++))
    else
        echo "  ❌ $name"; ((FAIL++))
    fi
}

echo "=== llm_call.sh Tests ==="

# Test 1: --user flag works
echo "Test 1: Direct user message"
RESULT=$("$SCRIPT_DIR/scripts/ops/llm_call.sh" --model free --user "Reply with only: PONG" 2>&1)
check "Returns response" echo "$RESULT" | grep -qi "pong\|PONG"

# Test 2: Pipe stdin works
echo "Test 2: Stdin pipe"
RESULT=$(echo "Reply with only: OK" | "$SCRIPT_DIR/scripts/ops/llm_call.sh" --model free 2>&1)
check "Stdin works" echo "$RESULT" | grep -qi "ok\|OK"

# Test 3: System message
echo "Test 3: System + user"
RESULT=$("$SCRIPT_DIR/scripts/ops/llm_call.sh" --model free \
    --system "You classify tickets. Reply with ONLY the category: BUG, FEAT, TASK" \
    --user "Add dark mode support" 2>&1)
check "Classification works" echo "$RESULT" | grep -qE "FEAT|BUG|TASK"

echo ""
echo "Results: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
```

**Step 3: Make executable**

Run: `chmod +x scripts/ops/llm_call.sh tests/test_llm_call.sh`

**Step 4: Test** (only if services running)

Run: `./tests/test_llm_call.sh`

**Step 5: Commit**

```bash
git add scripts/ops/llm_call.sh tests/test_llm_call.sh
git commit -m "feat(ops): add llm_call.sh helper for direct LiteLLM proxy calls from skills"
```

---

## Phase 2: Implementer Skill Changes

### Task 6: Add localModelStats to migrate-state.py

**Files:**
- Modify: `scripts/implementer/migrate-state.py:47` (before version bump)

**Step 1: Add localModelStats defaults**

After the `reviewStats` setdefault block, add:

```python
local = stats.setdefault("localModelStats", {})
local.setdefault("totalAttempts", 0)
local.setdefault("successCount", 0)
local.setdefault("escalatedToCloud", 0)
local.setdefault("failuresByType", {})
local.setdefault("avgQualityScore", 0)
```

**Step 2: Bump version to 6.1**

Change line 48 from `state["version"] = "6.0"` to `state["version"] = "6.1"`.

**Step 3: Test migration**

Run: `mkdir -p /tmp/test-migrate && cd /tmp/test-migrate && python3 /Users/fbelchi/github/backlog-agents/scripts/implementer/migrate-state.py`
Expected: "State ready: .claude/implementer-state.json"

Run: `python3 -c "import json; s=json.load(open('/tmp/test-migrate/.claude/implementer-state.json')); print(s['stats']['localModelStats']); print('version:', s['version'])"`
Expected: `{'totalAttempts': 0, 'successCount': 0, 'escalatedToCloud': 0, 'failuresByType': {}, 'avgQualityScore': 0}` and `version: 6.1`

**Step 4: Commit**

```bash
git add scripts/implementer/migrate-state.py
git commit -m "feat(state): add localModelStats tracking for local model escalation"
```

---

### Task 7: Add local-first routing rule to SKILL.md

**Files:**
- Modify: `skills/backlog-implementer/SKILL.md` (Cost-Aware Execution + Phase 0.5 + State Schema)

**Step 1: Add local model routing rule**

After the existing Model Tier Routing block (after `Model aliases resolve via LiteLLM config`), add:

```markdown
### Local Model Routing (Junior Programmer Pattern)

When Ollama is detected in Phase 0.5, simple tickets route through LiteLLM proxy `free` tier via `scripts/ops/llm_call.sh` instead of spawning Claude Code subagents.

The leader calls `llm_call.sh --model free` for plan gates. Review always uses cloud (Sonnet/Haiku) — local never reviews itself.

LOCAL-ELIGIBLE tickets (ALL must be true):
  - complexity != "high"
  - NO tags: ARCH, SECURITY
  - affected_files <= 3
  - NOT depends_on another ticket in this wave
  - localModelStats.escalatedToCloud / totalAttempts < 0.30

For LOCAL-ELIGIBLE tickets:
  Gate 1 PLAN:
    result=$(bash scripts/ops/llm_call.sh --model free --system "Write implementation plan" --file ticket.md)
    If empty or error → fallback to Task(model: "haiku") subagent
  Gate 2 IMPLEMENT:
    Task() subagent (needs tool_use for edits). Use normal routing.
  Gate 3 LINT:      → run locally (no LLM)
  Gate 4 REVIEW:    → Task(model: "haiku") subagent — cloud reviews local output
  Gate 5 COMMIT:    → always "cheap"

ESCALATION: If Gate 3/4 fails twice on local-routed ticket:
  1. stats.localModelStats.escalatedToCloud++
  2. stats.localModelStats.failuresByType[gate]++
  3. Re-route to Task(model: "sonnet") with full context
  4. Message: "Local failed on {id} at {gate}. Escalated."

Success: stats.localModelStats.successCount++, totalAttempts++
```

**Step 2: Update Phase 0.5 to detect Ollama**

Append to the Phase 0.5 paragraph:
`Also check Ollama: bash scripts/ops/llm_call.sh --model free --user "Reply OK". If response received, set ollamaAvailable=true, log "Local model: free tier via Ollama".`

**Step 3: Update state schema reference**

In State Schema line, add `localModelStats` after `reviewStats`.

**Step 4: Commit**

```bash
git add skills/backlog-implementer/SKILL.md
git commit -m "feat(implementer): add local-first routing with llm_call.sh and escalation"
```

---

### Task 8: Update design doc status and verify

**Files:**
- Modify: `docs/plans/2026-02-19-local-model-integration-design.md:4`

**Step 1: Update status**

Change line 4 from `**Status**: Approved` to `**Status**: Implemented`.

**Step 2: Run all existing tests**

Run: `python3 -m pytest tests/ -q`
Expected: All tests pass (25 batch + 24 RAG = 49 tests)

**Step 3: Run routing test (if services up)**

Run: `./tests/test_local_model_routing.sh` (skip if Docker services not running)

**Step 4: Final commit**

```bash
git add docs/plans/2026-02-19-local-model-integration-design.md
git commit -m "docs: mark local model integration design as implemented"
```

---

## Summary

| Task | Files | What it does |
|---|---|---|
| 1 | proxy-config.docker.yaml | Add free tier + fallbacks |
| 2 | docker-compose.yml | OLLAMA_HOST env var |
| 3 | start-services.sh | Model verification on startup |
| 4 | test_local_model_routing.sh | Integration tests |
| 5 | llm_call.sh | Helper script for direct LiteLLM proxy calls |
| 6 | migrate-state.py | localModelStats tracking |
| 7 | SKILL.md | Junior programmer routing + escalation |
| 8 | design doc | Mark implemented + verify |
