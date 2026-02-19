# backlog-sentinel v1.0 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a `backlog-sentinel` skill that analyzes HEAD commit with deterministic prescan + 2 parallel LLM reviewers + continuous learning via pattern ledger.

**Architecture:** One-shot skill (no daemon). Phase 0 runs `sentinel_prescan.py` at $0. Phase 0.5 queries RAG. Phase 1 spawns 2 parallel LLM reviewers. Phase 2 creates tickets via `backlog-ticket` logic. Phase 3 updates pattern ledger and proposes codeRules updates.

**Tech Stack:** Python 3.10+, Markdown SKILL.md, JSON Schema, bash git hook

**Design reference:** `docs/plans/2026-02-19-backlog-sentinel-design.md`

---

### Task 1: Add `sentinel` schema to `config/backlog.config.schema.json`

**Files:**
- Modify: `config/backlog.config.schema.json`

**Step 1: Read the existing schema to find the `llmOps` property block**

```bash
grep -n "llmOps" config/backlog.config.schema.json | head -5
```

**Step 2: Add `sentinel` as a new top-level property** after `llmOps`:

```json
"sentinel": {
  "type": "object",
  "description": "Sentinel code-review skill configuration.",
  "additionalProperties": false,
  "properties": {
    "enabled": { "type": "boolean", "default": true },
    "installGitHook": { "type": "boolean", "default": true },
    "prescan": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "runLinter":       { "type": "boolean", "default": true },
        "runTests":        { "type": "boolean", "default": true },
        "runTypeCheck":    { "type": "boolean", "default": true },
        "detectHardcoded": { "type": "boolean", "default": true },
        "detectTodos":     { "type": "boolean", "default": true },
        "maxFunctionLines":{ "type": "integer", "default": 80 }
      }
    },
    "reviewers": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "security": { "type": "boolean", "default": true },
        "quality":  { "type": "boolean", "default": true }
      }
    },
    "ragDeduplication": { "type": "boolean", "default": true },
    "patternThresholds": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "recurring":          { "type": "integer", "default": 2 },
        "escalateToSoftGate": { "type": "integer", "default": 3 },
        "escalateToHardGate": { "type": "integer", "default": 5 }
      }
    },
    "ticketMapping": {
      "type": "object",
      "additionalProperties": { "type": "string" },
      "default": {
        "security": "SEC",
        "bug": "BUG",
        "techDebt": "TASK",
        "architecture": "TASK"
      }
    }
  }
}
```

**Step 3: Run schema validation test**

```bash
node -e "
const schema = require('./config/backlog.config.schema.json');
console.log('sentinel keys:', Object.keys(schema.properties.sentinel.properties));
"
```
Expected: `sentinel keys: [ 'enabled', 'installGitHook', 'prescan', 'reviewers', 'ragDeduplication', 'patternThresholds', 'ticketMapping' ]`

**Step 4: Commit**

```bash
git add config/backlog.config.schema.json
git commit -m "feat(schema): add sentinel section to backlog.config schema"
```

---

### Task 2: Add `sentinel` defaults to `config/presets/default.json`

**Files:**
- Modify: `config/presets/default.json`

**Step 1: Read current end of default.json to find insertion point**

```bash
tail -20 config/presets/default.json
```

**Step 2: Add `sentinel` block** before the final closing `}`:

```json
"sentinel": {
  "enabled": true,
  "installGitHook": true,
  "prescan": {
    "runLinter": true,
    "runTests": true,
    "runTypeCheck": true,
    "detectHardcoded": true,
    "detectTodos": true,
    "maxFunctionLines": 80
  },
  "reviewers": {
    "security": true,
    "quality": true
  },
  "ragDeduplication": true,
  "patternThresholds": {
    "recurring": 2,
    "escalateToSoftGate": 3,
    "escalateToHardGate": 5
  },
  "ticketMapping": {
    "security": "SEC",
    "bug": "BUG",
    "techDebt": "TASK",
    "architecture": "TASK"
  }
}
```

**Step 3: Validate JSON is still valid**

```bash
python3 -c "import json; json.load(open('config/presets/default.json')); print('valid JSON')"
```
Expected: `valid JSON`

**Step 4: Commit**

```bash
git add config/presets/default.json
git commit -m "feat(config): add sentinel defaults to preset"
```

---
### Task 3: Create `scripts/ops/sentinel_prescan.py`

**Files:**
- Create: `scripts/ops/sentinel_prescan.py`

**Step 1: Create the file with this exact content:**

