# backlog-orchestrator

## Purpose

Single entrypoint that selects and coordinates the right workflow across skills, scripts, and gateway policy.

## Inputs

- `goal` (string)
- `mode` (`auto|plan|run|offline`)
- `cost_profile` (`aggressive|balanced`)
- `quality_profile` (`strict|standard`)
- `ticket_scope` (optional array)

## Outputs

- Selected workflow (`init|ticket|refinement|implementer|mixed`)
- Model alias map by phase
- Script actions list
- Escalation decision (with reason)

## Internal Flow

1. Parse objective and constraints.
2. Run deterministic preflight scripts.
3. Select workflow and route models by alias.
4. Execute workflow or enqueue batch job.
5. Persist usage/cost telemetry.

## Expected Cost

Low control-plane overhead; primary cost impact is reduction of unnecessary frontier calls.

## Frequent Errors

- Missing model registry.
- Missing usage ledger path.
- No fallback route configured.
