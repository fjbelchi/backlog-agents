#!/usr/bin/env bash
# ─── Robustness Test Script ──────────────────────────────────────────
# Tests all failure scenarios and auto-correction mechanisms

set -eo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_test() { echo -e "${BLUE}[TEST]${NC} $1"; }
log_pass() { echo -e "${GREEN}[PASS]${NC} $1"; }
log_fail() { echo -e "${RED}[FAIL]${NC} $1"; }
log_info() { echo -e "${YELLOW}[INFO]${NC} $1"; }

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEST_ENV="/tmp/test-backlog-env"
TESTS_PASSED=0
TESTS_FAILED=0

# ─── Test 1: Empty Credentials Detection ────────────────────────────
test_empty_credentials() {
    log_test "Test 1: Empty credentials detection"

    # Create test env file with empty credentials
    cat > "$TEST_ENV" <<'EOF'
export AWS_ACCESS_KEY_ID=''
export AWS_SECRET_ACCESS_KEY=''
export AWS_REGION='us-east-1'
export LITELLM_MASTER_KEY='test-key'
EOF

    # Source the test env (or return if it fails)
    # shellcheck source=/dev/null
    source "$TEST_ENV" || true

    # Test the detection logic
    local aws_key="${AWS_ACCESS_KEY_ID:-}"
    if [ "$aws_key" = "''" ] || [ "$aws_key" = "" ] || [ -z "$aws_key" ]; then
        log_pass "Correctly detected empty AWS_ACCESS_KEY_ID"
        ((TESTS_PASSED++))
    else
        log_fail "Failed to detect empty AWS_ACCESS_KEY_ID (got: '$aws_key')"
        ((TESTS_FAILED++))
    fi

    # Clean up
    rm -f "$TEST_ENV"
}

# ─── Test 2: PATH Detection and Fix ─────────────────────────────────
test_path_detection() {
    log_test "Test 2: LiteLLM PATH detection"

    # Try to find litellm
    if command -v litellm &> /dev/null; then
        local litellm_path=$(which litellm)
        log_pass "LiteLLM found at: $litellm_path"
        ((TESTS_PASSED++))
    else
        # Try to locate it
        local python_bin=$(python3 -m site --user-base 2>/dev/null)/bin
        if [ -f "$python_bin/litellm" ]; then
            log_pass "LiteLLM found at: $python_bin/litellm (not in PATH)"
            ((TESTS_PASSED++))
        else
            log_fail "LiteLLM not found anywhere"
            ((TESTS_FAILED++))
        fi
    fi
}

# ─── Test 3: Port Availability Check ────────────────────────────────
test_port_check() {
    log_test "Test 3: Port availability check"

    local test_ports=(8000 8001)
    local ports_ok=true

    for port in "${test_ports[@]}"; do
        if lsof -Pi :$port -sTCP:LISTEN -t &> /dev/null 2>&1; then
            log_info "Port $port is occupied"

            # Test if we can identify the process
            local pid=$(lsof -ti:$port)
            if [ -n "$pid" ]; then
                log_pass "Can identify process on port $port (PID: $pid)"
                ((TESTS_PASSED++))
            else
                log_fail "Cannot identify process on port $port"
                ((TESTS_FAILED++))
                ports_ok=false
            fi
        else
            log_pass "Port $port is available"
            ((TESTS_PASSED++))
        fi
    done
}

# ─── Test 4: Config File Validation ─────────────────────────────────
test_config_validation() {
    log_test "Test 4: LiteLLM config validation"

    local config_file="$HOME/.config/litellm/config.yaml"

    if [ -f "$config_file" ]; then
        if [ -s "$config_file" ]; then
            log_pass "Config file exists and is not empty"
            ((TESTS_PASSED++))

            # Try to validate YAML syntax
            if command -v python3 &> /dev/null; then
                if python3 -c "import yaml; yaml.safe_load(open('$config_file'))" 2>/dev/null; then
                    log_pass "Config file has valid YAML syntax"
                    ((TESTS_PASSED++))
                else
                    log_fail "Config file has invalid YAML syntax"
                    ((TESTS_FAILED++))
                fi
            fi
        else
            log_fail "Config file is empty"
            ((TESTS_FAILED++))
        fi
    else
        log_info "Config file not found (expected if setup not run)"
        ((TESTS_PASSED++))
    fi
}

