# tests/test_lint_fixer.py
import subprocess, json, sys, os, tempfile

SCRIPT = os.path.join(os.path.dirname(__file__), "../scripts/implementer/lint_fixer.py")

# Simulate eslint JSON output
ESLINT_OUTPUT = json.dumps([{
    "filePath": "/project/src/auth.ts",
    "messages": [{
        "ruleId": "no-unused-vars",
        "severity": 2,
        "message": "'token' is defined but never used.",
        "line": 12,
        "column": 7
    }],
    "errorCount": 1,
    "warningCount": 0
}])

def run_with_output(lint_output, format_flag="eslint-json"):
    result = subprocess.run(
        [sys.executable, SCRIPT, "--format", format_flag],
        input=lint_output, capture_output=True, text=True
    )
    return result

def test_parses_eslint_json_errors():
    r = run_with_output(ESLINT_OUTPUT)
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert data["clean"] is False
    assert len(data["errors"]) == 1
    assert data["errors"][0]["rule"] == "no-unused-vars"
    assert data["errors"][0]["line"] == 12

def test_clean_output_when_no_errors():
    empty = json.dumps([{"filePath": "/f.ts", "messages": [], "errorCount": 0, "warningCount": 0}])
    r = run_with_output(empty)
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert data["clean"] is True
    assert data["errors"] == []

def test_tsc_format_parsing():
    tsc_output = "src/auth.ts(12,7): error TS2304: Cannot find name 'token'.\n"
    r = run_with_output(tsc_output, format_flag="tsc")
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert data["clean"] is False
    assert data["errors"][0]["file"] == "src/auth.ts"
    assert data["errors"][0]["line"] == 12

def test_ruff_format_parsing():
    ruff_output = "src/models.py:45:1: E501 line too long (120 > 88 characters)\n"
    r = run_with_output(ruff_output, format_flag="ruff")
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert data["clean"] is False
    assert data["errors"][0]["file"] == "src/models.py"
    assert data["errors"][0]["line"] == 45
    assert data["errors"][0]["rule"] == "E501"

def test_eslint_warnings_excluded():
    """Severity 1 (warning) should not appear in errors list."""
    warning_output = json.dumps([{
        "filePath": "/project/src/foo.ts",
        "messages": [{
            "ruleId": "no-console",
            "severity": 1,
            "message": "Unexpected console statement.",
            "line": 5,
            "column": 1
        }],
        "errorCount": 0,
        "warningCount": 1
    }])
    r = run_with_output(warning_output)
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert data["clean"] is True
    assert data["errors"] == []

def test_context_extracted_for_existing_file():
    """When file exists, context lines should be returned."""
    import tempfile, os
    # Create a real temp file with known content
    with tempfile.NamedTemporaryFile(mode='w', suffix='.ts', delete=False) as f:
        for i in range(20):
            f.write(f"line {i+1} content\n")
        path = f.name
    try:
        lint_output = json.dumps([{
            "filePath": path,
            "messages": [{
                "ruleId": "no-unused-vars",
                "severity": 2,
                "message": "unused",
                "line": 10,
                "column": 1
            }],
            "errorCount": 1,
            "warningCount": 0
        }])
        r = run_with_output(lint_output)
        data = json.loads(r.stdout)
        assert data["clean"] is False
        assert len(data["errors"][0]["context"]) > 0
        # Should have ~10 lines of context (±5 from line 10)
        assert len(data["errors"][0]["context"]) >= 5
    finally:
        os.unlink(path)

def test_context_empty_for_missing_file():
    """When file doesn't exist, context should be empty list (not an error)."""
    lint_output = json.dumps([{
        "filePath": "/nonexistent/path/file.ts",
        "messages": [{
            "ruleId": "no-unused-vars",
            "severity": 2,
            "message": "unused",
            "line": 5,
            "column": 1
        }],
        "errorCount": 1,
        "warningCount": 0
    }])
    r = run_with_output(lint_output)
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert data["clean"] is False
    assert data["errors"][0]["context"] == []
