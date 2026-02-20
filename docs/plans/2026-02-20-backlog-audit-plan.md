# Backlog Audit Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement `/backlog-toolkit:audit` — full project health audit with 5-phase tiered model funnel ($1-3 vs $10-15 all-Opus).

**Architecture:** 12-check deterministic prescan -> Haiku sweep -> Sonnet deep analysis -> Opus critical review -> RAG dedup -> ticket creation via backlog-ticket.

**Tech Stack:** Python 3.10+ (prescan script), Markdown (SKILL.md, command), JSON (config schema/preset)

---

## Task 1: Add audit config to schema

**Files:**
- Modify: `config/backlog.config.schema.json`
- Modify: `config/presets/default.json`

### Steps

1. In `config/backlog.config.schema.json`, add `"audit"` property after `"sentinel"` at root level. Properties: `enabled` (bool), `prescan` object with `extensions` (string[]), `excludeDirs` (string[]), `maxFunctionLines` (int, default 80), `coverageThreshold` (int 0-100, default 70), `complexityThreshold` (int, default 10). Also `dimensions` (enum array of 6 values), `ragDeduplication` (bool), `ticketMapping` (object, additionalProperties string). Follow sentinel schema pattern exactly.

2. In `config/presets/default.json`, add `"audit"` section after `"sentinel"`:

```json
"audit": {
  "enabled": true,
  "prescan": {
    "extensions": [".ts", ".tsx", ".js", ".jsx", ".py"],
    "excludeDirs": ["node_modules", "dist", "coverage", ".next", "__pycache__", ".git"],
    "maxFunctionLines": 80,
    "coverageThreshold": 70,
    "complexityThreshold": 10
  },
  "dimensions": ["architecture", "security", "bugs", "performance", "tests", "hygiene"],
  "ragDeduplication": true,
  "ticketMapping": {
    "security": "SEC",
    "bugs": "BUG",
    "architecture": "TASK",
    "performance": "TASK",
    "tests": "TEST",
    "hygiene": "QUALITY"
  }
}
```

3. `git add config/backlog.config.schema.json config/presets/default.json && git commit -m "feat(audit): add audit config to schema and default preset"`

---

## Task 2: Update test-config-schema.sh

**Files:**
- Modify: `tests/test-config-schema.sh`

### Steps

1. Before the `# -- Summary --` section, add two new blocks:

```bash
# -- audit schema checks --
echo "-- audit schema --"
# Check audit exists in schema properties
# Check audit.prescan.extensions default is array
# Check audit.dimensions has enum constraint

# -- audit preset sub-keys --
echo "-- audit preset sub-keys --"
# Loop: enabled, prescan, dimensions, ragDeduplication, ticketMapping
# Check prescan sub-keys: extensions, excludeDirs, maxFunctionLines, coverageThreshold, complexityThreshold
```

Follow exact pattern from `agentRouting schema` and `reviewPipeline preset sub-keys` blocks.

2. Add `audit` to the `TOP_KEYS` array.

3. Run: `bash tests/test-config-schema.sh` -- expect all PASS, 0 FAIL.

4. `git add tests/test-config-schema.sh && git commit -m "test(audit): add audit schema validation checks"`

---

## Task 3: Create audit_prescan.py -- checks 1-6

**Files:**
- Create: `scripts/ops/audit_prescan.py`

### Steps

1. Create script based on `sentinel_prescan.py` pattern. Key differences: scans ALL project files (not just git diff), accepts `--mode=full`, reads `audit` config section.

