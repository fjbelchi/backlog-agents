#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP_SCRIPT="$(mktemp)"
trap 'rm -f "$TMP_SCRIPT"' EXIT

python3 - <<'PY' "$ROOT_DIR" "$TMP_SCRIPT"
import sys
from pathlib import Path

root = Path(sys.argv[1])
out = Path(sys.argv[2])

blocks = []
for md in (root / "docs").rglob("*.md"):
    lines = md.read_text(encoding="utf-8").splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line == "```bash verify":
            i += 1
            cmd_lines = []
            while i < len(lines) and lines[i].strip() != "```":
                cmd_lines.append(lines[i])
                i += 1
            if cmd_lines:
                blocks.append((md, cmd_lines))
        i += 1

with out.open("w", encoding="utf-8") as f:
    f.write("#!/usr/bin/env bash\nset -euo pipefail\n")
    f.write(f"cd '{root}'\n")
    for md, cmds in blocks:
        f.write(f"echo 'Running snippet from {md.relative_to(root)}'\n")
        for c in cmds:
            if c.strip():
                if "scripts/docs/verify-snippets.sh" in c:
                    # Avoid self-recursion when docs include the full validation chain.
                    continue
                f.write(c + "\n")

print(f"Collected {len(blocks)} verify block(s).")
PY

chmod +x "$TMP_SCRIPT"
"$TMP_SCRIPT"
