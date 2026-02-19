# Service Startup Guide

## Overview

The service startup scripts now provide **real-time progress feedback** and handle both interactive and non-interactive modes automatically.

## What to Expect

### Interactive Mode (Direct Execution)

When you run the script directly in a terminal:

```bash
./scripts/services/start-services.sh
```

**You will see:**

```
╔════════════════════════════════════════════════════════════════╗
║        Starting Backlog Toolkit Services                      ║
╚════════════════════════════════════════════════════════════════╝

[INFO] Loading environment variables...
[✓] Environment loaded from ~/.backlog-toolkit-env

[INFO] Running pre-flight diagnostics...
[✓] Auto-fixed 2 issue(s)

[INFO] Checking prerequisites...
[✓] LiteLLM found
[✓] Python found
[✓] AWS credentials configured (for Bedrock)
[✓] LiteLLM config found

[INFO] Starting LiteLLM proxy...
[INFO] Using config: ~/.config/litellm/config.yaml
[INFO] Port: 8000
[INFO] Waiting for LiteLLM to start (PID: 12345)...
  .....
  Still starting... (5s elapsed, checking health endpoint)
  .....
  Still starting... (10s elapsed, checking health endpoint)
[✓] LiteLLM started successfully (PID: 12345) in 12s
[INFO] Health check: http://localhost:8000/health

[INFO] Starting RAG server...
[INFO] Port: 8001
[INFO] Waiting for RAG server to start (PID: 12346)...
  ... 3s... 6s
[✓] RAG server started successfully (PID: 12346) in 8s

[✓] Services ready!
```

**Interactive prompts you may see:**

1. **Empty Credentials:**
   ```
   [!] Detected empty credentials in ~/.backlog-toolkit-env
   [INFO] Credentials are defined but not filled in

   Would you like to configure credentials now? (y/N):
   ```

2. **Occupied Ports:**
   ```
   [!] Port 8000 is occupied
   Kill process on port 8000? (y/N):
   ```

### Non-Interactive Mode (From Setup Script)

When called from `complete-setup.sh` or via pipe/redirect:

```bash
./scripts/setup/complete-setup.sh
```

**You will see:**

```
[INFO] Starting services (streaming output below)...

─────────────────────────────────────────────────────────────────
╔════════════════════════════════════════════════════════════════╗
║        Starting Backlog Toolkit Services                      ║
║        (Running in non-interactive mode)                       ║
╚════════════════════════════════════════════════════════════════╝

[INFO] Non-interactive mode: will skip prompts and use defaults
[INFO] Loading environment variables...
[✓] Environment loaded from ~/.backlog-toolkit-env
[INFO] Running in non-interactive mode, skipping credential configuration
[INFO] Edit ~/.backlog-toolkit-env manually and re-run

[INFO] Starting LiteLLM proxy...
  .....
  Still starting... (5s elapsed, checking health endpoint)
  .....
[✓] LiteLLM started successfully (PID: 12345) in 11s

⏳ Still starting... (15s elapsed)
⏳ Still starting... (20s elapsed)
[✓] Services started successfully (took 23s)
─────────────────────────────────────────────────────────────────
```

**Key differences:**
- ❌ No interactive prompts
- ✅ Real-time output streaming
- ✅ Progress indicators every 5 seconds
- ✅ Timeout warnings if taking too long

## Timing Expectations

### Normal Startup Times

| Service | Expected Time | Notes |
|---------|---------------|-------|
| LiteLLM | 5-15s | Depends on config size and model availability |
| RAG Server | 3-8s | Depends on dependencies installed |
| Redis | 1-2s | Optional service |
| Ollama | 2-5s | Optional service |

### Total Startup Time
- **Typical:** 10-25 seconds
- **First time:** 20-40 seconds (loading models)
- **With issues:** 30-60 seconds (diagnostics + fixes)

## Progress Indicators

### Dots (...)
```
[INFO] Waiting for LiteLLM to start (PID: 12345)...
  .....
```
- Each dot = 1 second elapsed
- Shown every 1-3 seconds during wait

### Status Updates
```
  Still starting... (5s elapsed, checking health endpoint)
```
- Shown every 5 seconds
- Confirms process is still alive
- Shows what's being checked

### Elapsed Time
```
  ... 3s... 6s... 9s
```
- Shows cumulative time
- Updated every 3 seconds
- Helps estimate remaining time

### Timeout Warnings
```
⏳ Still starting... (60s elapsed)
[!] Service startup taking longer than expected (60s)
[INFO] Continuing to wait, but you may want to check logs...
```
- Shown after 60 seconds
- Not a failure, just slow
- Suggests checking logs

## What If It Hangs?

### Symptoms
- No output for > 30 seconds
- Stuck on "Starting services..."
- No progress dots appearing

### Immediate Actions

1. **Check if process is running:**
   ```bash
   ps aux | grep litellm
   ps aux | grep python.*rag
   ```

