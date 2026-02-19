#!/usr/bin/env python3
"""Produce a simple deterministic impact map from a file list."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+", help="changed files")
    args = parser.parse_args()

    impact = {"direct": [], "indirect": []}
    for f in args.files:
        p = Path(f)
        impact["direct"].append(str(p))
        if p.suffix in {".ts", ".js", ".py"}:
            impact["indirect"].append(f"tests for {p}")

    print(json.dumps(impact, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
