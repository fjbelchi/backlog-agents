# Interactive Setup Guide

The complete setup script now includes an interactive wizard that guides you through provider and model selection.

## Overview

The setup script (`./scripts/setup/complete-setup.sh`) asks you:

1. **Anthropic Configuration**: Choose between Anthropic API or AWS Bedrock
2. **OpenAI Configuration**: Optionally add OpenAI models
3. **Ollama Configuration**: Detect and use local models
4. **Model Selection**: Choose which specific models to enable

## Provider Configuration

### Anthropic: API vs Bedrock

When you run the setup, you'll be asked:

```
╔════════════════════════════════════════════════════════════════╗
║              Anthropic Claude Configuration                    ║
╚════════════════════════════════════════════════════════════════╝

How do you want to access Claude models?
  1) Anthropic API (direct)
  2) AWS Bedrock

Select option [1-2]:
```

#### Option 1: Anthropic API

- Requires: Anthropic API key
- Prompts you to enter API key if not set in environment
- Models available:
  1. Claude Haiku 4.5 (cheap, fast)
  2. Claude Sonnet 4.6 (balanced)
  3. Claude Opus 4 (frontier)

#### Option 2: AWS Bedrock

- Uses existing AWS credentials from:
  - Environment variables (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`)
  - AWS CLI configuration (`~/.aws/credentials`)
  - Or prompts for credentials if neither exists
- Models available:
  1. Claude 3.5 Haiku (cheap, fast, 200K context)
  2. Claude 3.5 Sonnet v2 (balanced, 200K context)
  3. Claude 3.7 Sonnet (latest, 200K context)

### OpenAI (Optional)

```
╔════════════════════════════════════════════════════════════════╗
║                  OpenAI Configuration                          ║
╚════════════════════════════════════════════════════════════════╝

Do you want to use OpenAI models? (y/N):
```

If you choose yes:
- Prompts for OpenAI API key
- Models available:
  1. GPT-4 Turbo
  2. GPT-4
  3. GPT-3.5 Turbo

### Ollama (Optional)

```
╔════════════════════════════════════════════════════════════════╗
║              Ollama (Local Models) Configuration               ║
╚════════════════════════════════════════════════════════════════╝

```

The script will:
1. Check if Ollama is installed
2. List installed models
3. Offer to install popular models if none found
4. Ask if you want to use Ollama in your config

Popular models suggested:
- `llama3.1:8b` - General purpose (4.7GB)
- `codellama:13b` - Code generation (7.4GB)
- `mistral:7b` - Fast and efficient (4.1GB)

## Example Configuration Sessions

### Session 1: Anthropic API Only

```bash
$ ./scripts/setup/complete-setup.sh

How do you want to access Claude models?
  1) Anthropic API (direct)
  2) AWS Bedrock
Select option [1-2]: 1

Enter Anthropic API key: sk-ant-api03-...
✓ Anthropic API configured

Select Claude models to use (space-separated):
  1) Claude Haiku 4.5 (cheap, fast)
  2) Claude Sonnet 4.6 (balanced)
  3) Claude Opus 4 (frontier)
Models to enable [1 2 3]: 1 2

✓ Models configured: 1 2

Do you want to use OpenAI models? (y/N): n
✓ Skipping OpenAI configuration

Ollama not installed
Do you want to install Ollama? (y/N): n
```

**Result**: LiteLLM configured with Haiku and Sonnet via Anthropic API.

### Session 2: Bedrock with Existing AWS Credentials

```bash
$ ./scripts/setup/complete-setup.sh

How do you want to access Claude models?
  1) Anthropic API (direct)
  2) AWS Bedrock
Select option [1-2]: 2

✓ AWS credentials found in environment
Using AWS region: us-east-1

Select Claude models from Bedrock (space-separated):
  1) Claude Haiku 3.0
  2) Claude Sonnet 3.5
  3) Claude Opus 3.5
Models to enable [1 2]: 1 2

✓ Bedrock models configured: 1 2

Do you want to use OpenAI models? (y/N): n
```

**Result**: LiteLLM configured with Bedrock Haiku and Sonnet using existing AWS credentials.

### Session 3: Multi-Provider Setup

```bash
$ ./scripts/setup/complete-setup.sh

# Anthropic
Select option [1-2]: 1
Enter Anthropic API key: sk-ant-api03-...
Models to enable [1 2 3]: 2 3
✓ Models configured: 2 3

# OpenAI
Do you want to use OpenAI models? (y/N): y
Enter OpenAI API key: sk-...
Select OpenAI models (space-separated): 1
✓ OpenAI models configured: 1

