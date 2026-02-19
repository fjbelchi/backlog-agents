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
| Default gen model | `llmOps.routing.defaultGenerationModel` | `balanced` |
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
      IF response.results[0].similarity > 0.85 → mark finding as duplicate_skipped
    FOR each changed_file:
      Query RAG: {"query": "patterns in {file}", "n_results": 5}
      Store as rag_context[file]
    relevant_rules = Query RAG: {"query": "architecture rules for {changed_files}", "n_results": 5}
  IF RAG unreachable: skip silently, continue with direct file reads

PHASE 1: SPAWN REVIEWER TEAM
  commit_hash = run: git rev-parse --short HEAD
  author      = run: git log -1 --format="%an"
  date        = run: git log -1 --format="%ci"
  diff        = run: git diff HEAD~1..HEAD

  TeamCreate("sentinel-{commit_hash}")

  Spawn in PARALLEL (NO model: parameter):

  IF config.sentinel.reviewers.security:
    spawn security-reviewer:
      subagent_type: "security-engineer"
      team_name: "sentinel-{commit_hash}"
      name: "security-reviewer"
      prompt: <Security Reviewer Template below, filled with context>

  IF config.sentinel.reviewers.quality:
    spawn quality-reviewer:
      subagent_type: "code-quality"
      team_name: "sentinel-{commit_hash}"
      name: "quality-reviewer"
      prompt: <Quality Reviewer Template below, filled with context>

  Wait for both (5-minute timeout each)
  Collect findings from TaskList — each reviewer writes findings to their task
  reviewer_findings = parse JSON arrays from completed tasks

PHASE 2: CREATE TICKETS
  all_findings = [prescan_findings (non-duplicate)] + reviewer_findings

  FOR each finding:
    IF finding.duplicate_skipped: continue

    ticket_prefix = config.sentinel.ticketMapping[finding.category] or "TASK"
    auto_tags = []
    IF finding.category == "security" OR re.search(r"auth|crypto|inject|xss|token|secret", finding.description, re.I):
      auto_tags.append("SECURITY")
    IF re.search(r"architect|refactor|migrat|redesign|schema|breaking", finding.description, re.I):
      auto_tags.append("ARCH")

    Create ticket (inline, using backlog-ticket skill logic):
      - Read backlog.config.json for dataDir and ticketPrefixes
      - Auto-assign next sequential ID for ticket_prefix
      - Fill all required sections:
          title: first 80 chars of finding.description
          context: "Found in commit {commit_hash} ({author}, {date}) by backlog-sentinel v1.0"
          description: {finding.description}. File: {finding.file}, line {finding.line}.
                       Current code: {finding.current_code if available}
                       Suggested fix: {finding.suggested_fix if available}
          affected_files: [{finding.file}]
          acceptance_criteria:
            - [ ] AC-1: Issue at {finding.file}:{finding.line} is resolved
            - [ ] AC-2: Regression test added for this scenario
            - [ ] AC-3: No similar pattern introduced in nearby code
          tags: auto_tags
          batchEligible: true
          found_by: "backlog-sentinel-v1"
      - Run validation checks 1-3 (completeness, coherence, gaps)
      - Write to {config.backlog.dataDir}/pending/{ticket_prefix}-{NNN}.md

PHASE 3: LEARNING + CLEANUP + SUMMARY
  Write all findings to /tmp/sentinel-findings-{commit_hash}.json
  Run: python3 scripts/ops/sentinel_patterns.py \
         --findings /tmp/sentinel-findings-{commit_hash}.json \
         --config backlog.config.json \
         --propose-rules
  Clean up: rm /tmp/sentinel-findings-{commit_hash}.json

  Append to .backlog-ops/usage-ledger.jsonl:
  {"skill": "sentinel", "commit": "{commit_hash}", "tickets_created": N, "date": "YYYY-MM-DD"}

  Print summary:
  ─────────────────────────────────────────────────────
  sentinel complete — commit {commit_hash} ({author})
  ─────────────────────────────────────────────────────
  prescan ($0):    {N_prescan} findings
  reviewers (LLM): {N_llm} findings
  duplicates:      {N_dup} skipped
  ─────────────────────────────────────────────────────
  tickets created: {N_total} ({comma-separated IDs})
  ─────────────────────────────────────────────────────

  SendMessage shutdown_request to each teammate → TeamDelete

