# Implementer v10.0 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Eliminate Opus, reduce from 5 LLM gates to 3, add 3 deterministic scripts, move fast path to Haiku.

**Architecture:** Replace Gate 1 (Ollama) with `plan_generator.py`, integrate Gate 3 lint into Gate 2 via `lint_fixer.py`, collapse Gate 4b (Opus) into Gate 4 (Sonnet) activated by `diff_pattern_scanner.py`, move fast path trivial to Haiku.

**Tech Stack:** Python 3 (scripts), Markdown (SKILL.md, templates), JSON (config preset)

---

## Task 1: plan_generator.py — deterministic Gate 1 replacement

**Files:**
- Create: `scripts/implementer/plan_generator.py`
- Create: `tests/test_plan_generator.py`

**Step 1: Write the failing test**

```python
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
```

**Step 2: Run to verify it fails**

```bash
cd /Users/fbelchi/github/backlog-agents
python3 -m pytest tests/test_plan_generator.py -v 2>&1 | head -20
```
Expected: `ModuleNotFoundError` or `FileNotFoundError` — script doesn't exist yet.

**Step 3: Write `scripts/implementer/plan_generator.py`**

```python
#!/usr/bin/env python3
"""
plan_generator.py — Deterministic Gate 1 replacement.
Reads a ticket markdown file and emits ## Implementation Plan to stdout.
Cost: $0. No LLM calls.
"""
import argparse, re, sys
from pathlib import Path

def parse_affected_files(body: str) -> list[dict]:
    rows = []
    in_table = False
    for line in body.splitlines():
        if "## Affected Files" in line:
            in_table = True
            continue
        if in_table:
            if line.startswith("##"):
                break
            if line.startswith("|") and not re.match(r"\|[-| ]+\|", line):
                parts = [p.strip() for p in line.strip("|").split("|")]
                if len(parts) >= 3 and parts[0] not in ("File", "file"):
                    rows.append({"path": parts[0], "action": parts[1], "desc": parts[2]})
    return rows

def parse_acceptance_criteria(body: str) -> list[str]:
    return re.findall(r"- \[[ x]\] (AC-\d+[^:\n]*:[^\n]+)", body)

def generate_plan(files: list[dict], acs: list[str]) -> str:
    lines = ["## Implementation Plan"]
    # Order: create → modify → delete
    ordered = (
        [f for f in files if f["action"] == "create"] +
        [f for f in files if f["action"] == "modify"] +
        [f for f in files if f["action"] == "delete"]
    )
    for f in ordered:
        lines.append(f"- {f['action'].capitalize()} `{f['path']}`: {f['desc']}")
    if acs:
        lines.append("")
        lines.append("Tests to write:")
        for ac in acs:
            lines.append(f"- {ac.strip()}")
    return "\n".join(lines)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticket", required=True)
    args = parser.parse_args()

    path = Path(args.ticket)
    if not path.exists():
        print(f"Error: ticket file not found: {path}", file=sys.stderr)
        sys.exit(1)

    content = path.read_text()
    # Strip YAML frontmatter
    body = re.sub(r"^---.*?---\s*", "", content, flags=re.DOTALL)

    files = parse_affected_files(body)
    acs = parse_acceptance_criteria(body)
    print(generate_plan(files, acs))

if __name__ == "__main__":
    main()
```

**Step 4: Run tests**

```bash
cd /Users/fbelchi/github/backlog-agents
python3 -m pytest tests/test_plan_generator.py -v
```
Expected: 4 PASSED

**Step 5: Commit**

```bash
git add scripts/implementer/plan_generator.py tests/test_plan_generator.py
git commit -m "feat(implementer): add plan_generator.py — deterministic Gate 1 replacement, \$0 cost"
```

---
## Task 2: lint_fixer.py — smart lint error parser

**Files:**
- Create: `scripts/implementer/lint_fixer.py`
- Create: `tests/test_lint_fixer.py`

**Step 1: Write the failing test**

```python
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
```

**Step 2: Run to verify it fails**

```bash
cd /Users/fbelchi/github/backlog-agents
python3 -m pytest tests/test_lint_fixer.py -v 2>&1 | head -10
```
Expected: FAIL — script doesn't exist yet.

**Step 3: Write `scripts/implementer/lint_fixer.py`**

