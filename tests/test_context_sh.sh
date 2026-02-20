#!/usr/bin/env bash
# tests/test_context_sh.sh
set -euo pipefail
PASS=0; FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

TMPDIR_TEST="$(mktemp -d)"
ORIG_HOME="$HOME"
export HOME="$TMPDIR_TEST"

# Temporarily cd into a dir with backlog.config.json
mkdir -p "$TMPDIR_TEST/proj"
echo '{"project":{"name":"test-proj"}}' > "$TMPDIR_TEST/proj/backlog.config.json"
cd "$TMPDIR_TEST/proj"

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../scripts/ops/context.sh"

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
