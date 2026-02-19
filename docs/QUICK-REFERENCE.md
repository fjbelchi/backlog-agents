# Quick Reference - Backlog Toolkit

## Daily Usage

### Start Services
```bash
BACKLOG_AWS_PROFILE=cc ./scripts/services/start-services.sh
```

### Stop Services
```bash
./scripts/services/stop-services.sh
```

### Verify Everything Works
```bash
# Comprehensive verification (includes completion test)
./scripts/services/verify-litellm.sh

# Quick health check
curl -s http://localhost:8001/health | jq '.status'

# With LiteLLM auth
source ~/.backlog-toolkit-env
curl -s http://localhost:8000/health \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" | jq '.healthy_count'
```

### View Prompts/Logs
```bash
# Real-time logs
tail -f ~/.backlog-toolkit/services/logs/litellm.log

# See prompts being sent
grep -A 10 '"messages"' ~/.backlog-toolkit/services/logs/litellm.log

# See errors
grep -i error ~/.backlog-toolkit/services/logs/litellm.log | tail -20
```

## Service Endpoints

| Service | URL | Auth | Purpose |
|---------|-----|------|---------|
| LiteLLM | http://localhost:8000 | Yes | Model proxy |
| RAG | http://localhost:8001 | No | Code search |
| Ollama | http://localhost:11434 | No | Local models |

## LiteLLM Models

- `cheap` - Claude 3.5 Haiku (fast, cheap)
- `balanced` - Claude 3.5 Sonnet (balanced)
- `frontier` - Claude 3 Opus (powerful)

## Common Commands

### Renew SSO
```bash
aws sso login --profile cc
./scripts/services/restart-services.sh
```

### View Logs
```bash
tail -f ~/.backlog-toolkit/services/logs/litellm.log
tail -f ~/.backlog-toolkit/services/logs/rag.log
```

### Check Credentials
```bash
source ~/.backlog-toolkit-env
echo "Master Key: ${LITELLM_MASTER_KEY:0:15}..."
echo "AWS Region: $AWS_REGION"
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| 401 Auth Error | `source ~/.backlog-toolkit-env` and include master key |
| SSO Expired | `aws sso login --profile cc` |
| Port In Use | `./scripts/services/stop-services.sh` then restart |
| Service Down | `./scripts/services/restart-services.sh` |

## Files

- Config: `~/.config/litellm/config.yaml`
- Env: `~/.backlog-toolkit-env`
- Logs: `~/.backlog-toolkit/services/logs/`
- PIDs: `~/.backlog-toolkit/services/pids/`

## Documentation

- Setup: `docs/AWS-SSO-SETUP.md`
- Verify: `docs/SERVICE-VERIFICATION.md`
- Summary: `docs/SESSION-SUMMARY.md`
