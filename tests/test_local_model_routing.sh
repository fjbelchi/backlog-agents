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

# Test 3: Classification task
echo "Test 3: Classification task"
RESP=$(curl -s "$LITELLM_URL/v1/chat/completions" \
    -H "Authorization: Bearer $API_KEY" \
    -H "Content-Type: application/json" \
    -d '{"model":"free","messages":[{"role":"user","content":"Classify: BUG, FEAT, or TASK? \"Add login button\". Reply with ONE word."}],"max_tokens":10}' 2>&1)
check "Classification returns category" "FEAT" "$RESP"

echo ""
echo "Results: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
