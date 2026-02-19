# backlog-ticket

## Purpose

Generate high-quality tickets with validation and dependency awareness.

## Inputs

- User request text
- `backlog.config.json`
- Existing pending tickets

## Outputs

- New ticket markdown in `backlog/data/pending/`
- Validation warnings/errors
- Cost estimate metadata

## Internal Flow

1. Read config and scan existing backlog.
2. Build deterministic context pack.
3. Generate ticket content.
4. Run validation checks and resolve warnings.

## Expected Cost

Medium; optimized by script preflight and cheap-first routing.

## Frequent Errors

- Missing config file.
- Duplicate/conflicting ticket IDs.
- Invalid affected-file actions.
