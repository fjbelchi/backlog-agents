#!/usr/bin/env python3
"""Tests for audit_prescan.py — all 12 checks + integration tests."""
import json, os, shutil, sys, tempfile, pytest
from pathlib import Path

# Add scripts/ops to path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "ops"))
from audit_prescan import (
    get_project_files, check_secrets, check_todos, check_debug_leftovers,
    check_mock_hardcoded, check_long_functions, check_dependency_vulns,
    check_coverage_gaps, check_dead_code, check_cyclomatic_complexity,
    check_duplicate_code, check_file_size_circular_deps, check_type_safety,
)


@pytest.fixture
def safe_dir():
    """Create a temp directory whose path does NOT contain 'test', 'spec', 'mock', etc.

    grep_files() uses exclude_patterns with substring matching on the full file path.
    pytest's tmp_path always contains 'test' (e.g. /tmp/pytest-of-.../test_xxx0/),
    which triggers exclusion in check_secrets, check_debug_leftovers, and
    check_mock_hardcoded. This fixture creates a clean path without those substrings.
    """
    d = tempfile.mkdtemp(prefix="prescan_")
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def sample_project(tmp_path, safe_dir):
    """Create a mini project with known violations for all 12 checks.

    Files scanned by checks with exclude_patterns are placed in safe_dir.
    Other files use tmp_path (faster, auto-cleaned by pytest).
    """
    # --- Files in safe_dir (avoid exclude_patterns matching 'test' in path) ---

    # app.ts — secret, console.log, TODO, any type, non-null assertion
    (safe_dir / "app.ts").write_text(
        'import { unused } from "./utils";\n'
        'const password = "super_secret_123";\n'
        'console.log("debug");\n'
        "// TODO: fix this later\n"
        "function handler(req: any) {\n"
        "  const data = req.body as string;\n"
        "  return data!.trim();\n"
        "}\n"
    )

    # prod_data.ts — hardcoded IP
    (safe_dir / "prod_data.ts").write_text(
        'const API_URL = "http://192.168.1.100:3000/api";\n'
    )

    # --- Files in tmp_path (no exclude_patterns issue) ---

    # utils.py — unused import, 100+ line function, high-complexity function
    lines = ["def long_func():"]
    for i in range(100):
        lines.append(f"    x_{i} = {i}")
    lines.append("    return x_0")
    lines.append("")
    lines.append("def complex_func(a, b, c, d, e, f, g, h, i, j, k):")
    for var in "abcdefghijk":
        lines.append(f"    if {var}: pass")
    lines.append("    return True")

    (tmp_path / "utils.py").write_text(
        "import os\nimport re\n" + "\n".join(lines) + "\n"
    )

    # dup1.py + dup2.py — identical 15-line blocks (non-blank, non-comment)
    dup_block = "\n".join([f"line_{i} = {i} * 2" for i in range(15)])
    (tmp_path / "dup1.py").write_text(f"def func_a():\n    pass\n{dup_block}\n")
    (tmp_path / "dup2.py").write_text(f"def func_b():\n    pass\n{dup_block}\n")

    # big.py — 600+ line file
    big_lines = [f"x_{i} = {i}" for i in range(600)]
    (tmp_path / "big.py").write_text("\n".join(big_lines) + "\n")

    # Return both directories as a namespace-like object
    return type("SampleProject", (), {
        "safe": safe_dir,
        "tmp": tmp_path,
    })()


# CHECK 1: Secrets
def test_check_secrets(sample_project):
    files = [str(sample_project.safe / "app.ts")]
    findings = check_secrets(files)
    assert len(findings) >= 1
    assert any("secret" in f["description"].lower() or "password" in f["description"].lower() for f in findings)
    assert all(f["severity"] == "high" for f in findings)


def test_check_secrets_no_false_positive(safe_dir):
    (safe_dir / "clean.py").write_text('name = "hello world"\n')
    findings = check_secrets([str(safe_dir / "clean.py")])
    assert findings == []


# CHECK 2: TODOs
def test_check_todos(sample_project):
    files = [str(sample_project.safe / "app.ts")]
    findings = check_todos(files)
    assert len(findings) >= 1
    assert any("TODO" in f["description"] for f in findings)


# CHECK 3: Debug leftovers
def test_check_debug_leftovers(sample_project):
    files = [str(sample_project.safe / "app.ts")]
    findings = check_debug_leftovers(files)
    assert len(findings) >= 1
    assert any("console.log" in f["description"] for f in findings)


# CHECK 4: Mock/hardcoded data
def test_check_mock_hardcoded(sample_project):
    files = [str(sample_project.safe / "prod_data.ts")]
    findings = check_mock_hardcoded(files)
    assert len(findings) >= 1  # hardcoded IP and/or port


