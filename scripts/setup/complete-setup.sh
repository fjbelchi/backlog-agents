#!/usr/bin/env bash
# ─── Complete Setup Script for Backlog Toolkit ──────────────────────
# Automates installation and configuration of all dependencies
# Usage: ./scripts/setup/complete-setup.sh

# Exit on error, but allow some flexibility for interactive prompts
set -e

# Enable pipefail only if supported (bash)
if [ -n "${BASH_VERSION:-}" ]; then
    set -o pipefail
fi

# Don't exit on unset variables to allow optional vars
# set +u already default, but being explicit

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[✓]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[!]${NC} $1"; }
log_error() { echo -e "${RED}[✗]${NC} $1"; }

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
CONFIG_DIR="$HOME/.config/litellm"
SETUP_LOG="$REPO_ROOT/setup.log"

# Initialize log
echo "=== Backlog Toolkit Setup $(date) ===" > "$SETUP_LOG"

# ─── Step 1: Check Prerequisites ────────────────────────────────────
check_prerequisites() {
    log_info "Checking prerequisites..."

    local all_ok=true
    local warnings=0

    # Check Python
    if command -v python3 &> /dev/null; then
        local python_version=$(python3 --version | cut -d' ' -f2)
        local python_major=$(echo "$python_version" | cut -d'.' -f1)
        local python_minor=$(echo "$python_version" | cut -d'.' -f2)

        if [ "$python_major" -ge 3 ] && [ "$python_minor" -ge 10 ]; then
            log_success "Python $python_version found"
        else
            log_warning "Python $python_version found, but 3.10+ recommended"
            warnings=$((warnings + 1))
        fi
    else
        log_error "Python 3.10+ required but not found"
        echo "  Install: brew install python@3.11 (macOS) or apt install python3.11 (Linux)"
        all_ok=false
    fi

    # Check Node.js
    if command -v node &> /dev/null; then
        local node_version=$(node --version)
        log_success "Node.js $node_version found"
    else
        log_error "Node.js 18+ required but not found"
        echo "  Install: brew install node (macOS) or apt install nodejs (Linux)"
        all_ok=false
    fi

    # Check Git
    if command -v git &> /dev/null; then
        local git_version=$(git --version | cut -d' ' -f3)
        log_success "Git $git_version found"
    else
        log_error "Git required but not found"
        echo "  Install: brew install git (macOS) or apt install git (Linux)"
        all_ok=false
    fi

    # Check Bash/Zsh version
    if [ -n "${BASH_VERSION:-}" ]; then
        local bash_major=$(echo "$BASH_VERSION" | cut -d. -f1)
        if [ "$bash_major" -ge 4 ]; then
            log_success "Bash $BASH_VERSION found"
        else
            log_warning "Bash 4.0+ recommended (found $BASH_VERSION)"
            warnings=$((warnings + 1))
        fi
    elif [ -n "${ZSH_VERSION:-}" ]; then
        log_success "Zsh $ZSH_VERSION found"
    else
        log_warning "Unknown shell (Bash 4.0+ or Zsh recommended)"
        warnings=$((warnings + 1))
    fi

    # Check curl
    if command -v curl &> /dev/null; then
        log_success "curl found"
    else
        log_warning "curl not found (needed for health checks)"
        warnings=$((warnings + 1))
    fi

    if [ "$all_ok" = false ]; then
        echo ""
        log_error "Prerequisites check failed. Please install missing dependencies."
        echo ""
        echo "Quick install commands:"
        echo "  macOS: brew install python@3.11 node git"
        echo "  Ubuntu: sudo apt install python3.11 nodejs npm git"
        echo ""
        exit 1
    fi

    if [ "$warnings" -gt 0 ]; then
        log_warning "$warnings warning(s) found, but setup can continue"
    fi

    log_success "All critical prerequisites satisfied"
}

