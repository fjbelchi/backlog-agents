#!/usr/bin/env bash
set -uo pipefail

# ── Config Schema & Preset Validation ────────────────────────────────
# Validates:
#   - config/backlog.config.schema.json is valid JSON
#   - config/presets/default.json is valid JSON
#   - default.json contains all required keys and sub-keys
# ─────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

SCHEMA="${ROOT_DIR}/config/backlog.config.schema.json"
PRESET="${ROOT_DIR}/config/presets/default.json"

PASS=0
FAIL=0

pass() {
  echo "  PASS: $1"
  (( PASS++ ))
}

fail() {
  echo "  FAIL: $1"
  (( FAIL++ ))
}

echo "=== Config Schema & Preset Validation ==="
echo ""

# ── Schema file checks ──────────────────────────────────────────────

echo "-- Schema file --"

if [[ -f "$SCHEMA" ]]; then
  pass "backlog.config.schema.json exists"
else
  fail "backlog.config.schema.json does not exist"
fi

if [[ -f "$SCHEMA" ]] && python3 -c "import json, sys; json.load(open(sys.argv[1]))" "$SCHEMA" 2>/dev/null; then
  pass "backlog.config.schema.json is valid JSON"
else
  fail "backlog.config.schema.json is NOT valid JSON"
fi

echo ""

# ── Preset file checks ──────────────────────────────────────────────

echo "-- Default preset --"

if [[ -f "$PRESET" ]]; then
  pass "default.json exists"
else
  fail "default.json does not exist"
fi

if [[ -f "$PRESET" ]] && python3 -c "import json, sys; json.load(open(sys.argv[1]))" "$PRESET" 2>/dev/null; then
  pass "default.json is valid JSON"
else
  fail "default.json is NOT valid JSON"
fi

echo ""

# ── Required top-level keys ─────────────────────────────────────────

echo "-- Top-level keys --"

TOP_KEYS=(version project backlog qualityGates codeRules ticketValidation)

for key in "${TOP_KEYS[@]}"; do
  if python3 -c "
import json, sys
d = json.load(open(sys.argv[1]))
assert sys.argv[2] in d
" "$PRESET" "$key" 2>/dev/null; then
    pass "top-level key '${key}' present"
  else
    fail "top-level key '${key}' missing"
  fi
done

echo ""

# ── project sub-keys ────────────────────────────────────────────────

echo "-- project sub-keys --"

for key in name stack; do
  if python3 -c "
import json, sys
d = json.load(open(sys.argv[1]))
assert sys.argv[2] in d['project']
" "$PRESET" "$key" 2>/dev/null; then
    pass "project.${key} present"
  else
    fail "project.${key} missing"
  fi
done

echo ""

# ── backlog sub-keys ────────────────────────────────────────────────

echo "-- backlog sub-keys --"

for key in dataDir templatesDir ticketPrefixes requiredSections; do
  if python3 -c "
import json, sys
d = json.load(open(sys.argv[1]))
assert sys.argv[2] in d['backlog']
" "$PRESET" "$key" 2>/dev/null; then
    pass "backlog.${key} present"
  else
    fail "backlog.${key} missing"
  fi
done

echo ""

# ── qualityGates sub-keys ───────────────────────────────────────────

echo "-- qualityGates sub-keys --"

if python3 -c "
import json, sys
d = json.load(open(sys.argv[1]))
assert 'testCommand' in d['qualityGates']
" "$PRESET" 2>/dev/null; then
  pass "qualityGates.testCommand present"
else
  fail "qualityGates.testCommand missing"
fi

echo ""

# ── ticketValidation sub-keys ───────────────────────────────────────

echo "-- ticketValidation sub-keys --"

TV_KEYS=(requireTestStrategy requireAffectedFiles requireDependencyCheck minAcceptanceCriteria requireVerificationCommands)

for key in "${TV_KEYS[@]}"; do
  if python3 -c "
import json, sys
d = json.load(open(sys.argv[1]))
assert sys.argv[2] in d['ticketValidation']
" "$PRESET" "$key" 2>/dev/null; then
    pass "ticketValidation.${key} present"
  else
    fail "ticketValidation.${key} missing"
  fi
done

echo ""

# ── Summary ──────────────────────────────────────────────────────────

echo "=== Results: ${PASS} passed, ${FAIL} failed ==="

if [[ $FAIL -gt 0 ]]; then
  exit 1
fi
