#!/usr/bin/env bash
# tests/test_startup.sh — Tests for scripts/implementer/startup.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
STARTUP="$REPO_ROOT/scripts/implementer/startup.sh"

PASS=0; FAIL=0; TOTAL=0

pass() { echo "  PASS: $1"; PASS=$((PASS+1)); TOTAL=$((TOTAL+1)); }
fail() { echo "  FAIL: $1 — $2"; FAIL=$((FAIL+1)); TOTAL=$((TOTAL+1)); }

# Helper: validate JSON and extract a key
json_get() {
    python3 -c "import json,sys; d=json.loads(sys.stdin.read()); print(json.dumps(d.get('$1', 'MISSING')))"
}

json_val() {
    python3 -c "
import json, sys
data = json.loads(sys.argv[1])
keys = sys.argv[2].split('.')
v = data
for k in keys:
    if isinstance(v, dict):
        v = v.get(k, 'MISSING')
    else:
        v = 'MISSING'
        break
print(json.dumps(v) if not isinstance(v, str) else v)
" "$1" "$2"
}

setup_tmpdir() {
    local tmp
    tmp="$(mktemp -d)"
    echo "$tmp"
}

# Create a minimal backlog.config.json
write_config() {
    local dir="$1"
    cat > "$dir/backlog.config.json" <<'CONF'
{
  "version": "1.1",
  "project": {"name": "test-proj", "stack": "typescript"},
  "backlog": {
    "dataDir": "backlog/data",
    "templatesDir": "backlog/templates",
    "ticketPrefixes": ["FEAT","BUG"],
    "requiredSections": ["context","description"]
  },
  "qualityGates": {
    "testCommand": "npm test",
    "lintCommand": "npx eslint .",
    "typeCheckCommand": "npx tsc --noEmit"
  },
  "codeRules": {"source": ".claude/rules.md", "hardGates": [], "softGates": []},
  "ticketValidation": {
    "requireTestStrategy": true,
    "requireAffectedFiles": true,
    "requireDependencyCheck": true,
    "minAcceptanceCriteria": 3,
    "requireVerificationCommands": true
  },
  "llmOps": {
    "gateway": {"baseURL": "http://localhost:9999"},
    "cachePolicy": {"sessionMaxWaves": 3}
  }
}
CONF
}

# Create a pending ticket
write_ticket() {
    local dir="$1" id="$2" files="$3"
    mkdir -p "$dir"
    cat > "$dir/$id.md" <<EOF
---
id: $id
type: BUG
tags: [backend]
affected_files: [$files]
---
# $id
Fix the bug.
EOF
}

echo "=== startup.sh Tests ==="

# -------------------------------------------------------
# Test 1: Script is executable
# -------------------------------------------------------
echo "Test 1: Script is executable"
if [ -x "$STARTUP" ]; then
    pass "startup.sh is executable"
else
    fail "startup.sh is not executable" "chmod +x needed"
fi

# -------------------------------------------------------
# Test 2: Missing config -> error JSON with exit 1
# -------------------------------------------------------
echo "Test 2: Missing backlog.config.json"
TMPDIR2="$(setup_tmpdir)"
OUTPUT=""
EXIT_CODE=0
OUTPUT=$(cd "$TMPDIR2" && bash "$STARTUP" 2>/dev/null) || EXIT_CODE=$?
if [ "$EXIT_CODE" -ne 0 ]; then
    pass "exits non-zero when config missing"
else
    fail "should exit non-zero when config missing" "got exit $EXIT_CODE"
fi
# Validate it emits error JSON
ERR_MSG=$(echo "$OUTPUT" | python3 -c "import json,sys; print(json.loads(sys.stdin.read()).get('error',''))" 2>/dev/null || echo "")
if echo "$ERR_MSG" | grep -qi "backlog.config.json"; then
    pass "error JSON mentions backlog.config.json"
else
    fail "error JSON should mention backlog.config.json" "got: $ERR_MSG"
fi
rm -rf "$TMPDIR2"

# -------------------------------------------------------
# Test 3: Happy path with mock config and pending tickets
# -------------------------------------------------------
echo "Test 3: Happy path"
TMPDIR3="$(setup_tmpdir)"
write_config "$TMPDIR3"
mkdir -p "$TMPDIR3/backlog/data/pending"
write_ticket "$TMPDIR3/backlog/data/pending" "BUG-001" "src/a.ts"
write_ticket "$TMPDIR3/backlog/data/pending" "BUG-002" "src/b.ts, src/c.ts"

# Mock llm_call.sh to fail (Ollama unavailable) — create mock in PATH
MOCK_BIN="$TMPDIR3/mock_bin"
mkdir -p "$MOCK_BIN"
cat > "$MOCK_BIN/llm_call.sh" <<'MOCK'
#!/usr/bin/env bash
exit 1
MOCK
chmod +x "$MOCK_BIN/llm_call.sh"

OUTPUT3=""
EXIT_CODE3=0
OUTPUT3=$(cd "$TMPDIR3" && \
    CLAUDE_PLUGIN_ROOT="$REPO_ROOT" \
    PATH="$MOCK_BIN:$PATH" \
    bash "$STARTUP" 2>/dev/null) || EXIT_CODE3=$?

if [ "$EXIT_CODE3" -eq 0 ]; then
    pass "exits 0 on happy path"
else
    fail "should exit 0 on happy path" "got exit $EXIT_CODE3"
fi

# Validate JSON output
VALID_JSON=0
python3 -c "import json,sys; json.loads(sys.argv[1])" "$OUTPUT3" 2>/dev/null && VALID_JSON=1
if [ "$VALID_JSON" -eq 1 ]; then
    pass "output is valid JSON"
