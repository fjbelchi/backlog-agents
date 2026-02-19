#!/usr/bin/env python3
"""Deterministic pre-scan for backlog-sentinel. Runs lint, tests, and grep
patterns on HEAD-changed files. Returns JSON findings at $0 cost (no LLM).

Usage:
    python scripts/ops/sentinel_prescan.py
    python scripts/ops/sentinel_prescan.py --config path/to/backlog.config.json
"""

from __future__ import annotations
import argparse, json, os, re, subprocess, sys
from pathlib import Path


def get_changed_files() -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", "HEAD~1..HEAD"],
        capture_output=True, text=True
    )
    return [f for f in result.stdout.strip().splitlines() if f]


def run_cmd(cmd: str) -> tuple[int, str]:
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.returncode, result.stdout + result.stderr


def grep_files(files: list[str], pattern: str, label: str,
               category: str, exclude_patterns: list[str] | None = None) -> list[dict]:
    findings = []
    for fpath in files:
        if not Path(fpath).exists():
            continue
        if exclude_patterns and any(p in fpath for p in exclude_patterns):
            continue
        try:
            content = Path(fpath).read_text(encoding="utf-8", errors="ignore")
            for i, line in enumerate(content.splitlines(), 1):
                if re.search(pattern, line, re.IGNORECASE):
                    findings.append({
                        "category": category,
                        "severity": "medium",
                        "file": fpath,
                        "line": i,
                        "description": f"{label}: {line.strip()[:120]}",
                        "source": "prescan",
                    })
        except Exception:
            pass
    return findings


def check_long_functions(files: list[str], max_lines: int) -> list[dict]:
    findings = []
    func_patterns = [
        r"^\s*(def |async def |function |const \w+ = \(|func \w+\()",
    ]
    for fpath in files:
        if not Path(fpath).exists():
            continue
        try:
            lines = Path(fpath).read_text(encoding="utf-8", errors="ignore").splitlines()
            in_func, func_start, func_name = False, 0, ""
            for i, line in enumerate(lines, 1):
                if any(re.match(p, line) for p in func_patterns):
                    if in_func and (i - func_start) > max_lines:
                        findings.append({
                            "category": "techDebt",
                            "severity": "low",
                            "file": fpath,
                            "line": func_start,
                            "description": (
                                f"Long function '{func_name}' "
                                f"({i - func_start} lines > {max_lines})"
                            ),
                            "source": "prescan",
                        })
                    in_func, func_start = True, i
                    func_name = line.strip()[:60]
        except Exception:
            pass
    return findings


def run_quality_gates(config: dict) -> list[dict]:
    findings = []
    gates = config.get("qualityGates", {})
    prescan_cfg = config.get("sentinel", {}).get("prescan", {})

    for key, label, category in [
        ("lintCommand", "Lint error", "bug"),
        ("typeCheckCommand", "Type error", "bug"),
        ("testCommand", "Test failure", "bug"),
    ]:
        cmd = gates.get(key)
        if not cmd:
            continue
        if key == "lintCommand" and not prescan_cfg.get("runLinter", True):
            continue
        if key == "typeCheckCommand" and not prescan_cfg.get("runTypeCheck", True):
            continue
        if key == "testCommand" and not prescan_cfg.get("runTests", True):
            continue
        code, output = run_cmd(cmd)
        if code != 0:
            findings.append({
                "category": category,
                "severity": "high",
                "file": "project",
                "line": 0,
                "description": (
                    f"{label}: {cmd!r} exited {code}. "
                    f"Output: {output[:300]}"
                ),
                "source": "prescan",
            })
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Sentinel deterministic prescan")
    parser.add_argument("--config", default="backlog.config.json")
    args = parser.parse_args()

    config: dict = {}
    try:
        config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    except Exception as e:
        print(f"Warning: could not read config: {e}", file=sys.stderr)

    sentinel_cfg = config.get("sentinel", {})
    prescan_cfg = sentinel_cfg.get("prescan", {})
    changed_files = get_changed_files()

    findings: list[dict] = []

    # Quality gates (lint, typecheck, tests)
    findings += run_quality_gates(config)

    # Hardcoded secrets
    if prescan_cfg.get("detectHardcoded", True):
        findings += grep_files(
            changed_files,
            r'(password|api_key|secret|token|private_key)\s*=\s*["\'][^"\']{4,}["\']',
            "Possible hardcoded secret", "security",
            exclude_patterns=["test", "spec", ".example", ".env"]
        )

    # TODO/FIXME without ticket
    if prescan_cfg.get("detectTodos", True):
        findings += grep_files(
            changed_files,
            r'\b(TODO|FIXME|HACK|XXX)\b',
            "TODO/FIXME without ticket", "techDebt"
        )

    # console.log / print in production code
    findings += grep_files(
        changed_files,
        r'\b(console\.log|console\.debug|print\()',
        "Debug statement in production code", "techDebt",
        exclude_patterns=["test", "spec", "logger", "log."]
    )

    # Long functions
    max_lines = prescan_cfg.get("maxFunctionLines", 80)
    findings += check_long_functions(changed_files, max_lines)

    output = {
        "changed_files": changed_files,
        "findings": findings,
        "total": len(findings),
    }
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
