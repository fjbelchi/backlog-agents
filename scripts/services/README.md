# Service Management Scripts

Scripts for starting, stopping, and monitoring Backlog Toolkit services.

## Quick Start

```bash
# Start all services
./scripts/services/start-services.sh

# Check status
./scripts/services/status.sh

# Stop all services
./scripts/services/stop-services.sh

# Or use the wrapper to start services and Claude Code together
./claude-with-services.sh
```

## Scripts

### `start-services.sh`

Starts all required and optional services:

**Required**:
- LiteLLM proxy (port 8000)

**Optional**:
- RAG server (port 8001)
- Redis (default port)
- Ollama (port 11434)

**Usage**:
```bash
./scripts/services/start-services.sh
```

**What it does**:
1. Loads environment from `~/.backlog-toolkit-env`
2. Checks prerequisites (Python, LiteLLM, API keys)
3. Starts Redis if installed
4. Starts Ollama if installed
5. Starts LiteLLM proxy
6. Starts RAG server if available
7. Verifies all services are healthy
8. Shows service status

**Output**:
- Logs: `~/.backlog-toolkit/services/logs/`
- PIDs: `~/.backlog-toolkit/services/pids/`

### `stop-services.sh`

Gracefully stops all running services.

**Usage**:
```bash
./scripts/services/stop-services.sh
```

**What it does**:
1. Stops LiteLLM proxy
2. Stops RAG server
3. Stops Ollama
4. Stops Redis
5. Cleans up PID files

### `status.sh`

Checks status and health of all services.

**Usage**:
```bash
./scripts/services/status.sh
```

**Output**:
```
╔════════════════════════════════════════════════════════════════╗
║                    Service Status                              ║
╚════════════════════════════════════════════════════════════════╝

Required Services:
  litellm: Running (PID: 12345, Port: 8000) ✓

Optional Services:
  rag: Running (PID: 12346, Port: 8001) ✓
  Redis: Running ✓
  Ollama: Running ✓

✓ All required services are healthy
```

### `restart-services.sh`

Stops and starts all services.

**Usage**:
```bash
./scripts/services/restart-services.sh
```

## Service Endpoints

When services are running:

| Service | Endpoint | Description |
|---------|----------|-------------|
| LiteLLM | http://localhost:8000 | LLM proxy API |
| LiteLLM Health | http://localhost:8000/health | Health check |
| RAG | http://localhost:8001 | RAG search API |
| RAG Health | http://localhost:8001/health | Health check |
| Ollama | http://localhost:11434 | Local model API |

## Logs

Service logs are stored in `~/.backlog-toolkit/services/logs/`:

```bash
# View LiteLLM logs
tail -f ~/.backlog-toolkit/services/logs/litellm.log

# View RAG logs
tail -f ~/.backlog-toolkit/services/logs/rag.log

# View Redis logs
tail -f ~/.backlog-toolkit/services/logs/redis.log

# View Ollama logs
tail -f ~/.backlog-toolkit/services/logs/ollama.log
```

## Environment Variables

Services use environment variables from `~/.backlog-toolkit-env`:

```bash
# Required
ANTHROPIC_API_KEY="sk-ant-api03-..."
LITELLM_MASTER_KEY="sk-litellm-..."

# Optional
OPENAI_API_KEY="sk-..."
AWS_ACCESS_KEY_ID="AKIA..."
AWS_SECRET_ACCESS_KEY="..."
```

## Configuration

### LiteLLM Port

Change LiteLLM port:
```bash
export LITELLM_PORT=9000
./scripts/services/start-services.sh
```

### RAG Port

Change RAG server port:
```bash
export RAG_PORT=9001
./scripts/services/start-services.sh
```

### LiteLLM Config

LiteLLM uses config from:
```bash
~/.config/litellm/config.yaml
```

Override:
```bash
export LITELLM_CONFIG=/path/to/custom/config.yaml
./scripts/services/start-services.sh
```

## Troubleshooting

### Services Won't Start

**Check prerequisites**:
```bash
# Verify installations
litellm --version
python3 --version

# Check API keys
echo $ANTHROPIC_API_KEY
```

**Check logs**:
```bash
tail -f ~/.backlog-toolkit/services/logs/litellm.log
```

### Port Already in Use

**Find process using port**:
```bash
lsof -i :8000
```

**Kill process**:
```bash
kill -9 <PID>
```

**Or change port**:
```bash
export LITELLM_PORT=9000
./scripts/services/start-services.sh
```

### Service Health Check Fails

**LiteLLM not responding**:
```bash
# Check if running
ps aux | grep litellm

# Check config
cat ~/.config/litellm/config.yaml

# Test manually
curl http://localhost:8000/health
```

**RAG not responding**:
```bash
# Check if running
ps aux | grep "rag/server.py"

# Check logs
tail -f ~/.backlog-toolkit/services/logs/rag.log

# Test manually
curl http://localhost:8001/health
```

### Redis Connection Error

**Start Redis manually**:
```bash
# macOS
brew services start redis

# Ubuntu
sudo systemctl start redis-server

# Or run in foreground
redis-server
```

### Ollama Not Starting

**Check installation**:
```bash
ollama --version
```

**Start manually**:
```bash
ollama serve
```

**Pull models**:
```bash
ollama pull llama3.1:8b
```

## Integration with Claude Code

### Method 1: Wrapper Script (Recommended)

Use the wrapper that starts services automatically:

```bash
./claude-with-services.sh
```

This will:
1. Start all services
2. Verify they're healthy
3. Launch Claude Code

### Method 2: Manual

Start services first, then Claude Code:

```bash
# Terminal 1: Start services
./scripts/services/start-services.sh

# Terminal 2: Run Claude Code
claude
```

### Method 3: Background Services

Set up services to start automatically on boot (optional):

**macOS (launchd)**:
```bash
# Create launch agent
cp config/launchd/com.backlog-toolkit.services.plist \
   ~/Library/LaunchAgents/

# Load service
launchctl load ~/Library/LaunchAgents/com.backlog-toolkit.services.plist
```

**Linux (systemd)**:
```bash
# Create systemd service
sudo cp config/systemd/backlog-toolkit.service \
        /etc/systemd/system/

# Enable and start
sudo systemctl enable backlog-toolkit
sudo systemctl start backlog-toolkit
```

## Related Documentation

- [Complete Setup Guide](../../docs/tutorials/complete-setup-guide.md)
- [LiteLLM Configuration](../../docs/reference/litellm-proxy-config.md)
- [Troubleshooting](../../docs/troubleshooting/)