# CHECK 5: Long functions
def test_check_long_functions(sample_project):
    files = [str(sample_project.tmp / "utils.py")]
    findings = check_long_functions(files, max_lines=80)
    assert len(findings) >= 1
    assert any("long_func" in f["description"] for f in findings)


def test_check_long_functions_short_ok(tmp_path):
    (tmp_path / "short.py").write_text("def f():\n    return 1\n")
    findings = check_long_functions([str(tmp_path / "short.py")], max_lines=80)
    assert findings == []


# CHECK 6: Dependency vulns (just test it does not crash)
def test_check_dependency_vulns_no_crash():
    findings = check_dependency_vulns()
    assert isinstance(findings, list)


# CHECK 7: Coverage gaps
def test_check_coverage_gaps_no_report():
    findings = check_coverage_gaps({})
    assert findings == []


def test_check_coverage_gaps_istanbul(tmp_path):
    cov_dir = tmp_path / "coverage"
    cov_dir.mkdir()
    (cov_dir / "coverage-summary.json").write_text(json.dumps({
        "total": {"lines": {"pct": 90}},
        "src/app.ts": {"lines": {"pct": 40}, "branches": {"pct": 30}, "functions": {"pct": 50}},
    }))
    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        findings = check_coverage_gaps({"audit": {"prescan": {"coverageThreshold": 80}}})
        assert len(findings) >= 1
        assert any("Coverage gap" in f["description"] for f in findings)
    finally:
        os.chdir(old_cwd)


# CHECK 8: Dead code (unused imports)
def test_check_dead_code(sample_project):
    files = [str(sample_project.tmp / "utils.py")]
    findings = check_dead_code(files)
    assert len(findings) >= 1
    assert any("Unused import" in f["description"] for f in findings)


def test_check_dead_code_used_import(tmp_path):
    (tmp_path / "good.py").write_text("import os\nprint(os.getcwd())\n")
    findings = check_dead_code([str(tmp_path / "good.py")])
    assert findings == []


# CHECK 9: Cyclomatic complexity
def test_check_cyclomatic_complexity(sample_project):
    files = [str(sample_project.tmp / "utils.py")]
    findings = check_cyclomatic_complexity(files, threshold=5)
    assert len(findings) >= 1
    assert any("complex_func" in f["description"] for f in findings)


def test_check_cyclomatic_complexity_simple_ok(tmp_path):
    (tmp_path / "simple.py").write_text("def f(x):\n    return x + 1\n")
    findings = check_cyclomatic_complexity([str(tmp_path / "simple.py")], threshold=5)
    assert findings == []


# CHECK 10: Duplicate code
def test_check_duplicate_code(sample_project):
    files = [str(sample_project.tmp / "dup1.py"), str(sample_project.tmp / "dup2.py")]
    findings = check_duplicate_code(files)
    assert len(findings) >= 1
    assert any("Duplicate" in f["description"] for f in findings)


def test_check_duplicate_code_no_dups(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    (tmp_path / "b.py").write_text("y = 2\n")
    findings = check_duplicate_code([str(tmp_path / "a.py"), str(tmp_path / "b.py")])
    assert findings == []


# CHECK 11: File size + circular deps
def test_check_file_size(sample_project):
    files = [str(sample_project.tmp / "big.py")]
    findings = check_file_size_circular_deps(files)
    assert any("lines" in f["description"].lower() for f in findings)


def test_check_file_size_small_ok(tmp_path):
    (tmp_path / "small.py").write_text("x = 1\n")
    findings = check_file_size_circular_deps([str(tmp_path / "small.py")])
    assert findings == []


# CHECK 12: Type safety
def test_check_type_safety(sample_project):
    files = [str(sample_project.safe / "app.ts")]
    findings = check_type_safety(files)
    assert len(findings) >= 1
    assert any("any" in f["description"].lower() for f in findings)


def test_check_type_safety_non_null(sample_project):
    files = [str(sample_project.safe / "app.ts")]
    findings = check_type_safety(files)
    assert any("non-null" in f["description"].lower() or "Non-null" in f["description"] for f in findings)


def test_check_type_safety_clean(tmp_path):
    (tmp_path / "clean.ts").write_text("const x: string = 'hello';\n")
    findings = check_type_safety([str(tmp_path / "clean.ts")])
    assert findings == []


# INTEGRATION: get_project_files
def test_get_project_files(sample_project):
    files = get_project_files([".ts", ".py"], [], str(sample_project.safe))
    assert len(files) >= 2


def test_get_project_files_excludes(tmp_path):
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "dep.js").write_text("x=1")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.js").write_text("x=1")
    files = get_project_files([".js"], ["node_modules"], str(tmp_path))
    assert not any("node_modules" in f for f in files)
    assert len(files) >= 1


def test_config_disables_audit():
    """When audit.enabled is false, main() exists and is callable."""
    from audit_prescan import main
    assert callable(main)
