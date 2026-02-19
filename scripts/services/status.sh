#!/usr/bin/env bash
# ─── Check Status of Backlog Toolkit Services ───────────────────────
# Shows running status and health of all services
# Usage: ./scripts/services/status.sh

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SERVICES_DIR="$HOME/.backlog-toolkit/services"
LOG_DIR="$SERVICES_DIR/logs"
PID_DIR="$SERVICES_DIR/pids"
LITELLM_PORT="${LITELLM_PORT:-8000}"
RAG_PORT="${RAG_PORT:-8001}"

# ─── Docker Mode Detection ────────────────────────────────────────
is_docker_mode() {
    if [ "${BACKLOG_NATIVE_MODE:-}" = "true" ]; then return 1; fi
    local compose_file="$REPO_ROOT/docker-compose.yml"
    [ -f "$compose_file" ] && command -v docker &>/dev/null && docker info &>/dev/null 2>&1
}

# ─── Docker Status ────────────────────────────────────────────────
docker_status() {
    echo ""
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║                 Service Status (Docker)                       ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo ""

    local compose_file="$REPO_ROOT/docker-compose.yml"
    local env_file="$REPO_ROOT/.env.docker.local"

    # Show docker compose ps
    echo "Container Status:"
    if [ -f "$env_file" ]; then
        docker compose -f "$compose_file" --env-file "$env_file" ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || \
            docker compose -f "$compose_file" --env-file "$env_file" ps
    else
        docker compose -f "$compose_file" ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || \
            docker compose -f "$compose_file" ps
    fi
    echo ""

    # Health checks via curl
    local all_ok=true

    echo "Health Checks:"
    if curl -sf http://localhost:$LITELLM_PORT/health &>/dev/null; then
        echo -e "  LiteLLM: ${GREEN}Healthy${NC} (http://localhost:$LITELLM_PORT)"
    else
        echo -e "  LiteLLM: ${RED}Unhealthy${NC} (http://localhost:$LITELLM_PORT)"
        all_ok=false
    fi

    if curl -sf http://localhost:$RAG_PORT/health &>/dev/null; then
        echo -e "  RAG:     ${GREEN}Healthy${NC} (http://localhost:$RAG_PORT)"
    else
        echo -e "  RAG:     ${RED}Unhealthy${NC} (http://localhost:$RAG_PORT)"
    fi

    # Check Phase 2 services if running
    if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "backlog-memgraph$"; then
        echo -e "  Memgraph: ${GREEN}Running${NC} (bolt://localhost:7687)"
    fi
    if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "backlog-memgraph-lab$"; then
        echo -e "  Memgraph Lab: ${GREEN}Running${NC} (http://localhost:3000)"
    fi

    echo ""
    echo "Service Endpoints:"
    echo "  LiteLLM:      http://localhost:$LITELLM_PORT"
    echo "  LiteLLM UI:   http://localhost:$LITELLM_PORT/ui/login/"
    echo "  RAG:           http://localhost:$RAG_PORT"
    echo ""

    if [ "$all_ok" = true ]; then
        echo -e "${GREEN}All required services are healthy (Docker mode)${NC}"
        echo ""
        echo "You can run: claude"
    else
        echo -e "${RED}Some required services are not healthy${NC}"
        echo ""
        echo "Check logs: docker compose -f $compose_file logs"
    fi

    echo ""
    echo "Useful commands:"
    echo "  docker compose logs -f           - Tail all logs"
    echo "  docker compose logs -f litellm   - Tail LiteLLM logs"
    echo "  docker compose logs -f rag       - Tail RAG logs"
    echo ""
}

# ─── Check Service Status ───────────────────────────────────────────
check_service() {
    local service_name=$1
    local pid_file="$PID_DIR/${service_name}.pid"
    local port=${2:-}

    if [ ! -f "$pid_file" ]; then
        echo -e "  ${service_name}: ${YELLOW}Not started${NC}"
        return 1
    fi

    local pid=$(cat "$pid_file")

    if ! ps -p "$pid" &> /dev/null; then
        echo -e "  ${service_name}: ${RED}Dead${NC} (PID file exists but process not found)"
        return 1
    fi

    if [ -n "$port" ]; then
        if curl -s http://localhost:$port/health &> /dev/null; then
            echo -e "  ${service_name}: ${GREEN}Running${NC} (PID: $pid, Port: $port) ✓"
            return 0
        else
            echo -e "  ${service_name}: ${YELLOW}Running${NC} (PID: $pid) but health check failed"
            return 1
        fi
    else
        echo -e "  ${service_name}: ${GREEN}Running${NC} (PID: $pid)"
        return 0
    fi
}

# ─── Main ───────────────────────────────────────────────────────────
main() {
    # Docker mode
    if is_docker_mode; then
        docker_status
        return
    fi

    # Native mode
    echo ""
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║                 Service Status (Native)                       ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo ""

    local all_ok=true

    # Required services
    echo "Required Services:"
    check_service "litellm" "$LITELLM_PORT" || all_ok=false

    echo ""
    echo "Optional Services:"
    check_service "rag" "$RAG_PORT" || true

    # Redis
    if pgrep redis-server &> /dev/null; then
        echo -e "  Redis: ${GREEN}Running${NC} ✓"
    else
        echo -e "  Redis: ${YELLOW}Not running${NC}"
    fi

    # Ollama
    if pgrep ollama &> /dev/null; then
        if curl -s http://localhost:11434/api/tags &> /dev/null; then
            echo -e "  Ollama: ${GREEN}Running${NC} ✓"
        else
            echo -e "  Ollama: ${YELLOW}Running${NC} but not responding"
        fi
    else
        echo -e "  Ollama: ${YELLOW}Not running${NC}"
    fi

    echo ""
    echo "Service Endpoints:"
    echo "  LiteLLM: http://localhost:$LITELLM_PORT"
    echo "  RAG:     http://localhost:$RAG_PORT"
    echo "  Ollama:  http://localhost:11434"
    echo ""

    if [ "$all_ok" = true ]; then
        echo -e "${GREEN}✓ All required services are healthy${NC}"
        echo ""
        echo "You can run: claude"
    else
        echo -e "${RED}✗ Some required services are not running${NC}"
        echo ""
        echo "Start services with: ./scripts/services/start-services.sh"
    fi

    echo ""
    echo "Logs: $LOG_DIR"
    echo ""
}

main "$@"
