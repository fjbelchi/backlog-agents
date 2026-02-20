#!/usr/bin/env python3
"""Deterministic prescan for backlog-audit. Scans full project for code health issues.

Usage:
    python scripts/ops/audit_prescan.py --config backlog.config.json --mode full
    python scripts/ops/audit_prescan.py --config backlog.config.json --checks secrets,todos,debug
"""
from __future__ import annotations
import argparse, hashlib, json, os, re, subprocess, sys
from pathlib import Path
from collections import defaultdict


ALL_CHECKS = [
    "secrets", "todos", "debug", "mock_hardcoded", "long_functions",
    "dependency_vulns", "coverage_gaps", "dead_code", "complexity",
    "duplicate_code", "file_size_deps", "type_safety"
]


def get_project_files(extensions: list[str], exclude_dirs: list[str], root: str = ".") -> list[str]:
    """Walk project tree, return files matching extensions, skipping exclude_dirs."""
    files = []
    exclude_set = set(exclude_dirs)
    for dirpath, dirnames, filenames in os.walk(root):
        # Skip excluded directories
        dirnames[:] = [d for d in dirnames if d not in exclude_set]
        for fname in filenames:
            if any(fname.endswith(ext) for ext in extensions):
                files.append(os.path.join(dirpath, fname))
    return files


def grep_files(files, pattern, label, category, dimension, severity="medium", exclude_patterns=None):
    """Grep files for a regex pattern, return findings."""
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
                        "check": label,
                        "category": category,
                        "dimension": dimension,
                        "severity": severity,
                        "file": fpath,
                        "line": i,
                        "description": f"{label}: {line.strip()[:120]}",
                        "source": "prescan",
                    })
        except Exception:
            pass
    return findings


# CHECK 1: Secrets detection
def check_secrets(files):
    return grep_files(
        files,
        r'(password|api_key|secret|token|private_key)\s*[=:]\s*["\'][^"\']{4,}["\']',
        "Hardcoded secret", "security", "security",
        severity="high",
        exclude_patterns=["test", "spec", ".example", ".env", "mock", "fixture"]
    )


# CHECK 2: TODOs/FIXMEs
def check_todos(files):
    return grep_files(
        files,
        r'\b(TODO|FIXME|HACK|XXX)\b',
        "TODO/FIXME", "techDebt", "hygiene"
    )


# CHECK 3: Debug leftovers
def check_debug_leftovers(files):
    return grep_files(
        files,
        r'\b(console\.log|console\.debug|print\(|debugger\b)',
        "Debug statement", "techDebt", "hygiene",
        exclude_patterns=["test", "spec", "logger", "__test__"]
    )


# CHECK 4: Mock/hardcoded data
def check_mock_hardcoded(files):
    findings = []
    # Hardcoded IPs
    findings += grep_files(
        files,
        r'\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b',
        "Hardcoded IP", "bugs", "bugs",
        exclude_patterns=["test", "spec", "config", ".env", "fixture", "mock"]
    )
    # Mock/fake/stub values in production
    findings += grep_files(
        files,
        r'\b(mock|fake|stub|dummy|placeholder)\b.*[=:]',
        "Mock/stub data", "bugs", "bugs",
        exclude_patterns=["test", "spec", "__test__", "fixture", "mock", ".test.", ".spec."]
    )
    # Hardcoded ports (common non-standard)
    findings += grep_files(
        files,
        r':\s*(3000|3001|8080|8000|5000|9090)\b',
        "Hardcoded port", "bugs", "bugs",
        severity="low",
        exclude_patterns=["test", "spec", "config", ".env", "docker", "Dockerfile"]
    )
    return findings


