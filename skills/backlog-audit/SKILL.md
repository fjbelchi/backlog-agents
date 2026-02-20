---
name: backlog-audit
description: "Full project health audit: 12-check deterministic prescan ($0) + cascading Haiku→Sonnet→Opus funnel + RAG dedup + batch ticket creation. 15-call budget. v2.0."
allowed-tools: Read, Glob, Grep, Bash, Write, Edit, Task, TeamCreate, TeamDelete, SendMessage, TaskCreate, TaskList, TaskUpdate, TaskGet
---

# Backlog Audit v2.0

Full project health audit. Cascading Haiku→Sonnet→Opus funnel: deterministic prescan, Haiku full sweep, Sonnet deep analysis on suspects, Opus critical review on escalations, and batch ticket creation. 15-call budget. Runs once and exits.

## MODEL RULES FOR TASK TOOL

```
model: "haiku"   → Phase 1: full file sweep (max 4 batched agents)
                   Phase 4: ticket creation (1-2 batched agents)
model: "sonnet"  → Phase 2: deep analysis on Haiku suspects (1-3 batched agents)
model: "opus"    → Phase 3: critical review on Sonnet escalations (0-1 agent)

CALL BUDGET: 15 max.
NEVER spawn one agent per finding. ALWAYS batch.
```

## OUTPUT DISCIPLINE

```
- Never create ticket content inline in your response
- Max response length: ~30 lines
- Phase 4 ticket creation → parallel haiku write-agents (max 2 at once)
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

PHASE 1: HAIKU FULL SWEEP (~$0.50, max 4 agents)
  project_files = Glob all source files (exclude node_modules, .git, dist, build)
  Group files into mega-chunks (~750 files per chunk, max 4 chunks)
  TeamCreate("audit-{date}")

  FOR each chunk (parallel, max 4 at once):
    Task(
      model: "haiku",
      subagent_type: "general-purpose",
      team_name: "audit-{date}",
      name: "sweep-{chunk_index}",
      prompt: <Haiku Sweep Template filled with:
        chunk.files, prescan_findings for those files,
        config.audit.dimensions, architecture_rules>
    )

  Wait for all agents, collect findings
  haiku_findings = parse JSON from each agent

  Classify findings:
    high_confidence = [f for f in haiku_findings
      if f.confidence >= 0.8 AND f.severity in ["low","medium"] AND NOT f.suspect]
      → these go DIRECT to Phase 4 tickets
    suspect_findings = [f for f in haiku_findings if f.suspect]
      → these pass to Sonnet in Phase 2

  Print: "Phase 1 complete: {N} findings ({M} high-confidence, {K} suspects for Sonnet)"

PHASE 2: SONNET DEEP ANALYSIS (~$0.30-0.80, 1-3 agents)
  IF len(suspect_findings) == 0: skip Phase 2

  Batch suspect_findings into 1-3 prompts (NOT one per finding)
  FOR each batch (parallel, max 3):
    Task(
      model: "sonnet",
      subagent_type: "general-purpose",
      team_name: "audit-{date}",
      name: "deep-{batch_index}",
      prompt: <Sonnet Deep Template filled with:
        batch of suspect findings, source code around each,
        rag_context, architecture_rules>
    )

  Sonnet does TWO things per batch:
    1. Validates or rejects each Haiku suspect
    2. Discovers NEW issues on suspect files (cross-file, architectural, subtle logic)

  Output per finding:
    - validated/rejected with confidence
    - root_cause + fix for validated findings
    - NEW findings Sonnet discovered
    - escalate_to_opus: true for matches: serialization, db_schema, auth,
      error_handling, external_api, concurrency, OR severity == critical

  validated_findings = [f for f if f.validated]
  opus_queue = [f for f in validated_findings if f.escalate_to_opus]
  Print: "Phase 2: {N} validated, {M} rejected, {K} escalated to Opus"

PHASE 3: OPUS CRITICAL REVIEW (~$0-0.90, 0-1 agent)
  IF len(opus_queue) == 0: skip Phase 3 (0 calls)

  Task(
    model: "opus",
    subagent_type: "general-purpose",
    team_name: "audit-{date}",
    name: "opus-review",
    prompt: <Opus Critical Template with ALL opus_queue findings in single batch>
  )

  Opus does TWO things:
    1. Reviews Sonnet escalations — 6-point checklist
    2. Focuses on own expertise — concurrency, distributed systems, security edge cases

  Output: confirmed/downgraded/escalated verdicts with adjusted severity
  Print: "Phase 3: {N} critically reviewed by Opus"

PHASE 3.5: RAG DEDUPLICATION ($0)
  IF config.audit.ragDeduplication AND config.llmOps.ragPolicy.enabled:
    FOR each finding in all findings so far:
      Query RAG: {"query": finding.description,
        "filter": {"type": "ticket"}, "n_results": 3}
      IF similarity > 0.85 → mark duplicate_skipped
      IF similarity 0.60-0.85 → add "related_to" field
  Print: "Phase 3.5: {N} duplicates skipped"

PHASE 4: HAIKU TICKET CREATION + SUMMARY (~$0.30, 1-2 agents)
  all_findings = prescan_findings + high_confidence + validated_findings
  Remove findings marked duplicate_skipped
  SEQ = 1

  FOR each finding:
    ticket_prefix = config.audit.ticketMapping[finding.dimension] or "TASK"
    ticket_id = "AUDIT-{ticket_prefix}-{date}-{SEQ:03d}"
    SEQ += 1

  Batch ALL findings into 1-2 Haiku write-agents (up to 8 tickets per agent):
    FOR each batch:
      Task(
        model: "haiku",
        subagent_type: "general-purpose",
        team_name: "audit-{date}",
        name: "tickets-{batch_index}",
        prompt: <Haiku Ticket Writer Template filled with batch of findings>
      )

  Append to .backlog-ops/usage-ledger.jsonl:
  {"skill":"audit","date":"{date}","tickets_created":N,
   "phases":{"prescan":N,"haiku":N,"sonnet":N,"opus":N},
   "duplicates_skipped":N}

  Print summary:
  ═══════════════════════════════════════════════════
    PROJECT AUDIT: {project.name} | {date}
  ═══════════════════════════════════════════════════
    Scanned: {N} files | 12 deterministic checks
    Findings by phase:
      Phase 0 (prescan):  {N} ($0.00)
      Phase 1 (Haiku):    {N}
      Phase 2 (Sonnet):   {N}
      Phase 3 (Opus):     {N}
    Duplicates skipped: {N}
    Total: {N} findings → {N} tickets created
    API calls used: {N} / 15 budget
    Run /cost for actual spend
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
{chunk.files — list of file paths, ~750 files per chunk}

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
    "confidence": 0.0-1.0,
    "suspect": true|false
  }
]

Set suspect:true on anything you are NOT 100% sure about OR severity >= high.
High-confidence (>=0.8), low/medium severity, non-suspect findings go direct to tickets.
Suspect findings get passed to Sonnet for validation.
If no findings: return [].
```

