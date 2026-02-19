#!/usr/bin/env bash
# ─── Start Services and Launch Claude Code ──────────────────────────
# Ensures all services are running before starting Claude Code.
# Also starts the RAG file watcher in background (always-on).
# Usage: ./claude-with-services.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WATCHER_PID_FILE="/tmp/backlog-rag-watcher.pid"

# Kill watcher on exit (clean shutdown)
cleanup() {
    if [ -f "$WATCHER_PID_FILE" ]; then
        local pid
        pid="$(cat "$WATCHER_PID_FILE")"
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null && echo "[services] RAG watcher stopped (PID $pid)"
        fi
        rm -f "$WATCHER_PID_FILE"
    fi
}
trap cleanup EXIT INT TERM

# Start services
"$SCRIPT_DIR/scripts/services/start-services.sh"

# Start RAG file watcher in background
echo ""
echo "[services] Starting RAG file watcher..."
python3 "$SCRIPT_DIR/scripts/rag/watcher.py" --watch "$(pwd)" &
echo $! > "$WATCHER_PID_FILE"
echo "[services] RAG watcher started (PID $(cat "$WATCHER_PID_FILE")) — watching $(pwd)"

echo ""
echo "Starting Claude Code..."
echo ""

# Start Claude Code
if command -v claude &> /dev/null; then
    claude "$@"
else
    echo "Error: claude command not found"
    echo "Install with: npm install -g @anthropic-ai/claude-code"
    exit 1
fi
