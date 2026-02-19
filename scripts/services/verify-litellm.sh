#!/usr/bin/env bash
# ─── Verify LiteLLM is working correctly ────────────────────────────

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[✓]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[!]${NC} $1"; }
log_error() { echo -e "${RED}[✗]${NC} $1"; }

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║        LiteLLM Verification Script                            ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Load environment
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

if [ -f ~/.backlog-toolkit-env ]; then
    source ~/.backlog-toolkit-env
    log_success "Environment loaded from ~/.backlog-toolkit-env"
fi

# Override with Docker env if running in Docker mode
DOCKER_ENV_FILE="$REPO_ROOT/.env.docker.local"
if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^backlog-litellm$" && [ -f "$DOCKER_ENV_FILE" ]; then
    # Source Docker env vars (these are KEY=VALUE, not export KEY=VALUE)
    docker_master_key=$(grep "^LITELLM_MASTER_KEY=" "$DOCKER_ENV_FILE" 2>/dev/null | cut -d= -f2-)
    if [ -n "$docker_master_key" ]; then
        export LITELLM_MASTER_KEY="$docker_master_key"
        log_success "Master key loaded from .env.docker.local"
    fi
fi

if [ -z "${LITELLM_MASTER_KEY:-}" ]; then
    log_error "No environment file or master key found"
    exit 1
fi

# Check if LiteLLM is running (Docker or native)
log_info "Checking LiteLLM process..."
DOCKER_MODE=false
if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^backlog-litellm$"; then
    log_success "LiteLLM is running (Docker container: backlog-litellm)"
    DOCKER_MODE=true
elif pgrep -f "litellm --config" > /dev/null; then
    pid=$(pgrep -f "litellm --config")
    log_success "LiteLLM is running (native PID: $pid)"
else
    log_error "LiteLLM is not running"
    log_info "Start with: ./scripts/services/start-services.sh"
    exit 1
fi

# Check master key
log_info "Checking master key..."
if [ -z "${LITELLM_MASTER_KEY:-}" ]; then
    log_error "LITELLM_MASTER_KEY not set"
    exit 1
fi
log_success "Master key configured"

# Test health endpoint (note: health check may show unhealthy if role lacks
# bedrock:ListFoundationModels, but InvokeModel can still work)
log_info "Testing health endpoint..."
health_response=$(curl -s http://localhost:8000/health \
    -H "Authorization: Bearer $LITELLM_MASTER_KEY")

if echo "$health_response" | jq -e '.healthy_count' &>/dev/null; then
    healthy=$(echo "$health_response" | jq -r '.healthy_count')
    unhealthy=$(echo "$health_response" | jq -r '.unhealthy_count')
    log_success "Health endpoint responding"
    log_info "  Healthy models: $healthy"
    if [ "$unhealthy" -gt 0 ] 2>/dev/null; then
        log_warning "  Unhealthy models: $unhealthy (may be a health-check permission issue, testing invocation...)"
    fi
else
    log_warning "Health endpoint not responding as expected (continuing with completion test)"
fi

# Test all model tiers
MODELS=("cheap" "balanced" "frontier")
PASS_COUNT=0
FAIL_COUNT=0

log_info "Testing model completions..."
for model in "${MODELS[@]}"; do
    echo -n "  Testing '$model'... "

    completion_response=$(curl -s -m 20 http://localhost:8000/v1/chat/completions \
        -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
        -H "Content-Type: application/json" \
        -d "{
            \"model\": \"$model\",
            \"messages\": [
                {\"role\": \"user\", \"content\": \"Say OK\"}
            ],
            \"max_tokens\": 10
        }" 2>&1)

    if echo "$completion_response" | jq -e '.choices[0].message.content' &>/dev/null; then
        content=$(echo "$completion_response" | jq -r '.choices[0].message.content')
        prompt_tokens=$(echo "$completion_response" | jq -r '.usage.prompt_tokens')
        completion_tokens=$(echo "$completion_response" | jq -r '.usage.completion_tokens')
        echo -e "${GREEN}OK${NC} (response: $content, tokens: ${prompt_tokens}+${completion_tokens})"
        PASS_COUNT=$((PASS_COUNT + 1))

    elif echo "$completion_response" | grep -qi "ExpiredTokenException\|security token.*expired"; then
        echo -e "${RED}EXPIRED${NC}"
        log_error "SSO session expired. Run: aws sso login --profile cc"
        FAIL_COUNT=$((FAIL_COUNT + 1))

    elif echo "$completion_response" | grep -qi "AccessDeniedException\|not authorized"; then
        echo -e "${RED}ACCESS DENIED${NC}"
        log_error "Missing bedrock:InvokeModel permission for $model"
        FAIL_COUNT=$((FAIL_COUNT + 1))

    else
        echo -e "${RED}FAILED${NC}"
        echo "    Response: $(echo "$completion_response" | head -c 200)"
        FAIL_COUNT=$((FAIL_COUNT + 1))
    fi
done

echo ""
if [ $FAIL_COUNT -eq 0 ]; then
    log_success "All $PASS_COUNT models passed!"
else
    log_error "$FAIL_COUNT model(s) failed, $PASS_COUNT passed"
    echo ""
    log_info "Common fixes:"
    log_info "  SSO expired:    aws sso login --profile cc && restart services"
    log_info "  Credentials:    Restart start-services.sh to refresh credentials"
    log_info "  Permissions:    Role needs bedrock:InvokeModel"
    exit 1
fi

# Show config info
echo ""
log_info "Configuration:"
if [ "$DOCKER_MODE" = true ]; then
    log_info "  Mode:   Docker (credentials injected as env vars by start-services.sh)"
    log_info "  Config: config/litellm/proxy-config.docker.yaml"
else
    log_info "  Mode:   Native"
    log_info "  Config: ~/.config/litellm/config.yaml"
fi
log_info "  Auth:   AWS credentials (resolved from SSO at service start)"
log_info "  Models: cheap (Haiku), balanced (Sonnet), frontier (Opus)"

# Show how to view logs
echo ""
log_info "Viewing Prompts and Logs:"
if [ "$DOCKER_MODE" = true ]; then
    echo "  docker compose logs -f litellm"
else
    echo "  tail -f ~/.backlog-toolkit/services/logs/litellm.log"
fi
echo ""

log_success "All checks passed! LiteLLM is working correctly."
