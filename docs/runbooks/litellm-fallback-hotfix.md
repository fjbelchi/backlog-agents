# Runbook: LiteLLM Fallback Hotfix

## Trigger

- Provider outage.
- Model latency or timeout degradation.

## Steps

1. Validate current fallback state.
2. Add temporary fallback route.
3. Confirm routing health.
4. Remove temporary route after incident.

## API Operations

- `GET /fallback`
- `POST /fallback`
- `DELETE /fallback/{fallback_name}`

## Safety

All hotfix changes must be logged in incident notes and reverted when stable.
