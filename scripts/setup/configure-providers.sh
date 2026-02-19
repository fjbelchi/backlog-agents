#!/usr/bin/env bash
# ─── Provider Configuration Functions ────────────────────────────────
# Functions to configure Anthropic, OpenAI, Bedrock, and Ollama

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

# ─── Configure Anthropic (API vs Bedrock) ───────────────────────────
configure_anthropic() {
    local env_file=$1

    echo ""
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║              Anthropic Claude Configuration                    ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo ""

    echo "How do you want to access Claude models?"
    echo "  1) Anthropic API (direct)"
    echo "  2) AWS Bedrock"
    echo ""
    read -p "Select option [1-2]: " anthropic_choice

    case $anthropic_choice in
        1)
            log_info "Configuring Anthropic API..."

            if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
                log_success "ANTHROPIC_API_KEY already set in environment"
                echo "export USE_ANTHROPIC_API=true" >> "$env_file"
            else
                read -p "Enter Anthropic API key: " api_key
                if [ -n "$api_key" ]; then
                    echo "export ANTHROPIC_API_KEY='$api_key'" >> "$env_file"
                    echo "export USE_ANTHROPIC_API=true" >> "$env_file"
                    export ANTHROPIC_API_KEY="$api_key"
                    export USE_ANTHROPIC_API=true
                    log_success "Anthropic API configured"
                else
                    log_error "API key required for Anthropic API"
                    return 1
                fi
            fi

            # Select models
            echo ""
            echo "Select Claude models to use (space-separated, e.g., '1 2 3'):"
            echo "  1) Claude Haiku 4.5 (cheap, fast, 200K context)"
            echo "  2) Claude Sonnet 4.6 (balanced, 200K context)"
            echo "  3) Claude Opus 4.6 (most capable, 200K context)"
            echo ""
            read -p "Models to enable [1 2 3]: " -a model_choices
            model_choices=${model_choices:-"1 2 3"}

            echo "export ANTHROPIC_MODELS='${model_choices[*]}'" >> "$env_file"
            log_success "Models configured: ${model_choices[*]}"
            ;;

        2)
            log_info "Configuring AWS Bedrock..."

            # Check if AWS credentials exist
            if [ -n "${AWS_ACCESS_KEY_ID:-}" ] && [ -n "${AWS_SECRET_ACCESS_KEY:-}" ]; then
                log_success "AWS credentials found in environment"
                echo "export USE_BEDROCK=true" >> "$env_file"

                if [ -n "${AWS_REGION:-}" ]; then
                    log_info "Using AWS region: $AWS_REGION"
                else
                    read -p "AWS Region [us-east-1]: " aws_region
                    aws_region=${aws_region:-us-east-1}
                    echo "export AWS_REGION='$aws_region'" >> "$env_file"
                    export AWS_REGION="$aws_region"
                fi
            elif command -v aws &> /dev/null && aws sts get-caller-identity &> /dev/null; then
                log_success "AWS CLI configured with valid credentials"
                echo "export USE_BEDROCK=true" >> "$env_file"

                local region=$(aws configure get region 2>/dev/null || echo "us-east-1")
                log_info "Using AWS region: $region"
                echo "export AWS_REGION='$region'" >> "$env_file"
                export AWS_REGION="$region"
            else
                log_warning "No AWS credentials found"
                read -p "Enter AWS Access Key ID: " aws_key_id
                read -p "Enter AWS Secret Access Key: " aws_secret
                read -p "AWS Region [us-east-1]: " aws_region
                aws_region=${aws_region:-us-east-1}

                echo "export AWS_ACCESS_KEY_ID='$aws_key_id'" >> "$env_file"
                echo "export AWS_SECRET_ACCESS_KEY='$aws_secret'" >> "$env_file"
                echo "export AWS_REGION='$aws_region'" >> "$env_file"
                echo "export USE_BEDROCK=true" >> "$env_file"

                export AWS_ACCESS_KEY_ID="$aws_key_id"
                export AWS_SECRET_ACCESS_KEY="$aws_secret"
                export AWS_REGION="$aws_region"
                export USE_BEDROCK=true

                log_success "AWS Bedrock configured"
            fi

            # Select Bedrock models
            echo ""
            echo "Select Claude models from Bedrock (space-separated):"
            echo "  1) Claude Haiku 4.5 (cheap, fast, 200K context)"
            echo "  2) Claude Sonnet 4.6 (balanced, 200K context)"
            echo "  3) Claude Opus 4.6 (most capable, 200K context)"
            echo ""
            read -p "Models to enable [1 2]: " -a bedrock_models
            bedrock_models=${bedrock_models:-"1 2"}

            echo "export BEDROCK_MODELS='${bedrock_models[*]}'" >> "$env_file"
            log_success "Bedrock models configured: ${bedrock_models[*]}"
            ;;

        *)
            log_error "Invalid option"
            return 1
            ;;
    esac

    return 0
}

