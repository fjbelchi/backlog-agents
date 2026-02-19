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