### Sonnet Deep Template

```
You are a deep analysis agent. Validate Haiku suspects AND discover new issues.

SUSPECT FINDINGS FROM HAIKU: {batch of suspect findings as JSON array}
ARCHITECTURE RULES: {architecture_rules or "None"}
RAG CONTEXT: {rag_context or "None"}

For EACH suspect finding:
1. Read actual source code to verify
2. TRUE or FALSE positive?
3. If true: determine root_cause + suggested_fix
4. Set escalate_to_opus:true if matches: serialization, db_schema, auth,
   error_handling, external_api, concurrency, OR severity == critical

ALSO: Do your own deeper analysis on the suspect files:
- Cross-file dependency issues
- Architectural violations
- Subtle logic bugs Haiku might miss
- Include any NEW findings you discover

Output ONLY JSON:
{
  "validated": [
    {"original_finding": {index}, "validated": true, "confidence": 0-1,
     "root_cause": "...", "suggested_fix": "...", "escalate_to_opus": bool,
     "adjusted_severity": "critical|high|medium|low"}
  ],
  "rejected": [
    {"original_finding": {index}, "validated": false, "rejection_reason": "..."}
  ],
  "new_findings": [
    {"dimension": "...", "severity": "...", "file": "...", "line": N,
     "description": "...", "root_cause": "...", "suggested_fix": "...",
     "confidence": 0-1, "escalate_to_opus": bool}
  ]
}
```

### Opus Critical Template

```
You are a critical review agent. Review these high-risk validated findings.

FINDINGS: {opus_queue as JSON array}

6-point checklist per finding:
1. TYPE SAFETY — runtime type errors?  2. ERROR PROPAGATION — silent cascades?
3. PRODUCTION READINESS — survives 10x? 4. SEMANTIC CORRECTNESS — intended behavior?
5. RESOURCE MANAGEMENT — leaks?        6. BACKWARD COMPAT — breaks consumers?

ALSO: Apply your own expertise to the escalated code:
- Concurrency and distributed systems edge cases
- Security boundary violations
- Subtle serialization/deserialization issues
- Resource exhaustion scenarios

Output ONLY JSON array:
[{"finding_id":"id",
  "checklist":{"type_safety":"pass|fail|na","error_propagation":"...",
    "production_readiness":"...","semantic_correctness":"...",
    "resource_management":"...","backward_compatibility":"..."},
  "verdict":"confirmed|downgraded|escalated",
  "adjusted_severity":"critical|high|medium|low","notes":"..."}]
```

### Haiku Ticket Writer Template

```
You are a ticket write-agent. Create backlog ticket files using Write tool.
Do NOT output ticket content in your response.

FINDINGS TO WRITE (up to 8):
{batch of findings as JSON array with ticket_id pre-assigned}

For EACH finding, write to: {config.backlog.dataDir}/pending/{ticket_id}.md

Ticket format:
  id: {ticket_id}
  title: {first 80 chars of finding.description}
  status: pending
  priority: {critical/high → high, medium → medium, low → low}
  dimension: {finding.dimension}
  tags: [AUDIT, {finding.dimension}]
  batchEligible: true
  found_by: backlog-audit-v2
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

Use Write tool chunking rule: max 50 lines per tool call.
After writing ALL tickets, return ONLY:
[{"file": "{path}", "ticket_id": "{ticket_id}", "status": "ok"}, ...]
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
4. Haiku full sweep (4 mega-chunk agents) -- Phase 1
5. Sonnet deep analysis (1-3 agents, suspects only) -- Phase 2
6. Opus critical review (0-1 agent, escalated only) -- Phase 3
7. RAG deduplication -- Phase 3.5
8. Haiku ticket creation + print summary -- Phase 4
