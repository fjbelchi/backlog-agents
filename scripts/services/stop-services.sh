#!/usr/bin/env bash
# ─── Stop All Backlog Toolkit Services ──────────────────────────────
# Gracefully stops LiteLLM, RAG, and optional services
# Usage: ./scripts/services/stop-services.sh

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[✓]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[!]${NC} $1"; }

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SERVICES_DIR="$HOME/.backlog-toolkit/services"
PID_DIR="$SERVICES_DIR/pids"

# ─── Docker Mode Detection ────────────────────────────────────────
is_docker_mode() {
    if [ "${BACKLOG_NATIVE_MODE:-}" = "true" ]; then return 1; fi
    local compose_file="$REPO_ROOT/docker-compose.yml"
    [ -f "$compose_file" ] && command -v docker &>/dev/null && docker info &>/dev/null 2>&1
}

# ─── Stop Service ───────────────────────────────────────────────────
stop_service() {
    local service_name=$1
    local pid_file="$PID_DIR/${service_name}.pid"

    if [ ! -f "$pid_file" ]; then
        log_info "$service_name: Not running (no PID file)"
        return 0
    fi

    local pid=$(cat "$pid_file")

    if ! ps -p "$pid" &> /dev/null; then
        log_info "$service_name: Already stopped"
        rm -f "$pid_file"
        return 0
    fi

    log_info "Stopping $service_name (PID: $pid)..."
    kill "$pid" 2>/dev/null || true

    # Wait up to 10 seconds for graceful shutdown
    local count=0
    while ps -p "$pid" &> /dev/null && [ $count -lt 10 ]; do
        sleep 1
        ((count++))
    done

    if ps -p "$pid" &> /dev/null; then
        log_warning "$service_name did not stop gracefully, forcing..."
        kill -9 "$pid" 2>/dev/null || true
    fi

    rm -f "$pid_file"
    log_success "$service_name stopped"
}

# ─── Stop Redis ─────────────────────────────────────────────────────
stop_redis() {
    if command -v redis-cli &> /dev/null; then
        if redis-cli ping &> /dev/null 2>&1; then
            log_info "Stopping Redis..."
            redis-cli shutdown 2>/dev/null || true
            rm -f "$PID_DIR/redis.pid"
            log_success "Redis stopped"
        fi
    fi
}

# ─── Stop PostgreSQL Docker Container ───────────────────────────────
stop_postgres() {
    local container="backlog-postgres"
    if command -v docker &> /dev/null && docker info &>/dev/null 2>&1; then
        if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^${container}$"; then
            log_info "Stopping PostgreSQL container..."
            docker stop "$container" > /dev/null
            log_success "PostgreSQL stopped"
        fi
    fi
}

# ─── Main ───────────────────────────────────────────────────────────
main() {
    # Docker mode
    if is_docker_mode; then
        echo ""
        echo "╔════════════════════════════════════════════════════════════════╗"
        echo "║        Stopping Backlog Toolkit Services (Docker)             ║"
        echo "╚════════════════════════════════════════════════════════════════╝"
        echo ""

        local compose_file="$REPO_ROOT/docker-compose.yml"
        local env_file="$REPO_ROOT/.env.docker.local"

        if [ -f "$env_file" ]; then
            docker compose -f "$compose_file" --env-file "$env_file" down
        else
            docker compose -f "$compose_file" down
        fi

        echo ""
        log_success "All Docker services stopped"
        echo ""
        return
    fi

    # Native mode
    echo ""
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║        Stopping Backlog Toolkit Services (Native)             ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo ""

    stop_service "litellm"
    stop_service "rag"
    stop_service "ollama"
    stop_redis
    stop_postgres

    echo ""
    log_success "All services stopped"
    echo ""
}

main "$@"