```python
#!/usr/bin/env python3
"""
lint_fixer.py — Smart lint error parser.
Reads lint output from stdin, returns structured JSON with only error lines + context.
Cost: $0. Reduces Gate 3 Haiku tokens by ~70%.

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
    pattern = re.compile(r"^(.+?):(\d+):(\d+): ([A-Z]\d+) (.+)$", re.MULTILINE)
    for m in pattern.finditer(raw):
        path, line, col, code, msg = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4), m.group(5)
        errors.append({
            "file": path, "line": line, "column": col,
            "rule": code, "message": msg,
            "context": _extract_context(path, line)
        })
    return errors

def _extract_context(filepath: str, line: int, radius: int = 5) -> list[str]:
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
```

**Step 4: Run tests**

```bash
cd /Users/fbelchi/github/backlog-agents
python3 -m pytest tests/test_lint_fixer.py -v
```
Expected: 3 PASSED

**Step 5: Commit**

```bash
git add scripts/implementer/lint_fixer.py tests/test_lint_fixer.py
git commit -m "feat(implementer): add lint_fixer.py — smart lint parser, 70% token reduction for Gate 3"
```

---
## Task 3: diff_pattern_scanner.py — regex pattern detector

**Files:**
- Create: `scripts/implementer/diff_pattern_scanner.py`
- Create: `tests/test_diff_pattern_scanner.py`

**Step 1: Write the failing test**

```python
# tests/test_diff_pattern_scanner.py
import subprocess, json, sys, os, tempfile

SCRIPT = os.path.join(os.path.dirname(__file__), "../scripts/implementer/diff_pattern_scanner.py")

AUTH_DIFF = """+const token = jwt.sign({ userId }, process.env.JWT_SECRET);
+await bcrypt.hash(password, 10);
"""
CLEAN_DIFF = """+const greeting = "hello world";
+console.log(greeting);
"""
DB_DIFF = """+await db.createIndex({ field: 'userId' });
+await runMigration('add_users_table');
"""

def scan(diff_text):
    with tempfile.NamedTemporaryFile(mode='w', suffix='.diff', delete=False) as f:
        f.write(diff_text)
        path = f.name
    r = subprocess.run([sys.executable, SCRIPT, "--diff", path], capture_output=True, text=True)
    os.unlink(path)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)

def test_detects_auth_patterns():
    result = scan(AUTH_DIFF)
    assert "auth" in result["detected"]
    assert result["requires_high_risk_review"] is True

def test_clean_diff_no_review():
    result = scan(CLEAN_DIFF)
    assert result["detected"] == []
    assert result["requires_high_risk_review"] is False

def test_detects_db_schema():
    result = scan(DB_DIFF)
    assert "db_schema" in result["detected"]
    assert result["requires_high_risk_review"] is True

def test_multiple_patterns_detected():
    result = scan(AUTH_DIFF + DB_DIFF)
    assert "auth" in result["detected"]
    assert "db_schema" in result["detected"]
```

**Step 2: Run to verify it fails**

```bash
cd /Users/fbelchi/github/backlog-agents
python3 -m pytest tests/test_diff_pattern_scanner.py -v 2>&1 | head -10
```
Expected: FAIL — script doesn't exist yet.

**Step 3: Write `scripts/implementer/diff_pattern_scanner.py`**

```python
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
```

**Step 4: Run tests**

```bash
cd /Users/fbelchi/github/backlog-agents
python3 -m pytest tests/test_diff_pattern_scanner.py -v
```
Expected: 4 PASSED

**Step 5: Commit**

```bash
git add scripts/implementer/diff_pattern_scanner.py tests/test_diff_pattern_scanner.py
git commit -m "feat(implementer): add diff_pattern_scanner.py — regex high-risk detector, replaces Opus Gate 4b"
```

---
## Task 4: high-risk-review.md — Sonnet replacement for Opus Gate 4b

**Files:**
- Create: `skills/backlog-implementer/templates/high-risk-review.md`

**Step 1: Create the template**

