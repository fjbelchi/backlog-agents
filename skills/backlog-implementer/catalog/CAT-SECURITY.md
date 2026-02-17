## CAT-SECURITY: Security Patterns

Defensive practices to prevent vulnerabilities in every ticket, not just security tickets.

### Input Validation

1. **Validate all input at system boundaries.** User input, API request bodies, URL parameters, file reads, environment variables, and third-party API responses. Never trust data that crosses a trust boundary.

2. **Use schema validation libraries, not manual checks.** Zod, Joi, Pydantic, or equivalent. Schema validators are harder to bypass than hand-written if-statements.

3. **Reject unexpected input rather than sanitizing it.** Allowlists are safer than denylists. Define what is valid and reject everything else.

### Injection Prevention

4. **SQL injection: Use parameterized queries or ORM methods.** Never concatenate user input into SQL strings. `db.query("SELECT * FROM users WHERE id = ?", [userId])` not `db.query("SELECT * FROM users WHERE id = " + userId)`.

5. **XSS prevention: Escape output in HTML contexts.** Use framework-provided escaping (React JSX auto-escapes, template engines with auto-escape). Never use `dangerouslySetInnerHTML` or equivalent without explicit sanitization.

6. **Command injection: Never pass user input to shell commands.** Use language-native APIs instead of spawning shells. If shell is unavoidable, use allowlists for allowed values, never string interpolation.

7. **Path traversal: Validate and normalize file paths.** Reject paths containing `..`, resolve to absolute paths, and verify the resolved path is within the expected directory. Use `path.resolve()` and compare prefixes.

### Authentication and Authorization

8. **Verify authentication on every protected endpoint.** Do not rely on client-side checks. Middleware should enforce auth before the request reaches the handler.

9. **Verify authorization for every resource access.** Authenticated does not mean authorized. Check that the user has permission for the specific resource they are requesting.

10. **Use constant-time comparison for secrets and tokens.** Timing attacks can leak information through response time differences. Use `crypto.timingSafeEqual()` or equivalent.

### Secret Management

11. **Never hardcode API keys, tokens, passwords, or connection strings.** Use environment variables or secret management services. Scan for patterns like `password = "..."` or `apiKey: "sk-..."` in reviews.

12. **Never log secrets.** Ensure structured loggers do not accidentally include request headers with auth tokens or bodies with passwords. Redact sensitive fields.

### OWASP Top 10 Quick Check

13. **For every ticket, mentally scan:** Broken access control? Cryptographic failures? Injection? Insecure design? Security misconfiguration? Vulnerable components? Authentication failures? Data integrity failures? Logging gaps? Server-side request forgery?

### Dependency Security

14. **Check dependencies for known vulnerabilities.** Use `npm audit`, `pip audit`, `cargo audit`, or equivalent before adding new dependencies. Prefer well-maintained packages with recent updates.

15. **Pin dependency versions in production.** Lockfiles (`package-lock.json`, `poetry.lock`, `Cargo.lock`) must be committed. Unpinned dependencies can introduce vulnerabilities silently.
