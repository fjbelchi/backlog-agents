#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
REGISTRY="${ROOT_DIR}/.backlog-ops/model-registry.json"
OUT="${ROOT_DIR}/docs/reference/model-table.md"

if [[ ! -f "$REGISTRY" ]]; then
  cat > "$REGISTRY" <<'JSON'
{
  "version": "1.0",
  "generated_at": "1970-01-01T00:00:00Z",
  "aliases": {
    "cheap": [{"provider": "anthropic", "model": "claude-haiku-4-5"}],
    "balanced": [{"provider": "anthropic", "model": "claude-sonnet-4-6"}],
    "frontier": [{"provider": "openai", "model": "gpt-5.2"}],
    "code_frontier": [{"provider": "openai", "model": "gpt-5-codex"}]
  },
  "raw_catalog": {"anthropic": [], "openai": [], "google": []}
}
JSON
fi

python3 - <<'PY' "$REGISTRY" "$OUT"
import json
import sys
from pathlib import Path

registry = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
out = Path(sys.argv[2])

lines = [
    "# Model Table",
    "",
    "Generated from `.backlog-ops/model-registry.json`.",
    "",
    "| Alias | Provider | Model |",
    "|---|---|---|",
]

for alias, entries in sorted(registry.get("aliases", {}).items()):
    if not entries:
      lines.append(f"| `{alias}` | - | - |")
      continue
    for e in entries:
      lines.append(f"| `{alias}` | `{e.get('provider','')}` | `{e.get('model','')}` |")

out.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"Generated {out}")
PY
