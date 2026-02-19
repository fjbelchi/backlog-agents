#!/usr/bin/env python3
"""Validate ticket markdown file has key sections."""

from __future__ import annotations

import argparse
from pathlib import Path

REQUIRED = [
    "## Context",
    "## Description",
    "## Affected Files",
    "## Acceptance Criteria",
    "## Test Strategy",
    "## Dependencies",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("ticket_file")
    args = parser.parse_args()

    p = Path(args.ticket_file)
    if not p.exists():
        raise SystemExit(f"missing ticket file: {p}")

    text = p.read_text(encoding="utf-8")
    missing = [h for h in REQUIRED if h not in text]
    if missing:
        print("INVALID")
        for m in missing:
            print(f" - missing: {m}")
        return 1

    print("VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
