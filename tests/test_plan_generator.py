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
    lines = [l for l in body.splitlines() if l.strip().startswith("-")]
    assert any("create" in l.lower() for l in lines), f"No create line found in: {body}"
    create_idx = next(i for i, l in enumerate(lines) if "create" in l.lower())
    modify_idx = next((i for i, l in enumerate(lines) if "modify" in l.lower()), len(lines))
    assert create_idx < modify_idx, "Create must appear before modify"

def test_lists_acceptance_criteria_tests():
    r = run(TICKET)
    assert "AC-1" in r.stdout, f"AC-1 not found in output: {r.stdout}"

def test_exits_nonzero_on_missing_ticket():
    r = subprocess.run(
        [sys.executable, SCRIPT, "--ticket", "/nonexistent.md"],
        capture_output=True, text=True
    )
    assert r.returncode != 0

def test_empty_files_list():
    """Ticket with no Affected Files table — should produce just the heading."""
    ticket = textwrap.dedent("""
    ---
    id: FEAT-002
    title: Update docs
    ---
    ## Description
    Just a docs update.

    ## Acceptance Criteria
    - [ ] AC-1: Docs updated
    """).strip()
    r = run(ticket)
    assert r.returncode == 0, r.stderr
    assert "## Implementation Plan" in r.stdout

def test_no_acceptance_criteria():
    """Ticket with no AC lines — should not crash and should not emit 'Tests to write:'."""
    ticket = textwrap.dedent("""
    ---
    id: FEAT-003
    title: No ACs
    ---
    ## Affected Files
    | File | Action | Description |
    |------|--------|-------------|
    | src/foo.ts | modify | Update foo |

    ## Acceptance Criteria
    (None defined yet)
    """).strip()
    r = run(ticket)
    assert r.returncode == 0, r.stderr
    assert "## Implementation Plan" in r.stdout
    assert "Tests to write:" not in r.stdout

def test_modify_only_ordering():
    """Ticket with only modify actions — should list them all."""
    ticket = textwrap.dedent("""
    ---
    id: FEAT-004
    title: Modify only
    ---
    ## Affected Files
    | File | Action | Description |
    |------|--------|-------------|
    | src/a.ts | modify | Update a |
    | src/b.ts | modify | Update b |
    """).strip()
    r = run(ticket)
    assert r.returncode == 0, r.stderr
    assert "src/a.ts" in r.stdout
    assert "src/b.ts" in r.stdout