# ─── Step 2: Install Python Dependencies ───────────────────────────
install_python_deps() {
    log_info "Installing Python dependencies..."

    if ! python3 -m pip install --upgrade pip >> "$SETUP_LOG" 2>&1; then
        log_error "Failed to upgrade pip"
        return 1
    fi

    # Required dependencies (must succeed)
    local required_deps=(
        "litellm[proxy]"
        "flask"
    )

    # Optional dependencies (can fail)
    local optional_deps=(
        "chromadb"
        "sentence-transformers"
        "pyyaml"
        "redis"
    )

    # Install required dependencies
    for dep in "${required_deps[@]}"; do
        log_info "  Installing $dep (required)..."
        if python3 -m pip install "$dep" >> "$SETUP_LOG" 2>&1; then
            log_success "  Installed $dep"
        else
            log_error "  Failed to install $dep"
            log_error "  This is a required dependency. Check $SETUP_LOG for details."
            return 1
        fi
    done

    # Verify LiteLLM command is available
    if ! command -v litellm &> /dev/null; then
        log_warning "LiteLLM installed but command not found in PATH"
        log_info "Attempting to locate and fix PATH..."

        # Common Python bin locations
        local python_bin_dirs=(
            "$HOME/.local/bin"
            "$HOME/Library/Python/3.11/bin"
            "$HOME/Library/Python/3.10/bin"
            "$HOME/Library/Python/3.12/bin"
            "/opt/homebrew/bin"
            "/usr/local/bin"
        )

        local litellm_found=false
        local litellm_path=""

        # Search for litellm in common locations
        for bin_dir in "${python_bin_dirs[@]}"; do
            if [ -f "$bin_dir/litellm" ]; then
                litellm_path="$bin_dir"
                litellm_found=true
                log_success "Found litellm in: $litellm_path"
                break
            fi
        done

        if [ "$litellm_found" = false ]; then
            # Try to find using Python
            local pip_bin_dir=$(python3 -m site --user-base 2>/dev/null)/bin
            if [ -f "$pip_bin_dir/litellm" ]; then
                litellm_path="$pip_bin_dir"
                litellm_found=true
                log_success "Found litellm in: $litellm_path"
            fi
        fi

        if [ "$litellm_found" = true ]; then
            # Add to current session PATH
            export PATH="$litellm_path:$PATH"

            # Add to environment file
            local env_file="$HOME/.backlog-toolkit-env"
            if ! grep -q "export PATH=\"$litellm_path:\$PATH\"" "$env_file" 2>/dev/null; then
                echo "export PATH=\"$litellm_path:\$PATH\"" >> "$env_file"
                log_success "Added $litellm_path to PATH in $env_file"
            fi

            # Verify it works now
            if command -v litellm &> /dev/null; then
                log_success "LiteLLM is now accessible"
            else
                log_error "LiteLLM found but still not accessible"
                return 1
            fi
        else
            log_error "Could not locate litellm command"
            log_info "Try running: python3 -m pip show litellm"
            return 1
        fi
    fi

    # Install optional dependencies
    for dep in "${optional_deps[@]}"; do
        log_info "  Installing $dep (optional)..."
        if python3 -m pip install "$dep" >> "$SETUP_LOG" 2>&1; then
            log_success "  Installed $dep"
        else
            log_warning "  Failed to install $dep (optional)"
        fi
    done

    log_success "Python dependencies installed"
}

# ─── Step 3: Check Claude Code ─────────────────────────────────────
check_claude_code() {
    log_info "Checking Claude Code installation..."

    if command -v claude &> /dev/null; then
        local version=$(claude --version 2>&1 | head -n1)
        log_success "Claude Code found: $version"
        return 0
    else
        log_warning "Claude Code not found in PATH"
        log_info "Install with: npm install -g @anthropic-ai/claude-code"
        read -p "Continue without Claude Code? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
}

# ─── Step 4: Configure Providers ───────────────────────────────────
configure_providers() {
    log_info "Configuring LLM providers..."

    local env_file="$HOME/.backlog-toolkit-env"

    # Source provider configuration functions
    source "$SCRIPT_DIR/configure-providers.sh"

    # Configure Anthropic (API or Bedrock)
    configure_anthropic "$env_file" || return 1

    # Configure OpenAI (optional)
    configure_openai "$env_file"

    # Configure Ollama (optional)
    configure_ollama "$env_file"

    # LiteLLM master key
    if [ -z "${LITELLM_MASTER_KEY:-}" ]; then
        local master_key="sk-litellm-$(openssl rand -hex 16)"
        echo "export LITELLM_MASTER_KEY='$master_key'" >> "$env_file"
        export LITELLM_MASTER_KEY="$master_key"
        log_success "LiteLLM master key generated"
    fi

    if [ -f "$env_file" ]; then
        log_info "Environment file created at: $env_file"
        log_info "Add this to your shell profile:"
        echo ""
        echo "  source $env_file"
        echo ""
    fi
}