```python
#!/usr/bin/env python3
"""Deterministic prescan for backlog-audit. Scans full project for 12 checks.
Usage:
    python scripts/ops/audit_prescan.py --config backlog.config.json --mode=full
"""
from __future__ import annotations
import argparse, json, os, re, subprocess, sys
from pathlib import Path
from collections import defaultdict

def get_project_files(extensions: list[str], exclude_dirs: list[str], root: str = ".") -> list[str]:
    """Walk project tree, filter by extensions, skip exclude_dirs."""
    # os.walk, filter by ext in extensions, skip dirs in exclude_dirs
    ...

def grep_files(files, pattern, label, category, severity="medium", exclude_patterns=None) -> list[dict]:
    """Same as sentinel_prescan.grep_files but with severity param."""
    ...

def check_secrets(files: list[str]) -> list[dict]:          # Check 1
def check_todos(files: list[str]) -> list[dict]:             # Check 2
def check_debug_leftovers(files: list[str]) -> list[dict]:   # Check 3
def check_mock_hardcoded(files: list[str]) -> list[dict]:    # Check 4
def check_long_functions(files: list[str], max_lines: int) -> list[dict]:  # Check 5
def check_dependency_vulns() -> list[dict]:                  # Check 6
    """Run npm audit --json if package.json exists, pip audit --json if requirements.txt."""
    ...
```

- Check 1-4: reuse `grep_files` with appropriate regex patterns (copy from sentinel but add mock/hardcoded IP patterns for check 4)
- Check 5: copy `check_long_functions` from sentinel_prescan.py
- Check 6: subprocess `npm audit --json` or `pip audit --format=json`, parse JSON output

2. Add `main()` with argparse: `--config`, `--mode` (default/full), `--checks` (comma-separated list to enable)
3. Output JSON: `{"scanned_files": N, "findings": [...], "summary": {"critical": N, "high": N, "medium": N, "low": N}}`
4. `git add scripts/ops/audit_prescan.py && git commit -m "feat(audit): create audit_prescan.py with checks 1-6"`

---

## Task 4: Create audit_prescan.py -- checks 7-12

**Files:**
- Modify: `scripts/ops/audit_prescan.py`

### Steps

Add 6 more check functions:

```python
def check_coverage_gaps(config: dict) -> list[dict]:         # Check 7
    """Parse coverage/coverage-summary.json (istanbul) or .coverage (pytest-cov).
    Flag files below coverageThreshold."""

def check_dead_code(files: list[str]) -> list[dict]:         # Check 8
    """Regex: unused imports (import X ... X never referenced in file).
    For Python: import re on 'import X' then grep X usage.
    For TS/JS: import { X } then grep X usage."""

def check_cyclomatic_complexity(files: list[str], threshold: int) -> list[dict]:  # Check 9
    """Count if/elif/else/for/while/case/catch/&&/|| per function.
    Flag functions exceeding threshold."""

def check_duplicate_code(files: list[str]) -> list[dict]:    # Check 10
    """Token-based: normalize whitespace, hash sliding windows of 10 lines.
    Flag blocks appearing 2+ times in different locations."""

def check_file_size_circular_deps(files: list[str]) -> list[dict]:  # Check 11
    """Flag files > 500 lines. Build import graph, detect cycles via DFS."""

def check_type_safety(files: list[str]) -> list[dict]:       # Check 12
    """Grep .ts/.tsx files for: 'any' type annotations, 'as T' casts, '!.' non-null assertions."""
```

Update `main()` to call all 12 checks, controlled by `--checks` flag and config enable/disable.

`git add scripts/ops/audit_prescan.py && git commit -m "feat(audit): add checks 7-12 to audit_prescan.py"`

---

## Task 5: Test audit_prescan.py

**Files:**
- Create: `tests/test_audit_prescan.py`

### Steps

1. Create pytest test file. Use `tmp_path` fixture to create a mini project with known violations:
   - `app.ts`: secret, console.log, TODO, `any` type, `as string` cast
   - `utils.py`: unused import, 100-line function, 15-branch function
   - `dup1.py` + `dup2.py`: identical 15-line blocks
   - `big.py`: 600-line file with circular import