```python
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
               category: str, exclude_patterns: list[str] = None) -> list[dict]:
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
                            "description": f"Long function '{func_name}' ({i - func_start} lines > {max_lines})",
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

    for key, label, category in [
        ("lintCommand", "Lint error", "bug"),
        ("typeCheckCommand", "Type error", "bug"),
        ("testCommand", "Test failure", "bug"),
    ]:
        cmd = gates.get(key)
        if not cmd:
            continue
        prescan_cfg = config.get("sentinel", {}).get("prescan", {})
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
                "description": f"{label}: {cmd!r} exited {code}. Output: {output[:300]}",
                "source": "prescan",
            })
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Sentinel deterministic prescan")
    parser.add_argument("--config", default="backlog.config.json")
    args = parser.parse_args()

    config = {}
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
```

**Step 2: Make executable**

```bash
chmod +x scripts/ops/sentinel_prescan.py
```

**Step 3: Smoke test**

```bash
python3 scripts/ops/sentinel_prescan.py --help
```
Expected: shows usage without error.

**Step 4: Commit**

```bash
git add scripts/ops/sentinel_prescan.py
git commit -m "feat(sentinel): add deterministic prescan script"
```

---
### Task 4: Create `scripts/ops/sentinel_patterns.py`

**Files:**
- Create: `scripts/ops/sentinel_patterns.py`

**Step 1: Create the file:**

```python
#!/usr/bin/env python3
"""Pattern ledger for backlog-sentinel continuous learning.

Tracks recurring error patterns across commits. Escalates to codeRules
when occurrence threshold is exceeded.

Usage:
    python scripts/ops/sentinel_patterns.py --findings findings.json
    python scripts/ops/sentinel_patterns.py --findings findings.json --propose-rules
"""

from __future__ import annotations
import argparse, json, re
from datetime import datetime, timezone
from pathlib import Path


LEDGER_PATH = Path(".backlog-ops/sentinel-patterns.json")


def load_ledger() -> dict:
    if not LEDGER_PATH.exists():
        return {"version": "1.0", "patterns": [], "thresholds": {
            "recurring": 2, "escalateToSoftGate": 3, "escalateToHardGate": 5
        }}
    return json.loads(LEDGER_PATH.read_text(encoding="utf-8"))


def save_ledger(ledger: dict) -> None:
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    LEDGER_PATH.write_text(json.dumps(ledger, indent=2), encoding="utf-8")


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower())[:60].strip("-")


def similarity(a: str, b: str) -> float:
    """Simple word-overlap similarity."""
    wa = set(re.findall(r"\w+", a.lower()))
    wb = set(re.findall(r"\w+", b.lower()))
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def update_ledger(findings: list[dict], thresholds: dict) -> dict:
    """Match findings to patterns, increment counts, return escalated patterns."""
    ledger = load_ledger()
    ledger["thresholds"] = thresholds or ledger["thresholds"]
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    escalated = []

    for finding in findings:
        desc = finding.get("description", "")
        matched = False
        for pattern in ledger["patterns"]:
            if similarity(desc, pattern["description"]) > 0.6:
                pattern["occurrences"] += 1
                pattern["last_seen"] = today
                if finding.get("file") not in pattern["files"]:
                    pattern["files"].append(finding["file"])
                matched = True
                # Check escalation
                t = ledger["thresholds"]
                if (pattern["occurrences"] >= t.get("escalateToSoftGate", 3)
                        and not pattern.get("escalated_to_rules")):
                    escalated.append(pattern)
                break
        if not matched:
            ledger["patterns"].append({
                "id": slugify(desc),
                "description": desc,
                "category": finding.get("category", "bug"),
                "occurrences": 1,
                "files": [finding.get("file", "unknown")],
                "first_seen": today,
                "last_seen": today,
                "escalated_to_rules": False,
            })

    save_ledger(ledger)
    return {"ledger": ledger, "escalated": escalated}


def propose_rules(escalated: list[dict], rules_file: str) -> None:
    """Append escalated patterns to codeRules file as soft gates."""
    if not escalated:
        return
    rules_path = Path(rules_file)
    if not rules_path.exists():
        print(f"codeRules file not found: {rules_file}")
        return
    additions = "\n".join(
        f"- [ ] {p['description']}\n"
        f"      [auto-added by sentinel, {p['occurrences']}x — {p['last_seen']}]"
        for p in escalated
    )
    content = rules_path.read_text(encoding="utf-8")
    if "## Soft Gates" in content:
        content = content.replace(
            "## Soft Gates", f"## Soft Gates\n{additions}"
        )
    else:
        content += f"\n## Soft Gates (auto-added by sentinel)\n{additions}\n"
    rules_path.write_text(content, encoding="utf-8")
    print(f"Added {len(escalated)} pattern(s) to {rules_file}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Sentinel pattern ledger")
    parser.add_argument("--findings", required=True, help="JSON file with findings")
    parser.add_argument("--config", default="backlog.config.json")
    parser.add_argument("--propose-rules", action="store_true")
    args = parser.parse_args()

    findings = json.loads(Path(args.findings).read_text(encoding="utf-8"))
    if isinstance(findings, dict):
        findings = findings.get("findings", [])

    config = {}
    try:
        config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    except Exception:
        pass

    thresholds = config.get("sentinel", {}).get("patternThresholds", {})
    result = update_ledger(findings, thresholds)

    print(f"Patterns tracked: {len(result['ledger']['patterns'])}")
    print(f"Escalated: {len(result['escalated'])}")

    if args.propose_rules and result["escalated"]:
        rules_file = config.get("codeRules", {}).get("source", ".claude/code-rules.md")
        propose_rules(result["escalated"], rules_file)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

**Step 2: Make executable**

```bash
chmod +x scripts/ops/sentinel_patterns.py
```

**Step 3: Smoke test**

```bash
echo '{"findings":[]}' > /tmp/test-findings.json
python3 scripts/ops/sentinel_patterns.py --findings /tmp/test-findings.json
rm /tmp/test-findings.json
```
Expected: `Patterns tracked: 0` and `Escalated: 0` with no errors.

**Step 4: Commit**

```bash
git add scripts/ops/sentinel_patterns.py
git commit -m "feat(sentinel): add continuous learning pattern ledger"
```

---
### Task 5: Create `skills/backlog-sentinel/SKILL.md`

**Files:**
- Create: `skills/backlog-sentinel/SKILL.md`

**Step 1: Create the directory**

```bash
mkdir -p skills/backlog-sentinel
```

**Step 2: Create `skills/backlog-sentinel/SKILL.md` with this content:**

```markdown
---
name: backlog-sentinel
description: "One-shot code review on HEAD commit: deterministic prescan (lint+tests+grep at $0) + 2 parallel LLM reviewers + ticket creation via backlog-ticket + continuous learning via pattern ledger. Triggered on-demand or via pre-push git hook. v1.0."
allowed-tools: Read, Glob, Grep, Bash, Write, Edit, Task, TeamCreate, TeamDelete, SendMessage, TaskCreate, TaskList, TaskUpdate, TaskGet
---

