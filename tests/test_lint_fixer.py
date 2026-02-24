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