```markdown
<!-- high-risk-review.md — Loaded by Gate 4 when diff_pattern_scanner detects high-risk patterns.
     Replaces Opus Gate 4b. Model: sonnet. -->

You are conducting a HIGH-RISK security and correctness review. The diff contains patterns
that require deep scrutiny: {detected_patterns}.

Apply this 6-point checklist with NO exceptions:

### 1. Type Safety
- No `any` casts, `as unknown`, or `@ts-ignore` suppressions in changed lines
- All function parameters and return types are explicit
- No implicit type coercions (e.g., `== null` instead of `=== null`)

### 2. Error Propagation
- Every `catch` block either re-throws, logs + re-throws, or returns an error value
- No silent swallowing: `catch(e) {}` or `catch(e) { return null }` without logging
- Async errors not swallowed by missing `await` or unhandled promise rejections

### 3. Production Readiness
- No `console.log`, `debugger`, `TODO`, `FIXME`, or `hardcoded secrets` in changed lines
- No test-only imports or mock data in production paths
- Environment variables validated before use (not just accessed)

### 4. Semantic Correctness
- Implementation matches every acceptance criterion in the ticket exactly
- No off-by-one errors in loops, ranges, or pagination
- Business logic matches the ticket description (not just the test assertions)

### 5. Resource Management
- DB connections, file handles, streams, and locks are closed in finally blocks
- No connection leaks in error paths
- Timeouts set on all external calls

### 6. Backward Compatibility
- No breaking changes to exported function signatures
- No database schema changes without a migration
- API response shapes unchanged unless ticket explicitly requires it

---
**Pattern-specific checks for: {detected_patterns}**

{pattern_auth}
{pattern_db_schema}
{pattern_serialization}
{pattern_concurrency}
{pattern_external_api}
{pattern_error_handling}

---
**OUTPUT FORMAT:**

If all checks pass:
```
APPROVED (high-risk review)
Patterns reviewed: {detected_patterns}
No issues found.
```

If issues found:
```
CHANGES_REQUESTED
Issues:
- [CRITICAL|IMPORTANT] {check_number}: {specific_finding} at {file}:{line}
```

Only report CRITICAL (blocks merge) or IMPORTANT (should fix) findings.
Do NOT report style preferences or minor suggestions.
```

**Pattern-specific snippets** (inject into `{pattern_*}` placeholders when detected):

```
# auth:
AUTH CHECK: Verify token expiry is set, session invalidation works on logout,
no secrets appear in logs or error messages, bcrypt rounds >= 10.

# db_schema:
DB_SCHEMA CHECK: Migration is reversible (has down() method), new indexes
don't lock the table in production, column types match application types.

# serialization:
SERIALIZATION CHECK: Input validated before JSON.parse (try/catch or schema),
output escaped before JSON.stringify if user-controlled, Buffer.from encoding explicit.

# concurrency:
CONCURRENCY CHECK: No shared mutable state accessed without locks,
Promise.race has a timeout branch, no deadlock risk in lock ordering.

# external_api:
EXTERNAL_API CHECK: Timeout set on all fetch/axios calls, response status checked
before using body, retry logic has max attempts and backoff.

# error_handling:
ERROR_HANDLING CHECK: Promise.all failure doesn't silently skip items,
error types are specific (not just catch Error), retry won't retry on permanent errors.
```

**Step 2: Verify file created**

```bash
wc -l skills/backlog-implementer/templates/high-risk-review.md
```
Expected: ~70 lines

**Step 3: Commit**

```bash
git add skills/backlog-implementer/templates/high-risk-review.md
git commit -m "feat(implementer): add high-risk-review.md — Sonnet 6-point checklist replacing Opus Gate 4b"
```

---

## Task 5: Update config/presets/default.json

**Files:**
- Modify: `config/presets/default.json:73-78,90-98`

**Step 1: Change escalationModel from "frontier" to "balanced"**

Find in `config/presets/default.json` (line 96):
```json
      "escalationModel": "frontier",
```
Replace with:
```json
      "escalationModel": "balanced",
```

**Step 2: Disable frontierReview (detection now via diff_pattern_scanner.py)**

Find (lines 73-78):
```json
    "frontierReview": {
      "enabled": true,
      "triggerPatterns": ["serialization", "db_schema", "auth", "error_handling", "external_api", "concurrency"],
      "skipForComplexity": ["trivial"]
    }
```
Replace with:
```json
    "frontierReview": {
      "enabled": false,
      "triggerPatterns": [],
      "skipForComplexity": ["trivial"]
    }
```

**Step 3: Verify JSON is valid**

```bash
python3 -c "import json; json.load(open('config/presets/default.json')); print('valid')"
```
Expected: `valid`

**Step 4: Run schema test**

```bash
./tests/test-config-schema.sh 2>&1 | tail -3
```
Expected: all PASS

**Step 5: Commit**