# Backlog Sentinel v1.0

One-shot code review skill. Analyzes HEAD commit, creates tickets for every finding, updates the pattern ledger for continuous learning. No daemon, no infinite loop — runs once and exits.

## ⚠️ CRITICAL: DO NOT PASS model: TO TASK TOOL

Never pass `model:` when spawning subagents. They inherit the parent model automatically.

---

## Configuration

Reads from `backlog.config.json` at project root.

| What | Config Path | Default |
|------|-------------|---------|
| Sentinel enabled | `sentinel.enabled` | `true` |
| Prescan: run linter | `sentinel.prescan.runLinter` | `true` |
| Prescan: run tests | `sentinel.prescan.runTests` | `true` |
| Prescan: detect hardcoded | `sentinel.prescan.detectHardcoded` | `true` |
| Max function lines | `sentinel.prescan.maxFunctionLines` | `80` |
| Security reviewer | `sentinel.reviewers.security` | `true` |
| Quality reviewer | `sentinel.reviewers.quality` | `true` |
| RAG deduplication | `sentinel.ragDeduplication` | `true` |
| Ticket mapping | `sentinel.ticketMapping` | `{security:SEC, bug:BUG, techDebt:TASK}` |
| Pattern thresholds | `sentinel.patternThresholds` | `{soft: 3, hard: 5}` |
| Gen model | `llmOps.routing.defaultGenerationModel` | `balanced` |
| RAG server | `llmOps.ragPolicy.serverUrl` | `http://localhost:8001` |

---

## MAIN FLOW

