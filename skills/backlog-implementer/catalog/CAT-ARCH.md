## CAT-ARCH: Architecture Principles

Structural decisions that prioritize reliability, maintainability, and data integrity.

### Layered Architecture

1. **Separate concerns into layers: routes/controllers, services, repositories, models.** Each layer has one job. Controllers handle HTTP. Services contain business logic. Repositories handle data access. Models define data shapes.

2. **Dependencies flow inward.** Controllers call services. Services call repositories. Repositories call the database. Never skip layers: controllers must not query the database directly.

3. **Keep controllers thin (under 200 lines).** Validate input, call the service, return the response. No business logic. No database queries. No complex transformations.

### Data Integrity

4. **Validate at boundaries, trust internally.** Validate user input at the controller/API boundary using schema validation. Internal service-to-service calls within the same process can trust their inputs.

5. **Use database transactions for multi-step writes.** If an operation modifies multiple tables or documents, wrap it in a transaction. Partial writes corrupt data.

6. **Handle soft deletes consistently.** If the project uses soft deletes (`isDeleted`, `deletedAt`), every query must filter them out. Add this to the repository layer, not scattered across services.

### Fault Tolerance

7. **Handle errors gracefully with typed error classes.** Use the project's error hierarchy (NotFoundError, ValidationError, UnauthorizedError). Never `throw new Error("message")` -- use specific types.

8. **Retry transient failures with exponential backoff.** Network calls, database connections, and external APIs can fail temporarily. Retry 2-3 times with increasing delays. Do not retry permanent failures (400, 404, 422).

9. **Set timeouts on all external calls.** HTTP requests, database queries, and third-party APIs need timeouts. Without them, a hung dependency blocks your entire service.

### API Design

10. **Use consistent naming conventions.** camelCase for JSON fields (JS/TS), snake_case for Python APIs. Pick one and enforce it across the entire project.

11. **Return proper HTTP status codes.** 200 for success, 201 for created, 400 for bad input, 401 for unauthenticated, 403 for unauthorized, 404 for not found, 409 for conflict, 500 for server error. Never return 200 with an error body.

12. **Version APIs when breaking changes are unavoidable.** Prefix routes with `/v1/`, `/v2/`. Do not break existing clients without a migration path.

### Design Principles

13. **DRY but not premature.** Three similar lines of code are better than a premature abstraction. Wait until you have 3 concrete cases before extracting a shared function. Wrong abstractions are worse than duplication.

14. **YAGNI: Do not build for hypothetical future requirements.** Implement what the ticket asks for, not what might be needed someday. Unused abstractions are maintenance burden with zero value.

15. **Prefer composition over inheritance.** Small, focused functions that compose together are easier to test, reuse, and understand than deep inheritance hierarchies.