# CHECK 5: Long functions
def check_long_functions(files, max_lines=80):
    """Detect functions exceeding max_lines. Reuses sentinel_prescan logic."""
    findings = []
    func_patterns = [
        r'^\s*(def |async def |function |const \w+ = \(|func \w+\(|export (async )?function )',
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
                            "check": "long_function",
                            "category": "techDebt",
                            "dimension": "architecture",
                            "severity": "low",
                            "file": fpath,
                            "line": func_start,
                            "description": f"Long function '{func_name}' ({i - func_start} lines > {max_lines})",
                            "source": "prescan",
                        })
                    in_func, func_start = True, i
                    func_name = line.strip()[:60]
            # Check last function in file (no subsequent header to trigger the check)
            if in_func and (len(lines) + 1 - func_start) > max_lines:
                findings.append({
                    "check": "long_function",
                    "category": "techDebt",
                    "dimension": "architecture",
                    "severity": "low",
                    "file": fpath,
                    "line": func_start,
                    "description": f"Long function '{func_name}' ({len(lines) + 1 - func_start} lines > {max_lines})",
                    "source": "prescan",
                })
        except Exception:
            pass
    return findings


# CHECK 6: Dependency vulnerabilities
def check_dependency_vulns():
    """Run npm audit or pip audit, parse JSON output."""
    findings = []
    # npm audit
    if Path("package.json").exists():
        try:
            result = subprocess.run(
                ["npm", "audit", "--json"],
                capture_output=True, text=True, timeout=60
            )
            if result.returncode != 0 and result.stdout:
                data = json.loads(result.stdout)
                vulns = data.get("vulnerabilities", {})
                for name, info in vulns.items():
                    sev = info.get("severity", "medium")
                    severity_map = {"critical": "critical", "high": "high", "moderate": "medium", "low": "low"}
                    findings.append({
                        "check": "dependency_vuln",
                        "category": "security",
                        "dimension": "security",
                        "severity": severity_map.get(sev, "medium"),
                        "file": "package.json",
                        "line": 0,
                        "description": f"Vulnerable dependency: {name} ({sev}) — {info.get('title', 'N/A')[:80]}",
                        "source": "prescan",
                    })
        except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
            pass
    # pip audit (if requirements.txt or pyproject.toml exists)
    if Path("requirements.txt").exists() or Path("pyproject.toml").exists():
        try:
            result = subprocess.run(
                ["pip", "audit", "--format=json"],
                capture_output=True, text=True, timeout=60
            )
            if result.stdout:
                data = json.loads(result.stdout)
                for vuln in data.get("vulnerabilities", []):
                    findings.append({
                        "check": "dependency_vuln",
                        "category": "security",
                        "dimension": "security",
                        "severity": "high",
                        "file": "requirements.txt",
                        "line": 0,
                        "description": f"Vulnerable dependency: {vuln.get('name', '?')} — {vuln.get('description', '')[:80]}",
                        "source": "prescan",
                    })
        except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
            pass
    return findings


# CHECK 7: Coverage gaps
def check_coverage_gaps(config):
    """Flag files below coverageThreshold from istanbul or pytest-cov reports."""
    findings = []
    threshold = config.get("audit", {}).get("prescan", {}).get("coverageThreshold", 80)
    # Istanbul (JS/TS)
    istanbul_path = Path("coverage/coverage-summary.json")
    if istanbul_path.exists():
        try:
            data = json.loads(istanbul_path.read_text(encoding="utf-8"))
            for fpath, metrics in data.items():
                if fpath == "total":
                    continue
                for metric in ("lines", "branches", "functions"):
                    pct = metrics.get(metric, {}).get("pct", 100)
                    if pct < threshold:
                        findings.append({
                            "check": "coverage_gap", "category": "tests",
                            "dimension": "tests", "severity": "medium",
                            "file": fpath, "line": 0,
                            "description": f"Coverage gap: {metric} {pct}% < {threshold}% threshold",
                            "source": "prescan",
                        })
        except (json.JSONDecodeError, KeyError):
            pass
    # pytest-cov
    pytestcov_path = Path("htmlcov/status.json")
    if pytestcov_path.exists():
        try:
            data = json.loads(pytestcov_path.read_text(encoding="utf-8"))
            for fpath, info in data.get("files", {}).items():
                pct = info.get("summary", {}).get("percent_covered", 100)
                if pct < threshold:
                    findings.append({
                        "check": "coverage_gap", "category": "tests",
                        "dimension": "tests", "severity": "medium",
                        "file": fpath, "line": 0,
                        "description": f"Coverage gap: {pct:.1f}% < {threshold}% threshold",
                        "source": "prescan",
                    })
        except (json.JSONDecodeError, KeyError):
            pass
    return findings