```
STARTUP
  config = read("backlog.config.json")
  if not config.sentinel.enabled: exit "Sentinel disabled in config"
  nowMode = args.includes("--now")

PHASE 0: DETERMINISTIC PRESCAN ($0)
  Run: python3 scripts/ops/sentinel_prescan.py --config backlog.config.json
  Parse JSON output → prescan_findings[]
  Print: "Prescan complete: {N} findings"

PHASE 0.5: RAG CONTEXT PREP ($0)
  changed_files = prescan output's changed_files[]
  IF config.llmOps.ragPolicy.enabled AND config.sentinel.ragDeduplication:
    FOR each finding in prescan_findings:
      Query RAG: GET {ragPolicy.serverUrl}/search {"query": finding.description, "n_results": 3}
      IF similarity > 0.85 → mark finding as duplicate_skipped
    FOR each changed_file:
      Query RAG: {"query": "patterns in {file}", "n_results": 5}
      Store as rag_context[file]
  relevant_rules = Query RAG: {"query": "architecture rules for {changed_files}", "n_results": 5}

PHASE 1: SPAWN REVIEWER TEAM
  TeamCreate("sentinel-{first 7 chars of HEAD commit hash}")
  
  Spawn in PARALLEL (NO model: parameter):
  
  IF config.sentinel.reviewers.security:
    security-reviewer:
      subagent_type: "security-engineer"
      prompt: See Security Reviewer Template below
  
  IF config.sentinel.reviewers.quality:
    quality-reviewer:
      subagent_type: "code-quality"
      prompt: See Quality Reviewer Template below
  
  Wait for both (5-minute timeout each)
  Collect findings as reviewer_findings[]

PHASE 2: CREATE TICKETS
  all_findings = [prescan_findings (non-duplicate)] + reviewer_findings
  
  FOR each finding:
    IF finding.duplicate_skipped: continue
    
    ticket_type = config.sentinel.ticketMapping[finding.category]
    auto_tags = []
    IF finding.category == "security" OR any security keyword in finding.description:
      auto_tags.append("SECURITY")
    IF any arch keyword (architecture, refactor, migrate) in finding.description:
      auto_tags.append("ARCH")
    
    Create ticket using backlog-ticket skill logic:
      - type: ticket_type
      - description: "{finding.description} — found in {finding.file}:{finding.line}"
      - context: "Found in commit {hash} ({author}, {date}) by backlog-sentinel v1.0"
      - affected_files: [finding.file]
      - tags: auto_tags
      - batchEligible: true
      - found_by: "backlog-sentinel-v1"
      Run full 6-check validation, assign sequential ID, write to backlog/data/pending/

PHASE 3: LEARNING + SUMMARY
  Write all findings to /tmp/sentinel-findings-{hash}.json
  Run: python3 scripts/ops/sentinel_patterns.py \
         --findings /tmp/sentinel-findings-{hash}.json \
         --config backlog.config.json \
         --propose-rules
  
  Print summary:
    sentinel complete — commit {hash} ({author}, {date})
    ──────────────────────────────────────────────
    prescan (deterministic, $0):  {N} findings
    reviewers (LLM):              {N} findings  
    skipped (duplicates):         {N}
    ──────────────────────────────────────────────
    tickets created: {N} ({list of IDs})
    cost: ${cost}
  
  Log to .backlog-ops/usage-ledger.jsonl:
    {"skill": "sentinel", "commit": "{hash}", "tickets_created": N, "cost_usd": X, "date": "..."}
  
  TeamDelete

PHASE 3.5: GIT HOOK INSTALL (only when invoked directly, not from hook)
  IF config.sentinel.installGitHook AND NOT running_as_git_hook:
    IF not exists .git/hooks/pre-push:
      Write .git/hooks/pre-push:
        #!/bin/bash
        claude --skip-permissions -p "/backlog-toolkit:sentinel"
      chmod +x .git/hooks/pre-push
      Print: "Installed pre-push git hook"
```

---

## Reviewer Prompt Templates

### Security Reviewer Prompt

```
You are a security code reviewer. Analyze the following git diff for security vulnerabilities that require code flow understanding (NOT hardcoded secrets or obvious patterns — those are already caught by automated scan).

COMMIT: {hash} by {author}
CHANGED FILES: {changed_files}

PRESCAN ALREADY FOUND (do NOT duplicate):
{prescan_findings}

GIT DIFF:
{git diff HEAD~1..HEAD}

RELEVANT CODE CONTEXT (from RAG):
{rag_context for each changed file}

ARCHITECTURE RULES:
{relevant_rules}

Focus ONLY on:
- Auth bypass and privilege escalation requiring code flow understanding
- Injection vulnerabilities not caught by static patterns
- Insecure cryptographic choices  
- Data exposure through logic errors

For each finding output EXACTLY this JSON (one finding per object in array):
[
  {
    "category": "security",
    "severity": "high|medium|low",
    "file": "path/to/file.ts",
    "line": 42,
    "description": "One sentence describing the vulnerability",
    "current_code": "the problematic code line",
    "suggested_fix": "how to fix it"
  }
]

Output ONLY the JSON array. If no findings, output: []
```

