# Setup Scripts

Automated setup and configuration scripts for the Backlog Toolkit.

## Complete Setup

Run the interactive setup wizard to configure everything from scratch:

```bash
./scripts/setup/complete-setup.sh
```

This interactive script will:
1. ✓ Check all prerequisites (Python, Node.js, Git, Bash)
2. ✓ Install Python dependencies (LiteLLM, ChromaDB, etc.)
3. ✓ Check for Claude Code installation
4. ✓ Configure providers interactively (Anthropic, OpenAI, AWS, Ollama)
5. ✓ Select specific models to use
6. ✓ Generate LiteLLM proxy configuration
7. ✓ Check optional services (Redis, Ollama)
8. ✓ **Install Claude Code plugin automatically** (with confirmation)
9. ✓ **Start services automatically** (with confirmation)
10. ✓ **Verify installation** (comprehensive checks)
11. ✓ **Run connectivity tests** (health checks)

### New Automated Features

The script now offers to:
- **Install plugin**: Automatically installs the Backlog Toolkit plugin
- **Start services**: Starts LiteLLM, RAG, and optional services
- **Verify setup**: Comprehensive verification of all components
- **Test connectivity**: Quick tests to ensure everything works

## Manual Setup

For step-by-step manual configuration, see:
- [Complete Setup Guide](../../docs/tutorials/complete-setup-guide.md)

## What Gets Configured

### Environment Variables
Creates `~/.backlog-toolkit-env` with:
- `ANTHROPIC_API_KEY`
- `OPENAI_API_KEY` (optional)
- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` (optional)
- `LITELLM_MASTER_KEY`

### LiteLLM Configuration
Creates `~/.config/litellm/config.yaml` with:
- Model aliases (cheap/balanced/frontier)
- Provider configurations
- Routing and fallbacks
- Budget limits
- Caching setup

### Directory Structure
Creates:
- `~/.config/litellm/` - LiteLLM configuration
- `~/.backlog-toolkit-env` - Environment variables

## Post-Setup

After running the setup script, most steps are automated! But you can also:

### Option 1: Everything Done Automatically

If you said "yes" to all prompts:
```bash
# Just load environment and start using
source ~/.backlog-toolkit-env
claude
# Type: /backlog-toolkit:init
```

### Option 2: Manual Steps (if you skipped automation)

1. **Load environment**:
   ```bash
   source ~/.backlog-toolkit-env
   ```

2. **Start services**:
   ```bash
   ./scripts/services/start-services.sh
   ```

3. **Install plugin** (if skipped):
   ```bash
   cd /path/to/backlog-agents
   claude plugin install .
   ```

4. **Test**:
   ```bash
   claude
   # Type: /backlog-toolkit:init
   ```

### Verify Setup

Run comprehensive verification:
```bash
./scripts/setup/verify-setup.sh
```

This will:
- Check all configuration files
- Verify Python dependencies
- Test service connectivity
- Validate API credentials
- Check Claude Code plugin
- Give you a setup score (0-100%)

## Troubleshooting

### Prerequisites Missing

If prerequisites check fails:
- **macOS**: `brew install python@3.11 node`
- **Ubuntu**: `sudo apt install python3.11 python3-pip nodejs npm`

### API Key Issues

If API keys are not being read:
```bash
# Verify environment
echo $ANTHROPIC_API_KEY

# Reload environment
source ~/.backlog-toolkit-env
```

### LiteLLM Config Errors

Validate configuration:
```bash
litellm --config ~/.config/litellm/config.yaml --test
```

## Advanced Configuration

See the [Complete Setup Guide](../../docs/tutorials/complete-setup-guide.md) for:
- AWS Bedrock configuration
- Ollama local model setup
- Redis caching setup
- Custom model routing
- Multi-provider fallbacks