2. One test function per check (12 tests) + 3 integration tests:
   - `test_check_{1..12}` -- each asserts correct findings count and severity
   - `test_json_output_format` -- verify scanned_files, findings, summary keys
   - `test_mode_full_scans_all_files` -- --mode=full scans all, not just git diff
   - `test_config_disables_checks` -- enabled:false skips audit

2. Run: `python3 -m pytest tests/test_audit_prescan.py -v`
3. Expected: all tests pass, output shows 14+ test cases.
4. `git add tests/test_audit_prescan.py && git commit -m "test(audit): add tests for all 12 prescan checks"`

---

## Task 6: Create SKILL.md

**Files:**
- Create: `skills/backlog-audit/SKILL.md`

### Steps

1. Create SKILL.md following sentinel SKILL.md pattern exactly. Frontmatter:

```yaml
---
name: backlog-audit
description: "Full project health audit: 12-check deterministic prescan + Haiku sweep + Sonnet deep analysis + Opus critical review + RAG dedup + ticket creation. 5-phase tiered model funnel ($1-3 vs $10-15 all-Opus). v1.0."
allowed-tools: Read, Glob, Grep, Bash, Write, Edit, Task, TeamCreate, TeamDelete, SendMessage, TaskCreate, TaskList, TaskUpdate, TaskGet
---
```

2. MODEL RULES section:

```
model: "haiku"   -> Phase 1 sweep agents (one per directory chunk)
model: "sonnet"  -> Phase 2 deep analysis agents
model: "opus"    -> Phase 3 critical review (only HIGH_RISK_PATTERNS)
model: "sonnet"  -> Phase 4 ticket write-agents
no model:        -> inherits parent
```

3. OUTPUT DISCIPLINE + WRITE-AGENT CHUNKING RULE (same as sentinel).

4. Configuration table mapping audit config keys to defaults.

5. MAIN FLOW (pseudocode):

```
PHASE 0: DETERMINISTIC PRESCAN ($0)
  Run: python3 "${CLAUDE_PLUGIN_ROOT}/scripts/ops/audit_prescan.py" --config backlog.config.json --mode=full
  Parse JSON -> prescan_findings[]

PHASE 0.5: RAG CONTEXT PREP ($0)
  IF ragPolicy.enabled AND audit.ragDeduplication:
    Query RAG for architecture rules, past audit findings
    Mark findings with similarity > 0.85 as duplicate_skipped

PHASE 1: HAIKU SWEEP (~$0.05-0.15)
  Group project files by directory into chunks
  TeamCreate("audit-{date}")
  FOR each chunk (parallel, max 10):
    Task(model: "haiku", prompt: <Haiku Sweep Template>)
  Collect findings, each with: severity, dimension, file, line, description, needs_deep_review bool

PHASE 2: SONNET DEEP ANALYSIS (~$0.20-0.80)
  Filter: only needs_deep_review:true OR severity high+
  FOR each flagged finding (parallel, max 5):
    Task(model: "sonnet", prompt: <Sonnet Deep Template>)
  Sonnet validates/rejects, merges related findings, adds needs_opus bool

PHASE 3: OPUS CRITICAL REVIEW (~$0.15-0.50)
  Filter: needs_opus:true OR HIGH_RISK_PATTERNS OR severity critical
  Task(model: "opus", prompt: <Opus Critical Template>)
  6-point checklist: type safety, error propagation, production readiness,
    semantic correctness, resource management, backward compat

PHASE 3.5: RAG DEDUPLICATION ($0)
  FOR each surviving finding:
    Query RAG similarity > 0.85 -> SKIP
    Similarity 0.60-0.85 -> flag "related to TICKET-ID"

PHASE 4: TICKET CREATION + SUMMARY
  Spawn parallel sonnet write-agents (max 5) via backlog-ticket logic
  Print console summary table (scanned files, findings by phase, cost, tickets)
  Append to .backlog-ops/usage-ledger.jsonl
  SendMessage shutdown_request -> TeamDelete
```

