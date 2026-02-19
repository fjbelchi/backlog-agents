# Documentation Standards

## Required for Every Change

1. Update docs when changing `skills/`, `config/`, or `scripts/`.
2. Keep contracts synchronized with source definitions.
3. Include executable command examples when feasible.
4. Validate links and coverage before merge.

## Mandatory Sections (Skill Docs)

- Purpose
- Inputs
- Outputs
- Internal Flow
- Expected Cost
- Frequent Errors

## Validation Commands

```bash verify
./scripts/docs/check-links.sh
./scripts/docs/verify-snippets.sh
./scripts/docs/check-doc-coverage.py
```

## Review Rule

Pull requests that fail docs validation must not be merged.
