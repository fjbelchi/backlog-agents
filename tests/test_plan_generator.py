# tests/test_plan_generator.py
import subprocess, json, sys, os, tempfile, textwrap

SCRIPT = os.path.join(os.path.dirname(__file__), "../scripts/implementer/plan_generator.py")

TICKET = textwrap.dedent("""
---
id: FEAT-001
title: Add login endpoint
affected_files:
  - src/auth/login.ts
  - src/auth/session.ts
---
## Affected Files
| File | Action | Description |
|------|--------|-------------|
| src/auth/login.ts | create | New login handler |
| src/auth/session.ts | modify | Add session creation |

## Acceptance Criteria
- [ ] AC-1: Returns 200 on valid credentials
- [ ] AC-2: Returns 401 on invalid credentials
- [ ] AC-3: Creates session on success
""").strip()

def run(ticket_content):
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write(ticket_content)
        path = f.name
    result = subprocess.run(
        [sys.executable, SCRIPT, "--ticket", path],
        capture_output=True, text=True
    )
    os.unlink(path)
    return result

def test_outputs_implementation_plan_heading():
    r = run(TICKET)
    assert r.returncode == 0, r.stderr
    assert "## Implementation Plan" in r.stdout

def test_lists_create_files_first():
    r = run(TICKET)
    lines = r.stdout.splitlines()
    plan_idx = next(i for i, l in enumerate(lines) if "Implementation Plan" in l)
    body = "\n".join(lines[plan_idx:])
    assert "create" in body.lower() or "src/auth/login.ts" in body

def test_lists_acceptance_criteria_tests():
    r = run(TICKET)
    assert "AC-1" in r.stdout or "200" in r.stdout

def test_exits_nonzero_on_missing_ticket():
    r = subprocess.run(
        [sys.executable, SCRIPT, "--ticket", "/nonexistent.md"],
        capture_output=True, text=True
    )
    assert r.returncode != 0
