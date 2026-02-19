#!/usr/bin/env bash
# ─── Verify Backlog Toolkit Setup ───────────────────────────────────
# Comprehensive verification of installation and configuration
# Usage: ./scripts/setup/verify-setup.sh

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
log_error() { echo -e "${RED}[✗]${NC} $1"; }

echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║        Backlog Toolkit - Setup Verification                   ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

PASSED=0
FAILED=0
WARNINGS=0

# ─── Test 1: Environment File ───────────────────────────────────────
log_info "1. Checking environment file..."
if [ -f "$HOME/.backlog-toolkit-env" ]; then
    log_success "Environment file exists"
    PASSED=$((PASSED + 1))

    # Check if it's sourced
    if [ -n "${ANTHROPIC_API_KEY:-}${AWS_ACCESS_KEY_ID:-}${OPENAI_API_KEY:-}" ]; then
        log_success "Environment variables loaded"
        PASSED=$((PASSED + 1))
    else
        log_warning "Environment not loaded. Run: source ~/.backlog-toolkit-env"
        WARNINGS=$((WARNINGS + 1))
    fi
else
    log_error "Environment file missing"
    FAILED=$((FAILED + 1))
fi
echo ""

# ─── Test 2: LiteLLM Configuration ──────────────────────────────────
log_info "2. Checking LiteLLM configuration..."
if [ -f "$HOME/.config/litellm/config.yaml" ]; then
    log_success "LiteLLM config exists"
    PASSED=$((PASSED + 1))

    # Validate YAML syntax
    if python3 -c "import yaml; yaml.safe_load(open('$HOME/.config/litellm/config.yaml'))" 2>/dev/null; then
        log_success "Config syntax is valid"
        PASSED=$((PASSED + 1))
    else
        log_error "Config has syntax errors"
        FAILED=$((FAILED + 1))
    fi
else
    log_error "LiteLLM config missing"
    FAILED=$((FAILED + 1))
fi
echo ""

# ─── Test 3: Python Dependencies ────────────────────────────────────
log_info "3. Checking Python dependencies..."
PYTHON_DEPS=("litellm" "chromadb" "sentence_transformers" "flask")
DEPS_OK=true

for dep in "${PYTHON_DEPS[@]}"; do
    if python3 -c "import ${dep//-/_}" 2>/dev/null; then
        log_success "$dep installed"
        PASSED=$((PASSED + 1))
    else
        log_warning "$dep not installed"
        WARNINGS=$((WARNINGS + 1))
        DEPS_OK=false
    fi
done

if [ "$DEPS_OK" = false ]; then
    echo "  Install with: pip install litellm[proxy] chromadb sentence-transformers flask"
fi
echo ""

# ─── Test 4: LiteLLM Service ────────────────────────────────────────
log_info "4. Checking LiteLLM service..."
if curl -s -m 5 http://localhost:8000/health &> /dev/null; then
    log_success "LiteLLM is running on port 8000"
    PASSED=$((PASSED + 1))

    # Try to get models
    if curl -s -m 5 http://localhost:8000/models &> /dev/null; then
        log_success "LiteLLM API responding"
        PASSED=$((PASSED + 1))
    else
        log_warning "LiteLLM running but models endpoint not responding"
        WARNINGS=$((WARNINGS + 1))
    fi
else
    log_warning "LiteLLM not running"
    echo "  Start with: ./scripts/services/start-services.sh"
    WARNINGS=$((WARNINGS + 1))
fi
echo ""

# ─── Test 5: API Credentials ────────────────────────────────────────
log_info "5. Checking API credentials..."

# Source environment if not loaded
if [ -z "${ANTHROPIC_API_KEY:-}${AWS_ACCESS_KEY_ID:-}" ]; then
    if [ -f "$HOME/.backlog-toolkit-env" ]; then
        source "$HOME/.backlog-toolkit-env"
    fi
fi

if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
    log_success "Anthropic API key configured"
    PASSED=$((PASSED + 1))
elif [ -n "${AWS_ACCESS_KEY_ID:-}" ]; then
    log_success "AWS credentials configured"
    PASSED=$((PASSED + 1))
