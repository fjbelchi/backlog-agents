## CAT-TDD: Test-Driven Development

Best practices for writing tests first, implementing second, and refactoring third.

### Red-Green-Refactor Cycle

1. **RED -- Write a failing test first.** No production code exists yet. The test defines expected behavior. Run it and confirm it fails for the right reason (missing feature, not syntax error).

2. **GREEN -- Write the minimal code that makes the test pass.** Do not add features beyond what the test requires. Do not refactor surrounding code. Run the test and confirm it passes.

3. **REFACTOR -- Clean up while tests stay green.** Remove duplication, improve names, extract helpers. Run tests after every change to ensure nothing breaks.

4. **Never write production code without a failing test first.** If you find yourself writing code and then adding tests afterward, stop. Delete the code. Write the test. Start over.

### Minimum Test Coverage

5. **Write at least 3 tests per ticket.** One happy path (main flow with valid data), one error path (invalid input, missing resource, auth failure), one edge case (empty list, null, boundary value). Recommended: 5-8 tests for complex tickets.

6. **Happy path tests must assert specific values.** `expect(result).toBeDefined()` is vacuous. Assert the actual return value, status, or side effect: `expect(result.status).toBe('active')`.

7. **Error path tests must assert the error type.** `expect(fn).toThrow()` passes for any error. Assert the specific error class: `expect(fn).toThrow(NotFoundError)`.

8. **Edge case tests must cover boundaries.** Empty arrays, zero values, maximum lengths, concurrent access, missing optional fields.

### Verification Protocol

9. **Run tests BEFORE implementation to confirm failure.** A test that passes immediately is testing existing behavior, not new behavior. Fix or delete it.

10. **Run tests AFTER implementation to confirm all pass.** Read the actual output. Count failures. Zero failures means green. Any failure means stop and fix.

11. **Run the full test suite, not just your new tests.** Your changes may break existing functionality. Catch regressions before the reviewer does.

### Stack-Specific Hints

12. **Python:** `pytest -xvs path/to/test_file.py`. Name test files `test_*.py`. Use `pytest.raises(ErrorType)` for error assertions.

13. **TypeScript:** `npx vitest run path/to/file.test.ts --reporter=verbose` or `npx jest path/to/file.test.ts`. Name test files `*.test.ts` or `*.spec.ts`.

14. **Go:** `go test -v -run TestName ./path/to/package/...`. Name test files `*_test.go`. Use `t.Errorf` and `t.Fatalf` for assertions.

15. **Rust:** `cargo test test_name -- --nocapture`. Place tests in `#[cfg(test)] mod tests` inside the source file or in a separate `tests/` directory.

16. **Swift:** `swift test --filter TestClassName`. Name test files `*Tests.swift`. Use `XCTAssertEqual`, `XCTAssertThrowsError`.