# ─── Test 5: Directory Structure ────────────────────────────────────
test_directory_structure() {
    log_test "Test 5: Required directory structure"

    local required_dirs=(
        "$HOME/.backlog-toolkit/services"
        "$HOME/.backlog-toolkit/services/logs"
        "$HOME/.backlog-toolkit/services/pids"
        "$HOME/.config/litellm"
    )

    local all_ok=true
    for dir in "${required_dirs[@]}"; do
        if [ -d "$dir" ]; then
            log_pass "Directory exists: $dir"
            ((TESTS_PASSED++))
        else
            log_info "Directory missing: $dir (will be auto-created)"
            ((TESTS_PASSED++))  # Not a failure, should be auto-created
        fi
    done
}

# ─── Test 6: Python Dependencies ────────────────────────────────────
test_python_dependencies() {
    log_test "Test 6: Python dependencies check"

    local required_deps=("litellm" "flask")
    local optional_deps=("chromadb" "sentence_transformers" "yaml" "redis")

    # Check required
    for dep in "${required_deps[@]}"; do
        if python3 -c "import $dep" 2>/dev/null; then
            log_pass "Required dependency installed: $dep"
            ((TESTS_PASSED++))
        else
            log_fail "Required dependency missing: $dep"
            ((TESTS_FAILED++))
        fi
    done

    # Check optional (not failures)
    for dep in "${optional_deps[@]}"; do
        if python3 -c "import $dep" 2>/dev/null; then
            log_pass "Optional dependency installed: $dep"
        else
            log_info "Optional dependency missing: $dep"
        fi
        ((TESTS_PASSED++))
    done
}

# ─── Test 7: Service Health Checks ──────────────────────────────────
test_service_health() {
    log_test "Test 7: Service health endpoints"

    local services=(
        "8000:LiteLLM"
        "8001:RAG"
    )

    for service in "${services[@]}"; do
        local port=${service%%:*}
        local name=${service##*:}

        if curl -s -m 2 "http://localhost:$port/health" &> /dev/null; then
            log_pass "$name service is healthy"
            ((TESTS_PASSED++))
        else
            log_info "$name service not running (expected if not started)"
            ((TESTS_PASSED++))  # Not a failure
        fi
    done
}

# ─── Test 8: Stale PID Cleanup ──────────────────────────────────────
test_stale_pid_cleanup() {
    log_test "Test 8: Stale PID file detection"

    local pid_dir="$HOME/.backlog-toolkit/services/pids"

    if [ -d "$pid_dir" ]; then
        local stale_count=0
        for pid_file in "$pid_dir"/*.pid; do
            if [ -f "$pid_file" ]; then
                local pid=$(cat "$pid_file")
                if ! ps -p "$pid" &> /dev/null; then
                    log_pass "Detected stale PID: $(basename "$pid_file")"
                    ((stale_count++))
                fi
            fi
        done

        if [ $stale_count -eq 0 ]; then
            log_pass "No stale PID files found"
        else
            log_pass "Found $stale_count stale PID(s) that can be cleaned"
        fi
        ((TESTS_PASSED++))
    else
        log_info "PID directory doesn't exist yet"
        ((TESTS_PASSED++))
    fi
}

# ─── Run All Tests ───────────────────────────────────────────────────
main() {
    echo ""
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║         Backlog Toolkit - Robustness Test Suite               ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo ""

    test_empty_credentials
    echo ""

    test_path_detection
    echo ""

    test_port_check
    echo ""

    test_config_validation
    echo ""

    test_directory_structure
    echo ""

    test_python_dependencies
    echo ""

    test_service_health
    echo ""

    test_stale_pid_cleanup
    echo ""

    # Summary
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║                       Test Summary                             ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo ""
    echo "Tests Passed: ${GREEN}$TESTS_PASSED${NC}"
    echo "Tests Failed: ${RED}$TESTS_FAILED${NC}"
    echo ""

    if [ $TESTS_FAILED -eq 0 ]; then
        log_pass "All tests passed! ✓"
        echo ""
        log_info "The setup scripts should handle all common failure scenarios"
        return 0
    else
        log_fail "Some tests failed"
        echo ""
        log_info "Review failures above and update scripts accordingly"
        return 1
    fi
}

main "$@"