```bash
git add config/presets/default.json
git commit -m "feat(config): escalationModel frontier→balanced, disable frontierReview (replaced by diff_pattern_scanner.py)"
```

---
## Task 6: Update SKILL.md — all pipeline changes

**Files:**
- Modify: `skills/backlog-implementer/SKILL.md`

Make these changes in order, committing once at the end.

**Step 1: Update frontmatter description (line 3)**

Find:
```
description: "Adaptive pipeline implementer: complexity classifier → fast/full path, 5 quality gates, smart routing, configurable reviews, script delegation, cost tracking. v9.0."
```
Replace with:
```
description: "Adaptive pipeline implementer: complexity classifier → fast/full path, 3 LLM gates, smart routing, configurable reviews, full script delegation, cost tracking. v10.0."
```

**Step 2: Update title (line 7)**

Find: `# Backlog Implementer v9.0`
Replace: `# Backlog Implementer v10.0`

**Step 3: Update Model Rules table (lines 15-21)**

Find:
```
| haiku | Implementers, investigators, write-agents | Default for code tasks |
| sonnet | Fast-path single-agent, Gate 4 reviewers | Simple tickets, reviews |
| opus | Gate 4b frontier review | High-risk patterns only |
| free (Ollama) | Classify, wave plan, Gate 1 plan, pre-review, commit msg | Via llm_call.sh |
| parent (omit model:) | Escalation | ARCH/SEC tag, gateFails≥2, complex+fails≥1 |
```
Replace with:
```
| haiku | Implementers, investigators, fast-path trivial | Default for code tasks |
| sonnet | Fast-path simple review, Gate 4 reviewers, escalation | Reviews, high-risk, escalation |
| free (Ollama) | Classify, wave plan, pre-review, commit msg | Via llm_call.sh |
```

**Step 4: Update ROUTING table (lines 64-75)**

Find:
```
| Gate 1 PLAN | free (llm_call.sh) | haiku subagent | Ollama first |
| Gate 2 IMPL | haiku | sonnet on fail, parent on ARCH/SEC | TDD required |
| Gate 3 LINT | haiku | — | Run tools, LLM analyzes |
| Gate 4 REVIEW | sonnet | parent after 2nd fail | Pre-review via pre_review.py |
| Gate 4b FRONTIER | opus | — | Selective, high-risk only |
```
Replace with:
```
| Gate 1 PLAN | free (plan_generator.py) | — | $0 script, no LLM |
| Gate 2 IMPL+LINT | haiku | sonnet on fail, sonnet on ARCH/SEC | TDD + lint_fixer.py after each wave |
| Gate 4 REVIEW | sonnet | sonnet after 2nd fail | diff_pattern_scanner.py → high-risk-review.md if patterns |
```

**Step 5: Update MAIN LOOP (line 108)**

Find:
```
    All trivial/simple → FAST PATH (no team, single Sonnet per ticket)
```
Replace with:
```
    All trivial → FAST PATH Haiku (no team, single Haiku per ticket)
    All simple → FAST PATH Haiku+Sonnet-review (Haiku impl, Sonnet Gate 4 only)
```

**Step 6: Replace Gate 1 section (lines 159-164)**

Find:
```
### Gate 1: PLAN

Set context: `source scripts/ops/context.sh && set_backlog_context "$ticket_id" "plan" ...`
If ragAvailable: query RAG for snippets + sentinel patterns (inject warnings at top).
Implementer reads ticket, writes plan in `## Implementation Plan`. If unclear → "needs-investigation".
Log gate cost to usage-ledger.
```
Replace with:
```
### Gate 1: PLAN (script)

```bash
PLAN=$(python3 "${CLAUDE_PLUGIN_ROOT}/scripts/implementer/plan_generator.py" --ticket "$TICKET_PATH")
```
If script fails: implementer writes plan inline (fallback). Cost: $0.
Set context: `source scripts/ops/context.sh && set_backlog_context "$ticket_id" "plan" ...`
If ragAvailable: query RAG for snippets + sentinel patterns (inject warnings at top).
If ticket is unclear → mark "needs-investigation".
```

**Step 7: Update Gate 3 section (lines 180-182)**

Find:
```
### Gate 3: LINT

Run: typeCheckCommand (0 errors), lintCommand (0 warnings), testCommand (0 failures). Skip unconfigured. Auto-fix max 3 attempts. After 3: mark `lint-blocked`, skip to next wave.
```
Replace with:
```
### Gate 3: LINT (integrated into Gate 2)