### Quality Reviewer Prompt

```
You are a code quality reviewer. Analyze the following git diff for bugs and architecture violations that require code context understanding (NOT lint errors, long functions, or TODO comments — those are already caught by automated scan).

COMMIT: {hash} by {author}
CHANGED FILES: {changed_files}

PRESCAN ALREADY FOUND (do NOT duplicate):
{prescan_findings}

GIT DIFF:
{git diff HEAD~1..HEAD}

RELEVANT CODE CONTEXT (from RAG):
{rag_context for each changed file}

ARCHITECTURE RULES:
{relevant_rules}

Focus ONLY on:
- Race conditions and async bugs requiring context understanding
- Null/undefined edge cases in complex flows
- Architecture violations (patterns defined in architecture rules above)
- Performance anti-patterns requiring data shape awareness

For each finding output EXACTLY this JSON:
[
  {
    "category": "bug|architecture|techDebt",
    "severity": "high|medium|low",
    "file": "path/to/file.ts",
    "line": 42,
    "description": "One sentence describing the issue",
    "current_code": "the problematic code",
    "suggested_fix": "how to fix it"
  }
]

Output ONLY the JSON array. If no findings, output: []
```

---

## Start

1. Read `backlog.config.json`
2. Run deterministic prescan
3. Prep RAG context
4. Spawn reviewer team
5. Create tickets for all findings
6. Update pattern ledger
7. Print summary
```

**Step 3: Commit**

```bash
git add skills/backlog-sentinel/SKILL.md
git commit -m "feat(sentinel): add SKILL.md — main skill definition"
```

---
### Task 6: Create `skills/backlog-sentinel/CLAUDE.md`

**Files:**
- Create: `skills/backlog-sentinel/CLAUDE.md`

**Step 1: Create the file:**

```markdown
# Backlog Sentinel Skill

## Purpose

One-shot code review on HEAD commit. Runs deterministic prescan (lint+tests+grep at $0)
then 2 parallel LLM reviewers for findings requiring judgment.
Creates validated backlog tickets for every finding.
Updates pattern ledger for continuous learning.

## Key Features

1. **Deterministic Prescan**: lint, tests, grep — no LLM, no cost
2. **RAG Context Compression**: snippets not full files, deduplication against backlog
3. **2 Parallel Reviewers**: security-engineer + code-quality, config-driven model tiers
4. **Ticket Integration**: every finding → proper BUG/SEC/TASK ticket via backlog-ticket
5. **Pattern Ledger**: tracks recurring errors, auto-escalates to codeRules
6. **Git Hook**: installs pre-push hook on first run

## Invocation

```bash
/backlog-toolkit:sentinel          # on HEAD commit
/backlog-toolkit:sentinel --now    # force synchronous ticket creation
```

## Related Files

- `SKILL.md`: Full skill implementation
- `scripts/ops/sentinel_prescan.py`: Deterministic prescan script
- `scripts/ops/sentinel_patterns.py`: Pattern ledger management
- `.backlog-ops/sentinel-patterns.json`: Pattern ledger (auto-created)
```

**Step 2: Commit**

```bash
git add skills/backlog-sentinel/CLAUDE.md
git commit -m "docs(sentinel): add CLAUDE.md context file"
```

---

### Task 7: Create `commands/sentinel.md` and register in `plugin.json`

**Files:**
- Create: `commands/sentinel.md`
- Modify: `.claude-plugin/plugin.json`

**Step 1: Create `commands/sentinel.md`:**

```markdown
# Command: /backlog-toolkit:sentinel

Analyze HEAD commit with deterministic prescan + parallel LLM reviewers.
Creates validated backlog tickets for every finding (bugs, security, tech debt).
Installs pre-push git hook on first run for automatic future analysis.

## Syntax

/backlog-toolkit:sentinel [--now]

## Parameters

- `--now`: Force synchronous ticket creation (default: batch-eligible)

## Examples

### On-demand analysis
/backlog-toolkit:sentinel

### Synchronous (immediate tickets)
/backlog-toolkit:sentinel --now

## What it does

