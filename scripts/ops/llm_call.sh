#!/usr/bin/env bash
# llm_call.sh — Call LiteLLM proxy for single-shot LLM tasks
# Used by implementer skill to route gates through the proxy (including free/local tier)
#
# Usage:
#   echo "Classify this ticket: ..." | ./scripts/ops/llm_call.sh --model free
#   ./scripts/ops/llm_call.sh --model free --system "You are a classifier" --user "Classify: BUG or FEAT?"
#   ./scripts/ops/llm_call.sh --model free --file ticket.md --system "Write an implementation plan"
#   ./scripts/ops/llm_call.sh --model free --tag ticket:FEAT-001 --tag gate:plan
#
# Environment:
#   LITELLM_BASE_URL    (default: http://localhost:8000)
#   LITELLM_MASTER_KEY  (default: sk-litellm-changeme)
#   LLM_CALL_LOG        (default: /tmp/llm_call.log) — append-only call log

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
LOG_FILE="${LLM_CALL_LOG:-/tmp/llm_call.log}"
TAGS=()

# Parse args
while [[ $# -gt 0 ]]; do
    case "$1" in
        --model)       MODEL="$2"; shift 2;;
        --system)      SYSTEM_MSG="$2"; shift 2;;
        --user)        USER_MSG="$2"; shift 2;;
        --file)        FILE_PATH="$2"; shift 2;;
        --max-tokens)  MAX_TOKENS="$2"; shift 2;;
        --temperature) TEMPERATURE="$2"; shift 2;;
        --tag)         TAGS+=("$2"); shift 2;;
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

# Build request body with optional metadata tags
TAGS_JSON=$(python3 -c "
import json, sys
tags = sys.argv[1:]
print(json.dumps(tags))
" "${TAGS[@]+"${TAGS[@]}"}")

BODY=$(python3 -c "
import json, sys
body = {
    'model': sys.argv[1],
    'messages': json.loads(sys.argv[2]),
    'max_tokens': int(sys.argv[3]),
    'temperature': float(sys.argv[4])
}
tags = json.loads(sys.argv[5])
if tags:
    body['metadata'] = {'tags': tags}
    # Extract ticket tag for LiteLLM spend tracking (appears in spend/logs as 'user')
    ticket_tags = [t.split(':',1)[1] for t in tags if t.startswith('ticket:')]
    gate_tags = [t.split(':',1)[1] for t in tags if t.startswith('gate:')]
    user_id = '-'.join(ticket_tags + gate_tags) if (ticket_tags or gate_tags) else 'backlog-toolkit'
    body['user'] = user_id
else:
    body['user'] = 'backlog-toolkit'
print(json.dumps(body))
" "$MODEL" "$MESSAGES" "$MAX_TOKENS" "$TEMPERATURE" "$TAGS_JSON")

# Log call start
CALL_TS=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
echo "[${CALL_TS}] llm_call model=${MODEL} tags=[${TAGS[*]+"${TAGS[*]}"}] url=${BASE_URL}" >> "$LOG_FILE" 2>/dev/null || true

# Call LiteLLM proxy
RESPONSE=$(curl -s -w "\n%{http_code}" "$BASE_URL/v1/chat/completions" \
    -H "Authorization: Bearer $API_KEY" \
    -H "Content-Type: application/json" \
    -d "$BODY" 2>/dev/null)

HTTP_CODE=$(echo "$RESPONSE" | tail -1)
RESP_BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" -ge 200 ] && [ "$HTTP_CODE" -lt 300 ]; then
    # Extract content and log success with model details
    python3 -c "
import json, sys
r = json.loads(sys.argv[1])
content = r.get('choices',[{}])[0].get('message',{}).get('content','')
usage = r.get('usage',{})
actual_model = r.get('model','unknown')

# Log to file
import datetime
ts = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
log = {
    'ts': ts,
    'requested_model': sys.argv[2],
    'actual_model': actual_model,
    'tokens_in': usage.get('prompt_tokens',0),
    'tokens_out': usage.get('completion_tokens',0),
    'cache_read': usage.get('cache_read_input_tokens', usage.get('prompt_tokens_details',{}).get('cached_tokens',0)),
    'tags': json.loads(sys.argv[3]),
    'status': 'ok'
}
with open(sys.argv[4], 'a') as f:
    f.write(json.dumps(log) + '\n')

# Emit to stderr for visibility in Claude Code session
print(f'[llm_call] {sys.argv[2]} → {actual_model} | in={usage.get(\"prompt_tokens\",0)} out={usage.get(\"completion_tokens\",0)}', file=sys.stderr)

print(content)
" "$RESP_BODY" "$MODEL" "$TAGS_JSON" "$LOG_FILE" 2>&2
else
    # Log failure
    python3 -c "
import json, sys, datetime
ts = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
log = {
    'ts': ts,
    'requested_model': sys.argv[1],
    'actual_model': None,
    'http_code': int(sys.argv[2]),
    'tags': json.loads(sys.argv[3]),
    'status': 'error'
}
with open(sys.argv[4], 'a') as f:
    f.write(json.dumps(log) + '\n')
" "$MODEL" "$HTTP_CODE" "$TAGS_JSON" "$LOG_FILE" 2>/dev/null || true

    echo "[llm_call] ERROR: model=${MODEL} http=${HTTP_CODE}" >&2
    echo "$RESP_BODY" >&2
    exit 1
fi
