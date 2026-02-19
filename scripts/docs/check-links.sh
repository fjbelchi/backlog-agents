#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

python3 - <<'PY' "$ROOT_DIR"
import re
import sys
from pathlib import Path

root = Path(sys.argv[1])
docs = root / "docs"
pattern = re.compile(r"\[[^\]]+\]\(([^)]+)\)")

errors = []
for md in docs.rglob("*.md"):
    text = md.read_text(encoding="utf-8")
    for target in pattern.findall(text):
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        target = target.split("#", 1)[0]
        if not target:
            continue
        resolved = (md.parent / target).resolve()
        if not resolved.exists():
            errors.append(f"{md.relative_to(root)} -> {target}")

if errors:
    print("Broken links:")
    for e in errors:
        print(f" - {e}")
    raise SystemExit(1)

print("All markdown links are valid.")
PY
