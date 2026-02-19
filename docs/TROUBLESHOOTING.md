# Troubleshooting Guide

## Common Issues and Solutions

### Issue 1: Script Hangs on "Starting services..."

**Symptoms:**
```
[INFO] Starting services (streaming output below)...
─────────────────────────────────────────────────────────────────
[INFO] Loading environment variables...
[!] Detected empty credentials

Would you like to configure credentials now? (y/N):
⏳ Still starting... (5s elapsed)
⏳ Still starting... (10s elapsed)
...
```

**Cause:**
- Services script is waiting for interactive input
- Running in background but still trying to prompt user
- Empty credentials in `~/.backlog-toolkit-env`

**Solution 1: Fill in credentials before running setup**
```bash
# Edit environment file
nano ~/.backlog-toolkit-env

# Add your credentials (choose one):
# For Anthropic:
export ANTHROPIC_API_KEY='sk-ant-your-key-here'

# For AWS Bedrock:
export AWS_ACCESS_KEY_ID='AKIA...'
export AWS_SECRET_ACCESS_KEY='your-secret-key'
export AWS_REGION='us-east-1'

# Save and exit, then re-run setup
./scripts/setup/complete-setup.sh
```

**Solution 2: Kill hanging process and start fresh**
```bash
# Find and kill the hanging process
ps aux | grep "start-services.sh"
kill <pid>

# Or kill all related processes
pkill -f "start-services.sh"
pkill -f "litellm"

# Start fresh
./scripts/setup/complete-setup.sh
```

**Solution 3: Start services manually after setup**
```bash
# Skip service startup during setup
# When prompted "Start LiteLLM and other services now?"
# Answer: n

# Then configure credentials and start manually
nano ~/.backlog-toolkit-env
source ~/.backlog-toolkit-env
./scripts/services/start-services.sh
```

### Issue 2: Empty Credentials Detected

**Symptoms:**
```
[!] Detected empty credentials in ~/.backlog-toolkit-env
[INFO] Credentials are defined but not filled in
```

**Cause:**
Environment file has placeholder values:
```bash
export AWS_ACCESS_KEY_ID=''
export AWS_SECRET_ACCESS_KEY=''
```

**Solution:**
```bash
# Edit the file
nano ~/.backlog-toolkit-env

# Replace empty strings with real values
export AWS_ACCESS_KEY_ID='AKIA...'          # Real AWS key
export AWS_SECRET_ACCESS_KEY='...'           # Real AWS secret

# Remove empty quotes
# Bad:  export AWS_ACCESS_KEY_ID=''
# Good: export AWS_ACCESS_KEY_ID='AKIAIOSFODNN7EXAMPLE'

# Reload environment
source ~/.backlog-toolkit-env

# Verify credentials are loaded
echo $AWS_ACCESS_KEY_ID  # Should print your key
```

### Issue 3: Service Fails to Start

**Symptoms:**
```
[✗] LiteLLM process died during startup
[INFO] Last 10 lines of log:
  ModuleNotFoundError: No module named 'litellm'
```

**Cause:**
Python dependencies not installed correctly

**Solution:**
```bash
# Reinstall LiteLLM
pip3 install --force-reinstall 'litellm[proxy]'

# Verify installation
python3 -c "import litellm; print(litellm.__version__)"

# If still not found, check PATH
which python3
python3 -m site --user-base  # Check user install location

# Add to PATH if needed
export PATH="$HOME/Library/Python/3.9/bin:$PATH"

# Try again
./scripts/services/start-services.sh
```

### Issue 4: Port Already in Use

**Symptoms:**
```
[!] Port 8000 is occupied
```

**Cause:**
Previous instance of LiteLLM still running

**Solution:**
```bash
# Find what's using the port
lsof -i :8000

# Kill the process
kill $(lsof -ti:8000)

# Or use force kill
kill -9 $(lsof -ti:8000)

# Verify port is free
lsof -i :8000  # Should show nothing

# Try again
./scripts/services/start-services.sh
```

### Issue 5: Plugin Installation Fails

**Symptoms:**
```
[!] Plugin installation failed (may already be installed)
```

**Cause:**
Running inside an active Claude Code session

**Solution:**
```bash
# Exit Claude Code completely
# Then install plugin
cd /Users/fbelchi/github/backlog-agents && claude plugin install .

# Verify installation
claude plugin list | grep backlog-toolkit
```

See [PLUGIN-INSTALLATION.md](./PLUGIN-INSTALLATION.md) for detailed plugin troubleshooting.

### Issue 6: Prerequisites Check Fails

**Symptoms:**
```
[✗] Prerequisites check failed
[✗] No API credentials found
```

**Cause:**
Environment not loaded or credentials not set

**Solution:**
```bash
# Check if environment file exists
ls -la ~/.backlog-toolkit-env

# Load environment
source ~/.backlog-toolkit-env

# Check if credentials are now set
env | grep -E "ANTHROPIC_API_KEY|AWS_ACCESS_KEY_ID"

# If empty, edit and add credentials
nano ~/.backlog-toolkit-env

# Then reload
source ~/.backlog-toolkit-env
```

### Issue 7: LiteLLM Config Not Found

**Symptoms:**
```
[✗] LiteLLM config not found at ~/.config/litellm/config.yaml
```

**Cause:**
Setup didn't complete config generation

**Solution:**
```bash
# Check if config exists
ls -la ~/.config/litellm/config.yaml

# If not, re-run config generation
./scripts/setup/generate-litellm-config.sh ~/.config/litellm/config.yaml

# Or re-run complete setup
./scripts/setup/complete-setup.sh
```

