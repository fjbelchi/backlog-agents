#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT="${ROOT_DIR}/.backlog-ops/model-registry.json"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output)
      OUT="${2:-}"
      shift 2
      ;;
    *)
      echo "unknown option: $1" >&2
      exit 1
      ;;
  esac
done

mkdir -p "$(dirname "$OUT")"

cat > "$OUT" <<JSON
{
  "version": "1.0",
  "generated_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "aliases": {
    "cheap": [{"provider": "anthropic", "model": "claude-haiku-4-5"}],
    "balanced": [{"provider": "anthropic", "model": "claude-sonnet-4-6"}],
    "frontier": [{"provider": "anthropic", "model": "claude-opus-4-6"}],
    "code_frontier": [{"provider": "anthropic", "model": "claude-sonnet-4-6"}]
  },
  "raw_catalog": {
    "anthropic": [],
    "openai": [],
    "google": []
  }
}
JSON

echo "Wrote $OUT"
