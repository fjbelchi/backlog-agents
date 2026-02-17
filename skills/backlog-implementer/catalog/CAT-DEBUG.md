## CAT-DEBUG: Systematic Debugging

Hypothesis-driven approach to finding and fixing bugs with minimal collateral damage.

### Hypothesis First

1. **Form a hypothesis BEFORE investigating code.** Read the bug report, error message, or failing test. State what you think is wrong and why. This prevents aimless code wandering.

2. **Design a test for your hypothesis.** Before changing any code, write a test that would pass if your hypothesis is correct and the bug is present. This test becomes your regression test.

3. **If evidence contradicts your hypothesis, form a new one.** Do not force-fit evidence to your theory. Discard the hypothesis and start fresh with the new data.

### Evidence Collection

4. **Gather data, do not guess.** Read error logs, stack traces, and test output. Use `git log --oneline -10 -- path/to/file` to check recent changes in affected files. Use `git diff HEAD~5 -- path/to/file` to see what changed.

5. **Reproduce the bug before fixing it.** Write a failing test that demonstrates the exact bug behavior. If you cannot reproduce it, you cannot verify the fix.

6. **Use the 5-Whys technique for root cause analysis.** Ask "why?" at each level until you reach the actual root cause, not just the symptom. Fix the root cause, not the symptom.

### Git History Mining

7. **Check recent commits in affected files.** Bugs often correlate with recent changes. Use `git log --oneline -10 -- <file>` and `git blame <file>` to identify when the affected lines were last modified.

8. **Look for related changes across files.** A bug in file A may be caused by an incompatible change in file B. Check if files that import from or are imported by the affected file changed recently.

### Minimal Fix

9. **Change as little as possible.** A minimal fix is easier to review, less likely to introduce new bugs, and simpler to revert if needed. Resist the urge to refactor while fixing.

10. **One fix per commit.** Do not bundle a bug fix with unrelated improvements. The reviewer and future git-bisect users will thank you.

### Regression Test

11. **Every bug fix MUST include a regression test.** The test should fail without the fix and pass with it. This prevents the same bug from returning.

12. **Name regression tests descriptively.** Use the bug ticket ID or a description of the scenario: `it('should not crash when user has no subscriptions (BUG-042)')`.

### Debugging Checklist

13. **Before claiming "fixed," verify:** The regression test fails without your change (revert temporarily). The regression test passes with your change. The full test suite still passes. No new lint or type errors were introduced.