### Issue 8: Service Times Out

**Symptoms:**
```
⏳ Still starting... (60s elapsed)
[!] Service startup taking longer than expected
```

**Causes:**
- Slow network connection
- Downloading models
- Config file errors
- Credentials invalid

**Solution:**
```bash
# Check the logs in real-time
tail -f ~/.backlog-toolkit/services/logs/litellm.log

# Common issues in logs:

# 1. Network timeout
#    → Wait longer or check internet connection

# 2. Invalid credentials
#    → Fix credentials in ~/.backlog-toolkit-env

# 3. Config syntax error
#    → Validate: python3 -m yaml ~/.config/litellm/config.yaml

# 4. Missing Python modules
#    → Reinstall: pip install 'litellm[proxy]'
```

### Issue 9: Non-Interactive Mode Not Working

**Symptoms:**
Script still prompts when called from another script

**Solution:**
```bash
# Force non-interactive mode
export BACKLOG_INTERACTIVE_MODE=false

# Close stdin
./scripts/services/start-services.sh </dev/null

# Or both
BACKLOG_INTERACTIVE_MODE=false ./scripts/services/start-services.sh </dev/null
```

### Issue 10: Python Version Incompatibility

**Symptoms:**
```
[!] Python 3.9.6 found, but 3.10+ recommended
```

**Solution:**
```bash
# Install Python 3.11 (recommended)
# macOS:
brew install python@3.11

# Linux:
sudo apt install python3.11

# Update alternatives
sudo update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1

# Verify
python3 --version  # Should show 3.11+

# Reinstall dependencies
pip3 install 'litellm[proxy]' flask
```

## Diagnostic Commands

### Check System State

```bash
# Check all prerequisites
./scripts/test-robustness.sh

# Check service status
./scripts/services/status.sh

# Check running processes
ps aux | grep -E "litellm|python.*rag"

# Check ports
lsof -i :8000  # LiteLLM
lsof -i :8001  # RAG

# Check environment
env | grep -E "ANTHROPIC|AWS_ACCESS|LITELLM"

# Check logs
ls -la ~/.backlog-toolkit/services/logs/
tail -20 ~/.backlog-toolkit/services/logs/litellm.log
tail -20 ~/.backlog-toolkit/services/logs/rag.log
```

### Collect Diagnostics

```bash
# Create diagnostic report
cat > diagnostic-report.txt <<EOF
=== System Info ===
$(uname -a)
$(python3 --version)
$(node --version)
$(claude --version 2>&1)

=== Environment ===
$(env | grep -E "ANTHROPIC|AWS|LITELLM|PATH")

=== Services ===
$(ps aux | grep -E "litellm|rag")

=== Ports ===
$(lsof -i :8000 2>&1)
$(lsof -i :8001 2>&1)

=== Logs ===
$(tail -50 ~/.backlog-toolkit/services/logs/litellm.log 2>&1)
$(tail -50 ~/.backlog-toolkit/services/logs/rag.log 2>&1)

=== Setup Log ===
$(tail -100 setup.log 2>&1)
EOF

# Review report
cat diagnostic-report.txt
```

## Clean Slate

If all else fails, start fresh:

```bash
# Stop all services
./scripts/services/stop-services.sh

# Kill any remaining processes
pkill -f litellm
pkill -f "python.*rag"

# Remove runtime files
rm -rf ~/.backlog-toolkit/services/pids/*
rm -rf ~/.backlog-toolkit/services/logs/*

# Keep config and credentials
# (Don't delete ~/.config/litellm/ or ~/.backlog-toolkit-env)

# Start fresh
./scripts/setup/complete-setup.sh
```

## Getting Help

If issues persist after trying these solutions:

1. **Collect diagnostic info:**
   ```bash
   ./scripts/test-robustness.sh > diagnostics.txt
   cat setup.log >> diagnostics.txt
   tail -100 ~/.backlog-toolkit/services/logs/*.log >> diagnostics.txt
   ```

2. **Include in your report:**
   - Operating system and version
   - Python version
   - Claude Code version
   - Error messages
   - Relevant log excerpts
   - Steps to reproduce

3. **Where to report:**
   - GitHub Issues: https://github.com/fbelchi/backlog-agents/issues
   - Include diagnostic file
   - Describe what you were trying to do
   - Mention solutions you've already tried

## Prevention

### Best Practices

1. **Always configure credentials before starting services:**
   ```bash
   # Edit first
   nano ~/.backlog-toolkit-env
   # Then start
   ./scripts/setup/complete-setup.sh
   ```

2. **Check prerequisites before setup:**
   ```bash
   python3 --version  # Need 3.10+
   node --version     # Need 18+
   which claude       # Need Claude Code installed
   ```

3. **Load environment in every new shell:**
   ```bash
   # Add to ~/.zshrc or ~/.bashrc
   source ~/.backlog-toolkit-env
   ```

4. **Keep logs for debugging:**
   ```bash
   # Don't delete logs after issues
   ls -la ~/.backlog-toolkit/services/logs/
   ```

5. **Use the wrapper script:**
   ```bash
   # Handles environment and services automatically
   ./claude-with-services.sh
   ```

## Related Documentation

- [Service Startup Guide](./SERVICE-STARTUP-GUIDE.md)
- [Plugin Installation](./PLUGIN-INSTALLATION.md)
- [Robustness Improvements](./ROBUSTNESS-IMPROVEMENTS.md)