# Ollama
✓ Ollama found
Installed models:
  - llama3.1:8b
  - codellama:13b

Do you want to use Ollama models? (y/N): y
✓ Ollama configured
```

**Result**: LiteLLM configured with:
- Anthropic: Sonnet + Opus
- OpenAI: GPT-4 Turbo
- Ollama: llama3.1:8b + codellama:13b

## Generated Configuration

The script generates `~/.config/litellm/config.yaml` with your selections.

### Example: Anthropic API + OpenAI

```yaml
model_list:
  - model_name: balanced
    litellm_params:
      model: anthropic/claude-sonnet-4-6
      api_key: os.environ/ANTHROPIC_API_KEY

  - model_name: frontier
    litellm_params:
      model: anthropic/claude-opus-4
      api_key: os.environ/ANTHROPIC_API_KEY

  - model_name: gpt4-turbo
    litellm_params:
      model: openai/gpt-4-turbo-preview
      api_key: os.environ/OPENAI_API_KEY

router_settings:
  routing_strategy: simple-shuffle
  num_retries: 2
  timeout: 60

litellm_settings:
  budget_duration: monthly
  max_budget: 1000
  cache: true
```

### Example: Bedrock + Ollama

```yaml
model_list:
  - model_name: bedrock-haiku
    litellm_params:
      model: bedrock/anthropic.claude-3-haiku-20240307-v1:0
      aws_access_key_id: os.environ/AWS_ACCESS_KEY_ID
      aws_secret_access_key: os.environ/AWS_SECRET_ACCESS_KEY
      aws_region_name: os.environ/AWS_REGION

  - model_name: bedrock-sonnet
    litellm_params:
      model: bedrock/anthropic.claude-3-5-sonnet-20240620-v1:0
      aws_access_key_id: os.environ/AWS_ACCESS_KEY_ID
      aws_secret_access_key: os.environ/AWS_SECRET_ACCESS_KEY
      aws_region_name: os.environ/AWS_REGION

  - model_name: local-llama31-8b
    litellm_params:
      model: ollama/llama3.1:8b
      api_base: http://localhost:11434
```

## Environment Variables

The script creates `~/.backlog-toolkit-env` with:

```bash
# Anthropic API
export ANTHROPIC_API_KEY='sk-ant-api03-...'
export USE_ANTHROPIC_API=true
export ANTHROPIC_MODELS='1 2'

# OR Bedrock
export USE_BEDROCK=true
export AWS_REGION='us-east-1'
export BEDROCK_MODELS='1 2'

# OpenAI (optional)
export OPENAI_API_KEY='sk-...'
export USE_OPENAI=true
export OPENAI_MODELS='1'

# Ollama (optional)
export USE_OLLAMA=true
export OLLAMA_MODELS='llama3.1:8b codellama:13b'

# LiteLLM
export LITELLM_MASTER_KEY='sk-litellm-...'
```

## Re-running Setup

You can re-run the setup to change your configuration:

```bash
./scripts/setup/complete-setup.sh
```

The script will:
- Detect existing credentials in environment
- Ask to overwrite existing config file
- Keep your previous choices if you skip sections

## Next Steps

After setup:

1. **Load environment**:
   ```bash
   source ~/.backlog-toolkit-env
   ```

2. **Start services**:
   ```bash
   ./scripts/services/start-services.sh
   ```

3. **Test LiteLLM**:
   ```bash
   curl http://localhost:8000/health
   ```

4. **Use with Claude Code**:
   ```bash
   ./claude-with-services.sh
   ```

## Troubleshooting

### AWS Credentials Not Detected

If you have AWS CLI configured but script doesn't detect it:
```bash
# Verify AWS CLI works
aws sts get-caller-identity

# If it works, re-run setup
./scripts/setup/complete-setup.sh
```

### Ollama Models Not Showing

```bash
# Start Ollama first
ollama serve

# List models
ollama list

# Pull a model if needed
ollama pull llama3.1:8b

# Re-run setup
./scripts/setup/complete-setup.sh
```

### Want to Change Configuration

Edit environment file and regenerate:
```bash
# Edit selections
vim ~/.backlog-toolkit-env

# Regenerate LiteLLM config
./scripts/setup/complete-setup.sh
# Choose 'y' when asked to overwrite
```

## Related Documentation

- [Complete Setup Guide](./complete-setup-guide.md)
- [Service Management](../../scripts/services/README.md)
- [LiteLLM Configuration](../reference/litellm-proxy-config.md)
