#!/usr/bin/env bash
set -uo pipefail

# ── Template Validation ──────────────────────────────────────────────
# Validates each template in templates/*.md:
#   - File exists
#   - Has YAML frontmatter (opening and closing ---)
#   - Frontmatter contains required fields
#   - Body contains all required sections
# ─────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

TEMPLATES_DIR="${ROOT_DIR}/templates"

PASS=0
FAIL=0

pass() {
  echo "    PASS: $1"
  (( PASS++ ))
}

fail() {
  echo "    FAIL: $1"
  (( FAIL++ ))
}

TEMPLATES=(
  "feature-template.md"
  "bug-template.md"
  "task-template.md"
  "idea-template.md"
)

FRONTMATTER_FIELDS=(id title status priority depends_on shared_files)

REQUIRED_SECTIONS=(
  "Context"
  "Description"
  "Affected Files"
  "Acceptance Criteria"
  "Test Strategy"
  "Dependencies"
  "Implementation Notes"
  "History"
)

echo "=== Template Validation ==="
echo ""

for tmpl in "${TEMPLATES[@]}"; do
  filepath="${TEMPLATES_DIR}/${tmpl}"
  echo "-- ${tmpl} --"

  # ── File exists ──────────────────────────────────────────────────
  if [[ -f "$filepath" ]]; then
    pass "file exists"
  else
    fail "file does not exist"
    echo ""
    continue
  fi

  # ── YAML frontmatter ─────────────────────────────────────────────
  first_line="$(head -n 1 "$filepath")"
  if [[ "$first_line" == "---" ]]; then
    pass "starts with ---"
  else
    fail "does not start with ---"
  fi

  # Find the closing --- (second occurrence, skipping line 1)
  closing_line="$(tail -n +2 "$filepath" | grep -n '^---$' | head -n 1 | cut -d: -f1)"
  if [[ -n "$closing_line" ]]; then
    pass "has closing ---"
  else
    fail "missing closing ---"
    echo ""
    continue
  fi

  # Extract frontmatter (between line 2 and the closing ---)
  frontmatter="$(tail -n +2 "$filepath" | head -n "$(( closing_line - 1 ))")"

  # ── Required frontmatter fields ──────────────────────────────────
  for field in "${FRONTMATTER_FIELDS[@]}"; do
    if echo "$frontmatter" | grep -qE "^${field}:"; then
      pass "frontmatter field '${field}' present"
    else
      fail "frontmatter field '${field}' missing"
    fi
  done

  # ── Required sections ────────────────────────────────────────────
  body="$(tail -n +"$(( closing_line + 2 ))" "$filepath")"

  for section in "${REQUIRED_SECTIONS[@]}"; do
    if echo "$body" | grep -qE "^## ${section}"; then
      pass "section '${section}' present"
    else
      fail "section '${section}' missing"
    fi
  done

  echo ""
done

# ── Summary ──────────────────────────────────────────────────────────

echo "=== Results: ${PASS} passed, ${FAIL} failed ==="

if [[ $FAIL -gt 0 ]]; then
  exit 1
fi
