#!/usr/bin/env bash
set -euo pipefail

# ── Backlog Skills Installer ──────────────────────────────────────────
# Copies skill directories from this repo into a Claude skills folder.
#
# Usage:
#   ./install.sh                              # all skills → ~/.claude/skills/
#   ./install.sh --local                      # all skills → .claude/skills/
#   ./install.sh --skills init,ticket         # specific skills only
#   ./install.sh --force                      # overwrite without prompting
# ──────────────────────────────────────────────────────────────────────

ALL_SKILLS=(backlog-init backlog-ticket backlog-refinement backlog-implementer)

# ── Resolve source directory (where this script lives) ────────────────
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_SRC="${SOURCE_DIR}/skills"

if [[ ! -d "$SKILLS_SRC" ]]; then
  echo "Error: skills/ directory not found at ${SKILLS_SRC}" >&2
  exit 1
fi

# ── Defaults ──────────────────────────────────────────────────────────
TARGET_DIR="${HOME}/.claude/skills"
SELECTED_SKILLS=()
FORCE=false

# ── Parse arguments ───────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --local)
      TARGET_DIR="$(pwd)/.claude/skills"
      shift
      ;;
    --skills)
      if [[ -z "${2:-}" ]]; then
        echo "Error: --skills requires a comma-separated list" >&2
        exit 1
      fi
      IFS=',' read -ra RAW_SKILLS <<< "$2"
      for name in "${RAW_SKILLS[@]}"; do
        # Allow shorthand (e.g. "init" → "backlog-init")
        name="$(echo "$name" | xargs)"  # trim whitespace
        if [[ "$name" != backlog-* ]]; then
          name="backlog-${name}"
        fi
        # Validate
        found=false
        for valid in "${ALL_SKILLS[@]}"; do
          if [[ "$name" == "$valid" ]]; then
            found=true
            break
          fi
        done
        if ! $found; then
          echo "Error: unknown skill '${name}'" >&2
          echo "Available skills: ${ALL_SKILLS[*]}" >&2
          exit 1
        fi
        SELECTED_SKILLS+=("$name")
      done
      shift 2
      ;;
    --force)
      FORCE=true
      shift
      ;;
    -h|--help)
      echo "Usage: ./install.sh [OPTIONS]"
      echo ""
      echo "Options:"
      echo "  --local              Install to .claude/skills/ in current directory"
      echo "  --skills LIST        Comma-separated skills (init,ticket,refinement,implementer)"
      echo "  --force              Overwrite existing skills without prompting"
      echo "  -h, --help           Show this help message"
      echo ""
      echo "Available skills: ${ALL_SKILLS[*]}"
      exit 0
      ;;
    *)
      echo "Error: unknown option '${1}'" >&2
      echo "Run ./install.sh --help for usage." >&2
      exit 1
      ;;
  esac
done

# Default: install all skills
if [[ ${#SELECTED_SKILLS[@]} -eq 0 ]]; then
  SELECTED_SKILLS=("${ALL_SKILLS[@]}")
fi

# ── Create target directory ───────────────────────────────────────────
mkdir -p "$TARGET_DIR"

# ── Install each skill ────────────────────────────────────────────────
installed=()
skipped=()

for skill in "${SELECTED_SKILLS[@]}"; do
  src="${SKILLS_SRC}/${skill}"
  dest="${TARGET_DIR}/${skill}"

  if [[ ! -d "$src" ]]; then
    echo "Warning: source not found for ${skill}, skipping" >&2
    skipped+=("$skill")
    continue
  fi

  if [[ -d "$dest" ]]; then
    if $FORCE; then
      rm -rf "$dest"
    else
      read -rp "Skill '${skill}' already exists at ${dest}. Overwrite? [y/N] " answer
      case "$answer" in
        [yY]|[yY][eE][sS])
          rm -rf "$dest"
          ;;
        *)
          echo "  Skipped ${skill}"
          skipped+=("$skill")
          continue
          ;;
      esac
    fi
  fi

  cp -R "$src" "$dest"
  installed+=("$skill")
done

# ── Summary ───────────────────────────────────────────────────────────
echo ""
echo "── Install Summary ─────────────────────────────────"
echo "  Target: ${TARGET_DIR}"
echo ""

if [[ ${#installed[@]} -gt 0 ]]; then
  echo "  Installed (${#installed[@]}):"
  for s in "${installed[@]}"; do
    echo "    + ${s}"
  done
fi

if [[ ${#skipped[@]} -gt 0 ]]; then
  echo "  Skipped (${#skipped[@]}):"
  for s in "${skipped[@]}"; do
    echo "    - ${s}"
  done
fi

echo "────────────────────────────────────────────────────"