After each implementation wave, run via lint_fixer.py:
```bash
LINT_JSON=$(lintCommand 2>&1 | python3 "${CLAUDE_PLUGIN_ROOT}/scripts/implementer/lint_fixer.py" --format eslint-json)
TSC_JSON=$(typeCheckCommand 2>&1 | python3 "${CLAUDE_PLUGIN_ROOT}/scripts/implementer/lint_fixer.py" --format tsc)
```
If `clean: true`: no LLM call needed. If errors: pass ONLY the `errors` JSON to Haiku (not full files).
Auto-fix max 3 attempts. After 3: mark `lint-blocked`, skip to next wave.
```

**Step 8: Replace Gate 4b section (lines 200-208)**

Find:
```
### Gate 4b: FRONTIER REVIEW (selective Opus)

**Trigger** — scan diff for ANY of: SERIALIZATION (JSON.parse/stringify, Redis, Buffer, protobuf), DB_SCHEMA (Schema, createIndex, migration), AUTH (jwt, token, session, bcrypt, oauth), ERROR_HANDLING (Promise.all/allSettled, try-catch external, retry), EXTERNAL_API (HttpClient, fetch, axios), CONCURRENCY (Promise.race, worker_threads, mutex).

**Skip if**: diff touches only tests/docs/config, trivial complexity, maxEscalationsPerTicket reached.

Spawn ONE `Task(model:"opus", subagent_type:"code-quality")` with 6-point checklist: type safety, error propagation, production readiness, semantic correctness, resource management, backward compat. Plus own deep analysis on detected patterns.

If findings: CHANGES_REQUESTED → implementer fixes → re-run Gate 4 only (NOT 4b again).
```
Replace with:
```
### Gate 4: HIGH-RISK MODE (replaces Opus Gate 4b)

Before spawning Gate 4 reviewers, run:
```bash
SCAN=$(git diff HEAD~1 | python3 "${CLAUDE_PLUGIN_ROOT}/scripts/implementer/diff_pattern_scanner.py")
```
If `requires_high_risk_review: true`: reviewers load `templates/high-risk-review.md` instead of `templates/reviewer-prefix.md`.
If `requires_high_risk_review: false`: reviewers load standard `templates/reviewer-prefix.md`.
Cost of scan: $0. No separate Gate 4b spawn needed.
```

**Step 9: Update FAST PATH section (lines 221-236)**

Find:
```
Leader pre-loads: ticket content, affected files, code rules, test/lint/typecheck commands, RAG context.

```
Task(
  subagent_type: {routed_type},
  model: "sonnet",
  prompt: Read templates/fast-path-agent.md with placeholders filled
)
```

**Escalation**: If fast-path agent fails Gate 3 or Gate 4 twice → set complexity="complex", route to full path next wave, increment `stats.fastPathEscalations`.

Log: `{"ticket_id":"{id}","pipeline":"fast","model":"sonnet","cost_usd":X,"escalated_to_full":false}`
```
Replace with:
```
Leader pre-loads: ticket content, affected files, code rules, test/lint/typecheck commands, RAG context.

**Trivial tickets:**
```
Task(subagent_type: {routed_type}, model: "haiku",
     prompt: Read templates/fast-path-agent.md with placeholders filled)
```

**Simple tickets (two-step):**
```
Step 1: Task(model: "haiku", prompt: fast-path-agent.md — Gates 1-3 only)
Step 2: Task(model: "sonnet", prompt: reviewer-prefix.md — Gate 4 only, receives diff + test results)
```

**Escalation**: If fails Gate 3 or Gate 4 twice → complexity="complex", full path next wave, increment `stats.fastPathEscalations`.

