# backlog-init

## Purpose

Initialize backlog structures, templates, and configuration in a project.

## Inputs

- Project name
- Stack type
- Ticket prefixes
- Optional code-rules generation

## Outputs

- `backlog/` directory structure
- `backlog.config.json`
- Template files and conventions docs

## Internal Flow

1. Detect project stack from manifests.
2. Confirm user preferences.
3. Create directories and templates.
4. Write config and backlog conventions.

## Expected Cost

Minimal LLM cost; mostly deterministic filesystem operations.

## Frequent Errors

- Existing backlog directory conflicts.
- Invalid stack/tooling assumptions.