# ─── Step 5: Setup LiteLLM Configuration ───────────────────────────
setup_litellm_config() {
    log_info "Setting up LiteLLM configuration..."

    mkdir -p "$CONFIG_DIR"

    local config_file="$CONFIG_DIR/config.yaml"

    if [ -f "$config_file" ]; then
        log_warning "LiteLLM config already exists at $config_file"
        read -p "Overwrite? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_info "Keeping existing configuration"
            return 0
        fi
    fi

    # Source config generator
    source "$SCRIPT_DIR/generate-litellm-config.sh"

    # Generate config based on user selections
    generate_litellm_config "$config_file"

    log_info "Review and customize if needed: $config_file"
}

# ─── Step 6: Check Optional Services ───────────────────────────────
check_optional_services() {
    log_info "Checking optional services..."

    # Redis
    if command -v redis-cli &> /dev/null; then
        if redis-cli ping &> /dev/null; then
            log_success "Redis is running"
        else
            log_warning "Redis installed but not running"
            log_info "Start with: redis-server (or brew services start redis)"
        fi
    else
        log_info "Redis not installed (optional for response caching)"
        log_info "Install with: brew install redis (macOS) or apt install redis-server (Linux)"
    fi

    # Ollama
    if command -v ollama &> /dev/null; then
        log_success "Ollama found"
        if pgrep -x ollama &> /dev/null; then
            log_success "Ollama service is running"
        else
            log_warning "Ollama installed but not running"
            log_info "Start with: ollama serve"
        fi
    else
        log_info "Ollama not installed (optional for local models)"
        log_info "Install from: https://ollama.ai"
    fi
}

# ─── Step 7: Install Claude Code Skills ────────────────────────────
install_plugin() {
    log_info "Installing Backlog Toolkit skills..."

    if ! command -v claude &> /dev/null; then
        log_warning "Claude Code not found"
        log_info "Install Claude Code first: npm install -g @anthropic-ai/claude-code"
        return 0
    fi

    # Check if install script exists
    if [ ! -f "$REPO_ROOT/install.sh" ]; then
        log_error "Installation script not found at $REPO_ROOT/install.sh"
        return 1
    fi

    # Check if skills are already installed
    local skills_installed=false
    if [ -d "$HOME/.claude/skills/backlog-init" ] || \
       [ -d "$HOME/.claude/skills/backlog-ticket" ] || \
       [ -d "$HOME/.claude/skills/backlog-refinement" ] || \
       [ -d "$HOME/.claude/skills/backlog-implementer" ]; then
        skills_installed=true
    fi

    if [ "$skills_installed" = true ]; then
        log_success "Backlog skills appear to be already installed"
        echo ""
        read -p "Reinstall skills? (y/N): " -n 1 -r
        echo

        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_info "Keeping existing skill installation"
            return 0
        fi
    fi

    echo ""
    read -p "Install Backlog Toolkit skills now? (Y/n): " -n 1 -r
    echo

    if [[ $REPLY =~ ^[Nn]$ ]]; then
        log_info "Skipping skill installation"
        return 0
    fi

    log_info "Installing skills to ~/.claude/skills/"
    echo ""

    # Run the install script
    local temp_output=$(mktemp)
    if "$REPO_ROOT/install.sh" --force > "$temp_output" 2>&1; then
        log_success "Skills installed successfully"

        # Show what was installed
        echo ""
        log_info "Installed skills:"
        ls -1 "$HOME/.claude/skills/" 2>/dev/null | grep "^backlog-" | sed 's/^/  - /' || echo "  (checking...)"

        cat "$temp_output" >> "$SETUP_LOG"
        rm -f "$temp_output"
    else
        local exit_code=$?
        log_error "Skill installation failed (exit code: $exit_code)"
        echo ""
        log_info "Installation output:"
        cat "$temp_output" | sed 's/^/  /' | head -15
        cat "$temp_output" >> "$SETUP_LOG"
        rm -f "$temp_output"

        echo ""
        log_info "Troubleshooting steps:"
        log_info "  1. Try manual install: $REPO_ROOT/install.sh"
        log_info "  2. Check skills directory exists: ls -la $REPO_ROOT/skills/"
        log_info "  3. Check permissions: ls -la ~/.claude/"
        log_info "  4. Check logs: $SETUP_LOG"

        return 1
    fi
}

