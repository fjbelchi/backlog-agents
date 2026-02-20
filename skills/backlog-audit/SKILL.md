---
name: backlog-audit
description: "Full project health audit: 12-check deterministic prescan ($0) + Haiku sweep + Sonnet deep analysis + Opus critical review + RAG dedup + ticket creation via backlog-ticket. 5-phase tiered model funnel. v1.0."
allowed-tools: Read, Glob, Grep, Bash, Write, Edit, Task, TeamCreate, TeamDelete, SendMessage, TaskCreate, TaskList, TaskUpdate, TaskGet
---

# Backlog Audit v1.0

Full project health audit. 5-phase tiered model funnel: deterministic prescan, Haiku sweep, Sonnet deep analysis, Opus critical review, and ticket creation. Runs once and exits.

## MODEL RULES FOR TASK TOOL

```
model: "haiku"   → Phase 1: sweep agents (one per directory chunk)
model: "sonnet"  → Phase 2: deep analysis agents
model: "opus"    → Phase 3: critical review (only HIGH_RISK findings)
model: "sonnet"  → Phase 4: ticket write-agents
no model:        → inherits parent session model

NEVER pass model: to agents that should inherit the parent model.
```

## OUTPUT DISCIPLINE

```
- Never create ticket content inline in your response
- Max response length: ~30 lines
- Phase 4 ticket creation → parallel sonnet write-agents (max 5 at once)
```

## WRITE-AGENT CHUNKING RULE

Write-agents MUST write files in chunks to avoid hitting the output token limit:
```
1. Write tool    → first chunk (~40-50 lines): creates the file
2. Bash cat >>   → each subsequent chunk (~40-50 lines): appends sections
Never generate more than 50 lines of file content per tool call.
```

---

## Configuration

Reads from `backlog.config.json` at project root.

| What | Config Path | Default |
|------|-------------|---------|
| Audit enabled | `audit.enabled` | `true` |
| Prescan: run linter | `audit.prescan.runLinter` | `true` |
| Prescan: run tests | `audit.prescan.runTests` | `true` |
| Prescan: detect hardcoded | `audit.prescan.detectHardcoded` | `true` |
| Prescan: max function lines | `audit.prescan.maxFunctionLines` | `80` |
| Prescan: detect dead code | `audit.prescan.detectDeadCode` | `true` |
| Audit dimensions | `audit.dimensions` | `["security","architecture","performance","reliability","maintainability","observability"]` |
| RAG deduplication | `audit.ragDeduplication` | `true` |
| Ticket mapping | `audit.ticketMapping` | `{security:BUG, architecture:TASK, performance:TASK, reliability:BUG, maintainability:TASK, observability:TASK}` |
| RAG server | `llmOps.ragPolicy.serverUrl` | `http://localhost:8001` |

---

## MAIN FLOW

