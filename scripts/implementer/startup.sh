#!/usr/bin/env bash
# scripts/implementer/startup.sh — Merged Phase 0 + 0.5 startup for backlog-implementer
#
# Outputs a single JSON object to stdout with config, tickets, Ollama status,
# playbook stats, cache health, and state file status.
# All logging goes to stderr prefixed with [startup].
#
# Usage:
#   STARTUP_JSON=$(bash scripts/implementer/startup.sh)
#
# Environment:
#   CLAUDE_PLUGIN_ROOT   — override plugin root detection
#   LITELLM_BASE_URL     — override LiteLLM proxy URL
#   LITELLM_MASTER_KEY   — override LiteLLM API key

set -euo pipefail

log() { echo "[startup] $*" >&2; }

# -----------------------------------------------------------
# Step A: Resolve CLAUDE_PLUGIN_ROOT
# -----------------------------------------------------------
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-}"
if [ -z "$PLUGIN_ROOT" ]; then
    # Search common locations
    for candidate in \
        "$HOME/.claude/plugins/backlog-agents" \
        "$HOME/.claude-plugins/backlog-agents" \
        "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." 2>/dev/null && pwd)" \
    ; do
        if [ -d "$candidate/scripts/implementer" ]; then
            PLUGIN_ROOT="$candidate"
            break
        fi
    done
fi

if [ -n "$PLUGIN_ROOT" ]; then
    log "plugin_root=$PLUGIN_ROOT"
else
    log "plugin_root not found (non-fatal)"
fi

# -----------------------------------------------------------
# Step B: Read backlog.config.json
# -----------------------------------------------------------
if [ ! -f "backlog.config.json" ]; then
    python3 -c '
import json
print(json.dumps({"error": "No backlog.config.json found. Run /backlog-toolkit:init first"}))
'
    exit 1
fi

log "reading backlog.config.json"

CONFIG_JSON=$(python3 -c '
import json, sys

with open("backlog.config.json") as f:
    cfg = json.load(f)

backlog = cfg.get("backlog", {})
gates = cfg.get("qualityGates", {})
code_rules = cfg.get("codeRules", {})
llm_ops = cfg.get("llmOps", {})
cache_policy = llm_ops.get("cachePolicy", {})

result = {
    "dataDir": backlog.get("dataDir", "backlog/data"),
    "testCommand": gates.get("testCommand"),
    "lintCommand": gates.get("lintCommand"),
    "typeCheckCommand": gates.get("typeCheckCommand"),
    "codeRulesSource": code_rules.get("source"),
    "sessionMaxWaves": cache_policy.get("sessionMaxWaves", 5),
}
print(json.dumps(result))
')

DATA_DIR=$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['dataDir'])" "$CONFIG_JSON")