# ─── Step 8: Start Services ─────────────────────────────────────────
start_services() {
    log_info "Starting services..."

    # Load environment first to check credentials
    local env_file="$HOME/.backlog-toolkit-env"
    if [ -f "$env_file" ]; then
        # shellcheck source=/dev/null
        source "$env_file"
    else
        log_error "Environment file not found at $env_file"
        log_info "Run configure_providers step first"
        return 1
    fi

    # Validate credentials before offering to start services
    local has_credentials=false
    if [ -n "${ANTHROPIC_API_KEY:-}" ] && [ "${ANTHROPIC_API_KEY}" != "''" ] && [ "${ANTHROPIC_API_KEY}" != "" ]; then
        has_credentials=true
    elif [ -n "${AWS_ACCESS_KEY_ID:-}" ] && [ -n "${AWS_SECRET_ACCESS_KEY:-}" ] && \
         [ "${AWS_ACCESS_KEY_ID}" != "''" ] && [ "${AWS_SECRET_ACCESS_KEY}" != "''" ]; then
        has_credentials=true
    fi

    if [ "$has_credentials" = false ]; then
        log_warning "No valid API credentials found in environment"
        log_info "Services require API credentials to function"
        echo ""
        log_info "Your options:"
        log_info "  1. Configure credentials now (edit $env_file)"
        log_info "  2. Skip service startup and configure later"
        log_info "  3. Continue anyway (services will fail without credentials)"
        echo ""
        read -p "Skip service startup? (Y/n): " -n 1 -r
        echo

        if [[ ! $REPLY =~ ^[Nn]$ ]]; then
            log_info "Skipping service startup due to missing credentials"
            log_info "Configure credentials in: $env_file"
            return 0
        fi

        log_warning "Continuing with empty credentials (services will likely fail)"
    fi

    echo ""
    read -p "Start LiteLLM and other services now? (Y/n): " -n 1 -r
    echo

    if [[ $REPLY =~ ^[Nn]$ ]]; then
        log_info "Skipping service startup"
        return 0
    fi

    # Diagnose and fix common issues before starting
    log_info "Running pre-start diagnostics..."
    echo ""

    local issues_fixed=0

    # Fix 1: Check if directories exist
    local services_dir="$HOME/.backlog-toolkit/services"
    local log_dir="$services_dir/logs"
    local pid_dir="$services_dir/pids"

    if [ ! -d "$services_dir" ]; then
        log_info "Creating services directory..."
        mkdir -p "$services_dir" "$log_dir" "$pid_dir"
        log_success "Directories created"
        issues_fixed=$((issues_fixed + 1))
    fi

    # Fix 2: Check LiteLLM config exists
    local litellm_config="$HOME/.config/litellm/config.yaml"
    if [ ! -f "$litellm_config" ]; then
        log_error "LiteLLM config not found at $litellm_config"
        log_info "This should have been created in setup_litellm_config step"
        return 1
    fi

    # Fix 3: Kill any stale processes
    if [ -f "$pid_dir/litellm.pid" ]; then
        local old_pid=$(cat "$pid_dir/litellm.pid")
        if ! ps -p "$old_pid" &> /dev/null; then
            log_info "Cleaning up stale PID file..."
            rm -f "$pid_dir/litellm.pid"
            issues_fixed=$((issues_fixed + 1))
        fi
    fi

    # Fix 4: Check if ports are already in use
    if lsof -Pi :8000 -sTCP:LISTEN -t &> /dev/null; then
        log_warning "Port 8000 already in use"
        log_info "Attempting to stop existing LiteLLM process..."

        local existing_pid=$(lsof -ti:8000)
        kill "$existing_pid" 2>/dev/null || true
        sleep 2

        if lsof -Pi :8000 -sTCP:LISTEN -t &> /dev/null; then
            log_error "Could not free port 8000"
            log_info "Kill manually: kill $(lsof -ti:8000)"
            return 1
        else
            log_success "Port 8000 freed"
            issues_fixed=$((issues_fixed + 1))
        fi
    fi

    if [ "$issues_fixed" -gt 0 ]; then
        log_success "Fixed $issues_fixed issue(s)"
        echo ""
    fi

    # Start services
    if [ -f "$REPO_ROOT/scripts/services/start-services.sh" ]; then
        log_info "Starting services (streaming output below)..."
        echo ""
        echo "─────────────────────────────────────────────────────────────────"

        # Run with live output using tee
        local temp_log=$(mktemp)

        # CRITICAL: Force non-interactive mode and close stdin
        # Start services in background with output streaming
        BACKLOG_INTERACTIVE_MODE=false "$REPO_ROOT/scripts/services/start-services.sh" </dev/null 2>&1 | tee "$temp_log" &
        local service_pid=$!

        # Monitor the process
        local waited=0
        local max_wait=60  # 60 seconds timeout
        local last_dot=0

        while ps -p $service_pid &> /dev/null; do
            sleep 1
            waited=$((waited + 1))

            # Show progress every 5 seconds if no output
            if [ $((waited % 5)) -eq 0 ] && [ $waited -gt $last_dot ]; then
                echo -n "⏳ Still starting... (${waited}s elapsed)"
                echo ""
                last_dot=$waited
            fi

            # Timeout check
            if [ $waited -ge $max_wait ]; then
                log_warning "Service startup taking longer than expected (${max_wait}s)"
                log_info "Continuing to wait, but you may want to check logs..."
                max_wait=$((max_wait + 30))  # Extend timeout
            fi
        done

        # Get exit code
        wait $service_pid 2>/dev/null
        local exit_code=$?

        echo "─────────────────────────────────────────────────────────────────"
        echo ""

        # Append to setup log
        cat "$temp_log" >> "$SETUP_LOG"

        if [ $exit_code -eq 0 ]; then
            log_success "Services started successfully (took ${waited}s)"
            rm -f "$temp_log"
        else
            # Service failed - analyze why
            log_error "Service startup failed (exit code: $exit_code)"
            echo ""
            log_info "Analyzing failure..."

            # Show relevant error lines
            if grep -i "error\|failed\|not found" "$temp_log" | head -5; then
                echo ""
            fi

            # Specific diagnostics
            if grep -q "ANTHROPIC_API_KEY\|AWS_ACCESS_KEY_ID" "$temp_log"; then
                log_error "Credentials not found in environment"
                log_info "Solution: Ensure $env_file has your API keys"
                log_info "  - For Anthropic: ANTHROPIC_API_KEY"
                log_info "  - For Bedrock: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY"
            fi

            if grep -q "litellm.*not found\|command not found" "$temp_log"; then
                log_error "LiteLLM command not found"
                log_info "Solution: Reinstall LiteLLM and fix PATH"
                log_info "  pip install 'litellm[proxy]'"
            fi

            if grep -q "config.*not found\|FileNotFoundError" "$temp_log"; then
                log_error "LiteLLM config file issue"
                log_info "Solution: Check if $litellm_config exists and is valid"
            fi

            rm -f "$temp_log"
            echo ""
            log_info "Full logs at: $SETUP_LOG"

            return 1
        fi
    else
        log_warning "Service start script not found"
        return 1
    fi
}

