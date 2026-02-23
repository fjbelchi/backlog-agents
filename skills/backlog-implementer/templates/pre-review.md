<!-- Extracted from SKILL.md for v9.0. Primary: scripts/implementer/pre_review.py. This is the LLM fallback. -->

## Git Diff
{GIT_DIFF}

## Test Results
{TEST_OUTPUT}

## Lint Output
{LINT_OUTPUT}

Checklist (mark [x] or [ ]):
- All imports used, no missing imports
- Lint output is clean (0 warnings)
- All tests pass
- No debug artifacts (console.log, TODO, FIXME, HACK)
- Format is consistent with surrounding code
- Error messages match project language (check existing patterns)
