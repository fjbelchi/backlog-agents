#!/usr/bin/env python3
"""
diff_pattern_scanner.py — Regex-based high-risk pattern detector.
Scans git diff for patterns that require deeper Sonnet review.
Replaces Opus Gate 4b. Cost: $0.

Usage:
  git diff HEAD~1 | python3 diff_pattern_scanner.py
  python3 diff_pattern_scanner.py --diff path/to/file.diff
"""
import argparse, json, re, sys
from pathlib import Path

PATTERNS: dict[str, str] = {
    "auth":           r"jwt\.|bcrypt\.|session\.|\.token|oauth|password\s*=",
    "db_schema":      r"createIndex\b|migration|ALTER\s+TABLE|schema\.\w+\s*=",
    "serialization":  r"JSON\.parse\b|JSON\.stringify\b|Buffer\.from\b|\.encode\(",
    "error_handling": r"Promise\.all\b|Promise\.allSettled\b|\.catch\s*\(|retry\s*\(",
    "external_api":   r"fetch\s*\(|axios\.|http\.request\b|got\s*\(",
    "concurrency":    r"worker_threads|Promise\.race\b|mutex\b|semaphore\b",
}

def scan(diff_text: str) -> dict:
    # Only scan added lines (lines starting with +, excluding +++ header)
    added = "\n".join(
        line[1:] for line in diff_text.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )
    detected = [
        name for name, pattern in PATTERNS.items()
        if re.search(pattern, added)
    ]
    return {
        "detected": detected,
        "requires_high_risk_review": len(detected) > 0,
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--diff", help="Path to diff file (default: read stdin)")
    args = parser.parse_args()

    if args.diff:
        diff_text = Path(args.diff).read_text()
    else:
        diff_text = sys.stdin.read()

    print(json.dumps(scan(diff_text)))

if __name__ == "__main__":
    main()