1. **Prescan** (deterministic, $0): runs lint, tests, grep on changed files
2. **RAG** ($0): compresses context, deduplicates against existing backlog
3. **Reviewers** (LLM): security + quality analysis with focused context
4. **Tickets**: every finding → validated BUG/SEC/TASK ticket
5. **Learning**: updates pattern ledger, proposes codeRules updates when patterns recur

## Related

- Skill: `skills/backlog-sentinel/SKILL.md`
- Scripts: `scripts/ops/sentinel_prescan.py`, `scripts/ops/sentinel_patterns.py`
- Ledger: `.backlog-ops/sentinel-patterns.json`
```

**Step 2: Add sentinel to `.claude-plugin/plugin.json` commands array:**

Read `plugin.json`, then add `"./commands/sentinel.md"` to the `commands` array:

```json
{
  "commands": [
    "./commands/init.md",
    "./commands/ticket.md",
    "./commands/refinement.md",
    "./commands/implementer.md",
    "./commands/sentinel.md"
  ]
}
```

**Step 3: Validate JSON**

```bash
python3 -c "import json; d=json.load(open('.claude-plugin/plugin.json')); print('commands:', d['commands'])"
```
Expected: shows 5 commands including `./commands/sentinel.md`

**Step 4: Commit**

```bash
git add commands/sentinel.md .claude-plugin/plugin.json
git commit -m "feat(sentinel): add command definition and register in plugin.json"
```

---

### Task 8: Update `skills/backlog-init/SKILL.md`

**Files:**
- Modify: `skills/backlog-init/SKILL.md`

**Step 1: Read current Step 3 (Create Directory Structure) to find the exact text**

Look for "## Step 3" in the file.

**Step 2: Add sentinel hook installation to Step 3**

After the `.gitkeep` file creation, add:

```markdown
If `sentinel.installGitHook` is `true` in the chosen preset (default: true),
create `.git/hooks/pre-push`:

```bash
#!/bin/bash
# Installed by backlog-init — runs backlog-sentinel on every push
claude --skip-permissions -p "/backlog-toolkit:sentinel"
```

Then: `chmod +x .git/hooks/pre-push`
```

**Step 3: Add sentinel to the generated `backlog.config.json` in Step 4**

The config template in Step 4 already includes the `llmOps` section (added earlier).
Now add the `sentinel` section to the config template — paste the full sentinel
block from `config/presets/default.json` (Task 2).

**Step 4: Add sentinel to Step 8 (Print Summary) output**

Append to the "Created:" list:
```
  - .git/hooks/pre-push  (pre-push git hook for sentinel)
```

**Step 5: Commit**

```bash
git add skills/backlog-init/SKILL.md
git commit -m "feat(init): add sentinel config and git hook installation to backlog-init"
```

---

### Task 9: Add `.backlog-ops/` to `.gitignore` (optional sentinel data)

**Files:**
- Modify: `.gitignore`

**Step 1: Check current .gitignore**

```bash
grep "backlog-ops" .gitignore
```

**Step 2: If not present, add:**

```
# Sentinel pattern ledger (commit this to share patterns with team, or gitignore to keep local)
# .backlog-ops/sentinel-patterns.json
.backlog-ops/batch-queue/
```

The pattern ledger itself (`.backlog-ops/sentinel-patterns.json`) should be **committed** so patterns are shared across the team. Only the batch queue directory needs ignoring.

**Step 3: Commit**

```bash
git add .gitignore
git commit -m "chore: ensure .backlog-ops batch queue is gitignored"
```

---

### Task 10: End-to-end validation

**Step 1: Verify all new files exist**

```bash
ls skills/backlog-sentinel/
ls scripts/ops/sentinel_prescan.py scripts/ops/sentinel_patterns.py
ls commands/sentinel.md
```

**Step 2: Validate JSON files**

```bash
python3 -c "import json; json.load(open('config/backlog.config.schema.json')); print('schema OK')"
python3 -c "import json; json.load(open('config/presets/default.json')); print('default OK')"
python3 -c "import json; json.load(open('.claude-plugin/plugin.json')); print('plugin OK')"
```

**Step 3: Test prescan with no changes (should return empty findings)**

```bash
python3 scripts/ops/sentinel_prescan.py 2>&1 | head -5
```

**Step 4: Test pattern ledger with empty findings**

```bash
echo '{"findings":[]}' > /tmp/empty.json
python3 scripts/ops/sentinel_patterns.py --findings /tmp/empty.json
rm /tmp/empty.json
```

**Step 5: Final commit and push**

```bash
git status
git push origin main
```

---
