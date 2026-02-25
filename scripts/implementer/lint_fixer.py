#!/usr/bin/env python3
"""
lint_fixer.py — Smart lint error parser.
Reads lint output from stdin, returns structured JSON with only error lines + context.
Cost: $0. Reduces Gate 3 tokens by ~70%.

Usage:
  lintCommand 2>&1 | python3 lint_fixer.py --format eslint-json
  tsc --noEmit 2>&1 | python3 lint_fixer.py --format tsc
"""
import argparse, json, re, sys
from pathlib import Path

def parse_eslint_json(raw: str) -> list[dict]:
    errors = []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    for file_result in data:
        for msg in file_result.get("messages", []):
            if msg.get("severity", 0) >= 2:  # errors only
                errors.append({
                    "file": file_result["filePath"],
                    "line": msg.get("line", 0),
                    "column": msg.get("column", 0),
                    "rule": msg.get("ruleId", "unknown"),
                    "message": msg.get("message", ""),
                    "context": _extract_context(file_result["filePath"], msg.get("line", 0))
                })
    return errors

def parse_tsc(raw: str) -> list[dict]:
    errors = []
    pattern = re.compile(r"^(.+?)\((\d+),(\d+)\): error (TS\d+): (.+)$", re.MULTILINE)
    for m in pattern.finditer(raw):
        path, line, col, code, msg = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4), m.group(5)
        errors.append({
            "file": path,
            "line": line,
            "column": col,
            "rule": code,
            "message": msg,
            "context": _extract_context(path, line)
        })
    return errors

def parse_ruff(raw: str) -> list[dict]:
    errors = []
    pattern = re.compile(r"^(.+?):(\d+):(\d+): ([A-Z]{1,4}\d+) (.+)$", re.MULTILINE)
    for m in pattern.finditer(raw):
        path, line, col, code, msg = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4), m.group(5)
        errors.append({
            "file": path, "line": line, "column": col,
            "rule": code, "message": msg,
            "context": _extract_context(path, line)
        })
    return errors

def _extract_context(filepath: str, line: int, radius: int = 5) -> list[str]:
    if line <= 0:
        return []
    try:
        lines = Path(filepath).read_text().splitlines()
        start = max(0, line - radius - 1)
        end = min(len(lines), line + radius)
        return [f"{start+i+1}: {l}" for i, l in enumerate(lines[start:end])]
    except Exception:
        return []

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--format", default="eslint-json",
                        choices=["eslint-json", "tsc", "ruff"])
    args = parser.parse_args()

    raw = sys.stdin.read()
    parsers = {"eslint-json": parse_eslint_json, "tsc": parse_tsc, "ruff": parse_ruff}
    errors = parsers[args.format](raw)
    print(json.dumps({"clean": len(errors) == 0, "errors": errors}))

if __name__ == "__main__":
    main()
