#!/usr/bin/env python3
"""Grep/diff-based pre-review checklist. Stdlib only.

Usage: python3 pre_review.py --diff-file diff.txt [--test-output t.log] [--lint-output l.log]
"""
from __future__ import annotations
import argparse, json, re, sys  # noqa: E401
_DEBUG_RE = [re.compile(p) for p in [
    r"console\.log\b", r"\bprint\(", r"\bdebugger\b",
    r"\bTODO\b", r"\bFIXME\b", r"\bHACK\b",
]]
_MIXED_INDENT = re.compile(r"^\t+ | +\t")
_PY_FROM = re.compile(r"from\s+\S+\s+import\s+(.+)")
_PY_IMPORT = re.compile(r"import\s+(.+)")
_JS_NAMED = re.compile(r"import\s+\{([^}]+)\}\s+from")
_JS_DEFAULT = re.compile(r"import\s+(\w+)\s+from")


def _check_imports(added: list[str]) -> bool:
    names, rest = [], []
    for s in (l.strip() for l in added):
        m = _PY_FROM.match(s) or _JS_NAMED.match(s)
        if m:
            names += [n.strip().split(" as ")[-1].strip() for n in m.group(1).split(",")]
        elif (m := _JS_DEFAULT.match(s)):
            names.append(m.group(1))
        elif (m := _PY_IMPORT.match(s)):
            names += [n.strip().split(" as ")[-1].strip().split(".")[-1] for n in m.group(1).split(",")]
        else:
            rest.append(s)
    if not names:
        return True
    combined = " ".join(rest)
    return all((not n or n in combined) for n in names)


def run_pre_review(diff: str, test_output: str = "", lint_output: str = "") -> dict:
    """Run 5 checks: imports_ok, lint_clean, tests_pass, no_debug, format_ok."""
    issues: list[str] = []
    added = [l[1:] for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++")]
    imports_ok = _check_imports(added)
    if not imports_ok:
        issues.append("Unused import(s) detected in added lines")
    lint_clean = True
    if lint_output.strip() and not ("0 warnings" in lint_output or "0 errors" in lint_output):
        lint_clean = False; issues.append("Lint output indicates errors or warnings")
    tests_pass = True
    if test_output.strip() and ("failed" in test_output.lower() or "passed" not in test_output.lower()):
        tests_pass = False; issues.append("Test output indicates failures")
    no_debug = True
    for line in added:
        for p in _DEBUG_RE:
            if p.search(line):
                no_debug = False; issues.append(f"Debug artifact found: {p.pattern!r} in added line"); break
    format_ok = True
    for line in added:
        if _MIXED_INDENT.search(line):
            format_ok = False; issues.append("Mixed tabs and spaces in added line"); break
    return {"imports_ok": imports_ok, "lint_clean": lint_clean, "tests_pass": tests_pass,
            "no_debug": no_debug, "format_ok": format_ok, "issues": issues}


def main() -> int:
    ap = argparse.ArgumentParser(description="Pre-review checklist.")
    ap.add_argument("--diff-file", required=True)
    ap.add_argument("--test-output", default="")
    ap.add_argument("--lint-output", default="")
    a = ap.parse_args()
    try:
        diff = open(a.diff_file).read()
    except OSError as e:
        print(f"Error: {e}", file=sys.stderr); return 1
    to = open(a.test_output).read() if a.test_output else ""
    lo = open(a.lint_output).read() if a.lint_output else ""
    print(json.dumps(run_pre_review(diff, to, lo), indent=2)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
