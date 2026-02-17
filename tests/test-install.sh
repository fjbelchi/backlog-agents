#!/usr/bin/env bash
set -uo pipefail

# ── Install Script Validation ────────────────────────────────────────
# Tests install.sh --local by:
#   - Creating a temp directory
#   - Running install.sh --local from inside it
#   - Verifying all 4 skill directories were created with SKILL.md
#   - Cleaning up the temp directory
# ─────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

INSTALL_SCRIPT="${ROOT_DIR}/install.sh"

PASS=0
FAIL=0
TMPDIR=""

pass() {
  echo "  PASS: $1"
  (( PASS++ ))
}

fail() {
  echo "  FAIL: $1"
  (( FAIL++ ))
}

cleanup() {
  if [[ -n "$TMPDIR" && -d "$TMPDIR" ]]; then
    rm -rf "$TMPDIR"
  fi
}
trap cleanup EXIT

SKILLS=(backlog-init backlog-ticket backlog-refinement backlog-implementer)

echo "=== Install Script Validation ==="
echo ""

# ── Check install.sh exists and is executable ───────────────────────

echo "-- Pre-checks --"

if [[ -f "$INSTALL_SCRIPT" ]]; then
  pass "install.sh exists"
else
  fail "install.sh does not exist"
  echo ""
  echo "=== Results: ${PASS} passed, ${FAIL} failed ==="
  exit 1
fi

if [[ -x "$INSTALL_SCRIPT" ]]; then
  pass "install.sh is executable"
else
  fail "install.sh is not executable (attempting chmod)"
  chmod +x "$INSTALL_SCRIPT" 2>/dev/null || true
fi

echo ""

# ── Create temp directory and run install ───────────────────────────

echo "-- Running install --"

TMPDIR="$(mktemp -d)"

if [[ -d "$TMPDIR" ]]; then
  pass "temp directory created at ${TMPDIR}"
else
  fail "could not create temp directory"
  echo ""
  echo "=== Results: ${PASS} passed, ${FAIL} failed ==="
  exit 1
fi

# Run install.sh --local from the temp directory so .claude/skills/ lands there
install_output="$(cd "$TMPDIR" && bash "$INSTALL_SCRIPT" --local --force 2>&1)"
install_exit=$?

if [[ $install_exit -eq 0 ]]; then
  pass "install.sh exited with code 0"
else
  fail "install.sh exited with code ${install_exit}"
  echo "  Output:"
  echo "$install_output" | sed 's/^/    /'
fi

echo ""

# ── Verify skill directories ────────────────────────────────────────

echo "-- Skill directories --"

SKILLS_TARGET="${TMPDIR}/.claude/skills"

for skill in "${SKILLS[@]}"; do
  skill_dir="${SKILLS_TARGET}/${skill}"

  if [[ -d "$skill_dir" ]]; then
    pass "directory ${skill}/ created"
  else
    fail "directory ${skill}/ not found"
    continue
  fi

  if [[ -f "${skill_dir}/SKILL.md" ]]; then
    pass "${skill}/SKILL.md exists"
  else
    fail "${skill}/SKILL.md missing"
  fi
done

echo ""

# ── Summary ──────────────────────────────────────────────────────────

echo "=== Results: ${PASS} passed, ${FAIL} failed ==="

if [[ $FAIL -gt 0 ]]; then
  exit 1
fi
