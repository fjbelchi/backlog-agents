# Backlog Config Schema (Generated)

Source: `config/backlog.config.schema.json`

| Key | Type | Required | Description |
|---|---|---|---|
| `agentRouting` | `object` | `no` | Smart agent routing configuration. Determines which agent handles a ticket based on pattern matching. |
| `backlog` | `object` | `yes` | Backlog data and template configuration. |
| `codeRules` | `object` | `yes` | Code-quality rules enforced during implementation. |
| `project` | `object` | `yes` | Project-level metadata. |
| `qualityGates` | `object` | `yes` | Commands executed as quality gates during ticket implementation. |
| `reviewPipeline` | `object` | `no` | Configurable review pipeline. Defines which reviewers run and their thresholds. |
| `ticketValidation` | `object` | `yes` | Validation rules applied when creating or updating tickets. |
| `version` | `string` | `yes` | Configuration schema version. |