# ─── Step 9: Verify Installation ───────────────────────────────────
verify_installation() {
    log_info "Verifying installation..."
    echo ""

    local all_ok=true

    # Check environment file
    if [ -f "$HOME/.backlog-toolkit-env" ]; then
        log_success "Environment file exists"
    else
        log_error "Environment file missing"
        all_ok=false
    fi

    # Check LiteLLM config
    if [ -f "$CONFIG_DIR/config.yaml" ]; then
        log_success "LiteLLM config exists"
    else
        log_error "LiteLLM config missing"
        all_ok=false
    fi

    # Check if LiteLLM is accessible
    if command -v litellm &> /dev/null; then
        log_success "LiteLLM command available"

        # Check if LiteLLM is running
        sleep 3  # Give it a moment to start
        if curl -s http://localhost:8000/health &> /dev/null; then
            log_success "LiteLLM proxy is running and healthy"
        else
            log_info "LiteLLM proxy not running (you can start it manually)"
        fi
    else
        log_warning "LiteLLM not in PATH"
    fi

    # Check if skills are installed
    if command -v claude &> /dev/null; then
        local skills_count=0
        for skill in backlog-init backlog-ticket backlog-refinement backlog-implementer; do
            if [ -d "$HOME/.claude/skills/$skill" ]; then
                ((skills_count++))
            fi
        done

        if [ $skills_count -eq 4 ]; then
            log_success "Backlog Toolkit skills installed (4/4)"
        elif [ $skills_count -gt 0 ]; then
            log_info "Backlog Toolkit skills partially installed ($skills_count/4)"
            log_info "  Reinstall: $REPO_ROOT/install.sh --force"
        else
            log_info "Skills not installed yet"
            log_info "  Install: $REPO_ROOT/install.sh"
        fi
    fi

    echo ""
    if [ "$all_ok" = true ]; then
        log_success "All critical components verified!"
    else
        log_warning "Some issues detected, check logs at $SETUP_LOG"
    fi
}