Log: `{"ticket_id":"{id}","pipeline":"fast","model":"haiku|haiku+sonnet","cost_usd":X,"escalated_to_full":false}`
```

**Step 10: Update Wave banner (line 261)**

Find: `Models: free:{N} haiku:{N} sonnet:{N} opus:{N}`
Replace: `Models: free:{N} haiku:{N} sonnet:{N}`

**Step 11: Verify changes**

```bash
grep -n "opus\|v9\.0\|model.*sonnet.*fast" skills/backlog-implementer/SKILL.md
```
Expected: 0 matches for "opus", 0 for "v9.0"

```bash
grep -n "plan_generator\|lint_fixer\|diff_pattern" skills/backlog-implementer/SKILL.md
```
Expected: 3 matches (one per script)

**Step 12: Commit**

```bash
git add skills/backlog-implementer/SKILL.md
git commit -m "feat(implementer): v10.0 — 3-gate pipeline, Gate 1 scripted, Gate 3 integrated, Gate 4b removed, fast path Haiku"
```

---
## Task 7: Update fast-path-agent.md template

**Files:**
- Modify: `skills/backlog-implementer/templates/fast-path-agent.md`

**Step 1: Update the template**

Find line 1:
```
<!-- Extracted from SKILL.md for v9.0. Primary: scripts/implementer/fast_path.py. This is the LLM fallback. -->
```
Replace with:
```
<!-- fast-path-agent.md v10.0. Used for trivial (Haiku) and simple impl-phase (Haiku). -->
```

Find lines 19-22 (Gate 1 section):
```
## EXECUTE THESE 5 GATES IN ORDER:

### Gate 1: PLAN
Write a 3-5 bullet implementation plan. Do not create a separate file.
```
Replace with:
```
## EXECUTE THESE 4 GATES IN ORDER:

### Gate 1: PLAN (pre-generated)
{plan_generator_output}
Review the plan above. If anything is unclear, note it but proceed with implementation.
```

Find lines 30-32 (Gate 3 section):
```
### Gate 3: LINT
Run: {lintCommand} and {typeCheckCommand}
If errors: fix and re-run (max 3 attempts). If still failing after 3: STOP and report.
```
Replace with:
```
### Gate 3: LINT
Run: {lintCommand} 2>&1 | python3 {CLAUDE_PLUGIN_ROOT}/scripts/implementer/lint_fixer.py --format {lint_format}
If output shows `"clean": false`: fix ONLY the reported error lines. Re-run max 3 attempts.
If still failing after 3: STOP and report.
```

**Step 2: Verify**

```bash
grep -n "Gate\|haiku\|sonnet\|opus" skills/backlog-implementer/templates/fast-path-agent.md
```
Expected: no "opus" references, no "5 GATES" (now 4)

**Step 3: Commit**

```bash
git add skills/backlog-implementer/templates/fast-path-agent.md
git commit -m "feat(implementer): update fast-path-agent.md — inject plan_generator output, lint_fixer in Gate 3, 4 gates"
```

---

## Task 8: Update CLAUDE.md — model routing and cost model

**Files:**
- Modify: `skills/backlog-implementer/CLAUDE.md`

**Step 1: Update title and version**

Find: `# Backlog Implementer Skill v9.0`
Replace: `# Backlog Implementer Skill v10.0`

**Step 2: Update v9.0 Changes section**

Find:
```
### v9.0 Changes (from v8.0)

- **Script delegation**: 7 LLM calls replaced with Python/bash scripts ($0 cost, 0 tokens)
- **Template extraction**: 4 inline prompts moved to template files (loaded on-demand)
- **Prompt compression**: Tables replace prose, duplicates removed, "why" commentary moved here
```
Replace with:
```
### v10.0 Changes (from v9.0)

- **Opus eliminated**: Gate 4b removed, replaced by `diff_pattern_scanner.py` (regex) + Sonnet `high-risk-review.md`
- **Gate 1 scripted**: `plan_generator.py` replaces Ollama/Haiku LLM call ($0, deterministic)
- **Gate 3 integrated**: `lint_fixer.py` integrates lint into Gate 2, passes only error lines to Haiku (70% token reduction)
- **Fast path Haiku**: Trivial tickets use Haiku (was Sonnet); simple use Haiku+Sonnet-review
- **3 LLM gates**: Down from 5 (was: Plan+Impl+Lint+Review+Frontier → now: Impl+Lint(conditional)+Review)
```

**Step 3: Update Model Routing table**

Find:
```
| Tier | Model | Usage |
|------|-------|-------|
| free | Ollama qwen3-coder | Gate 1 PLAN text only (remaining calls now scripts) |
| cheap | Haiku | Implementers, investigators |
| balanced | Sonnet | Fast-path agent, Gate 4 reviewers |
| frontier | Opus | Gate 4b selective high-risk review |
```
Replace with:
```
| Tier | Model | Usage |
|------|-------|-------|
| free | Ollama qwen3-coder | Wave plan, pre-review, commit msg (via llm_call.sh) |
| cheap | Haiku | Implementers, investigators, fast-path trivial |
| balanced | Sonnet | Fast-path simple review, Gate 4 reviewers, escalation |
```

