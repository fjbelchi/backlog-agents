#!/usr/bin/env python3
"""Very lightweight duplicate detection using title token overlap."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


def tokens(s: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", s.lower()))


def extract_title(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("title:"):
            return line.split(":", 1)[1].strip()
    return ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("ticket_file")
    parser.add_argument("--pending-dir", default="backlog/data/pending")
    parser.add_argument("--threshold", type=float, default=0.6)
    args = parser.parse_args()

    tpath = Path(args.ticket_file)
    pdir = Path(args.pending_dir)
    if not tpath.exists() or not pdir.exists():
        return 0

    t_tokens = tokens(extract_title(tpath.read_text(encoding="utf-8")))
    if not t_tokens:
        return 0

    for other in pdir.glob("*.md"):
        if other.resolve() == tpath.resolve():
            continue
        o_tokens = tokens(extract_title(other.read_text(encoding="utf-8")))
        if not o_tokens:
            continue
        score = len(t_tokens & o_tokens) / max(1, len(t_tokens | o_tokens))
        if score >= args.threshold:
            print(f"{other}: overlap={score:.2f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
