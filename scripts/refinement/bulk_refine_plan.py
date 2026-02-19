#!/usr/bin/env python3
"""Bucket pending tickets by deterministic risk hints."""

from __future__ import annotations

import json
from pathlib import Path

PENDING = Path("backlog/data/pending")


def score(text: str) -> int:
    s = 0
    for k in ("critical", "security", "auth", "payment", "incident"):
        if k in text.lower():
            s += 1
    return s


def main() -> int:
    buckets = {"no-llm": [], "cheap-llm": [], "requires-frontier": []}
    if not PENDING.exists():
        print(json.dumps(buckets, indent=2))
        return 0

    for f in sorted(PENDING.glob("*.md")):
        txt = f.read_text(encoding="utf-8")
        sc = score(txt)
        if sc == 0:
            buckets["no-llm"].append(str(f))
        elif sc == 1:
            buckets["cheap-llm"].append(str(f))
        else:
            buckets["requires-frontier"].append(str(f))

    print(json.dumps(buckets, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