2. **Check logs in real-time:**
   ```bash
   tail -f ~/.backlog-toolkit/services/logs/litellm.log
   tail -f ~/.backlog-toolkit/services/logs/rag.log
   ```

3. **Check ports:**
   ```bash
   lsof -i :8000  # LiteLLM
   lsof -i :8001  # RAG
   ```

4. **Kill and retry:**
   ```bash
   ./scripts/services/stop-services.sh
   ./scripts/services/start-services.sh
   ```

### Common Causes of Hanging

1. **Waiting for interactive input**
   - **Fix:** Run in interactive mode: `./scripts/services/start-services.sh` directly

2. **Config file has errors**
   - **Fix:** Validate config: `python3 -c "import yaml; yaml.safe_load(open('~/.config/litellm/config.yaml'))"`

3. **Port already occupied**
   - **Fix:** Kill process: `kill $(lsof -ti:8000)`

4. **Missing credentials**
   - **Fix:** Edit `~/.backlog-toolkit-env` and add credentials

5. **Python module issues**
   - **Fix:** Reinstall: `pip install --force-reinstall 'litellm[proxy]'`

## Timeout Behavior

### Soft Timeout (60s)
- Shows warning
- Extends timeout by 30s
- Continues waiting
- **Action:** Check logs if concerned

### Hard Timeout (from setup script)
- 60 seconds default
- Script continues monitoring
- Won't kill process
- **Action:** Process keeps running in background

### No Timeout (direct execution)
- Waits indefinitely
- Shows progress every 5s
- Ctrl+C to cancel
- **Action:** Manual intervention needed

## Environment Variables

### BACKLOG_INTERACTIVE_MODE
Control interactive mode explicitly:

```bash
# Force interactive mode
export BACKLOG_INTERACTIVE_MODE=true
./scripts/services/start-services.sh

# Force non-interactive mode
export BACKLOG_INTERACTIVE_MODE=false
./scripts/services/start-services.sh
```

### LITELLM_PORT / RAG_PORT
Change default ports:

```bash
export LITELLM_PORT=9000
export RAG_PORT=9001
./scripts/services/start-services.sh
```

## Success Indicators

### LiteLLM Started Successfully
```
[✓] LiteLLM started successfully (PID: 12345) in 12s
[INFO] Health check: http://localhost:8000/health
```

**What it means:**
- Process is running
- Health endpoint responding
- Ready to accept requests

**Verify:**
```bash
curl http://localhost:8000/health
```

### RAG Server Started Successfully
```
[✓] RAG server started successfully (PID: 12346) in 8s
```

**What it means:**
- Flask server running
- ChromaDB initialized
- Ready for code search

**Verify:**
```bash
curl http://localhost:8001/health
```

### All Services Ready
```
[✓] Services ready!

You can now run: claude
```

**What it means:**
- All required services started
- Optional services status shown
- System ready for use

## Troubleshooting Quick Reference

| Symptom | Probable Cause | Quick Fix |
|---------|----------------|-----------|
| Hangs on "Starting services..." | Interactive prompt waiting | Run directly: `./scripts/services/start-services.sh` |
| "Process died during startup" | Python import error | Reinstall: `pip install 'litellm[proxy]' flask` |
| "Port already in use" | Previous instance running | Kill: `./scripts/services/stop-services.sh` |
| "Credentials not found" | Empty env file | Edit: `nano ~/.backlog-toolkit-env` |
| "Config not found" | Setup incomplete | Run: `./scripts/setup/complete-setup.sh` |
| Timeout after 60s | Slow network/downloads | Wait or check logs |
| Health check fails | Service crashed | Check: `tail ~/.backlog-toolkit/services/logs/litellm.log` |

## Advanced: Manual Service Start

If scripts fail, start services manually:

### LiteLLM
```bash
# Load environment
source ~/.backlog-toolkit-env

# Start LiteLLM
litellm --config ~/.config/litellm/config.yaml --port 8000 \
  > ~/.backlog-toolkit/services/logs/litellm.log 2>&1 &

# Save PID
echo $! > ~/.backlog-toolkit/services/pids/litellm.pid

# Check health
sleep 5
curl http://localhost:8000/health
```

### RAG Server
```bash
# Start RAG
python3 scripts/rag/server.py --port 8001 \
  > ~/.backlog-toolkit/services/logs/rag.log 2>&1 &

# Save PID
echo $! > ~/.backlog-toolkit/services/pids/rag.pid

# Check health
sleep 3
curl http://localhost:8001/health
```

## Getting Help

If issues persist:

1. **Collect diagnostic info:**
   ```bash
   ./scripts/test-robustness.sh > diagnostic-report.txt
   ```

2. **Check full logs:**
   ```bash
   cat ~/.backlog-toolkit/services/logs/litellm.log
   cat setup.log
   ```

3. **Report issue with:**
   - Script output
   - Log files
   - System info (OS, Python version)
   - What you were trying to do