# CHECK 8: Dead imports
def _extract_imports(line):
    """Extract imported names from a single line."""
    # Python: from X import Y, Z
    m = re.match(r'^\s*from\s+\S+\s+import\s+(.+)', line)
    if m:
        return [n.strip().split(" as ")[-1].strip() for n in m.group(1).split(",")]
    # Python: import X, Y
    m = re.match(r'^\s*import\s+(.+)', line)
    if m and "from" not in line:
        return [n.strip().split(" as ")[-1].strip().split(".")[-1] for n in m.group(1).split(",")]
    # JS/TS: import { X, Y } from '...'
    m = re.match(r'^\s*import\s+\{([^}]+)\}\s+from\s+', line)
    if m:
        return [n.strip().split(" as ")[-1].strip() for n in m.group(1).split(",")]
    return []


def check_dead_code(files):
    """Detect imports that are never referenced after the import line."""
    findings = []
    for fpath in files:
        if fpath.endswith("__init__.py"):
            continue
        try:
            lines = Path(fpath).read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            continue
        for i, line in enumerate(lines):
            names = _extract_imports(line)
            rest = "\n".join(lines[i + 1:])
            for name in names:
                if not name or len(name) < 2:
                    continue
                if not re.search(r'\b' + re.escape(name) + r'\b', rest):
                    findings.append({
                        "check": "dead_import", "category": "techDebt",
                        "dimension": "hygiene", "severity": "low",
                        "file": fpath, "line": i + 1,
                        "description": f"Unused import: '{name}'",
                        "source": "prescan",
                    })
    return findings


# CHECK 9: Cyclomatic complexity
def check_cyclomatic_complexity(files, threshold=10):
    """Count branching keywords per function; flag if above threshold."""
    findings = []
    func_patterns = [
        r'^\s*(def |async def |function |const \w+ = \(|func \w+\(|export (async )?function )',
    ]
    branch_re = re.compile(
        r'\b(if|elif|else|for|while|case|catch)\b|&&|\|\||\?(?!=)'
    )
    for fpath in files:
        try:
            lines = Path(fpath).read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            continue
        func_name, func_start, complexity = "", 0, 1
        in_func = False
        for i, line in enumerate(lines, 1):
            is_header = any(re.match(p, line) for p in func_patterns)
            if is_header:
                if in_func and complexity > threshold:
                    findings.append({
                        "check": "cyclomatic_complexity", "category": "techDebt",
                        "dimension": "architecture", "severity": "medium",
                        "file": fpath, "line": func_start,
                        "description": f"High complexity ({complexity}) in '{func_name}'",
                        "source": "prescan",
                    })
                in_func, func_start, complexity = True, i, 1
                func_name = line.strip()[:60]
            elif in_func:
                complexity += len(branch_re.findall(line))
        # Last function
        if in_func and complexity > threshold:
            findings.append({
                "check": "cyclomatic_complexity", "category": "techDebt",
                "dimension": "architecture", "severity": "medium",
                "file": fpath, "line": func_start,
                "description": f"High complexity ({complexity}) in '{func_name}'",
                "source": "prescan",
            })
    return findings


