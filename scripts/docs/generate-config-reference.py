#!/usr/bin/env python3
"""Generate docs/reference/backlog-config-schema-generated.md from JSON schema."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "config" / "backlog.config.schema.json"
OUT_PATH = ROOT / "docs" / "reference" / "backlog-config-schema-generated.md"


def main() -> int:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    props = schema.get("properties", {})

    lines = [
        "# Backlog Config Schema (Generated)",
        "",
        f"Source: `{SCHEMA_PATH.relative_to(ROOT)}`",
        "",
        "| Key | Type | Required | Description |",
        "|---|---|---|---|",
    ]

    required = set(schema.get("required", []))
    for key in sorted(props):
        value = props[key]
        t = value.get("type", "object")
        desc = value.get("description", "")
        lines.append(f"| `{key}` | `{t}` | `{'yes' if key in required else 'no'}` | {desc} |")

    OUT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Generated {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
