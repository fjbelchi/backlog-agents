#!/usr/bin/env bash
# ─── Restart All Backlog Toolkit Services ───────────────────────────
# Stops and starts all services
# Usage: ./scripts/services/restart-services.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Restarting services..."
echo ""

"$SCRIPT_DIR/stop-services.sh"
sleep 2
"$SCRIPT_DIR/start-services.sh"