6. Include abbreviated prompt templates:

**Haiku Sweep Template:** Analyze this directory for 6 dimensions (architecture, security, bugs, performance, tests, hygiene). Include prescan findings as context. Output JSON array with needs_deep_review flag.

**Sonnet Deep Template:** Validate Haiku finding. Confirm or reject. If valid: root cause, fix, confidence 0-100, needs_opus flag. Group related findings.

**Opus Critical Template:** 6-point checklist review. Only for critical/security/HIGH_RISK_PATTERNS. Output: validated finding with production-ready fix recommendation.

7. Error handling table (same pattern as sentinel): config not found, audit disabled, RAG unreachable, agent timeout, ticket validation failure.

8. `git add skills/backlog-audit/SKILL.md && git commit -m "feat(audit): create SKILL.md with 5-phase tiered model funnel"`

---

## Task 7: Create CLAUDE.md + command + register

**Files:**
- Create: `skills/backlog-audit/CLAUDE.md`
- Create: `commands/audit.md`
- Modify: `.claude-plugin/plugin.json`

### Steps

1. Create `skills/backlog-audit/CLAUDE.md` following sentinel CLAUDE.md pattern:
   - Purpose: Full project health audit
   - Key Features: 12-check prescan, 3-tier LLM funnel, RAG dedup, ticket integration
   - Invocation: `/backlog-toolkit:audit`
   - Flow Overview (5 phases, one-liner each)
   - Cost Model table: Phase 0 $0, Phase 1 ~$0.10, Phase 2 ~$0.50, Phase 3 ~$0.30, Phase 4 ~$0.05
   - Related Files: SKILL.md, audit_prescan.py, design doc

2. Create `commands/audit.md` following `commands/sentinel.md` pattern exactly. Sections: description, Syntax (`/backlog-toolkit:audit [--dimensions=...]`), Parameters (`--dimensions`), Examples (basic + filtered), What it does (5-phase summary), Configuration (reference audit section), Related (SKILL.md, prescan, design doc).

3. In `.claude-plugin/plugin.json`, add `"./commands/audit.md"` to the `commands` array after sentinel.

4. Commit all three:
```bash
git add skills/backlog-audit/CLAUDE.md commands/audit.md .claude-plugin/plugin.json
git commit -m "feat(audit): add command, CLAUDE.md, and register in plugin.json"
```

---

## Task 8: End-to-end validation

**Files:**
- Test: `tests/test-config-schema.sh`
- Test: `scripts/ops/audit_prescan.py`
- Test: `tests/test_audit_prescan.py`
- Verify: `skills/backlog-audit/SKILL.md`
- Verify: `.claude-plugin/plugin.json`

### Steps

1. `bash tests/test-config-schema.sh` -- expect all PASS including new audit checks, 0 FAIL
2. `python3 scripts/ops/audit_prescan.py --help` -- expect usage text, exit 0
3. `python3 -m pytest tests/test_audit_prescan.py -v` -- expect all tests pass
4. Verify SKILL.md contains all 5 phases: `grep -c "PHASE" skills/backlog-audit/SKILL.md` -- expect >= 6
5. Verify command registered: `python3 -c "import json; d=json.load(open('.claude-plugin/plugin.json')); assert './commands/audit.md' in d['commands']"`
6. `git status` -- expect clean working tree
7. If any uncommitted changes: `git add -A && git commit -m "chore(audit): final cleanup"`

**Expected final output:**
```
=== Config Schema & Preset Validation ===
  ... all PASS ...
=== Results: NN passed, 0 failed ===

scripts/ops/audit_prescan.py --help:
  usage: audit_prescan.py [-h] [--config CONFIG] [--mode {default,full}] [--checks CHECKS]

tests/test_audit_prescan.py:
  14 passed in X.XXs

SKILL.md phases: 6+
plugin.json: audit command registered
git status: clean
```