# CHECK 10: Duplicate code blocks
def _normalize_lines(lines):
    """Strip whitespace, skip blanks and comment-only lines."""
    result = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "//", "/*", "*")):
            continue
        result.append(stripped)
    return result


def check_duplicate_code(files):
    """Sliding-window hash to detect duplicate 10-line blocks across files."""
    findings = []
    window_size = 10
    hash_map = defaultdict(list)  # hash -> [(file, start_line)]
    for fpath in files:
        try:
            raw_lines = Path(fpath).read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            continue
        normed = _normalize_lines(raw_lines)
        for i in range(len(normed) - window_size + 1):
            block = "\n".join(normed[i:i + window_size])
            h = hashlib.md5(block.encode()).hexdigest()
            hash_map[h].append((fpath, i + 1))
    count = 0
    for h, locations in hash_map.items():
        unique_files = set(loc[0] for loc in locations)
        if len(unique_files) < 2:
            continue
        if count >= 20:
            break
        count += 1
        for fpath, line_num in locations[:2]:
            findings.append({
                "check": "duplicate_code", "category": "techDebt",
                "dimension": "hygiene", "severity": "low",
                "file": fpath, "line": line_num,
                "description": f"Duplicate code block ({window_size} lines) found in {len(unique_files)} files",
                "source": "prescan",
            })
    return findings


# CHECK 11: File size + circular dependencies
def _extract_import_paths(fpath, lines):
    """Extract imported module paths from file lines."""
    paths = []
    for line in lines:
        # Python: import X  /  from X import Y
        m = re.match(r'^\s*(?:from|import)\s+([\w.]+)', line)
        if m:
            paths.append(m.group(1))
            continue
        # JS/TS: import ... from 'path'  /  require('path')
        m = re.search(r'''(?:from|require\()\s*['"]([^'"]+)['"]''', line)
        if m:
            paths.append(m.group(1))
    return paths


def _detect_cycles(graph):
    """DFS cycle detection, returns set of files in cycles."""
    in_cycle = set()
    visited, on_stack = set(), set()
    path = []

    def dfs(node):
        visited.add(node)
        on_stack.add(node)
        path.append(node)
        for neighbor in graph.get(node, []):
            if neighbor not in visited:
                dfs(neighbor)
            elif neighbor in on_stack:
                idx = path.index(neighbor)
                for n in path[idx:]:
                    in_cycle.add(n)
        path.pop()
        on_stack.discard(node)

    for node in graph:
        if node not in visited:
            dfs(node)
    return in_cycle


def check_file_size_circular_deps(files):
    """Flag large files (>500 lines) and circular import dependencies."""
    findings = []
    graph = defaultdict(list)
    file_set = set(files)
    for fpath in files:
        try:
            lines = Path(fpath).read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            continue
        if len(lines) > 500:
            findings.append({
                "check": "large_file", "category": "techDebt",
                "dimension": "architecture", "severity": "low",
                "file": fpath, "line": 0,
                "description": f"Large file: {len(lines)} lines (> 500)",
                "source": "prescan",
            })
        imports = _extract_import_paths(fpath, lines)
        for imp in imports:
            # Resolve relative path heuristic
            base = os.path.dirname(fpath)
            candidate = os.path.normpath(os.path.join(base, imp.replace(".", "/")))
            for ext in ("", ".py", ".ts", ".tsx", ".js", ".jsx"):
                full = candidate + ext
                if full in file_set:
                    graph[fpath].append(full)
                    break
    cycle_files = _detect_cycles(graph)
    for fpath in cycle_files:
        findings.append({
            "check": "circular_dependency", "category": "architecture",
            "dimension": "architecture", "severity": "medium",
            "file": fpath, "line": 0,
            "description": f"File participates in a circular import dependency",
            "source": "prescan",
        })
    return findings


