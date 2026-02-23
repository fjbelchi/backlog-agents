<!-- Extracted from SKILL.md for v9.0. Primary: scripts/implementer/fast_path.py. This is the LLM fallback. -->

You are implementing ticket {TICKET_ID}. Execute ALL 5 gates sequentially.

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

## EXECUTE THESE 5 GATES IN ORDER:

### Gate 1: PLAN
Write a 3-5 bullet implementation plan. Do not create a separate file.

### Gate 2: IMPLEMENT (TDD)
1. Write failing test(s) first (min 3: happy path + error + edge)
2. Run: {testCommand} — verify tests fail
3. Implement minimal code to make tests pass
4. Run: {testCommand} — verify tests pass

### Gate 3: LINT
Run: {lintCommand} and {typeCheckCommand}
If errors: fix and re-run (max 3 attempts). If still failing after 3: STOP and report.

### Gate 4: SELF-REVIEW
Check against acceptance criteria:
{acceptance_criteria_from_ticket}
Check code rules compliance. Report any issues found and fix them.

### Gate 5: COMMIT
Stage ONLY the files you modified:
git add {specific_files}
git commit with conventional format: "{type}({area}): {description}\n\nCloses: {TICKET_ID}"

IRON LAWS: Never use --no-verify. Never use type suppressions. Never skip hooks.