# -----------------------------------------------------------
# Step C: Set LiteLLM defaults
# -----------------------------------------------------------
LITELLM_URL=$(python3 -c '
import json, sys
with open("backlog.config.json") as f:
    cfg = json.load(f)
gw = cfg.get("llmOps", {}).get("gateway", {})
print(gw.get("baseURL", "http://localhost:8000"))
')
export LITELLM_BASE_URL="${LITELLM_BASE_URL:-$LITELLM_URL}"
export LITELLM_MASTER_KEY="${LITELLM_MASTER_KEY:-sk-litellm-changeme}"

log "litellm_url=$LITELLM_BASE_URL"

# -----------------------------------------------------------
# Step D: Test Ollama via llm_call.sh
# -----------------------------------------------------------
OLLAMA_AVAILABLE="false"

# Find llm_call.sh: check PATH first, then plugin root, then relative
LLM_CALL=""
if command -v llm_call.sh >/dev/null 2>&1; then
    LLM_CALL="llm_call.sh"
elif [ -n "$PLUGIN_ROOT" ] && [ -x "$PLUGIN_ROOT/scripts/ops/llm_call.sh" ]; then
    LLM_CALL="$PLUGIN_ROOT/scripts/ops/llm_call.sh"
fi

if [ -n "$LLM_CALL" ]; then
    log "testing Ollama via $LLM_CALL"
    if timeout 10 bash "$LLM_CALL" --model free --user "Reply OK" >/dev/null 2>&1; then
        OLLAMA_AVAILABLE="true"
        log "Ollama: available"
    else
        log "Ollama: unavailable"
    fi
else
    log "llm_call.sh not found, skipping Ollama check"
fi

# -----------------------------------------------------------
# Step E: Classify pending tickets
# -----------------------------------------------------------
TICKETS_JSON="[]"
TICKET_COUNT=0

PENDING_DIR="$DATA_DIR/pending"
if [ -d "$PENDING_DIR" ]; then
    # Find classify.py
    CLASSIFY=""
    if [ -n "$PLUGIN_ROOT" ] && [ -f "$PLUGIN_ROOT/scripts/implementer/classify.py" ]; then
        CLASSIFY="$PLUGIN_ROOT/scripts/implementer/classify.py"
    fi

    TICKETS_JSON=$(python3 -c '
import json, sys, os, subprocess, re

pending_dir = sys.argv[1]
classify_py = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] else ""

tickets = []
for fname in sorted(os.listdir(pending_dir)):
    if not fname.endswith(".md"):
        continue
    fpath = os.path.join(pending_dir, fname)
    ticket_id = fname.replace(".md", "")

    complexity = "complex"  # safe default
    if classify_py and os.path.isfile(classify_py):
        try:
            result = subprocess.run(
                ["python3", classify_py, fpath],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                complexity = result.stdout.strip()
        except Exception:
            pass

    tickets.append({
        "id": ticket_id,
        "complexity": complexity,
        "path": fpath,
    })

print(json.dumps(tickets))
' "$PENDING_DIR" "${CLASSIFY:-}")

    TICKET_COUNT=$(python3 -c "import json,sys; print(len(json.loads(sys.argv[1])))" "$TICKETS_JSON")
    log "classified $TICKET_COUNT pending ticket(s)"
else
    log "no pending directory at $PENDING_DIR"
fi

# -----------------------------------------------------------
# Step F: Load playbook stats
# -----------------------------------------------------------
PLAYBOOK_STATS="null"
PLAYBOOK_PATH="$DATA_DIR/playbook.md"

if [ -f "$PLAYBOOK_PATH" ]; then
    PLAYBOOK_UTILS=""
    if [ -n "$PLUGIN_ROOT" ] && [ -f "$PLUGIN_ROOT/scripts/ops/playbook_utils.py" ]; then
        PLAYBOOK_UTILS="$PLUGIN_ROOT/scripts/ops/playbook_utils.py"
    fi

    if [ -n "$PLAYBOOK_UTILS" ]; then
        PLAYBOOK_STATS=$(python3 "$PLAYBOOK_UTILS" stats "$PLAYBOOK_PATH" 2>/dev/null) || PLAYBOOK_STATS="null"
        log "playbook stats loaded"
    else
        log "playbook_utils.py not found"
    fi
else
    log "no playbook at $PLAYBOOK_PATH"
fi

# -----------------------------------------------------------
# Step G: Cache health from usage-ledger.jsonl
# -----------------------------------------------------------
CACHE_HEALTH="null"
LEDGER_PATH=".backlog-ops/usage-ledger.jsonl"

if [ -f "$LEDGER_PATH" ]; then
    CACHE_HEALTH=$(python3 -c '
import json, sys

path = sys.argv[1]
warn_threshold = float(sys.argv[2]) if len(sys.argv) > 2 else 0.80

lines = []
with open(path) as f:
    for line in f:
        line = line.strip()
        if line:
            try:
                lines.append(json.loads(line))
            except json.JSONDecodeError:
                continue

# Take last 10 entries
recent = lines[-10:] if len(lines) > 10 else lines
if not recent:
    print("null")
    sys.exit(0)

rates = []
for entry in recent:
    rate = entry.get("cache_hit_rate")
    if rate is not None:
        try:
            rates.append(float(rate))
        except (TypeError, ValueError):
            continue

if not rates:
    print("null")
    sys.exit(0)

avg = sum(rates) / len(rates)
warning = avg < warn_threshold
print(json.dumps({"avg_hit_rate": round(avg, 4), "warning": warning}))
' "$LEDGER_PATH" "0.80" 2>/dev/null) || CACHE_HEALTH="null"

    if [ "$CACHE_HEALTH" != "null" ]; then
        log "cache health computed"
    fi
else
    log "no usage ledger at $LEDGER_PATH"
fi

# -----------------------------------------------------------
# Step H: Check state file
# -----------------------------------------------------------
STATE_EXISTS="false"
if [ -f ".claude/implementer-state.json" ]; then
    STATE_EXISTS="true"
    log "state file exists"
else
    log "no state file"
fi

# -----------------------------------------------------------
# Assemble final JSON
# -----------------------------------------------------------
python3 -c '
import json, sys

plugin_root = sys.argv[1] if sys.argv[1] else None
config = json.loads(sys.argv[2])
ollama = sys.argv[3] == "true"
litellm_url = sys.argv[4]
tickets = json.loads(sys.argv[5])
ticket_count = int(sys.argv[6])
playbook_stats = json.loads(sys.argv[7]) if sys.argv[7] != "null" else None
cache_health = json.loads(sys.argv[8]) if sys.argv[8] != "null" else None
state_exists = sys.argv[9] == "true"

output = {
    "plugin_root": plugin_root,
    "config": config,
    "ollama_available": ollama,
    "litellm_url": litellm_url,
    "tickets": tickets,
    "ticket_count": ticket_count,
    "playbook_stats": playbook_stats,
    "cache_health": cache_health,
    "state_exists": state_exists,
}
print(json.dumps(output, indent=2))
' \
    "${PLUGIN_ROOT:-}" \
    "$CONFIG_JSON" \
    "$OLLAMA_AVAILABLE" \
    "$LITELLM_BASE_URL" \
    "$TICKETS_JSON" \
    "$TICKET_COUNT" \
    "$PLAYBOOK_STATS" \
    "$CACHE_HEALTH" \
    "$STATE_EXISTS"