```
STARTUP
  config = read("backlog.config.json")
  if not config.audit.enabled: exit "Audit disabled in config"
  date = YYYY-MM-DD format of today

PHASE 0: DETERMINISTIC PRESCAN ($0)
  Resolve CLAUDE_PLUGIN_ROOT:
    IF $CLAUDE_PLUGIN_ROOT set → use it
    ELSE → Glob("**/skills/backlog-audit/SKILL.md"), derive root from match
  Run: python3 "${CLAUDE_PLUGIN_ROOT}/scripts/ops/audit_prescan.py" \
    --config backlog.config.json --mode full
  Parse JSON output → prescan_findings[]
  Print: "Phase 0 complete: {N} findings across {M} files ($0.00)"

PHASE 0.5: RAG CONTEXT PREP ($0)
  IF config.llmOps.ragPolicy.enabled:
    architecture_rules = Query RAG: {"query": "architecture rules", "n_results": 5}
    past_findings = Query RAG: {"query": "audit findings", "n_results": 10}
  IF RAG unreachable: skip silently, continue without RAG context

PHASE 1: HAIKU SWEEP (~$0.05-0.15)
  project_files = Glob all source files (exclude node_modules, .git, dist, build)
  Group files by top-level directory → chunks[]
  TeamCreate("audit-{date}")

  FOR each chunk (parallel, max 10 at once):
    Task(
      model: "haiku",
      subagent_type: "general-purpose",
      team_name: "audit-{date}",
      name: "sweep-{dir}",
      prompt: <Haiku Sweep Template filled with:
        chunk.files, prescan_findings for those files,
        config.audit.dimensions, architecture_rules>
    )

  Wait for all agents, collect findings
  haiku_findings = parse JSON from each agent
  Print: "Phase 1 complete: {N} findings from Haiku sweep"

PHASE 2: SONNET DEEP ANALYSIS (~$0.20-0.80)
  deep_queue = [f for f in haiku_findings
    if f.needs_deep_review OR f.severity in ["high","critical"]]

  FOR each flagged finding (parallel, max 5):
    Task(
      model: "sonnet",
      subagent_type: "general-purpose",
      prompt: <Sonnet Deep Template filled with:
        finding, file content around finding.line,
        rag_context, architecture_rules>
    )

  Sonnet validates or rejects each finding
  Groups related findings sharing root cause
  Adds needs_opus flag for critical/security patterns

  validated_findings = [f for f if f.validated]
  Print: "Phase 2: {N} validated, {M} rejected"

PHASE 3: OPUS CRITICAL REVIEW (~$0.15-0.50)
  HIGH_RISK_PATTERNS = [serialization, db_schema, auth,
    error_handling, external_api, concurrency]

  opus_queue = [f for f in validated_findings
    if f.needs_opus OR f.matches(HIGH_RISK_PATTERNS)
    OR f.severity == "critical" OR f.ticket_type == "SEC"]

  IF len(opus_queue) > 0:
    Task(
      model: "opus",
      subagent_type: "general-purpose",
      prompt: <Opus Critical Template with all opus_queue findings>
    )

  Print: "Phase 3: {N} critically reviewed by Opus"

PHASE 3.5: RAG DEDUPLICATION ($0)
  IF config.audit.ragDeduplication AND config.llmOps.ragPolicy.enabled:
    FOR each finding in all findings so far:
      Query RAG: {"query": finding.description,
        "filter": {"type": "ticket"}, "n_results": 3}
      IF similarity > 0.85 → mark duplicate_skipped
      IF similarity 0.60-0.85 → add "related_to" field
  Print: "Phase 3.5: {N} duplicates skipped"

PHASE 4: TICKET CREATION + SUMMARY
  all_findings = prescan_findings + haiku_findings + validated_findings
  Remove findings marked duplicate_skipped
  SEQ = 1

  FOR each finding:
    ticket_prefix = config.audit.ticketMapping[finding.dimension] or "TASK"
    ticket_id = "AUDIT-{ticket_prefix}-{date}-{SEQ:03d}"
    SEQ += 1

  Spawn parallel sonnet write-agents (max 5 at once):
    FOR each batch of up to 5 findings:
      FOR each finding in batch:
        Task(
          model: "sonnet",
          subagent_type: "general-purpose",
          prompt: """
You are a write-agent. Create a backlog ticket file using Write tool.
Do NOT output ticket content in your response.

Write to: {config.backlog.dataDir}/pending/{ticket_id}.md

Ticket content:
  id: {ticket_id}
  title: {first 80 chars of finding.description}
  status: pending
  priority: {critical/high → high, medium → medium, low → low}
  dimension: {finding.dimension}
  tags: [AUDIT, {finding.dimension}]
  batchEligible: true
  found_by: backlog-audit-v1
  phase_found: {finding.phase}
  confidence: {finding.confidence}
  description: {finding.description}
    File: {finding.file}, line {finding.line}
    Current code: {finding.current_code}
    Suggested fix: {finding.suggested_fix}
    Root cause: {finding.root_cause or "N/A"}
  affected_files: [{finding.file}]
  acceptance_criteria:
    - [ ] AC-1: Issue at {finding.file}:{finding.line} is resolved
    - [ ] AC-2: Regression test covers this scenario
    - [ ] AC-3: No similar pattern in codebase

After writing, return ONLY:
{"file": "{path}", "ticket_id": "{ticket_id}", "status": "ok"}
"""
        )
      Wait for batch to complete

  Append to .backlog-ops/usage-ledger.jsonl:
  {"skill":"audit","date":"{date}","tickets_created":N,
   "phases":{"prescan":N,"haiku":N,"sonnet":N,"opus":N},
   "duplicates_skipped":N,"estimated_cost":"$X.XX"}

  Print summary:
  ═══════════════════════════════════════════════════
    PROJECT AUDIT: {project.name} | {date}
  ═══════════════════════════════════════════════════
    Scanned: {N} files | 12 deterministic checks
    Findings by phase:
      Phase 0 (prescan):  {N} ($0.00)
      Phase 1 (Haiku):    {N} (~$X.XX)
      Phase 2 (Sonnet):   {N} (~$X.XX)
      Phase 3 (Opus):     {N} (~$X.XX)
    Duplicates skipped: {N}
    Total: {N} findings → {N} tickets created
    Estimated cost: ~$X.XX
  ═══════════════════════════════════════════════════

  SendMessage shutdown_request to each teammate → TeamDelete
```

