#!/usr/bin/env python3
"""Build a minimal deterministic context pack for ticket generation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("request", help="ticket request text")
    parser.add_argument("--output", default="tmp/context-pack.json")
    args = parser.parse_args()

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "request": args.request,
        "hints": ["Use existing templates", "Prefer deterministic checks first"],
    }
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(str(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
