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
