# Command: /backlog-toolkit:reflect

Deep reflection on implementer wave outcomes. Analyzes playbook effectiveness and proposes improvements.

## Syntax

```
/backlog-toolkit:reflect [--waves N] [--dry-run]
```

## Parameters

- `--waves N`: Number of recent waves to analyze (default: 10)
- `--dry-run`: Show proposed changes without applying them

## Examples

### Standard reflection
```
/backlog-toolkit:reflect
```

### Analyze last 5 waves only
```
/backlog-toolkit:reflect --waves 5
```

### Preview changes without applying
```
/backlog-toolkit:reflect --dry-run
```

## Output

- Updates `.claude/playbook.md` with counter changes, new bullets, and pruning
- Writes report to `.backlog-ops/reflections/reflect-{date}.md`

## Related

- Skill: `skills/backlog-reflect/SKILL.md`
- Design: `docs/plans/2026-02-23-ace-learning-system-design.md`
- Playbook utils: `scripts/ops/playbook_utils.py`