---

## Prompt Templates

### Haiku Sweep Template

Fill placeholders before spawning each sweep agent:

```
You are an audit sweep agent. Analyze the following files for project health issues.

DIMENSIONS TO CHECK: {config.audit.dimensions as comma-separated list}
PRESCAN ALREADY FOUND (do NOT duplicate): {prescan_findings for this chunk as JSON}
ARCHITECTURE RULES: {architecture_rules or "None available"}

FILES TO ANALYZE:
{chunk.files — list of file paths}

For each file, read it and check all configured dimensions.
(security=injection/auth/secrets, architecture=layering/circular-deps,
performance=N+1/unbounded-loops, reliability=error-handling/race-conditions,
maintainability=dead-code/duplication, observability=logging/metrics)

Output ONLY a JSON array:
[
  {
    "dimension": "security|architecture|performance|reliability|maintainability|observability",
    "severity": "critical|high|medium|low",
    "file": "path/to/file",
    "line": 42,
    "description": "One sentence",
    "current_code": "problematic snippet",
    "suggested_fix": "how to fix",
    "needs_deep_review": true|false,
    "confidence": 0.0-1.0
  }
]

Set needs_deep_review:true for anything requiring cross-file analysis,
subtle logic bugs, or severity >= high. If no findings: return [].
```

### Sonnet Deep Template

```
You are a deep analysis agent. Validate or reject this Haiku finding.

FINDING: {finding as JSON}
SOURCE CODE: {50 lines around finding.line from finding.file}
RAG CONTEXT: {rag_context or "None"}
ARCHITECTURE RULES: {architecture_rules or "None"}

1. Read actual source to verify  2. TRUE or FALSE positive?
3. If true: root cause + fix     4. Group related findings
5. Set needs_opus:true if matches: serialization, db_schema, auth,
   error_handling, external_api, concurrency

Output ONLY JSON:
{"validated":bool, "original_finding":id, "confidence":0-1,
 "root_cause":"...", "suggested_fix":"...", "related_findings":[],
 "needs_opus":bool, "rejection_reason":"if rejected"}
```

### Opus Critical Template

```
You are a critical review agent. Review these high-risk validated findings.

FINDINGS: {opus_queue as JSON array}

6-point checklist per finding:
1. TYPE SAFETY — runtime type errors?  2. ERROR PROPAGATION — silent cascades?
3. PRODUCTION READINESS — survives 10x? 4. SEMANTIC CORRECTNESS — intended behavior?
5. RESOURCE MANAGEMENT — leaks?        6. BACKWARD COMPAT — breaks consumers?

Output ONLY JSON array:
[{"finding_id":"id",
  "checklist":{"type_safety":"pass|fail|na","error_propagation":"...",
    "production_readiness":"...","semantic_correctness":"...",
    "resource_management":"...","backward_compatibility":"..."},
  "verdict":"confirmed|downgraded|escalated",
  "adjusted_severity":"critical|high|medium|low","notes":"..."}]
```

---

## Error Handling

| Situation | Action |
|-----------|--------|
| `backlog.config.json` not found | Stop: "Run /backlog-toolkit:init first" |
| `audit.enabled: false` | Exit silently with message |
| RAG server unreachable | Skip RAG steps, continue without context |
| Haiku agent timeout (>3 min) | Log warning, continue with findings from other agents |
| Sonnet validation timeout (>5 min) | Log warning, mark finding as unvalidated, skip |
| Opus review timeout (>5 min) | Log warning, keep Sonnet validation as final |
| Ticket creation fails | Log error for that finding, continue with next |
| Prescan script not found | Stop: "Plugin installation incomplete — missing audit_prescan.py" |

---

## Start

1. Read `backlog.config.json` — verify `audit.enabled`
2. Run deterministic prescan (12 checks) -- Phase 0
3. RAG context prep -- Phase 0.5
4. Haiku sweep (parallel per directory) -- Phase 1
5. Sonnet deep analysis (parallel per finding) -- Phase 2
6. Opus critical review (high-risk only) -- Phase 3
7. RAG deduplication -- Phase 3.5
8. Create tickets + print summary -- Phase 4