else
    log_error "No API credentials found"
    FAILED=$((FAILED + 1))
fi

if [ -n "${OPENAI_API_KEY:-}" ]; then
    log_success "OpenAI API key configured"
    PASSED=$((PASSED + 1))
fi

if [ -n "${LITELLM_MASTER_KEY:-}" ]; then
    log_success "LiteLLM master key configured"
    PASSED=$((PASSED + 1))
else
    log_warning "LiteLLM master key not set"
    WARNINGS=$((WARNINGS + 1))
fi
echo ""

# ─── Test 6: Optional Services ──────────────────────────────────────
log_info "6. Checking optional services..."

# Redis
if command -v redis-cli &> /dev/null && redis-cli ping &> /dev/null 2>&1; then
    log_success "Redis is running"
    PASSED=$((PASSED + 1))
else
    log_info "Redis not running (optional)"
fi

# Ollama
if command -v ollama &> /dev/null && pgrep ollama &> /dev/null; then
    log_success "Ollama is running"
    PASSED=$((PASSED + 1))
else
    log_info "Ollama not running (optional)"
fi

# RAG
if curl -s -m 5 http://localhost:8001/health &> /dev/null 2>&1; then
    log_success "RAG server is running"
    PASSED=$((PASSED + 1))
else
    log_info "RAG server not running (optional)"
fi
echo ""

# ─── Test 7: Claude Code ────────────────────────────────────────────
log_info "7. Checking Claude Code..."
if command -v claude &> /dev/null; then
    log_success "Claude Code installed"
    PASSED=$((PASSED + 1))

    # Check if plugin is installed
    if claude plugin list 2>&1 | grep -q "backlog-toolkit"; then
        log_success "Backlog Toolkit plugin installed"
        PASSED=$((PASSED + 1))
    else
        log_warning "Plugin not installed"
        echo "  Install with: claude plugin install --path $(pwd)"
        WARNINGS=$((WARNINGS + 1))
    fi
else
    log_warning "Claude Code not installed"
    echo "  Install with: npm install -g @anthropic-ai/claude-code"
    WARNINGS=$((WARNINGS + 1))
fi
echo ""

# ─── Test 8: Directory Structure ────────────────────────────────────
log_info "8. Checking directory structure..."
DIRS=(
    "$HOME/.backlog-toolkit"
    "$HOME/.backlog-toolkit/services"
    "$HOME/.backlog-toolkit/services/logs"
    "$HOME/.backlog-toolkit/services/pids"
    "$HOME/.config/litellm"
)

for dir in "${DIRS[@]}"; do
    if [ -d "$dir" ]; then
        log_success "$(basename $dir) directory exists"
        PASSED=$((PASSED + 1))
    else
        log_info "$(basename $dir) directory will be created on first use"
    fi
done
echo ""

# ─── Summary ─────────────────────────────────────────────────────────
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                    Verification Summary                        ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo -e "  ${GREEN}Passed:${NC}   $PASSED"
echo -e "  ${YELLOW}Warnings:${NC} $WARNINGS"
echo -e "  ${RED}Failed:${NC}   $FAILED"
echo ""

TOTAL=$((PASSED + WARNINGS + FAILED))
SCORE=$((PASSED * 100 / TOTAL))

if [ $FAILED -eq 0 ]; then
    if [ $WARNINGS -eq 0 ]; then
        echo -e "${GREEN}✓ Perfect! Everything is configured correctly.${NC}"
        echo ""
        echo "You're ready to use the Backlog Toolkit!"
        echo "  Run: claude"
        echo "  Test: /backlog-toolkit:init"
    else
        echo -e "${YELLOW}⚠ Setup mostly complete with minor warnings.${NC}"
        echo ""
        echo "You can use the toolkit, but some optional features may not work."
    fi
else
    echo -e "${RED}✗ Setup has issues that need to be fixed.${NC}"
    echo ""
    echo "Run the setup script again: ./scripts/setup/complete-setup.sh"
fi

echo ""
echo "Score: $SCORE%"
echo ""

# Exit with status based on failures
if [ $FAILED -gt 0 ]; then
    exit 1
else
    exit 0
fi
