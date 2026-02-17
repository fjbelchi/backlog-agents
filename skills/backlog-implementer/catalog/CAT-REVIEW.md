## CAT-REVIEW: Multi-Pass Code Review

Structured review process that catches real bugs without drowning in noise.

### 3-Pass Review Structure

1. **Pass 1: Project Rules Compliance.** Read the project's CLAUDE.md and code rules file (if configured). Check every changed file against these rules. Flag violations with the specific rule name and file:line reference.

2. **Pass 2: Bug Detection in Changed Code.** Review ONLY the lines that were added or modified. Do not report pre-existing issues in unchanged code. Look for: logic errors, off-by-one, null dereference, unhandled promise rejections, race conditions, resource leaks, incorrect error handling.

3. **Pass 3: Test Coverage and Quality.** Verify tests exist for new behavior. Check that tests assert meaningful values (not just `toBeDefined()`). Confirm happy path, error path, and edge case coverage. Flag untested code paths.

### Confidence Scoring

4. **Rate every finding 0-100.** 0 = wild guess, likely false positive. 25 = somewhat confident, might be intentional. 50 = moderately confident, worth investigating. 75 = highly confident, real and important. 100 = absolutely certain, will cause a bug.

5. **Only report findings at or above the confidence threshold.** Default threshold is 80. Below-threshold findings are noise that wastes implementer time. When in doubt, raise the threshold rather than lower it.

6. **Include file:line references for every finding.** A finding without a location is not actionable. Format: `src/services/user.ts:42` followed by the issue description.

### Severity Classification

7. **Critical (must fix before commit).** Security vulnerabilities, data loss risk, crashes, broken functionality, Iron Law violations. These block the commit.

8. **Important (should fix before commit).** Missing error handling, incomplete test coverage, performance issues with user impact, code rule violations. These should be fixed but can be justified.

9. **Suggestion (nice to have).** Style improvements, minor refactors, documentation gaps. These are optional and should not block the commit.

### Review Output Format

10. **Structure the review as a list of findings, not prose.** Each finding: severity, confidence score, file:line, description, and suggested fix.

11. **End with a verdict: APPROVED or CHANGES_REQUESTED.** APPROVED means zero Critical findings and all Important findings addressed or justified. CHANGES_REQUESTED must list exactly what needs to change.

12. **Limit review rounds to 3.** After 3 rejections, mark the ticket as `review-blocked` and escalate to the leader. Do not enter infinite review loops.
