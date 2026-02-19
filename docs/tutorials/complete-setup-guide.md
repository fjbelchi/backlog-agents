# Complete Setup Guide - From Zero to Production

This guide walks you through setting up the Backlog Toolkit from scratch, including Claude Code, LiteLLM proxy with multiple providers (Anthropic, OpenAI, AWS Bedrock, Ollama), and all dependencies.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Claude Code Installation](#claude-code-installation)
3. [LiteLLM Proxy Setup](#litellm-proxy-setup)
4. [Provider Configuration](#provider-configuration)
5. [RAG Setup](#rag-setup)
6. [Plugin Installation](#plugin-installation)
7. [Verification](#verification)
8. [Automated Setup](#automated-setup)

---

## Prerequisites

### Required Software

```bash
# Check versions
python --version    # Python 3.10+
node --version      # Node.js 18+
git --version       # Git 2.30+
bash --version      # Bash 4.0+
```

### Install Missing Dependencies

**macOS**:
```bash
# Install Homebrew if needed
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install dependencies
brew install python@3.11 node git
```

**Ubuntu/Debian**:
```bash
sudo apt update
sudo apt install python3.11 python3-pip nodejs npm git
```

**Windows** (via WSL2):
```bash
# Install WSL2 first, then use Ubuntu commands above
wsl --install
```

### Optional: Redis for Response Caching

```bash
# macOS
brew install redis
brew services start redis

# Ubuntu
sudo apt install redis-server
sudo systemctl start redis-server
```

---

## Claude Code Installation

### 1. Install Claude Code CLI

```bash
# Install via npm (recommended)
npm install -g @anthropic-ai/claude-code

# Or download binary from GitHub releases
# https://github.com/anthropics/claude-code/releases
```

### 2. Verify Installation

```bash
claude --version
# Should output: claude-code version X.X.X
```

### 3. Initial Configuration

```bash
# Run first-time setup
claude init

# This creates ~/.claude/config.json
```

### 4. Set Anthropic API Key

```bash
export ANTHROPIC_API_KEY="sk-ant-api03-..."

# Add to shell profile for persistence
echo 'export ANTHROPIC_API_KEY="sk-ant-api03-..."' >> ~/.bashrc
# or ~/.zshrc on macOS
```

---

## LiteLLM Proxy Setup

LiteLLM provides a unified interface to multiple LLM providers with cost tracking, caching, and fallbacks.

### 1. Install LiteLLM

```bash
pip install 'litellm[proxy]'

# Verify installation
litellm --version
```

### 2. Create Configuration Directory

```bash
mkdir -p ~/.config/litellm
cd ~/.config/litellm
```

### 3. Create Configuration File

Copy the template from this repository:

```bash
cp /path/to/backlog-agents/config/litellm/proxy-config.template.yaml \
   ~/.config/litellm/config.yaml
```

Or create from scratch (see sections below).

---

## Provider Configuration

### Anthropic Claude (Primary)

```yaml
model_list:
  - model_name: cheap
    litellm_params:
      model: anthropic/claude-haiku-4-5
      api_key: os.environ/ANTHROPIC_API_KEY

  - model_name: balanced
    litellm_params:
      model: anthropic/claude-sonnet-4-6
      api_key: os.environ/ANTHROPIC_API_KEY

  - model_name: frontier
    litellm_params:
      model: anthropic/claude-opus-4
      api_key: os.environ/ANTHROPIC_API_KEY
```

**Setup**:
```bash
export ANTHROPIC_API_KEY="sk-ant-api03-..."
```

### OpenAI GPT Models

Add to `model_list`:

```yaml
  - model_name: gpt4-turbo
    litellm_params:
      model: openai/gpt-4-turbo-preview
      api_key: os.environ/OPENAI_API_KEY

  - model_name: gpt4
    litellm_params:
      model: openai/gpt-4
      api_key: os.environ/OPENAI_API_KEY

  - model_name: gpt35-turbo
    litellm_params:
      model: openai/gpt-3.5-turbo
      api_key: os.environ/OPENAI_API_KEY
```

**Setup**:
```bash
export OPENAI_API_KEY="sk-..."
```

### AWS Bedrock

Add to `model_list`:

```yaml
  - model_name: bedrock-claude-sonnet
    litellm_params:
      model: bedrock/anthropic.claude-3-5-sonnet-20240620-v1:0
      aws_access_key_id: os.environ/AWS_ACCESS_KEY_ID
      aws_secret_access_key: os.environ/AWS_SECRET_ACCESS_KEY
      aws_region_name: us-east-1

  - model_name: bedrock-claude-haiku
    litellm_params:
      model: bedrock/anthropic.claude-3-haiku-20240307-v1:0
      aws_access_key_id: os.environ/AWS_ACCESS_KEY_ID
      aws_secret_access_key: os.environ/AWS_SECRET_ACCESS_KEY
      aws_region_name: us-east-1
```

**Setup**:
```bash
export AWS_ACCESS_KEY_ID="AKIA..."
export AWS_SECRET_ACCESS_KEY="..."
export AWS_REGION="us-east-1"

# Or use AWS CLI configuration
aws configure
```

**Prerequisites**:
- AWS account with Bedrock access
- Models enabled in AWS Bedrock console
- IAM user with `bedrock:InvokeModel` permission

### Ollama (Local Models)

First, install and run Ollama:

```bash
# macOS
brew install ollama

# Linux
curl https://ollama.ai/install.sh | sh

# Windows
# Download from https://ollama.ai/download

# Start Ollama service
ollama serve

# Pull models
ollama pull llama3.1:8b
ollama pull codellama:13b
ollama pull mistral:7b
```

Add to `model_list`:

```yaml
  - model_name: local-llama
    litellm_params:
      model: ollama/llama3.1:8b
      api_base: http://localhost:11434

  - model_name: local-code
    litellm_params:
      model: ollama/codellama:13b
      api_base: http://localhost:11434

  - model_name: local-mistral
    litellm_params:
      model: ollama/mistral:7b
      api_base: http://localhost:11434
```

**No API key needed** - Ollama runs locally.

### Complete Configuration Example

Save this to `~/.config/litellm/config.yaml`:

```yaml
model_list:
  # Anthropic (primary)
  - model_name: cheap
    litellm_params:
      model: anthropic/claude-haiku-4-5
      api_key: os.environ/ANTHROPIC_API_KEY

  - model_name: balanced
    litellm_params:
      model: anthropic/claude-sonnet-4-6
      api_key: os.environ/ANTHROPIC_API_KEY

  - model_name: frontier
    litellm_params:
      model: anthropic/claude-opus-4
      api_key: os.environ/ANTHROPIC_API_KEY

  # OpenAI
  - model_name: gpt4-turbo
    litellm_params:
      model: openai/gpt-4-turbo-preview
      api_key: os.environ/OPENAI_API_KEY

  # AWS Bedrock
  - model_name: bedrock-sonnet
    litellm_params:
      model: bedrock/anthropic.claude-3-5-sonnet-20240620-v1:0
      aws_access_key_id: os.environ/AWS_ACCESS_KEY_ID
      aws_secret_access_key: os.environ/AWS_SECRET_ACCESS_KEY
      aws_region_name: us-east-1

  # Ollama (local)
  - model_name: local-llama
    litellm_params:
      model: ollama/llama3.1:8b
      api_base: http://localhost:11434

litellm_settings:
  budget_duration: monthly
  max_budget: 1000
  request_timeout: 60
  num_retries: 2
  cache: true
  cache_params:
    type: redis
    ttl: 3600
    host: localhost
    port: 6379

general_settings:
  master_key: os.environ/LITELLM_MASTER_KEY
```

---

## RAG Setup

The toolkit uses RAG (Retrieval-Augmented Generation) for efficient context retrieval.

### 1. Install Dependencies

```bash
pip install chromadb sentence-transformers
```

### 2. Initialize RAG Database

```bash
# Clone or navigate to backlog-agents
cd /path/to/backlog-agents

# Run RAG initialization (will be created by setup script)
./scripts/rag/init-rag.sh
```

### 3. Index Your Codebase

```bash
# Index a project for RAG
./scripts/rag/index-codebase.sh /path/to/your/project

# Verify index
./scripts/rag/query-rag.sh "authentication logic"
```

---

## Plugin Installation

### 1. Clone Repository

```bash
cd ~/projects  # or your preferred location
git clone https://github.com/[your-org]/backlog-agents.git
cd backlog-agents
```

### 2. Install Plugin in Claude Code

```bash
# Install from local path
claude plugin install .

# Or symlink for development
ln -s $(pwd) ~/.claude/plugins/backlog-toolkit
```

### 3. Verify Plugin

```bash
claude plugin list
# Should show: backlog-toolkit v1.0.0
```

### 4. Test Commands

```bash
# Start Claude Code
claude

# In Claude prompt, test:
/backlog-toolkit:init
```

---

## Verification

Run all verification checks:

```bash
cd /path/to/backlog-agents

# Test config schema
./tests/test-config-schema.sh

# Test templates
./tests/test-templates.sh

# Test installation
./tests/test-install.sh

# All tests should pass ✓
```

---

## Automated Setup

Use the automated setup script to configure everything:

```bash
cd /path/to/backlog-agents
./scripts/setup/complete-setup.sh
```

This script will:
1. Check all prerequisites
2. Install missing dependencies
3. Configure LiteLLM with your providers
4. Set up RAG
5. Install the plugin
6. Run verification tests
7. Generate summary report

See [Automated Setup Script](#automated-setup-script-reference) for details.

---

## Environment Variables Summary

Add these to `~/.bashrc` or `~/.zshrc`:

```bash
# Anthropic
export ANTHROPIC_API_KEY="sk-ant-api03-..."

# OpenAI (optional)
export OPENAI_API_KEY="sk-..."

# AWS Bedrock (optional)
export AWS_ACCESS_KEY_ID="AKIA..."
export AWS_SECRET_ACCESS_KEY="..."
export AWS_REGION="us-east-1"

# LiteLLM
export LITELLM_MASTER_KEY="sk-litellm-$(openssl rand -hex 16)"

# Redis (if using)
export REDIS_HOST="localhost"
export REDIS_PORT="6379"
```

Reload shell:
```bash
source ~/.bashrc  # or ~/.zshrc
```

---

## Next Steps

After setup is complete:

1. **Initialize a project**: `cd your-project && claude` then `/backlog-toolkit:init`
2. **Create a ticket**: `/backlog-toolkit:ticket "your feature description"`
3. **Run refinement**: `/backlog-toolkit:refinement`
4. **Implement tickets**: `/backlog-toolkit:implementer`

## Troubleshooting

See [Troubleshooting Guide](../troubleshooting/) for common issues.

## Advanced Configuration

- [LiteLLM Proxy Configuration](../reference/litellm-proxy-config.md)
- [Cost Optimization](./token-optimization-playbook.md)
- [Custom Agent Routing](../reference/agent-routing.md)