# CHECK 12: TypeScript type safety
def check_type_safety(files):
    """Flag unsafe type patterns in .ts/.tsx files."""
    findings = []
    ts_files = [f for f in files if f.endswith((".ts", ".tsx"))]
    any_re = re.compile(r':\s*any\b|as\s+any\b')
    as_unknown_re = re.compile(r'as\s+unknown\s+as\b')
    assertion_re = re.compile(r'\bas\s+(?!const\b)\w+')
    non_null_re = re.compile(r'!\.|!;')
    for fpath in ts_files:
        try:
            lines = Path(fpath).read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            continue
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("//") or stripped.startswith("*"):
                continue
            if any_re.search(line):
                findings.append({
                    "check": "type_safety_any", "category": "bugs",
                    "dimension": "bugs", "severity": "medium",
                    "file": fpath, "line": i,
                    "description": f"Unsafe 'any' usage: {stripped[:100]}",
                    "source": "prescan",
                })
            elif as_unknown_re.search(line):
                findings.append({
                    "check": "type_safety_assertion", "category": "bugs",
                    "dimension": "bugs", "severity": "low",
                    "file": fpath, "line": i,
                    "description": f"Double assertion (as unknown as): {stripped[:100]}",
                    "source": "prescan",
                })
            elif non_null_re.search(line):
                findings.append({
                    "check": "type_safety_assertion", "category": "bugs",
                    "dimension": "bugs", "severity": "low",
                    "file": fpath, "line": i,
                    "description": f"Non-null assertion: {stripped[:100]}",
                    "source": "prescan",
                })
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit deterministic prescan")
    parser.add_argument("--config", default="backlog.config.json")
    parser.add_argument("--mode", choices=["default", "full"], default="full")
    parser.add_argument("--checks", default=",".join(ALL_CHECKS),
                        help="Comma-separated list of checks to run")
    args = parser.parse_args()

    config = {}
    try:
        config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    except Exception as e:
        print(f"Warning: could not read config: {e}", file=sys.stderr)

    audit_cfg = config.get("audit", {})
    if not audit_cfg.get("enabled", True):
        print(json.dumps({"scanned_files": 0, "findings": [], "summary": {}}))
        return 0

    prescan_cfg = audit_cfg.get("prescan", {})
    extensions = prescan_cfg.get("extensions", [".ts", ".tsx", ".js", ".jsx", ".py"])
    exclude_dirs = prescan_cfg.get("excludeDirs", ["node_modules", "dist", "coverage", ".next", "__pycache__", ".git"])
    max_func_lines = prescan_cfg.get("maxFunctionLines", 80)
    complexity_threshold = prescan_cfg.get("complexityThreshold", 10)

    enabled_checks = set(args.checks.split(","))
    files = get_project_files(extensions, exclude_dirs)

    findings = []
    if "secrets" in enabled_checks:
        findings += check_secrets(files)
    if "todos" in enabled_checks:
        findings += check_todos(files)
    if "debug" in enabled_checks:
        findings += check_debug_leftovers(files)
    if "mock_hardcoded" in enabled_checks:
        findings += check_mock_hardcoded(files)
    if "long_functions" in enabled_checks:
        findings += check_long_functions(files, max_func_lines)
    if "dependency_vulns" in enabled_checks:
        findings += check_dependency_vulns()
    if "coverage_gaps" in enabled_checks:
        findings += check_coverage_gaps(config)
    if "dead_code" in enabled_checks:
        findings += check_dead_code(files)
    if "complexity" in enabled_checks:
        findings += check_cyclomatic_complexity(files, complexity_threshold)
    if "duplicate_code" in enabled_checks:
        findings += check_duplicate_code(files)
    if "file_size_deps" in enabled_checks:
        findings += check_file_size_circular_deps(files)
    if "type_safety" in enabled_checks:
        findings += check_type_safety(files)

    summary = defaultdict(int)
    for f in findings:
        summary[f["severity"]] += 1

    output = {
        "scanned_files": len(files),
        "findings": findings,
        "summary": dict(summary),
    }
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
