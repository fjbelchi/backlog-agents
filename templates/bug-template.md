---
id: BUG-NNN
title: Actionable description
status: pending
priority: medium
severity: medium
environment: all
created: YYYY-MM-DD
updated: YYYY-MM-DD
assignee: unassigned
blockers: []
depends_on: []
shared_files: []
related_docs: []
---

# BUG-NNN: Title

## Context
<!-- Why this bug matters and how it affects the system -->

## Description
<!-- What is broken, with enough detail to reproduce and fix -->

## Steps to Reproduce
1. Step one
2. Step two
3. Step three

## Expected Behavior
<!-- What should happen -->

## Actual Behavior
<!-- What happens instead -->

## Affected Files
| File | Action | Description |
|------|--------|-------------|
| path/to/file | create/modify/delete | What changes |

## Acceptance Criteria
- [ ] AC-1: Bug no longer reproducible following the steps above
- [ ] AC-2: Regression test added covering this scenario
- [ ] AC-3: ...

## Test Strategy
### Regression Tests
- test: "should not reproduce BUG-NNN when Y" → verifies the fix holds
- test: "should handle edge case Z" → verifies related paths

### Unit Tests
- test: "should X when Y" → verifies Z

### Integration Tests
- test: "X interacts with Y correctly" → verifies flow

### Verification Commands
```bash
# Commands to verify the fix
```

## Dependencies
| Ticket | What it needs | Status |
|--------|---------------|--------|
| (none) | — | — |

## Implementation Notes
<!-- Root cause analysis, patterns, constraints -->

## History
| Date | Change | Author |
|------|--------|--------|
| YYYY-MM-DD | Created | claude-code |
