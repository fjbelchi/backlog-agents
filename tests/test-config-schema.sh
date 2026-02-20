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

TOP_KEYS=(version project backlog qualityGates codeRules ticketValidation agentRouting reviewPipeline audit)

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

# ── agentRouting schema checks ────────────────────────────────────────

echo "-- agentRouting schema --"

if python3 -c "
import json, sys
s = json.load(open(sys.argv[1]))
assert 'agentRouting' in s['properties']
" "$SCHEMA" 2>/dev/null; then
  pass "agentRouting section exists in schema"
else
  fail "agentRouting section missing from schema"
fi

if python3 -c "
import json, sys
s = json.load(open(sys.argv[1]))
assert s['properties']['agentRouting']['properties']['rules']['type'] == 'array'
" "$SCHEMA" 2>/dev/null; then
  pass "agentRouting.rules is an array"
else
  fail "agentRouting.rules is not an array"
fi

if python3 -c "
import json, sys
s = json.load(open(sys.argv[1]))
assert s['properties']['agentRouting']['properties']['llmOverride']['type'] == 'boolean'
" "$SCHEMA" 2>/dev/null; then
  pass "agentRouting.llmOverride is a boolean"
else
  fail "agentRouting.llmOverride is not a boolean"
fi

echo ""

# ── reviewPipeline schema checks ─────────────────────────────────────

echo "-- reviewPipeline schema --"

if python3 -c "
import json, sys
s = json.load(open(sys.argv[1]))
assert 'reviewPipeline' in s['properties']
" "$SCHEMA" 2>/dev/null; then
  pass "reviewPipeline section exists in schema"
else
  fail "reviewPipeline section missing from schema"
fi

if python3 -c "
import json, sys
s = json.load(open(sys.argv[1]))
assert s['properties']['reviewPipeline']['properties']['reviewers']['type'] == 'array'
" "$SCHEMA" 2>/dev/null; then
  pass "reviewPipeline.reviewers is an array"
else
  fail "reviewPipeline.reviewers is not an array"
fi

if python3 -c "
import json, sys
s = json.load(open(sys.argv[1]))
ct = s['properties']['reviewPipeline']['properties']['confidenceThreshold']
assert ct['minimum'] == 0
assert ct['maximum'] == 100
" "$SCHEMA" 2>/dev/null; then
  pass "reviewPipeline.confidenceThreshold has min 0 and max 100"
else
  fail "reviewPipeline.confidenceThreshold min/max incorrect"
fi

if python3 -c "
import json, sys
s = json.load(open(sys.argv[1]))
assert s['properties']['reviewPipeline']['properties']['maxReviewRounds']['type'] == 'number'
" "$SCHEMA" 2>/dev/null; then
  pass "reviewPipeline.maxReviewRounds is a number"
else
  fail "reviewPipeline.maxReviewRounds is not a number"
fi

echo ""

# ── agentRouting preset sub-keys ──────────────────────────────────────

echo "-- agentRouting preset sub-keys --"

for key in rules llmOverride; do
  if python3 -c "
import json, sys
d = json.load(open(sys.argv[1]))
assert sys.argv[2] in d['agentRouting']
" "$PRESET" "$key" 2>/dev/null; then
    pass "agentRouting.${key} present"
  else
    fail "agentRouting.${key} missing"
  fi
done

echo ""

# ── reviewPipeline preset sub-keys ────────────────────────────────────

echo "-- reviewPipeline preset sub-keys --"

for key in reviewers confidenceThreshold maxReviewRounds; do
  if python3 -c "
import json, sys
d = json.load(open(sys.argv[1]))
assert sys.argv[2] in d['reviewPipeline']
" "$PRESET" "$key" 2>/dev/null; then
    pass "reviewPipeline.${key} present"
  else
    fail "reviewPipeline.${key} missing"
  fi
done

echo ""

# ── llmOps.routing sub-keys ──────────────────────────────────────────

echo "-- llmOps.routing sub-keys --"

ROUTING_KEYS=(entryModelClassify entryModelPlan entryModelDraft entryModelImplement entryModelReview escalationModel)

for key in "${ROUTING_KEYS[@]}"; do
  if python3 -c "
import json, sys
d = json.load(open(sys.argv[1]))
assert sys.argv[2] in d['llmOps']['routing']
" "$PRESET" "$key" 2>/dev/null; then
    pass "llmOps.routing.${key} present"
  else
    fail "llmOps.routing.${key} missing"
  fi
done

# ── llmOps.cachePolicy sub-keys ──────────────────────────────────────

echo "-- llmOps.cachePolicy sub-keys --"

CACHE_KEYS=(warnBelowHitRate sessionMaxWaves)

for key in "${CACHE_KEYS[@]}"; do
  if python3 -c "
import json, sys
d = json.load(open(sys.argv[1]))
assert sys.argv[2] in d['llmOps']['cachePolicy']
" "$PRESET" "$key" 2>/dev/null; then
    pass "llmOps.cachePolicy.${key} present"
  else
    fail "llmOps.cachePolicy.${key} missing"
  fi
done

echo ""

# ── audit schema checks ─────────────────────────────────────────────

echo "-- audit schema --"

if python3 -c "
import json, sys
s = json.load(open(sys.argv[1]))
assert 'audit' in s['properties']
" "$SCHEMA" 2>/dev/null; then
  pass "audit section exists in schema"
else
  fail "audit section missing from schema"
fi

if python3 -c "
import json, sys
s = json.load(open(sys.argv[1]))
assert s['properties']['audit']['properties']['prescan']['properties']['extensions']['type'] == 'array'
" "$SCHEMA" 2>/dev/null; then
  pass "audit.prescan.extensions is an array"
else
  fail "audit.prescan.extensions is not an array"
fi

if python3 -c "
import json, sys
s = json.load(open(sys.argv[1]))
dims = s['properties']['audit']['properties']['dimensions']
assert dims['items']['type'] == 'string'
assert 'enum' in dims['items']
" "$SCHEMA" 2>/dev/null; then
  pass "audit.dimensions has enum constraint"
else
  fail "audit.dimensions does not have enum constraint"
fi

echo ""

# ── audit preset sub-keys ───────────────────────────────────────────

echo "-- audit preset sub-keys --"

for key in enabled prescan dimensions ragDeduplication ticketMapping; do
  if python3 -c "
import json, sys
d = json.load(open(sys.argv[1]))
assert sys.argv[2] in d['audit']
" "$PRESET" "$key" 2>/dev/null; then
    pass "audit.${key} present"
  else
    fail "audit.${key} missing"
  fi
done

echo ""

echo "-- audit.prescan sub-keys --"

for key in extensions excludeDirs maxFunctionLines coverageThreshold complexityThreshold; do
  if python3 -c "
import json, sys
d = json.load(open(sys.argv[1]))
assert sys.argv[2] in d['audit']['prescan']
" "$PRESET" "$key" 2>/dev/null; then
    pass "audit.prescan.${key} present"
  else
    fail "audit.prescan.${key} missing"
  fi
done

echo ""

# ── Summary ──────────────────────────────────────────────────────────

echo "=== Results: ${PASS} passed, ${FAIL} failed ==="

if [[ $FAIL -gt 0 ]]; then
  exit 1
fi
