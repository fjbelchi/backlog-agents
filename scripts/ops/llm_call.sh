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
