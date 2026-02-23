#!/usr/bin/env bash
# benchmark_capture.sh — Capture LiteLLM spend snapshot from Postgres
# Used by backlog-benchmark skill to measure cost deltas.
#
# Usage:
#   ./benchmark_capture.sh snapshot           → JSON snapshot to stdout
#   ./benchmark_capture.sh breakdown <row_offset> → Per-model breakdown since row_offset
#   ./benchmark_capture.sh top-expensive <N> <days> → Top N expensive requests
#   ./benchmark_capture.sh zero-cost <days>   → Zero-cost anomalies
#   ./benchmark_capture.sh daily <days>       → Daily spend breakdown
#
# Environment:
#   POSTGRES_CONTAINER (default: backlog-postgres)
#   POSTGRES_USER      (default: litellm)
#   POSTGRES_DB        (default: litellm)

set -euo pipefail

CONTAINER="${POSTGRES_CONTAINER:-backlog-postgres}"
USER="${POSTGRES_USER:-litellm}"
DB="${POSTGRES_DB:-litellm}"

psql_query() {
  docker exec "$CONTAINER" psql -U "$USER" -d "$DB" -t -A -c "$1" 2>/dev/null
}

case "${1:-snapshot}" in
  snapshot)
    ROW=$(psql_query "
      SELECT json_build_object(
        'timestamp', NOW(),
        'total_spend', ROUND(SUM(spend)::numeric, 6),
        'total_requests', COUNT(*),
        'total_prompt', SUM(prompt_tokens),
        'total_completion', SUM(completion_tokens),
        'row_count', COUNT(*)
      ) FROM \"LiteLLM_SpendLogs\";")
    echo "$ROW"
    ;;
  breakdown)
    OFFSET="${2:-0}"
    psql_query "
      WITH numbered AS (
        SELECT *, ROW_NUMBER() OVER (ORDER BY \"startTime\") as rn
        FROM \"LiteLLM_SpendLogs\"
      )
      SELECT json_agg(row_to_json(t)) FROM (
        SELECT model, COUNT(*) as requests,
          ROUND(SUM(spend)::numeric, 6) as spend,
          SUM(prompt_tokens) as prompt_tokens,
          SUM(completion_tokens) as completion_tokens
        FROM numbered WHERE rn > $OFFSET
        GROUP BY model ORDER BY SUM(spend) DESC
      ) t;"
    ;;
  top-expensive)
    N="${2:-10}"; DAYS="${3:-7}"
    psql_query "
      SELECT json_agg(row_to_json(t)) FROM (
        SELECT model, ROUND(spend::numeric, 6) as spend,
          prompt_tokens, completion_tokens,
          to_char(\"startTime\", 'YYYY-MM-DD HH24:MI') as time
        FROM \"LiteLLM_SpendLogs\"
        WHERE \"startTime\" > NOW() - INTERVAL '${DAYS} days'
        ORDER BY spend DESC LIMIT $N
      ) t;"
    ;;
  zero-cost)
    DAYS="${2:-7}"
    psql_query "
      SELECT json_agg(row_to_json(t)) FROM (
        SELECT model, COUNT(*) as count, SUM(prompt_tokens) as prompt_tokens
        FROM \"LiteLLM_SpendLogs\"
        WHERE spend = 0 AND prompt_tokens > 1000
          AND \"startTime\" > NOW() - INTERVAL '${DAYS} days'
        GROUP BY model
      ) t;"
    ;;
  daily)
    DAYS="${2:-7}"
    psql_query "
      SELECT json_agg(row_to_json(t)) FROM (
        SELECT DATE(\"startTime\") as date,
          ROUND(SUM(spend)::numeric, 4) as spend,
          COUNT(*) as requests
        FROM \"LiteLLM_SpendLogs\"
        WHERE \"startTime\" > NOW() - INTERVAL '${DAYS} days'
        GROUP BY DATE(\"startTime\")
        ORDER BY DATE(\"startTime\")
      ) t;"
    ;;
  *)
    echo "Usage: $0 {snapshot|breakdown <offset>|top-expensive <N> <days>|zero-cost <days>|daily <days>}" >&2
    exit 1
    ;;
esac
