#!/usr/bin/env python3
"""Check prompt manifest entries for prefix consistency hints."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args()

    path = Path(args.manifest)
    if not path.exists():
        raise SystemExit(f"manifest not found: {path}")

    doc = json.loads(path.read_text(encoding="utf-8"))
    prompts = doc.get("prompts", [])
    violations = []
    for p in prompts:
        if "stable_prefix" not in p:
            violations.append(f"missing stable_prefix for id={p.get('id','unknown')}")

    if violations:
        print("PROMPT PREFIX VIOLATIONS")
        for v in violations:
            print(f" - {v}")
        return 1

    print("Prompt prefix manifest is valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