PHASE 3.5: GIT HOOK INSTALL (only on first direct invocation)
  IF config.sentinel.installGitHook:
    IF .git/hooks/pre-push does not exist:
      Write .git/hooks/pre-push:
        #!/bin/bash
        claude --skip-permissions -p "/backlog-toolkit:sentinel"
      chmod +x .git/hooks/pre-push
      Print: "Installed pre-push git hook — sentinel will run on every push"
```

---

## Reviewer Prompt Templates

### Security Reviewer

Fill placeholders before spawning:

```
You are a security code reviewer. Analyze the following git diff for security
vulnerabilities requiring code flow understanding.

AUTOMATED SCAN ALREADY FOUND (do NOT duplicate these):
{prescan_findings as JSON}

COMMIT: {commit_hash} by {author} on {date}
CHANGED FILES: {changed_files joined by comma}

GIT DIFF:
{git diff HEAD~1..HEAD — full output}

RELEVANT CODE SNIPPETS (from RAG, may be empty):
{rag_context joined}

ARCHITECTURE/SECURITY RULES:
{relevant_rules or "No rules file configured"}

Analyze ONLY findings that require understanding code flow:
- Auth bypass / privilege escalation through logic errors
- Injection vulnerabilities not caught by static regex
- Insecure cryptographic choices (weak algo, bad IV, etc.)
- Sensitive data exposure through logic paths

Write your findings to your assigned task using TaskUpdate.
Use this EXACT JSON format in the task description field:

[
  {
    "category": "security",
    "severity": "high|medium|low",
    "file": "path/to/file",
    "line": 42,
    "description": "One sentence describing the vulnerability",
    "current_code": "the problematic line",
    "suggested_fix": "how to fix it"
  }
]

If no findings: write [] to the task.
```

### Quality Reviewer

```
You are a code quality reviewer. Analyze the following git diff for bugs and
architecture violations requiring code context to understand.

AUTOMATED SCAN ALREADY FOUND (do NOT duplicate these):
{prescan_findings as JSON}

COMMIT: {commit_hash} by {author} on {date}
CHANGED FILES: {changed_files joined by comma}

GIT DIFF:
{git diff HEAD~1..HEAD — full output}

RELEVANT CODE SNIPPETS (from RAG, may be empty):
{rag_context joined}

ARCHITECTURE RULES:
{relevant_rules or "No rules file configured"}

Analyze ONLY findings that require code context:
- Race conditions and async bugs in complex flows
- Null/undefined edge cases not caught by type checker
- Architecture violations (patterns defined in the rules above)
- Performance anti-patterns requiring data shape awareness (complex N+1, etc.)

Write your findings to your assigned task using TaskUpdate.
Use this EXACT JSON format:

[
  {
    "category": "bug|architecture|techDebt",
    "severity": "high|medium|low",
    "file": "path/to/file",
    "line": 42,
    "description": "One sentence describing the issue",
    "current_code": "the problematic code",
    "suggested_fix": "how to fix it"
  }
]

If no findings: write [] to the task.
```

---

## Error Handling

| Situation | Action |
|-----------|--------|
| `backlog.config.json` not found | Stop: "Run /backlog-toolkit:init first" |
| `sentinel.enabled: false` | Exit silently with message |
| RAG server unreachable | Skip RAG steps, continue with full file reads |
| Reviewer timeout (>5 min) | Log warning, continue with findings from other reviewer |
| `git diff HEAD~1..HEAD` empty | Print "No changes in HEAD — nothing to analyze" and exit |
| Ticket creation fails validation | Log error for that finding, continue with next |
| Pattern ledger write fails | Log warning, continue (non-critical) |

---

## Start

1. Read `backlog.config.json`
2. Run deterministic prescan → Phase 0
3. RAG context prep → Phase 0.5
4. Spawn reviewer team → Phase 1
5. Create tickets for all findings → Phase 2
6. Update pattern ledger + print summary → Phase 3
7. Install git hook if first run → Phase 3.5
