#!/usr/bin/env bash
# ─── Start All Required Services for Backlog Toolkit ────────────────
# Starts LiteLLM proxy, RAG server, and optional services (Redis, Ollama)
# Usage: ./scripts/services/start-services.sh [options]

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Logging
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[✓]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[!]${NC} $1"; }
log_error() { echo -e "${RED}[✗]${NC} $1"; }

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SERVICES_DIR="$HOME/.backlog-toolkit/services"
LOG_DIR="$SERVICES_DIR/logs"
PID_DIR="$SERVICES_DIR/pids"

# Create directories
mkdir -p "$SERVICES_DIR" "$LOG_DIR" "$PID_DIR"

# Service configuration
LITELLM_CONFIG="${LITELLM_CONFIG:-$HOME/.config/litellm/config.yaml}"
LITELLM_PORT="${LITELLM_PORT:-8000}"
RAG_PORT="${RAG_PORT:-8001}"

# Detect interactive mode
# Check environment variable first (highest priority)
if [ -n "${BACKLOG_INTERACTIVE_MODE:-}" ]; then
    INTERACTIVE_MODE="$BACKLOG_INTERACTIVE_MODE"
# Then check if stdin is a terminal
elif [ -t 0 ]; then
    INTERACTIVE_MODE=true
else
    INTERACTIVE_MODE=false
fi

# Debug output
if [ "${DEBUG:-false}" = true ]; then
    echo "[DEBUG] INTERACTIVE_MODE=$INTERACTIVE_MODE" >&2
    echo "[DEBUG] stdin is terminal: $([ -t 0 ] && echo true || echo false)" >&2
    echo "[DEBUG] BACKLOG_INTERACTIVE_MODE=${BACKLOG_INTERACTIVE_MODE:-unset}" >&2
fi

# ─── Docker Mode Detection ────────────────────────────────────────
is_docker_mode() {
    # Docker mode if: compose file exists AND docker is running AND not forced native
    if [ "${BACKLOG_NATIVE_MODE:-}" = "true" ]; then return 1; fi
    local compose_file="$REPO_ROOT/docker-compose.yml"
    [ -f "$compose_file" ] && command -v docker &>/dev/null && docker info &>/dev/null 2>&1
}

# ─── Start Services via Docker Compose ────────────────────────────
start_docker_services() {
    echo ""
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║        Starting Backlog Toolkit Services (Docker)             ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo ""

    local compose_file="$REPO_ROOT/docker-compose.yml"
    local env_file="$REPO_ROOT/.env.docker.local"
    local template_file="$REPO_ROOT/.env.docker"

    # 1. Check AWS SSO is valid
    local aws_profile="${AWS_PROFILE:-default}"
    log_info "Checking AWS SSO session (profile: $aws_profile)..."
    if aws sts get-caller-identity --profile "$aws_profile" &>/dev/null; then
        log_success "AWS SSO session valid"
    else
        log_warning "AWS SSO session expired or invalid"
        log_info "Run: aws sso login --profile $aws_profile"
        if [ "$INTERACTIVE_MODE" = true ]; then
            echo ""
            read -p "Run 'aws sso login --profile $aws_profile' now? (y/N): " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                aws sso login --profile "$aws_profile"
            fi
        fi
        # Re-check after potential login
        if ! aws sts get-caller-identity --profile "$aws_profile" &>/dev/null; then
            log_error "AWS SSO still not valid — Bedrock models will not work"
            log_info "Continue anyway (LiteLLM will start but model calls will fail)"
        fi
    fi

    # 1b. Build CA bundle (includes corporate certs like Zscaler)
    local ca_bundle_script="$REPO_ROOT/docker/certs/build-ca-bundle.sh"
    local ca_bundle_file="$REPO_ROOT/docker/certs/ca-bundle.crt"
    if [ -x "$ca_bundle_script" ] && [ ! -f "$ca_bundle_file" ]; then
        log_info "Building CA certificate bundle for Docker..."
        "$ca_bundle_script"
    fi

    # 1c. Resolve SSO credentials on the host and export as env vars
    # Docker containers can't refresh SSO tokens (missing corporate CA certs),
    # so we resolve credentials here and pass them via environment variables.
    log_info "Resolving AWS credentials for Docker..."
    local creds_json
    creds_json=$(aws configure export-credentials --profile "$aws_profile" 2>/dev/null || true)

    if [ -n "$creds_json" ] && echo "$creds_json" | jq -e '.AccessKeyId' &>/dev/null; then
        export AWS_ACCESS_KEY_ID=$(echo "$creds_json" | jq -r '.AccessKeyId')
        export AWS_SECRET_ACCESS_KEY=$(echo "$creds_json" | jq -r '.SecretAccessKey')
        export AWS_SESSION_TOKEN=$(echo "$creds_json" | jq -r '.SessionToken // empty')
        export AWS_DEFAULT_REGION=$(aws configure get region --profile "$aws_profile" 2>/dev/null || echo "us-east-1")
        log_success "AWS credentials resolved (AccessKeyId: ${AWS_ACCESS_KEY_ID:0:8}...)"
        log_info "Region: $AWS_DEFAULT_REGION"
    else
        log_error "Failed to resolve AWS credentials from profile '$aws_profile'"
        log_info "Ensure SSO session is valid: aws sso login --profile $aws_profile"
        log_info "Docker containers will not be able to call Bedrock models"
    fi
    echo ""

    # 2. Ensure .env.docker.local exists
    if [ ! -f "$env_file" ]; then
        if [ -f "$template_file" ]; then
            log_info "Creating .env.docker.local from template..."
            cp "$template_file" "$env_file"
            log_success "Created $env_file — review and update values if needed"
        else
            log_error "No .env.docker template found at $template_file"
            return 1
        fi
    else
        log_success ".env.docker.local found"
    fi
    echo ""

    # 3. Start services with docker compose
    log_info "Starting Docker services..."
    if ! docker compose -f "$compose_file" --env-file "$env_file" up -d --build 2>&1; then
        log_error "docker compose up failed"
        log_info "Check: docker compose -f $compose_file logs"
        return 1
    fi
    echo ""

    # 4. Wait for health endpoints
    log_info "Waiting for services to become healthy..."

    # Wait for LiteLLM
    local max_wait=60
    local waited=0
    echo -n "  LiteLLM: "
    while [ $waited -lt $max_wait ]; do
        if curl -sf http://localhost:8000/health/readiness &>/dev/null; then
            echo ""
            log_success "LiteLLM healthy at http://localhost:8000"
            break
        fi
        sleep 2
        waited=$((waited + 2))
        echo -n "."
    done
    if [ $waited -ge $max_wait ]; then
        echo ""
        log_warning "LiteLLM did not become healthy in ${max_wait}s"
        log_info "Check: docker compose -f $compose_file logs litellm"
    fi

    # Wait for RAG
    waited=0
    max_wait=60
    echo -n "  RAG: "
    while [ $waited -lt $max_wait ]; do
        if curl -sf http://localhost:8001/health &>/dev/null; then
            echo ""
            log_success "RAG healthy at http://localhost:8001"
            break
        fi
        sleep 2
        waited=$((waited + 2))
        echo -n "."
    done
    if [ $waited -ge $max_wait ]; then
        echo ""
        log_warning "RAG did not become healthy in ${max_wait}s"
        log_info "Check: docker compose -f $compose_file logs rag"
    fi

    echo ""

    # 5. Show status summary
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║                    Service Status (Docker)                    ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo ""
    docker compose -f "$compose_file" --env-file "$env_file" ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || \
        docker compose -f "$compose_file" --env-file "$env_file" ps
    echo ""

    # 6. Show LiteLLM UI credentials
    # shellcheck disable=SC1090
    local ui_key=$(grep "^LITELLM_MASTER_KEY=" "$env_file" 2>/dev/null | cut -d= -f2-)
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║                  LiteLLM UI Credentials                      ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo ""
    echo "  URL:      http://localhost:8000/ui/login/"
    echo "  Username: admin"
    if [ -n "$ui_key" ]; then
        echo "  Password: $ui_key"
    else
        echo "  Password: (check .env.docker.local for LITELLM_MASTER_KEY)"
    fi
    echo ""

    log_success "Docker services ready!"
    echo ""
    echo "Useful commands:"
    echo "  docker compose logs -f                        - Tail all logs"
    echo "  docker compose logs -f litellm                - Tail LiteLLM logs"
    echo "  ./scripts/services/stop-services.sh           - Stop all services"
    echo "  ./scripts/services/status.sh                  - Check service status"
    echo "  BACKLOG_NATIVE_MODE=true ./scripts/services/start-services.sh  - Force native mode"
    echo ""
}

