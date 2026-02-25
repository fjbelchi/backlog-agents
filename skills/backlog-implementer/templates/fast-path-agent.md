<!-- fast-path-agent.md v10.0. Used for trivial (Sonnet) and simple impl-phase (Sonnet). -->

You are implementing ticket {TICKET_ID}. Execute ALL 4 gates sequentially.

## TICKET
{full_ticket_markdown}

## AFFECTED FILES (pre-loaded — do NOT re-read these)
{file_contents_pre_read_by_leader}

## CODE RULES
{code_rules_content}

## COMMANDS
Test: {testCommand}
Lint: {lintCommand}
TypeCheck: {typeCheckCommand}

## EXECUTE THESE 4 GATES IN ORDER:

### Gate 1: PLAN (pre-generated)
{plan_generator_output}
Review the plan above. If anything is unclear, note it but proceed with implementation.

### Gate 2: IMPLEMENT (TDD)
1. Write failing test(s) first (min 3: happy path + error + edge)
2. Run: {testCommand} — verify tests fail
3. Implement minimal code to make tests pass
4. Run: {testCommand} — verify tests pass

### Gate 3: LINT
Run: {lintCommand} 2>&1 | python3 {CLAUDE_PLUGIN_ROOT}/scripts/implementer/lint_fixer.py --format {lint_format}
If output shows `"clean": false`: fix ONLY the reported error lines. Re-run max 3 attempts.
If still failing after 3: STOP and report.

### Gate 4: SELF-REVIEW
Check against acceptance criteria:
{acceptance_criteria_from_ticket}
Check code rules compliance. Report any issues found and fix them.

### Gate 5: COMMIT
Stage ONLY the files you modified:
git add {specific_files}
git commit with conventional format: "{type}({area}): {description}\n\nCloses: {TICKET_ID}"

IRON LAWS: Never use --no-verify. Never use type suppressions. Never skip hooks.