else
    fail "output should be valid JSON" "got: $OUTPUT3"
fi

# Check config fields
DATA_DIR=$(json_val "$OUTPUT3" "config.dataDir")
if [ "$DATA_DIR" = "backlog/data" ]; then
    pass "config.dataDir parsed correctly"
else
    fail "config.dataDir" "expected backlog/data, got $DATA_DIR"
fi

TEST_CMD=$(json_val "$OUTPUT3" "config.testCommand")
if [ "$TEST_CMD" = "npm test" ]; then
    pass "config.testCommand parsed correctly"
else
    fail "config.testCommand" "expected 'npm test', got $TEST_CMD"
fi

MAX_WAVES=$(json_val "$OUTPUT3" "config.sessionMaxWaves")
if [ "$MAX_WAVES" = "3" ]; then
    pass "config.sessionMaxWaves parsed correctly"
else
    fail "config.sessionMaxWaves" "expected 3, got $MAX_WAVES"
fi

# Check ticket count
TCOUNT=$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['ticket_count'])" "$OUTPUT3" 2>/dev/null || echo "ERR")
if [ "$TCOUNT" = "2" ]; then
    pass "ticket_count is 2"
else
    fail "ticket_count should be 2" "got $TCOUNT"
fi

rm -rf "$TMPDIR3"

# -------------------------------------------------------
# Test 4: No pending tickets -> ticket_count: 0
# -------------------------------------------------------
echo "Test 4: No pending tickets"
TMPDIR4="$(setup_tmpdir)"
write_config "$TMPDIR4"
# No pending dir at all

OUTPUT4=""
OUTPUT4=$(cd "$TMPDIR4" && \
    CLAUDE_PLUGIN_ROOT="$REPO_ROOT" \
    PATH="$MOCK_BIN:$PATH" \
    bash "$STARTUP" 2>/dev/null) || true

TCOUNT4=$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['ticket_count'])" "$OUTPUT4" 2>/dev/null || echo "ERR")
if [ "$TCOUNT4" = "0" ]; then
    pass "ticket_count is 0 when no pending dir"
else
    fail "ticket_count should be 0" "got $TCOUNT4"
fi

# Also check tickets is empty list
TICKETS4=$(python3 -c "import json,sys; print(len(json.loads(sys.argv[1])['tickets']))" "$OUTPUT4" 2>/dev/null || echo "ERR")
if [ "$TICKETS4" = "0" ]; then
    pass "tickets is empty list"
else
    fail "tickets should be empty list" "got length $TICKETS4"
fi
rm -rf "$TMPDIR4"

# -------------------------------------------------------
# Test 5: Ollama unavailable -> ollama_available: false
# -------------------------------------------------------
echo "Test 5: Ollama unavailable"
TMPDIR5="$(setup_tmpdir)"
write_config "$TMPDIR5"
MOCK_BIN5="$TMPDIR5/mock_bin"
mkdir -p "$MOCK_BIN5"
cat > "$MOCK_BIN5/llm_call.sh" <<'MOCK'
#!/usr/bin/env bash
exit 1
MOCK
chmod +x "$MOCK_BIN5/llm_call.sh"

OUTPUT5=""
OUTPUT5=$(cd "$TMPDIR5" && \
    CLAUDE_PLUGIN_ROOT="$REPO_ROOT" \
    PATH="$MOCK_BIN5:$PATH" \
    bash "$STARTUP" 2>/dev/null) || true

OLLAMA5=$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['ollama_available'])" "$OUTPUT5" 2>/dev/null || echo "ERR")
if [ "$OLLAMA5" = "False" ]; then
    pass "ollama_available is false when llm_call fails"
else
    fail "ollama_available should be False" "got $OLLAMA5"
fi
rm -rf "$TMPDIR5"

# -------------------------------------------------------
# Test 6: cache_mode field present in startup JSON
# -------------------------------------------------------
echo "Test 6: cache_mode field present in startup JSON"
TMPDIR6="$(setup_tmpdir)"
write_config "$TMPDIR6"
MOCK_BIN6="$TMPDIR6/mock_bin"
mkdir -p "$MOCK_BIN6"
cat > "$MOCK_BIN6/llm_call.sh" <<'MOCK'
#!/usr/bin/env bash
exit 1
MOCK
chmod +x "$MOCK_BIN6/llm_call.sh"

OUTPUT6=""
OUTPUT6=$(cd "$TMPDIR6" && \
    CLAUDE_PLUGIN_ROOT="$REPO_ROOT" \
    PATH="$MOCK_BIN6:$PATH" \
    bash "$STARTUP" 2>/dev/null) || true

if echo "$OUTPUT6" | python3 -c "import json,sys; d=json.loads(sys.stdin.read()); assert 'cache_mode' in d, 'missing cache_mode'" 2>/dev/null; then
    pass "cache_mode present in startup JSON"
else
    fail "cache_mode field" "cache_mode missing from startup JSON"
fi

# Test 7: cache_mode value is 'litellm' or 'direct'
echo "Test 7: cache_mode value is 'litellm' or 'direct'"
if echo "$OUTPUT6" | python3 -c "
import json,sys
d=json.loads(sys.stdin.read())
assert d.get('cache_mode') in ('litellm','direct'), f\"unexpected: {d.get('cache_mode')}\"
" 2>/dev/null; then
    pass "cache_mode has valid value ('litellm' or 'direct')"
else
    fail "cache_mode value" "cache_mode has unexpected value (not 'litellm' or 'direct')"
fi
rm -rf "$TMPDIR6"

# -------------------------------------------------------
# Summary
# -------------------------------------------------------
echo ""
echo "=== $PASS passed, $FAIL failed out of $TOTAL ==="
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
