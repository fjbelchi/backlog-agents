#!/usr/bin/env bash
# ─── Generate LiteLLM Configuration ──────────────────────────────────
# Generates config.yaml based on user selections

generate_litellm_config() {
    local config_file=$1

    log_info "Generating LiteLLM configuration..."

    cat > "$config_file" << 'EOF'
# ─── LiteLLM Proxy Config (Auto-generated) ──────────────────────────

model_list:
EOF

    # Add Anthropic API models
    if [ "${USE_ANTHROPIC_API:-}" = "true" ]; then
        for model_id in ${ANTHROPIC_MODELS:-1 2 3}; do
            case $model_id in
                1)
                    cat >> "$config_file" << 'EOF'
  - model_name: cheap
    litellm_params:
      model: anthropic/claude-haiku-4-5-20251001
      api_key: os.environ/ANTHROPIC_API_KEY

EOF
                    ;;
                2)
                    cat >> "$config_file" << 'EOF'
  - model_name: balanced
    litellm_params:
      model: anthropic/claude-sonnet-4-6-20250610
      api_key: os.environ/ANTHROPIC_API_KEY

EOF
                    ;;
                3)
                    cat >> "$config_file" << 'EOF'
  - model_name: frontier
    litellm_params:
      model: anthropic/claude-opus-4-6-20250515
      api_key: os.environ/ANTHROPIC_API_KEY

EOF
                    ;;
            esac
        done
    fi

    # Add Bedrock models
    if [ "${USE_BEDROCK:-}" = "true" ]; then
        for model_id in ${BEDROCK_MODELS:-1 2}; do
            case $model_id in
                1)
                    cat >> "$config_file" << 'EOF'
  - model_name: bedrock-haiku
    litellm_params:
      model: bedrock/anthropic.claude-haiku-4-5-20251001-v1:0
      aws_access_key_id: os.environ/AWS_ACCESS_KEY_ID
      aws_secret_access_key: os.environ/AWS_SECRET_ACCESS_KEY
      aws_region_name: os.environ/AWS_REGION

EOF
                    ;;
                2)
                    cat >> "$config_file" << 'EOF'
  - model_name: bedrock-sonnet
    litellm_params:
      model: bedrock/anthropic.claude-sonnet-4-6
      aws_access_key_id: os.environ/AWS_ACCESS_KEY_ID
      aws_secret_access_key: os.environ/AWS_SECRET_ACCESS_KEY
      aws_region_name: os.environ/AWS_REGION

EOF
                    ;;
                3)
                    cat >> "$config_file" << 'EOF'
  - model_name: bedrock-opus
    litellm_params:
      model: bedrock/anthropic.claude-opus-4-6-v1
      aws_access_key_id: os.environ/AWS_ACCESS_KEY_ID
      aws_secret_access_key: os.environ/AWS_SECRET_ACCESS_KEY
      aws_region_name: os.environ/AWS_REGION

EOF
                    ;;
            esac
        done
    fi

    # Add OpenAI models
    if [ "${USE_OPENAI:-}" = "true" ]; then
        for model_id in ${OPENAI_MODELS:-1}; do
            case $model_id in
                1)
                    cat >> "$config_file" << 'EOF'
  - model_name: gpt4-turbo
    litellm_params:
      model: openai/gpt-4-turbo-preview
      api_key: os.environ/OPENAI_API_KEY

EOF
                    ;;
                2)
                    cat >> "$config_file" << 'EOF'
  - model_name: gpt4
    litellm_params:
      model: openai/gpt-4
      api_key: os.environ/OPENAI_API_KEY

EOF
                    ;;
                3)
                    cat >> "$config_file" << 'EOF'
  - model_name: gpt35-turbo
    litellm_params:
      model: openai/gpt-3.5-turbo
      api_key: os.environ/OPENAI_API_KEY

EOF
                    ;;
            esac
        done
    fi

    # Add Ollama models
    if [ "${USE_OLLAMA:-}" = "true" ]; then
        for model in ${OLLAMA_MODELS}; do
            local model_name=$(echo "$model" | sed 's/:/-/g' | sed 's/[^a-zA-Z0-9-]//g')
            cat >> "$config_file" << EOF
  - model_name: local-$model_name
    litellm_params:
      model: ollama/$model
      api_base: http://localhost:11434

EOF
        done
    fi

    # Add common settings
    cat >> "$config_file" << 'EOF'
# ─── Router Settings ────────────────────────────────────────────────
router_settings:
  routing_strategy: simple-shuffle
  num_retries: 2
  timeout: 60

# ─── LiteLLM Settings ───────────────────────────────────────────────
litellm_settings:
  budget_duration: monthly
  max_budget: 1000
  request_timeout: 60
  num_retries: 2

  # Response cache
  cache: true
  cache_params:
    type: local
    ttl: 3600

# ─── General Settings ───────────────────────────────────────────────
general_settings:
  master_key: os.environ/LITELLM_MASTER_KEY
EOF

    log_success "LiteLLM config generated at $config_file"
}