# ─── Configure OpenAI ────────────────────────────────────────────────
configure_openai() {
    local env_file=$1

    echo ""
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║                  OpenAI Configuration                          ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo ""

    read -p "Do you want to use OpenAI models? (y/N): " -n 1 -r
    echo

    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "Skipping OpenAI configuration"
        return 0
    fi

    if [ -n "${OPENAI_API_KEY:-}" ]; then
        log_success "OPENAI_API_KEY already set in environment"
        echo "export USE_OPENAI=true" >> "$env_file"
        export USE_OPENAI=true
    else
        read -p "Enter OpenAI API key: " openai_key
        if [ -n "$openai_key" ]; then
            echo "export OPENAI_API_KEY='$openai_key'" >> "$env_file"
            echo "export USE_OPENAI=true" >> "$env_file"
            export OPENAI_API_KEY="$openai_key"
            export USE_OPENAI=true
            log_success "OpenAI API configured"
        else
            log_warning "No API key provided, skipping OpenAI"
            return 0
        fi
    fi

    # Select OpenAI models
    echo ""
    echo "Select OpenAI models to use (space-separated):"
    echo "  1) GPT-4 Turbo"
    echo "  2) GPT-4"
    echo "  3) GPT-3.5 Turbo"
    echo ""
    read -p "Models to enable [1]: " -a openai_models
    openai_models=${openai_models:-"1"}

    echo "export OPENAI_MODELS='${openai_models[*]}'" >> "$env_file"
    log_success "OpenAI models configured: ${openai_models[*]}"

    return 0
}

# ─── Configure Ollama ────────────────────────────────────────────────
configure_ollama() {
    local env_file=$1

    echo ""
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║              Ollama (Local Models) Configuration               ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo ""

    if ! command -v ollama &> /dev/null; then
        log_info "Ollama not installed"
        read -p "Do you want to install Ollama? (y/N): " -n 1 -r
        echo

        if [[ $REPLY =~ ^[Yy]$ ]]; then
            log_info "Visit https://ollama.ai to install Ollama"
            log_info "After installation, run this setup script again"
        fi
        return 0
    fi

    log_success "Ollama found"

    # Check if Ollama is running
    if ! pgrep ollama &> /dev/null; then
        log_info "Starting Ollama service..."
        ollama serve > /dev/null 2>&1 &
        sleep 3
    fi

    # List available models
    log_info "Checking installed models..."
    local installed_models=$(ollama list 2>/dev/null | tail -n +2 | awk '{print $1}')

    if [ -z "$installed_models" ]; then
        log_warning "No models installed"
        echo ""
        echo "Popular models:"
        echo "  - llama3.1:8b (general purpose, 4.7GB)"
        echo "  - codellama:13b (code generation, 7.4GB)"
        echo "  - mistral:7b (fast, efficient, 4.1GB)"
        echo ""
        read -p "Enter model names to install (space-separated, or press Enter to skip): " -a models_to_install

        if [ ${#models_to_install[@]} -gt 0 ]; then
            for model in "${models_to_install[@]}"; do
                log_info "Pulling $model..."
                ollama pull "$model"
            done
            installed_models=$(ollama list 2>/dev/null | tail -n +2 | awk '{print $1}')
        fi
    else
        log_success "Installed models:"
        echo "$installed_models" | sed 's/^/  - /'
    fi

    if [ -n "$installed_models" ]; then
        echo ""
        read -p "Do you want to use Ollama models? (y/N): " -n 1 -r
        echo

        if [[ $REPLY =~ ^[Yy]$ ]]; then
            echo "export USE_OLLAMA=true" >> "$env_file"
            echo "export OLLAMA_MODELS='$installed_models'" >> "$env_file"
            export USE_OLLAMA=true
            log_success "Ollama configured"
        fi
    fi

    return 0
}
