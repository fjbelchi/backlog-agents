#!/usr/bin/env python3
"""Deterministic ticket complexity classifier.

Replaces Qwen3 LLM call with heuristic rules from SKILL.md.
Parses YAML-ish frontmatter from markdown ticket files.
Only uses Python stdlib — no external dependencies.

Usage:
    python3 classify.py ticket.md
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


# Tags that force complex classification regardless of file count
COMPLEX_TAGS = {"ARCH", "SECURITY", "SEC"}


def _parse_frontmatter(text: str) -> dict[str, object]:
    """Parse YAML-ish frontmatter from markdown text.

    Handles both inline lists ``[a, b]`` and multiline YAML lists
    with ``- item`` format. Returns a dict of string keys to values
    (strings or lists of strings). Missing frontmatter returns empty dict.
    """
    match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not match:
        return {}

    frontmatter: dict[str, object] = {}
    lines = match.group(1).split("\n")
    current_key: str | None = None
    current_list: list[str] | None = None

    for line in lines:
        # Multiline list continuation: "  - value"
        if current_key is not None and re.match(r"^\s+-\s+", line):
            item = re.sub(r"^\s+-\s+", "", line).strip()
            if item and current_list is not None:
                current_list.append(item)
            continue

        # New key: "key: value" — flush any pending list
        kv_match = re.match(r"^(\w[\w_]*):\s*(.*)", line)
        if kv_match:
            # Flush previous multiline list
            if current_key is not None and current_list is not None:
                frontmatter[current_key] = current_list

            key = kv_match.group(1)
            raw_value = kv_match.group(2).strip()

            # Inline list: [a, b, c]
            inline_match = re.match(r"^\[(.*)\]$", raw_value)
            if inline_match:
                items_str = inline_match.group(1).strip()
                if items_str:
                    items = [s.strip() for s in items_str.split(",") if s.strip()]
                else:
                    items = []
                frontmatter[key] = items
                current_key = None
                current_list = None
            elif raw_value == "":
                # Start of multiline list (value on next lines)
                current_key = key
                current_list = []
            else:
                # Scalar value
                frontmatter[key] = raw_value
                current_key = None
                current_list = None
        else:
            # Non-matching line ends any pending list
            if current_key is not None and current_list is not None:
                frontmatter[current_key] = current_list
                current_key = None
                current_list = None

    # Flush final pending list
    if current_key is not None and current_list is not None:
        frontmatter[current_key] = current_list

    return frontmatter


def classify_ticket(path: str) -> str:
    """Classify a ticket as trivial, simple, or complex.

    Rules (applied in order):
    1. If ticket has explicit ``complexity:`` in frontmatter, use that (manual override).
    2. If tags contain ARCH, SECURITY, or SEC, return complex.
    3. If depends_on is non-empty, return complex.
    4. If affected_files count <= 1, return trivial.
    5. If affected_files count <= 3, return simple.
    6. Otherwise, return complex.

    If the file cannot be read or has no frontmatter, returns complex
    as a safe default.
    """
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, IOError):
        return "complex"

    fm = _parse_frontmatter(text)
    if not fm:
        return "complex"

    # Rule 1: Manual override
    complexity = fm.get("complexity")
    if isinstance(complexity, str) and complexity in ("trivial", "simple", "complex"):
        return complexity

    # Rule 2: Complex tags
    tags = fm.get("tags", [])
    if isinstance(tags, list):
        upper_tags = {t.upper() if isinstance(t, str) else t for t in tags}
        if upper_tags & COMPLEX_TAGS:
            return "complex"

    # Rule 3: Dependencies
    depends_on = fm.get("depends_on", [])
    if isinstance(depends_on, list) and len(depends_on) > 0:
        return "complex"

    # Rules 4-6: File count
    affected_files = fm.get("affected_files", [])
    if isinstance(affected_files, list):
        count = len(affected_files)
    else:
        count = 0

    if count <= 1:
        return "trivial"
    if count <= 3:
        return "simple"
    return "complex"


def main() -> int:
    """CLI entry point: classify.py <ticket.md>."""
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <ticket.md>", file=sys.stderr)
        return 1

    result = classify_ticket(sys.argv[1])
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