# ─── Step 10: Run Quick Test ────────────────────────────────────────
run_quick_test() {
    echo ""
    read -p "Run connectivity tests and auto-fix issues? (Y/n): " -n 1 -r
    echo

    if [[ $REPLY =~ ^[Nn]$ ]]; then
        return 0
    fi

    log_info "Running connectivity tests with auto-fix..."
    echo ""

    local env_file="$HOME/.backlog-toolkit-env"
    local all_ok=true

    # Test 1: API Keys - Load environment if missing
    log_info "[1/4] Testing API credentials..."
    if [ -n "${ANTHROPIC_API_KEY:-}" ] || [ -n "${AWS_ACCESS_KEY_ID:-}" ]; then
        log_success "API Keys: Already loaded"
    else
        log_warning "API Keys: Not in current environment"
        if [ -f "$env_file" ]; then
            log_info "Loading environment from $env_file..."
            # shellcheck source=/dev/null
            source "$env_file"

            if [ -n "${ANTHROPIC_API_KEY:-}" ] || [ -n "${AWS_ACCESS_KEY_ID:-}" ]; then
                log_success "API Keys: Loaded successfully"
            else
                log_error "API Keys: Still not found after loading environment"
                log_info "Check your $env_file file"
                all_ok=false
            fi
        else
            log_error "Environment file not found at $env_file"
            all_ok=false
        fi
    fi
    echo ""

    # Test 2: Python dependencies
    log_info "[2/4] Testing Python dependencies..."
    if python3 -c "import litellm" 2>/dev/null; then
        log_success "LiteLLM Python module: OK"
    else
        log_error "LiteLLM Python module: Not found"
        log_info "Reinstalling..."
        if python3 -m pip install 'litellm[proxy]' >> "$SETUP_LOG" 2>&1; then
            log_success "LiteLLM: Reinstalled successfully"
        else
            log_error "LiteLLM: Reinstallation failed"
            all_ok=false
        fi
    fi
    echo ""

    # Test 3: LiteLLM Service - Start if not running
    log_info "[3/4] Testing LiteLLM proxy..."
    if curl -s -m 5 http://localhost:8000/health &> /dev/null; then
        log_success "LiteLLM proxy: Running"
    else
        log_warning "LiteLLM proxy: Not responding"
        log_info "Attempting to start services..."

        if [ -f "$REPO_ROOT/scripts/services/start-services.sh" ]; then
            "$REPO_ROOT/scripts/services/start-services.sh" >> "$SETUP_LOG" 2>&1

            # Wait and retry
            log_info "Waiting for services to start..."
            sleep 8

            if curl -s -m 5 http://localhost:8000/health &> /dev/null; then
                log_success "LiteLLM proxy: Started successfully"
            else
                log_error "LiteLLM proxy: Failed to start"
                log_info "Check logs: tail -f ~/.backlog-toolkit/services/logs/litellm.log"
                all_ok=false
            fi
        else
            log_error "Start services script not found"
            all_ok=false
        fi
    fi
    echo ""

    # Test 4: RAG Server - Required service
    log_info "[4/4] Testing RAG server..."
    if curl -s -m 5 http://localhost:8001/health &> /dev/null; then
        log_success "RAG server: Running"
    else
        log_warning "RAG server: Not responding"

        # Check if RAG server exists
        local rag_server="$REPO_ROOT/scripts/rag/server.py"
        if [ ! -f "$rag_server" ]; then
            log_error "RAG server script not found at $rag_server"
            log_info "RAG server is required for code search functionality"
            all_ok=false
        else
            log_info "RAG server script exists but not running"
            log_info "It should have started with LiteLLM. Check logs:"
            log_info "  tail -f ~/.backlog-toolkit/services/logs/rag.log"

            # Try to start it manually
            log_info "Attempting to start RAG server..."
            nohup python3 "$rag_server" --port 8001 \
                > ~/.backlog-toolkit/services/logs/rag.log 2>&1 &
            local rag_pid=$!
            echo $rag_pid > ~/.backlog-toolkit/services/pids/rag.pid

            sleep 5

            if curl -s -m 5 http://localhost:8001/health &> /dev/null; then
                log_success "RAG server: Started successfully"
            else
                log_warning "RAG server: Failed to start (check if dependencies are installed)"
                log_info "Install dependencies: pip install chromadb sentence-transformers"
                # RAG is important but not critical
            fi
        fi
    fi
    echo ""

    # Final summary
    if [ "$all_ok" = true ]; then
        log_success "✓ All critical tests passed!"
        echo ""
        log_info "Your setup is ready to use."
    else
        log_error "✗ Some critical issues remain"
        echo ""
        log_info "Review the errors above and:"
        log_info "  1. Check setup log: $SETUP_LOG"
        log_info "  2. Check service logs: ~/.backlog-toolkit/services/logs/"
        log_info "  3. Re-run setup: ./scripts/setup/complete-setup.sh"
        return 1
    fi
}

