## CAT-PERF: Performance & Efficiency

Practices for maximizing throughput, minimizing token usage, and avoiding wasted work.

### Token Efficiency

1. **Provide complete context upfront.** When spawning a subagent, include everything it needs in the initial prompt: ticket content, affected files, code rules, test patterns. Round-trips to ask for more context waste tokens.

2. **Be specific in prompts.** "Read src/services/user.ts and add a getByEmail method that queries the users table" is cheaper than "figure out where to add email lookup." Specific instructions reduce exploration tokens.

3. **Trim irrelevant context.** Do not dump entire files when only a few functions matter. Quote the relevant section and provide file:line references for the rest.

### Tool Selection

4. **Use the right tool for the job.** Use Glob for finding files by name pattern, not `find`. Use Grep for searching file contents, not `grep` or `rg` in Bash. Use Read for viewing files, not `cat`. Specialized tools are optimized for correctness and permissions.

5. **Read multiple files in parallel when independent.** If you need to read 3 files that do not depend on each other, issue all 3 Read calls in the same message. Sequential reads waste round-trips.

6. **Prefer Edit over Write for existing files.** Edit replaces specific strings and preserves the rest of the file. Write overwrites the entire file and requires reading it first. Edit is safer and more efficient for targeted changes.

### Parallelization

7. **Run independent tasks in parallel.** Tickets that modify different files can be implemented simultaneously. Tests and lint checks that do not depend on each other can run in the same message.

8. **Run dependent tasks sequentially.** If task B needs the output of task A, wait for A to complete. Do not guess at intermediate results or use placeholders.

9. **Chain dependent shell commands with &&.** `git add file.ts && git commit -m "msg"` ensures the commit only runs if the add succeeds. Use `;` only when you do not care if earlier commands fail.

### Effort Scaling

10. **Match effort to ticket complexity.** A one-line config change does not need 8 tests and 3 review rounds. A new authentication system needs thorough testing and careful review. Scale effort proportionally.

11. **Simple tickets (1-2 files, no new logic): 3 tests, 1 review round.** Focus on correctness, not ceremony.

12. **Complex tickets (new features, multiple files, business logic): 5-8 tests, up to 3 review rounds.** Invest in thorough validation because bugs here are expensive.

### Fresh Context

13. **Each subagent starts with clean context.** Do not assume a subagent remembers previous waves or tickets. Include all necessary information in its initial prompt. Context pollution causes subtle bugs.

14. **Do not reuse subagents across waves.** Shut down the team after each wave and create fresh subagents for the next one. Accumulated context degrades performance and accuracy.

### Verification

15. **Always run tests and lint after changes.** Do not assume your change is correct. Run the configured test and lint commands and read the actual output. "Should pass" is not evidence.

16. **Read the verification output, do not just check exit codes.** A test suite can exit 0 while skipping all tests. A linter can exit 0 while reporting warnings. Read the summary line and count the numbers.