# ─── Check if SSO Session is Valid ─────────────────────────────────
check_sso_session() {
    local profile="$1"

    # Try to get caller identity using the profile
    if aws sts get-caller-identity --profile "$profile" &>/dev/null; then
        return 0
    else
        return 1
    fi
}

# ─── Get SSO Credentials from Cache ─────────────────────────────────
get_sso_credentials() {
    local profile="$1"

    # Use aws configure export-credentials (AWS CLI 2.13+)
    if command -v aws &>/dev/null; then
        local creds=$(aws configure export-credentials --profile "$profile" --format json 2>/dev/null)

        if [ -n "$creds" ]; then
            export AWS_ACCESS_KEY_ID=$(echo "$creds" | jq -r '.AccessKeyId // empty')
            export AWS_SECRET_ACCESS_KEY=$(echo "$creds" | jq -r '.SecretAccessKey // empty')
            export AWS_SESSION_TOKEN=$(echo "$creds" | jq -r '.SessionToken // empty')

            if [ -n "$AWS_ACCESS_KEY_ID" ] && [ -n "$AWS_SECRET_ACCESS_KEY" ]; then
                return 0
            fi
        fi
    fi

    # Fallback: read from cache directly
    local cache_dir="$HOME/.aws/cli/cache"
    if [ -d "$cache_dir" ]; then
        # Find the most recent cache file for this profile
        local cache_file=$(ls -t "$cache_dir"/*.json 2>/dev/null | head -1)

        if [ -f "$cache_file" ]; then
            local access_key=$(jq -r '.Credentials.AccessKeyId // empty' "$cache_file" 2>/dev/null)
            local secret_key=$(jq -r '.Credentials.SecretAccessKey // empty' "$cache_file" 2>/dev/null)
            local session_token=$(jq -r '.Credentials.SessionToken // empty' "$cache_file" 2>/dev/null)
            local expiration=$(jq -r '.Credentials.Expiration // empty' "$cache_file" 2>/dev/null)

            if [ -n "$access_key" ] && [ -n "$secret_key" ]; then
                # Check if credentials are expired
                if [ -n "$expiration" ]; then
                    local exp_epoch=$(date -j -f "%Y-%m-%dT%H:%M:%SZ" "$expiration" "+%s" 2>/dev/null || echo "0")
                    local now_epoch=$(date "+%s")

                    if [ "$exp_epoch" -gt "$now_epoch" ]; then
                        export AWS_ACCESS_KEY_ID="$access_key"
                        export AWS_SECRET_ACCESS_KEY="$secret_key"
                        export AWS_SESSION_TOKEN="$session_token"
                        return 0
                    else
                        log_warning "SSO credentials expired: $expiration"
                        return 1
                    fi
                fi
            fi
        fi
    fi

    return 1
}

# ─── Check if Profile is SSO ────────────────────────────────────────
is_sso_profile() {
    local profile="$1"
    local config_file="$HOME/.aws/config"

    if [ ! -f "$config_file" ]; then
        return 1
    fi

    # Check if profile has sso_* settings
    local profile_header="[profile $profile]"
    if [ "$profile" = "default" ]; then
        profile_header="[default]"
    fi

    local in_profile=false
    while IFS= read -r line; do
        if [[ "$line" =~ ^\[([^]]+)\] ]]; then
            if [ "$line" = "$profile_header" ]; then
                in_profile=true
            else
                in_profile=false
            fi
        elif [ "$in_profile" = true ]; then
            if [[ "$line" =~ ^sso_session ]] || [[ "$line" =~ ^sso_start_url ]]; then
                return 0
            fi
        fi
    done < "$config_file"

    return 1
}

# ─── Find First Profile with Credentials ───────────────────────────
find_profile_with_credentials() {
    local aws_creds_file="$1"
    local current_profile=""
    local has_key=false
    local has_secret=false

    while IFS= read -r line; do
        # Check if this is a profile header
        if [[ "$line" =~ ^\[([^]]+)\] ]]; then
            # If we found a complete profile, return it
            if [ -n "$current_profile" ] && [ "$has_key" = true ] && [ "$has_secret" = true ]; then
                echo "$current_profile"
                return 0
            fi

            # Start checking a new profile
            current_profile="${BASH_REMATCH[1]}"
            has_key=false
            has_secret=false
        elif [ -n "$current_profile" ]; then
            # Check for credentials in current profile
            if [[ "$line" =~ ^aws_access_key_id ]]; then
                has_key=true
            elif [[ "$line" =~ ^aws_secret_access_key ]]; then
                has_secret=true
            fi
        fi
    done < "$aws_creds_file"

    # Check the last profile
    if [ -n "$current_profile" ] && [ "$has_key" = true ] && [ "$has_secret" = true ]; then
        echo "$current_profile"
        return 0
    fi

    return 1
}

# ─── Load AWS Credentials from Standard Files ──────────────────────
load_aws_credentials_from_files() {
    local aws_creds_file="$HOME/.aws/credentials"
    local aws_config_file="$HOME/.aws/config"

    # Try to load from ~/.aws/credentials
    if [ ! -f "$aws_creds_file" ]; then
        return 1
    fi

    log_info "Found AWS credentials file: $aws_creds_file"

    # Determine which profile to use
    # Priority: BACKLOG_AWS_PROFILE > AWS_PROFILE > default > auto-detect
    local profile="${BACKLOG_AWS_PROFILE:-${AWS_PROFILE:-}}"
    local profile_source="default"

    # Check if profile is set and has credentials
    if [ -n "$profile" ]; then
        # First, check if it's an SSO profile
        if is_sso_profile "$profile"; then
            log_info "Detected SSO profile: $profile"

            # Try to get SSO credentials
            if get_sso_credentials "$profile"; then
                log_success "SSO credentials loaded for profile: $profile"

                # Get region from config
                if [ -f "$aws_config_file" ]; then
                    local profile_header="[profile $profile]"
                    if [ "$profile" = "default" ]; then
                        profile_header="[default]"
                    fi

                    local in_profile=false
                    while IFS= read -r line; do
                        if [[ "$line" =~ ^\[([^]]+)\] ]]; then
                            if [ "$line" = "$profile_header" ]; then
                                in_profile=true
                            else
                                in_profile=false
                            fi
                        elif [ "$in_profile" = true ]; then
                            if [[ "$line" =~ ^region[[:space:]]*=[[:space:]]*(.+)$ ]]; then
                                export AWS_REGION=$(echo "${BASH_REMATCH[1]}" | xargs)
                            fi
                        fi
                    done < "$aws_config_file"
                fi

                if [ -n "${AWS_REGION:-}" ]; then
                    log_success "AWS region: $AWS_REGION"
                else
                    log_info "No region configured, using default (us-east-1)"
                    export AWS_REGION="us-east-1"
                fi

                return 0
            else
                log_warning "Failed to load SSO credentials for profile: $profile"
                log_info "Try running: aws sso login --profile $profile"

                if [ "$INTERACTIVE_MODE" = true ]; then
                    echo ""
                    read -p "Run 'aws sso login --profile $profile' now? (y/N): " -n 1 -r
                    echo
                    if [[ $REPLY =~ ^[Yy]$ ]]; then
                        aws sso login --profile "$profile"
                        # Try again after login
                        if get_sso_credentials "$profile"; then
                            log_success "SSO credentials loaded after login"
                            return 0
                        fi
                    fi
                fi

                profile=""  # Fall through to other methods
            fi
        else
            # Check if the specified profile has static credentials
            local has_creds=$(awk -v prof="$profile" '
                $0 ~ "^\\[" prof "\\]$" {in_profile=1; next}
                /^\[/ {in_profile=0}
                in_profile && /^aws_access_key_id/ {print "yes"; exit}
            ' "$aws_creds_file")

            if [ "$has_creds" = "yes" ]; then
                if [ -n "${BACKLOG_AWS_PROFILE:-}" ]; then
                    log_info "Using BACKLOG_AWS_PROFILE: $profile"
                else
                    log_info "Using AWS_PROFILE from environment: $profile"
                fi
                profile_source="env_var"
            else
                log_warning "Profile '$profile' has no static credentials"

                # In interactive mode, show available profiles and let user choose
                if [ "$INTERACTIVE_MODE" = true ]; then
                    echo ""
                    log_info "Available AWS profiles with credentials:"
                    local profiles=$(grep -o "^\[[^]]*\]" "$aws_creds_file" | tr -d '[]')
                    local valid_profiles=()

                    for p in $profiles; do
                        local check=$(awk -v prof="$p" '
                            $0 ~ "^\\[" prof "\\]$" {in_profile=1; next}
                            /^\[/ {in_profile=0}
                            in_profile && /^aws_access_key_id/ {print "yes"; exit}
                        ' "$aws_creds_file")
                        if [ "$check" = "yes" ]; then
                            valid_profiles+=("$p")
                            echo "  - $p"
                        fi
                    done

                    echo ""
                    read -p "Select profile to use (or press Enter to skip): " selected_profile

                    if [ -n "$selected_profile" ]; then
                        # Verify the selected profile is valid
                        for vp in "${valid_profiles[@]}"; do
                            if [ "$vp" = "$selected_profile" ]; then
                                profile="$selected_profile"
                                profile_source="user_selected"
                                log_success "Using selected profile: $profile"
                                break
                            fi
                        done

                        if [ "$profile_source" != "user_selected" ]; then
                            log_warning "Invalid profile selected, will auto-detect"
                            profile=""
                        fi
                    else
                        profile=""
                    fi
                else
                    log_info "Searching for valid profile..."
                    profile=""
                fi
            fi
        fi
    fi

    # If no valid profile yet, try to find a profile with actual credentials
    if [ -z "$profile" ]; then
        # Try 'default' first
        if grep -q "^\[default\]" "$aws_creds_file"; then
            # Check if default has credentials
            local has_creds=$(awk '/^\[default\]/,/^\[/ { if (/^aws_access_key_id/) print "yes" }' "$aws_creds_file" | head -1)
            if [ "$has_creds" = "yes" ]; then
                profile="default"
                profile_source="default_profile"
            fi
        fi

        # If no default or default has no credentials, find first profile with credentials
        if [ -z "$profile" ]; then
            profile=$(find_profile_with_credentials "$aws_creds_file")
            if [ -z "$profile" ]; then
                log_info "No AWS profiles with static credentials found"
                log_info "Note: SSO profiles (like 'cc') are not supported for this toolkit"
                log_info "You need to configure static AWS credentials for Bedrock access"
                return 1
            fi
            profile_source="auto_detected"
        fi
    fi

    if [ "$profile_source" = "auto_detected" ]; then
        log_warning "Auto-detected AWS profile: $profile"
        log_info "To use a specific profile, set: export BACKLOG_AWS_PROFILE=your-profile"
    elif [ "$profile_source" = "default_profile" ]; then
        log_info "Using default AWS profile"
    fi

    # Read credentials from the selected profile
    local in_profile=false
    while IFS= read -r line; do
        # Check if we're in the right profile
        if [[ "$line" =~ ^\[([^]]+)\] ]]; then
            if [ "${BASH_REMATCH[1]}" = "$profile" ]; then
                in_profile=true
            else
                in_profile=false
            fi
        elif [ "$in_profile" = true ]; then
            # Extract credentials (trim whitespace)
            if [[ "$line" =~ ^aws_access_key_id[[:space:]]*=[[:space:]]*(.+)$ ]]; then
                export AWS_ACCESS_KEY_ID=$(echo "${BASH_REMATCH[1]}" | xargs)
            elif [[ "$line" =~ ^aws_secret_access_key[[:space:]]*=[[:space:]]*(.+)$ ]]; then
                export AWS_SECRET_ACCESS_KEY=$(echo "${BASH_REMATCH[1]}" | xargs)
            fi
        fi
    done < "$aws_creds_file"

    # Try to load region from ~/.aws/config if we found credentials
    if [ -n "${AWS_ACCESS_KEY_ID:-}" ] && [ -f "$aws_config_file" ]; then
        local profile_header="[profile $profile]"
        if [ "$profile" = "default" ]; then
            profile_header="[default]"
        fi

        local in_profile=false
        while IFS= read -r line; do
            if [[ "$line" =~ ^\[([^]]+)\] ]]; then
                if [ "$line" = "$profile_header" ]; then
                    in_profile=true
                else
                    in_profile=false
                fi
            elif [ "$in_profile" = true ]; then
                if [[ "$line" =~ ^region[[:space:]]*=[[:space:]]*(.+)$ ]]; then
                    export AWS_REGION=$(echo "${BASH_REMATCH[1]}" | xargs)
                fi
            fi
        done < "$aws_config_file"
    fi

    # Check if we successfully loaded AWS credentials
    if [ -n "${AWS_ACCESS_KEY_ID:-}" ] && [ -n "${AWS_SECRET_ACCESS_KEY:-}" ]; then
        log_success "AWS credentials loaded from ~/.aws/ (profile: ${profile})"
        if [ -n "${AWS_REGION:-}" ]; then
            log_success "AWS region: $AWS_REGION"
        else
            log_info "No region configured, using default (us-east-1)"
            export AWS_REGION="us-east-1"
        fi
        return 0
    fi

    return 1
}

# ─── Load Environment ───────────────────────────────────────────────
load_environment() {
    log_info "Loading environment variables..."

    local env_file="$HOME/.backlog-toolkit-env"
    if [ -f "$env_file" ]; then
        # shellcheck source=/dev/null
        source "$env_file"
        log_success "Environment loaded from $env_file"

        # Check for empty credentials
        local has_empty=false
        local aws_empty=false
        local anthropic_empty=false

        if [ "${AWS_ACCESS_KEY_ID:-}" = "''" ] || [ "${AWS_ACCESS_KEY_ID:-}" = "" ]; then
            if grep -q "AWS_ACCESS_KEY_ID" "$env_file"; then
                has_empty=true
                aws_empty=true
            fi
        fi
        if [ "${AWS_SECRET_ACCESS_KEY:-}" = "''" ] || [ "${AWS_SECRET_ACCESS_KEY:-}" = "" ]; then
            if grep -q "AWS_SECRET_ACCESS_KEY" "$env_file"; then
                has_empty=true
                aws_empty=true
            fi
        fi
        if [ "${ANTHROPIC_API_KEY:-}" = "''" ] || [ "${ANTHROPIC_API_KEY:-}" = "" ]; then
            if grep -q "ANTHROPIC_API_KEY" "$env_file"; then
                has_empty=true
                anthropic_empty=true
            fi
        fi

        # Try to load AWS credentials from standard AWS files if empty
        if [ "$aws_empty" = true ]; then
            log_info "AWS credentials empty in toolkit config"
            log_info "Checking ~/.aws/ files for static credentials..."
            echo ""
            log_info "Note: This toolkit needs AWS Bedrock credentials"
            log_info "  - SSO profiles (like 'cc' for Claude Code) won't work"
            log_info "  - You need static AWS credentials configured for Bedrock"
            log_info "  - Set BACKLOG_AWS_PROFILE to choose a specific profile"
            echo ""

            if load_aws_credentials_from_files; then
                has_empty=false  # We found credentials, no need to prompt
            fi
        fi

        if [ "$has_empty" = true ]; then
            log_warning "Detected empty credentials in $env_file"
            log_info "Credentials are defined but not filled in"

            if [ "$INTERACTIVE_MODE" = true ]; then
                echo ""
                read -p "Would you like to configure credentials now? (y/N): " -n 1 -r
                echo
                if [[ $REPLY =~ ^[Yy]$ ]]; then
                    configure_credentials_interactive "$env_file"
                else
                    log_info "Continuing with empty credentials (will fail later)"
                fi
            else
                log_info "Running in non-interactive mode, skipping credential configuration"
                log_info "Edit $env_file manually and re-run"
            fi
        fi
    else
        log_warning "Environment file not found at $env_file"
        log_info "Run ./scripts/setup/complete-setup.sh first"
    fi
}

# ─── Configure Credentials Interactively ───────────────────────────
configure_credentials_interactive() {
    local env_file=$1

    # Safety check: should never be called in non-interactive mode
    if [ "$INTERACTIVE_MODE" != true ]; then
        log_error "configure_credentials_interactive called in non-interactive mode"
        return 1
    fi

    echo ""
    echo "Choose credential type to configure:"
    echo "  1) AWS Bedrock (recommended for production)"
    echo "  2) Anthropic API (simpler, direct access)"
    echo "  3) Skip (configure later)"
    echo ""
    read -p "Select [1-3]: " cred_choice

    case $cred_choice in
        1)
            log_info "Configuring AWS Bedrock credentials..."
            echo ""
            read -p "AWS Access Key ID: " aws_key
            read -p "AWS Secret Access Key: " aws_secret
            read -p "AWS Region [us-east-1]: " aws_region
            aws_region=${aws_region:-us-east-1}

            if [ -n "$aws_key" ] && [ -n "$aws_secret" ]; then
                # Create clean version without empty credentials
                local temp_file=$(mktemp)
                grep -v "export AWS_ACCESS_KEY_ID=''" "$env_file" | \
                grep -v "export AWS_SECRET_ACCESS_KEY=''" | \
                grep -v "export AWS_REGION=''" > "$temp_file"

                # Add new entries
                {
                    echo ""
                    echo "# AWS Bedrock Credentials (configured $(date))"
                    echo "export AWS_ACCESS_KEY_ID='$aws_key'"
                    echo "export AWS_SECRET_ACCESS_KEY='$aws_secret'"
                    echo "export AWS_REGION='$aws_region'"
                } >> "$temp_file"

                # Replace original file
                mv "$temp_file" "$env_file"

                # Reload environment
                # shellcheck source=/dev/null
                source "$env_file"

                log_success "AWS credentials configured and loaded"
            else
                log_error "Credentials cannot be empty"
            fi
            ;;

        2)
            log_info "Configuring Anthropic API..."
            echo ""
            read -p "Anthropic API Key: " api_key

            if [ -n "$api_key" ]; then
                # Create clean version without empty credentials
                local temp_file=$(mktemp)
                grep -v "export ANTHROPIC_API_KEY=''" "$env_file" > "$temp_file"

                # Add new entry
                {
                    echo ""
                    echo "# Anthropic API Key (configured $(date))"
                    echo "export ANTHROPIC_API_KEY='$api_key'"
                } >> "$temp_file"

                # Replace original file
                mv "$temp_file" "$env_file"

                # Reload environment
                # shellcheck source=/dev/null
                source "$env_file"

                log_success "Anthropic API key configured and loaded"
            else
                log_error "API key cannot be empty"
            fi
            ;;

        3|*)
            log_info "Skipping credential configuration"
            ;;
    esac
}

# ─── Pre-flight Diagnostics ────────────────────────────────────────
run_diagnostics() {
    log_info "Running pre-flight diagnostics..."

    local issues_found=0
    local issues_fixed=0

    # Check 1: Required directories
    if [ ! -d "$SERVICES_DIR" ] || [ ! -d "$LOG_DIR" ] || [ ! -d "$PID_DIR" ]; then
        log_info "Creating required directories..."
        mkdir -p "$SERVICES_DIR" "$LOG_DIR" "$PID_DIR"
        log_success "Directories created"
        issues_fixed=$((issues_fixed + 1))
    fi

    # Check 2: Clean stale PID files
    for pid_file in "$PID_DIR"/*.pid; do
        if [ -f "$pid_file" ]; then
            local pid=$(cat "$pid_file")
            if ! ps -p "$pid" &> /dev/null; then
                log_info "Removing stale PID: $(basename "$pid_file")"
                rm -f "$pid_file"
                issues_fixed=$((issues_fixed + 1))
            fi
        fi
    done

    # Check 3: Free occupied ports
    for port in $LITELLM_PORT $RAG_PORT; do
        if lsof -Pi :$port -sTCP:LISTEN -t &> /dev/null 2>&1; then
            log_warning "Port $port is occupied"
            issues_found=$((issues_found + 1))

            if [ "$INTERACTIVE_MODE" = true ]; then
                read -p "Kill process on port $port? (y/N): " -n 1 -r
                echo
                if [[ $REPLY =~ ^[Yy]$ ]]; then
                    local pid=$(lsof -ti:$port)
                    kill "$pid" 2>/dev/null || kill -9 "$pid" 2>/dev/null
                    sleep 1
                    if ! lsof -Pi :$port -sTCP:LISTEN -t &> /dev/null 2>&1; then
                        log_success "Port $port freed"
                        issues_fixed=$((issues_fixed + 1))
                    fi
                fi
            else
                log_info "Running in non-interactive mode"
                log_info "Kill manually with: kill \$(lsof -ti:$port)"
            fi
        fi
    done

    if [ "$issues_fixed" -gt 0 ]; then
        log_success "Auto-fixed $issues_fixed issue(s)"
    fi

    if [ "$issues_found" -gt "$issues_fixed" ]; then
        log_warning "$((issues_found - issues_fixed)) issue(s) remain"
    fi
}

# ─── Check Prerequisites ────────────────────────────────────────────
check_prerequisites() {
    log_info "Checking prerequisites..."

    local all_ok=true
    local warnings=0

    # Check LiteLLM
    if command -v litellm &> /dev/null; then
        log_success "LiteLLM found"
    else
        log_error "LiteLLM not found"
        log_info "Install: pip install 'litellm[proxy]'"
        log_info "Or run: ./scripts/setup/complete-setup.sh"
        all_ok=false
    fi

    # Check Python
    if command -v python3 &> /dev/null; then
        log_success "Python found"
    else
        log_error "Python 3.10+ required"
        all_ok=false
    fi

    # Check API keys (need either Anthropic API or AWS Bedrock credentials)
    local has_credentials=false
    local empty_credentials=false

    # Check Anthropic API key
    if [ -n "${ANTHROPIC_API_KEY:-}" ] && [ "${ANTHROPIC_API_KEY}" != "''" ] && [ "${ANTHROPIC_API_KEY}" != "" ]; then
        log_success "ANTHROPIC_API_KEY configured"
        has_credentials=true
    fi

    # Check AWS Bedrock credentials (must have both and not be empty)
    if [ -n "${AWS_ACCESS_KEY_ID:-}" ] && [ -n "${AWS_SECRET_ACCESS_KEY:-}" ]; then
        # Check if they're empty strings or just quotes
        if [ "${AWS_ACCESS_KEY_ID}" != "''" ] && [ "${AWS_ACCESS_KEY_ID}" != "" ] && \
           [ "${AWS_SECRET_ACCESS_KEY}" != "''" ] && [ "${AWS_SECRET_ACCESS_KEY}" != "" ]; then
            log_success "AWS credentials configured (for Bedrock)"
            has_credentials=true
        else
            log_warning "AWS credentials exist but are empty"
            empty_credentials=true
        fi
    fi

    if [ "$has_credentials" = false ]; then
        if [ "$empty_credentials" = true ]; then
            log_error "API credentials are empty (not configured)"
            log_info "Your ~/.backlog-toolkit-env has empty credential values"
            echo ""
            log_info "To fix this:"
            log_info "  1. Edit: nano ~/.backlog-toolkit-env"
            log_info "  2. Fill in your AWS credentials:"
            log_info "     export AWS_ACCESS_KEY_ID='your-actual-key'"
            log_info "     export AWS_SECRET_ACCESS_KEY='your-actual-secret'"
            log_info "  3. Or set ANTHROPIC_API_KEY if using Anthropic direct"
            log_info "  4. Then reload: source ~/.backlog-toolkit-env"
        else
            log_error "No API credentials found"
            log_info "Solution options:"
            log_info "  1. Source environment: source ~/.backlog-toolkit-env"
            log_info "  2. For Anthropic: export ANTHROPIC_API_KEY='your-key'"
            log_info "  3. For Bedrock: export AWS_ACCESS_KEY_ID='...' AWS_SECRET_ACCESS_KEY='...'"
            log_info "  4. Run setup: ./scripts/setup/complete-setup.sh"
        fi
        all_ok=false
    fi

    # Check LiteLLM config
    if [ -f "$LITELLM_CONFIG" ]; then
        if [ -s "$LITELLM_CONFIG" ]; then
            log_success "LiteLLM config found"
        else
            log_error "LiteLLM config is empty"
            all_ok=false
        fi
    else
        log_error "LiteLLM config not found at $LITELLM_CONFIG"
        log_info "Run setup: ./scripts/setup/complete-setup.sh"
        all_ok=false
    fi

    if [ "$all_ok" = false ]; then
        log_error "Prerequisites check failed"
        echo ""
        log_info "Quick fix: Run the setup wizard"
        log_info "  ./scripts/setup/complete-setup.sh"
        return 1
    fi

    if [ "$warnings" -gt 0 ]; then
        log_warning "$warnings warning(s) - services may have issues"
    fi
}

# ─── Start PostgreSQL via Docker (for LiteLLM UI) ───────────────────
POSTGRES_CONTAINER="backlog-postgres"
POSTGRES_USER="litellm"
POSTGRES_PASSWORD="litellm_pass"
POSTGRES_DB="litellm"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
DATABASE_URL="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@localhost:${POSTGRES_PORT}/${POSTGRES_DB}"

start_postgres() {
    log_info "Checking PostgreSQL (for LiteLLM UI)..."

    # Check Docker is available
    if ! command -v docker &> /dev/null; then
        log_info "Docker not installed - LiteLLM UI will be unavailable"
        log_info "Install Docker Desktop: https://www.docker.com/products/docker-desktop/"
        return 0
    fi

    # Check Docker daemon is running
    if ! docker info &> /dev/null 2>&1; then
        log_warning "Docker daemon not running - LiteLLM UI will be unavailable"
        log_info "Start Docker Desktop and re-run this script to enable the UI"
        return 0
    fi

    # Check if container already running
    if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^${POSTGRES_CONTAINER}$"; then
        log_success "PostgreSQL already running (container: $POSTGRES_CONTAINER)"
        export DATABASE_URL="$DATABASE_URL"
        return 0
    fi

    # Check if container exists but stopped
    if docker ps -a --format '{{.Names}}' 2>/dev/null | grep -q "^${POSTGRES_CONTAINER}$"; then
        log_info "Restarting existing PostgreSQL container..."
        docker start "$POSTGRES_CONTAINER" > /dev/null
    else
        log_info "Creating PostgreSQL container..."
        docker run -d \
            --name "$POSTGRES_CONTAINER" \
            -e POSTGRES_USER="$POSTGRES_USER" \
            -e POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
            -e POSTGRES_DB="$POSTGRES_DB" \
            -p "${POSTGRES_PORT}:5432" \
            --restart unless-stopped \
            postgres:16-alpine > /dev/null
    fi

    log_info "Waiting for PostgreSQL to be ready..."
    local max_wait=20
    local waited=0
    while [ $waited -lt $max_wait ]; do
        sleep 1
        waited=$((waited + 1))
        if docker exec "$POSTGRES_CONTAINER" pg_isready -U "$POSTGRES_USER" &>/dev/null 2>&1; then
            log_success "PostgreSQL ready (Port: $POSTGRES_PORT)"
            export DATABASE_URL="$DATABASE_URL"
            return 0
        fi
    done

    log_warning "PostgreSQL did not become ready in ${max_wait}s - LiteLLM UI may not work"
    return 0  # Not critical, LiteLLM can still run without UI
}

# ─── Start Redis (Optional) ─────────────────────────────────────────
start_redis() {
    log_info "Checking Redis..."

    if ! command -v redis-server &> /dev/null; then
        log_info "Redis not installed (optional)"
        return 0
    fi

    if pgrep redis-server &> /dev/null; then
        log_success "Redis already running"
        return 0
    fi

    log_info "Starting Redis..."
    redis-server --daemonize yes \
        --logfile "$LOG_DIR/redis.log" \
        --pidfile "$PID_DIR/redis.pid" \
        2>&1 | tee -a "$LOG_DIR/redis.log"

    sleep 2

    if redis-cli ping &> /dev/null; then
        log_success "Redis started successfully"
    else
        log_warning "Redis failed to start (optional service)"
    fi
}

# ─── Start Ollama (Optional) ────────────────────────────────────────
start_ollama() {
    log_info "Checking Ollama..."

    if ! command -v ollama &> /dev/null; then
        log_info "Ollama not installed (optional)"
        return 0
    fi

    if pgrep ollama &> /dev/null; then
        log_success "Ollama already running"
        return 0
    fi

    log_info "Starting Ollama..."
    nohup ollama serve > "$LOG_DIR/ollama.log" 2>&1 &
    echo $! > "$PID_DIR/ollama.pid"

    sleep 3

    if curl -s http://localhost:11434/api/tags &> /dev/null; then
        # Verify qwen3-coder model is available
        if ollama list 2>/dev/null | grep -q "qwen3-coder"; then
            log_success "Ollama started (qwen3-coder available)"
        else
            log_warning "Ollama running but qwen3-coder not found. Run: ollama pull qwen3-coder:30b"
        fi
    else
        log_warning "Ollama failed to start (optional — LiteLLM will fall back to Haiku)"
    fi
}

# ─── Start LiteLLM Proxy ────────────────────────────────────────────
start_litellm() {
    log_info "Starting LiteLLM proxy..."

    # Check if already running
    if [ -f "$PID_DIR/litellm.pid" ]; then
        local pid=$(cat "$PID_DIR/litellm.pid")
        if ps -p "$pid" &> /dev/null; then
            log_success "LiteLLM already running (PID: $pid)"
            return 0
        else
            log_info "Cleaning stale PID file"
            rm -f "$PID_DIR/litellm.pid"
        fi
    fi

    # Check config exists
    if [ ! -f "$LITELLM_CONFIG" ]; then
        log_error "LiteLLM config not found at $LITELLM_CONFIG"
        log_info "Run setup first: ./scripts/setup/complete-setup.sh"
        return 1
    fi

    # Validate config is not empty
    if [ ! -s "$LITELLM_CONFIG" ]; then
        log_error "LiteLLM config is empty"
        return 1
    fi

    # Check if port is already in use
    if lsof -Pi :$LITELLM_PORT -sTCP:LISTEN -t &> /dev/null; then
        log_warning "Port $LITELLM_PORT already in use"
        log_info "Attempting to free port..."

        local existing_pid=$(lsof -ti:$LITELLM_PORT)
        kill "$existing_pid" 2>/dev/null || true
        sleep 2

        if lsof -Pi :$LITELLM_PORT -sTCP:LISTEN -t &> /dev/null; then
            log_error "Could not free port $LITELLM_PORT"
            log_info "Kill manually: kill \$(lsof -ti:$LITELLM_PORT)"
            return 1
        fi
        log_success "Port freed"
    fi

    log_info "Using config: $LITELLM_CONFIG"
    log_info "Port: $LITELLM_PORT"

    # Prepare environment variables for LiteLLM
    local env_vars=""

    # Pass AWS credentials if available
    if [ -n "${AWS_ACCESS_KEY_ID:-}" ]; then
        env_vars="AWS_ACCESS_KEY_ID='$AWS_ACCESS_KEY_ID' AWS_SECRET_ACCESS_KEY='$AWS_SECRET_ACCESS_KEY' AWS_REGION='${AWS_REGION:-us-east-1}'"

        # Include session token if present (for SSO)
        if [ -n "${AWS_SESSION_TOKEN:-}" ]; then
            env_vars="$env_vars AWS_SESSION_TOKEN='$AWS_SESSION_TOKEN'"
        fi

        log_info "Starting with AWS credentials (Bedrock)"
    fi

    # Pass Anthropic API key if available
    if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
        if [ -n "$env_vars" ]; then
            env_vars="$env_vars ANTHROPIC_API_KEY='$ANTHROPIC_API_KEY'"
        else
            env_vars="ANTHROPIC_API_KEY='$ANTHROPIC_API_KEY'"
        fi
        log_info "Starting with Anthropic API key"
    fi

    # Pass LiteLLM master key if set
    if [ -n "${LITELLM_MASTER_KEY:-}" ]; then
        env_vars="$env_vars LITELLM_MASTER_KEY='$LITELLM_MASTER_KEY'"
    fi

    # Pass DATABASE_URL if PostgreSQL is running (enables LiteLLM UI)
    if [ -n "${DATABASE_URL:-}" ]; then
        env_vars="$env_vars DATABASE_URL='$DATABASE_URL'"
        log_info "Starting with database support (UI enabled)"
    fi

    # Start LiteLLM with environment variables
    # Note: Using --detailed_debug for better logging
    if [ -n "$env_vars" ]; then
        eval "nohup env $env_vars litellm --config '$LITELLM_CONFIG' --port '$LITELLM_PORT' --detailed_debug > '$LOG_DIR/litellm.log' 2>&1 &"
    else
        nohup litellm --config "$LITELLM_CONFIG" --port "$LITELLM_PORT" --detailed_debug \
            > "$LOG_DIR/litellm.log" 2>&1 &
    fi

    local pid=$!
    echo $pid > "$PID_DIR/litellm.pid"

    log_info "Waiting for LiteLLM to start (PID: $pid)..."
    echo -n "  "

    # Wait with progress
    local max_wait=15
    local waited=0
    while [ $waited -lt $max_wait ]; do
        sleep 1
        waited=$((waited + 1))

        # Check if process died
        if ! ps -p "$pid" &> /dev/null; then
            echo ""
            log_error "LiteLLM process died during startup (after ${waited}s)"
            log_info "Last 10 lines of log:"
            tail -n 10 "$LOG_DIR/litellm.log" | sed 's/^/  /'
            return 1
        fi

        # Check if health endpoint responds
        if curl -s -m 2 http://localhost:$LITELLM_PORT/health/readiness &> /dev/null; then
            echo ""
            log_success "LiteLLM started successfully (PID: $pid) in ${waited}s"
            log_info "Health check: http://localhost:$LITELLM_PORT/health/readiness"

            # Test completions if in interactive mode
            if [ "$INTERACTIVE_MODE" = true ] && [ -n "${LITELLM_MASTER_KEY:-}" ]; then
                echo ""
                log_info "Testing model access..."

                local test_result=$(curl -s -m 10 http://localhost:$LITELLM_PORT/v1/chat/completions \
                    -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
                    -H "Content-Type: application/json" \
                    -d '{"model":"cheap","messages":[{"role":"user","content":"test"}],"max_tokens":5}' 2>&1)

                # Check if we got a valid response
                if echo "$test_result" | jq -e '.choices[0].message.content' &>/dev/null; then
                    log_success "Model test successful - completions working ✓"
                elif echo "$test_result" | grep -qi "bedrock.*InvokeModel\|Invalid Authentication\|security token"; then
                    log_warning "Bedrock permissions issue detected"
                    log_info "Your SSO role may not have bedrock:InvokeModel permission"
                    log_info "See: docs/BEDROCK-PERMISSIONS.md for solutions"
                elif echo "$test_result" | grep -qi "ANTHROPIC_API_KEY\|Missing.*API Key"; then
                    log_warning "API credentials not configured"
                    log_info "Add ANTHROPIC_API_KEY to ~/.backlog-toolkit-env"
                else
                    log_warning "Model test inconclusive - check logs if issues occur"
                fi
            fi

            return 0
        fi

        # Show progress with status messages
        if [ $((waited % 5)) -eq 0 ]; then
            echo ""
            log_info "  Still starting... (${waited}s elapsed, checking health endpoint)"
            echo -n "  "
        else
            echo -n "."
        fi
    done

    echo ""

    # Timeout - analyze what went wrong
    if ps -p "$pid" &> /dev/null; then
        log_warning "LiteLLM running but health check failed after ${max_wait}s"
        log_info "Process is alive but not responding, checking logs..."
    else
        log_error "LiteLLM process terminated"
    fi

    log_info "Last 15 lines of log:"
    tail -n 15 "$LOG_DIR/litellm.log" | sed 's/^/  /'

    # Try to diagnose common issues
    if grep -q "ModuleNotFoundError\|ImportError" "$LOG_DIR/litellm.log"; then
        log_error "Missing Python dependencies"
        log_info "Fix: pip install 'litellm[proxy]'"
    elif grep -q "config.*error\|yaml.*error" "$LOG_DIR/litellm.log"; then
        log_error "Config file error"
        log_info "Fix: Validate $LITELLM_CONFIG"
    elif grep -q "credential\|authentication\|API.*key" "$LOG_DIR/litellm.log"; then
        log_error "API credentials issue"
        log_info "Fix: Check environment variables in ~/.backlog-toolkit-env"
    fi

    return 1
}

# ─── Start RAG Server ───────────────────────────────────────────────
start_rag() {
    log_info "Starting RAG server..."

    # Check if already running
    if [ -f "$PID_DIR/rag.pid" ]; then
        local pid=$(cat "$PID_DIR/rag.pid")
        if ps -p "$pid" &> /dev/null; then
            log_success "RAG server already running (PID: $pid)"
            return 0
        else
            log_info "Cleaning stale PID file"
            rm -f "$PID_DIR/rag.pid"
        fi
    fi

    # Check if RAG server script exists
    local rag_server="$REPO_ROOT/scripts/rag/server.py"
    if [ ! -f "$rag_server" ]; then
        log_warning "RAG server not found at $rag_server"
        log_info "RAG provides code search - recommended for best experience"
        return 0
    fi

    # Check if port is available
    if lsof -Pi :$RAG_PORT -sTCP:LISTEN -t &> /dev/null; then
        log_warning "Port $RAG_PORT already in use"
        local existing_pid=$(lsof -ti:$RAG_PORT)
        kill "$existing_pid" 2>/dev/null || true
        sleep 1
    fi

    log_info "Port: $RAG_PORT"

    # Check Python dependencies
    if ! python3 -c "import flask, chromadb, sentence_transformers" 2>/dev/null; then
        log_warning "RAG dependencies missing"
        log_info "Install with: pip install flask chromadb sentence-transformers"
        log_info "Continuing without RAG (code search will be limited)"
        return 0
    fi

    # Start RAG server
    nohup python3 "$rag_server" --port "$RAG_PORT" \
        > "$LOG_DIR/rag.log" 2>&1 &

    local pid=$!
    echo $pid > "$PID_DIR/rag.pid"

    log_info "Waiting for RAG server to start (PID: $pid)..."
    echo -n "  "

    # Wait with timeout (embedding model load takes ~10s on first run)
    local max_wait=30
    local waited=0
    while [ $waited -lt $max_wait ]; do
        sleep 1
        waited=$((waited + 1))

        # Check if process died
        if ! ps -p "$pid" &> /dev/null; then
            echo ""
            log_warning "RAG server process died (after ${waited}s)"
            log_info "Last 5 lines of log:"
            tail -n 5 "$LOG_DIR/rag.log" | sed 's/^/  /'
            return 0  # Not critical
        fi

        # Check health
        if curl -s -m 2 http://localhost:$RAG_PORT/health &> /dev/null; then
            echo ""
            log_success "RAG server started successfully (PID: $pid) in ${waited}s"
            return 0
        fi

        # Show progress
        if [ $((waited % 3)) -eq 0 ]; then
            echo -n " ${waited}s"
        else
            echo -n "."
        fi
    done

    echo ""
    log_warning "RAG server timeout after ${max_wait}s (not critical, continuing)"
    log_info "Check logs: tail -f $LOG_DIR/rag.log"
}

# ─── Verify All Services ────────────────────────────────────────────
verify_services() {
    log_info "Verifying services..."
    echo ""

    local all_ok=true

    # LiteLLM
    if curl -s http://localhost:$LITELLM_PORT/health/readiness &> /dev/null; then
        log_success "LiteLLM: http://localhost:$LITELLM_PORT ✓"
    else
        log_error "LiteLLM: Not responding"
        all_ok=false
    fi

    # RAG (optional)
    if curl -s http://localhost:$RAG_PORT/health &> /dev/null 2>&1; then
        log_success "RAG: http://localhost:$RAG_PORT ✓"
    else
        log_info "RAG: Not available (optional)"
    fi

    # Redis (optional)
    if command -v redis-cli &> /dev/null && redis-cli ping &> /dev/null; then
        log_success "Redis: Available ✓"
    else
        log_info "Redis: Not available (optional)"
    fi

    # Ollama (optional)
    if curl -s http://localhost:11434/api/tags &> /dev/null; then
        log_success "Ollama: http://localhost:11434 ✓"
    else
        log_info "Ollama: Not available (optional)"
    fi

    echo ""

    if [ "$all_ok" = true ]; then
        log_success "All required services are running!"
    else
        log_error "Some required services failed to start"
        return 1
    fi
}

# ─── Show Service Status ────────────────────────────────────────────
show_status() {
    echo ""
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║                    Service Status                              ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo ""

    # LiteLLM
    if [ -f "$PID_DIR/litellm.pid" ]; then
        local pid=$(cat "$PID_DIR/litellm.pid")
        if ps -p "$pid" &> /dev/null; then
            echo -e "  LiteLLM:  ${GREEN}Running${NC} (PID: $pid, Port: $LITELLM_PORT)"
        else
            echo -e "  LiteLLM:  ${RED}Stopped${NC}"
        fi
    else
        echo -e "  LiteLLM:  ${RED}Not started${NC}"
    fi

    # RAG
    if [ -f "$PID_DIR/rag.pid" ]; then
        local pid=$(cat "$PID_DIR/rag.pid")
        if ps -p "$pid" &> /dev/null; then
            echo -e "  RAG:      ${GREEN}Running${NC} (PID: $pid, Port: $RAG_PORT)"
        else
            echo -e "  RAG:      ${RED}Stopped${NC}"
        fi
    else
        echo -e "  RAG:      ${YELLOW}Not configured${NC}"
    fi

    # Redis
    if pgrep redis-server &> /dev/null; then
        echo -e "  Redis:    ${GREEN}Running${NC}"
    else
        echo -e "  Redis:    ${YELLOW}Not running${NC}"
    fi

    # Ollama
    if pgrep ollama &> /dev/null; then
        echo -e "  Ollama:   ${GREEN}Running${NC}"
    else
        echo -e "  Ollama:   ${YELLOW}Not running${NC}"
    fi

    echo ""
    echo "Logs directory: $LOG_DIR"
    echo "PIDs directory: $PID_DIR"
    echo ""
}

# ─── Main ───────────────────────────────────────────────────────────
main() {
    # Docker mode: auto-detect and use docker compose if available
    if is_docker_mode; then
        start_docker_services
        return
    fi

    echo ""
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║        Starting Backlog Toolkit Services (Native)             ║"
    if [ "$INTERACTIVE_MODE" = false ]; then
        echo "║        (Running in non-interactive mode)                       ║"
    fi
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo ""

    if [ "$INTERACTIVE_MODE" = false ]; then
        log_info "Non-interactive mode: will skip prompts and use defaults"
        echo ""
    fi

    load_environment
    echo ""

    run_diagnostics
    echo ""

    check_prerequisites || exit 1
    echo ""

    # Start optional services first
    start_redis
    echo ""

    start_ollama
    echo ""

    start_postgres
    echo ""

    # Start required services
    start_litellm || {
        echo ""
        log_error "Failed to start LiteLLM proxy"
        log_info "Troubleshooting:"
        log_info "  1. Check logs: tail -n 50 $LOG_DIR/litellm.log"
        log_info "  2. Verify config: cat $LITELLM_CONFIG"
        log_info "  3. Test command: litellm --config $LITELLM_CONFIG --port $LITELLM_PORT"
        log_info "  4. Re-run setup: ./scripts/setup/complete-setup.sh"
        exit 1
    }
    echo ""

    start_rag
    echo ""

    # Verify everything
    verify_services || {
        echo ""
        log_warning "Service verification had issues"
        log_info "Check individual service logs in: $LOG_DIR/"
    }
    echo ""

    show_status

    log_success "Services ready!"
    echo ""

    # Show LiteLLM UI credentials
    local ui_key="${LITELLM_MASTER_KEY:-}"
    if [ -z "$ui_key" ]; then
        # Try to read the last defined master key from env file
        local env_file="$HOME/.backlog-toolkit-env"
        if [ -f "$env_file" ]; then
            ui_key=$(grep "^export LITELLM_MASTER_KEY=" "$env_file" | tail -1 | sed "s/export LITELLM_MASTER_KEY='\(.*\)'/\1/" | sed 's/export LITELLM_MASTER_KEY="\(.*\)"/\1/' | tr -d "'\"")
        fi
    fi

    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║                  LiteLLM UI Credentials                        ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo ""
    echo "  URL:      http://localhost:$LITELLM_PORT/ui/login/"
    echo "  Username: admin"
    if [ -n "$ui_key" ]; then
        echo "  Password: $ui_key"
    else
        echo "  Password: (LITELLM_MASTER_KEY not set)"
    fi
    echo ""

    echo "You can now run: claude"
    echo ""
    echo "Useful commands:"
    echo "  ./scripts/services/stop-services.sh   - Stop all services"
    echo "  ./scripts/services/status.sh          - Check service status"
    echo "  tail -f $LOG_DIR/litellm.log          - View LiteLLM logs"
    echo "  tail -f $LOG_DIR/rag.log              - View RAG logs"
    echo ""
}

main "$@"