# ─── Main Setup Flow ────────────────────────────────────────────────
main() {
    echo ""
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║         Backlog Toolkit - Complete Setup Wizard               ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo ""

    check_prerequisites
    echo ""

    install_python_deps
    echo ""

    check_claude_code
    echo ""

    configure_providers
    echo ""

    setup_litellm_config
    echo ""

    check_optional_services
    echo ""

    # New automated steps
    install_plugin
    echo ""

    start_services
    echo ""

    verify_installation
    echo ""

    run_quick_test
    echo ""

    # Summary
    log_success "Setup complete!"
    echo ""
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║                    Setup Summary                               ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo ""
    echo "✓ Environment configured: ~/.backlog-toolkit-env"
    echo "✓ LiteLLM config created: ~/.config/litellm/config.yaml"

    # Check skills status
    if command -v claude &> /dev/null; then
        local skills_count=0
        for skill in backlog-init backlog-ticket backlog-refinement backlog-implementer; do
            if [ -d "$HOME/.claude/skills/$skill" ]; then
                ((skills_count++))
            fi
        done

        if [ $skills_count -eq 4 ]; then
            echo "✓ Skills installed (4/4)"
        elif [ $skills_count -gt 0 ]; then
            echo "○ Skills partially installed ($skills_count/4)"
        else
            echo "○ Skills: Not installed yet"
        fi
    else
        echo "○ Skills: Claude Code not found"
    fi

    # Check services status
    if curl -s -m 2 http://localhost:8000/health &> /dev/null; then
        echo "✓ Services running"
    else
        echo "○ Services: Not started yet"
    fi

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Next Steps:"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "1. Load environment (required for every new shell):"
    echo "   source ~/.backlog-toolkit-env"
    echo ""
    echo "2. Install skills (if not already installed):"
    echo "   $REPO_ROOT/install.sh"
    echo ""
    echo "3. Start services (if not already running):"
    echo "   ./scripts/services/start-services.sh"
    echo ""
    echo "4. Use Claude Code:"
    echo "   claude"
    echo ""
    echo "5. Test the toolkit:"
    echo "   /backlog-toolkit:init"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Convenience Options:"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "• Use the wrapper script (loads env + starts services + launches Claude):"
    echo "  ./claude-with-services.sh"
    echo ""
    echo "• Add to shell profile for automatic setup:"
    echo "  echo 'source ~/.backlog-toolkit-env' >> ~/.zshrc"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "Logs:"
    echo "  Setup: $SETUP_LOG"
    echo "  Services: ~/.backlog-toolkit/services/logs/"
}

# Only run main if script is executed, not sourced
if [ "${BASH_SOURCE[0]:-}" = "${0}" ] || [ -z "${BASH_SOURCE[0]:-}" ]; then
    main "$@"
fi