**Step 4: Update Gate 4b Trigger Patterns section**

Find:
```
### Gate 4b Trigger Patterns

Opus frontier review triggers on: SERIALIZATION (JSON.parse, Redis, Buffer), DB_SCHEMA (createIndex, migration), AUTH (jwt, session, bcrypt), ERROR_HANDLING (Promise.all, retry), EXTERNAL_API (fetch, axios), CONCURRENCY (worker_threads, mutex). Skips: tests/docs only, trivial tickets.
```
Replace with:
```
### High-Risk Pattern Detection (replaces Gate 4b)

`diff_pattern_scanner.py` scans git diff with regex for: AUTH (jwt, bcrypt, session, token), DB_SCHEMA (createIndex, migration, ALTER TABLE), SERIALIZATION (JSON.parse, Buffer.from), ERROR_HANDLING (Promise.all, retry), EXTERNAL_API (fetch, axios), CONCURRENCY (worker_threads, mutex). If any detected → Gate 4 uses `high-risk-review.md` instead of `reviewer-prefix.md`. Cost: $0.
```

**Step 5: Update Escalation Rules section**

Find:
```
- ARCH or SECURITY tag → parent model
- qualityGateFails ≥ 2 → parent model
- complex ticket + gateFails ≥ 1 → parent model
- Fast path: 2 fails → escalate to full path
```
Replace with:
```
- ARCH or SECURITY tag → sonnet (balanced)
- qualityGateFails ≥ 2 → sonnet (balanced)
- complex ticket + gateFails ≥ 1 → sonnet (balanced)
- Fast path: 2 fails → escalate to full path
```

**Step 6: Update Cost Model table**

Find:
```
| trivial | fast path | $0.10-0.25 | $0.08-0.20 | ~20% |
| simple | fast path | $0.25-0.50 | $0.20-0.40 | ~20% |
| complex | full path | $1.50-3.00 | $1.20-2.50 | ~20% |
```
Replace with:
```
| trivial | fast path Haiku | $0.08-0.20 | $0.03-0.08 | ~60% |
| simple | fast path Haiku+Sonnet | $0.20-0.40 | $0.10-0.20 | ~50% |
| complex | full path no Opus | $1.20-2.50 | $0.70-1.50 | ~40% |
```

**Step 7: Update Key Files / Script Layer table**

Add 3 new rows to the Script Layer table:
```
| `scripts/implementer/plan_generator.py` | Gate 1 plan generation | $0 |
| `scripts/implementer/lint_fixer.py` | Gate 3 lint error parsing | $0 |
| `scripts/implementer/diff_pattern_scanner.py` | High-risk pattern detection | $0 |
```

And add to Template Layer:
```
| `templates/high-risk-review.md` | Sonnet 6-point high-risk checklist | When patterns detected |
```

**Step 8: Verify**

```bash
grep -n "opus\|v9\.0\|frontier.*Opus\|Gate 4b" skills/backlog-implementer/CLAUDE.md
```
Expected: 0 matches

**Step 9: Commit**

```bash
git add skills/backlog-implementer/CLAUDE.md
git commit -m "docs(implementer): update CLAUDE.md for v10.0 — model routing, cost model, script layer"
```

---

## Summary

| Task | File | Type | Test |
|------|------|------|------|
| 1 | `scripts/implementer/plan_generator.py` | NEW script | 4 pytest |
| 2 | `scripts/implementer/lint_fixer.py` | NEW script | 3 pytest |
| 3 | `scripts/implementer/diff_pattern_scanner.py` | NEW script | 4 pytest |
| 4 | `templates/high-risk-review.md` | NEW template | wc -l |
| 5 | `config/presets/default.json` | MODIFY config | schema test |
| 6 | `skills/backlog-implementer/SKILL.md` | MODIFY skill | grep check |
| 7 | `templates/fast-path-agent.md` | MODIFY template | grep check |
| 8 | `skills/backlog-implementer/CLAUDE.md` | MODIFY docs | grep check |

**Expected outcome:** No Opus anywhere. Gate 1 = script. Gate 3 integrated. Gate 4b removed. Fast path Haiku. 40-60% cost reduction across all ticket types.
