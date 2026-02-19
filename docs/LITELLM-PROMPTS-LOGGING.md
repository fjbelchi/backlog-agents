# LiteLLM Prompts and Logging

## Overview

This guide explains how to see the prompts being sent through LiteLLM and monitor API calls.

## Viewing Prompts in Real-Time

### Option 1: Watch Log File

```bash
# See all logs in real-time
tail -f ~/.backlog-toolkit/services/logs/litellm.log

# Filter for prompts only
tail -f ~/.backlog-toolkit/services/logs/litellm.log | grep -A 5 "messages"

# Filter for specific model
tail -f ~/.backlog-toolkit/services/logs/litellm.log | grep -A 10 "model.*cheap"
```

### Option 2: Detailed Debug Mode

LiteLLM is already running with `--detailed_debug` flag, which logs:
- Request headers
- Full request body (including prompts)
- Response data
- Token counts
- Latency metrics

### Option 3: Enable Request Logging

Add to `~/.config/litellm/config.yaml`:

```yaml
litellm_settings:
  # Log all requests to file
  request_log: true

  # Success callback (logs successful requests)
  success_callback: ["langfuse", "s3"]  # Optional integrations

  # Failure callback (logs failed requests)
  failure_callback: ["langfuse", "sentry"]  # Optional integrations
```

## Log Format

### Request Log Format

```
POST /v1/chat/completions
Headers: {
  "Authorization": "Bearer sk-litellm-...",
  "Content-Type": "application/json"
}
Body: {
  "model": "cheap",
  "messages": [
    {"role": "user", "content": "Your prompt here"}
  ],
  "max_tokens": 100
}
```

### Response Log Format

```
Response: {
  "id": "chatcmpl-...",
  "model": "cheap",
  "choices": [{
    "message": {
      "role": "assistant",
      "content": "Model response here"
    }
  }],
  "usage": {
    "prompt_tokens": 10,
    "completion_tokens": 15,
    "total_tokens": 25
  }
}
```

## Viewing Specific Information

### See All Prompts

```bash
grep -A 10 '"messages"' ~/.backlog-toolkit/services/logs/litellm.log | less
```

### See Token Usage

```bash
grep '"usage"' ~/.backlog-toolkit/services/logs/litellm.log | jq '.'
```

### See Errors Only

```bash
grep -i error ~/.backlog-toolkit/services/logs/litellm.log | tail -20
```

### See Recent API Calls

```bash
# Last 50 lines
tail -50 ~/.backlog-toolkit/services/logs/litellm.log

# Last 10 minutes
find ~/.backlog-toolkit/services/logs/ -name "litellm.log" -mmin -10 -exec tail -100 {} \;
```

## Prometheus Metrics

LiteLLM exposes metrics at `/metrics` endpoint:

```bash
# View all metrics
curl -s http://localhost:8000/metrics

# Filter for specific metrics
curl -s http://localhost:8000/metrics | grep litellm_request
```

**Available Metrics:**
- `litellm_requests_total` - Total requests
- `litellm_request_duration_seconds` - Request latency
- `litellm_llm_api_failed_requests_total` - Failed requests
- `litellm_tokens_total` - Token usage

## Cost Tracking

### Enable Spend Logging

In `~/.config/litellm/config.yaml`:

```yaml
litellm_settings:
  # Track spending
  max_budget: 1000
  budget_duration: monthly

  # Per-model budgets
model_max_budget:
  cheap: 100
  balanced: 500
  frontier: 400
```

### View Spend

```bash
# Check current spend (requires database)
curl -s http://localhost:8000/spend/tags \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY"
```

## Advanced Logging

### Log to Custom File

```bash
# Redirect LiteLLM logs to custom location
litellm --config ~/.config/litellm/config.yaml \
  --port 8000 \
  --detailed_debug \
  > /custom/path/litellm.log 2>&1 &
```

### Rotate Logs

Create logrotate config at `/etc/logrotate.d/litellm`:

```
/Users/fbelchi/.backlog-toolkit/services/logs/litellm.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 0644 fbelchi staff
}
```

## Testing Prompt Logging

### Send Test Request

```bash
source ~/.backlog-toolkit-env

curl -s http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "cheap",
    "messages": [
      {"role": "system", "content": "You are a helpful assistant."},
      {"role": "user", "content": "What is 2+2?"}
    ],
    "max_tokens": 50
  }' | jq '.'
```

### Check Logs

```bash
# See the request in logs
tail -100 ~/.backlog-toolkit/services/logs/litellm.log | grep -A 20 "What is 2+2"
```

## Filtering Logs

### By Model

```bash
# See all requests to 'cheap' model
grep '"model": "cheap"' ~/.backlog-toolkit/services/logs/litellm.log
```

### By Time Range

```bash
# Today's logs
grep "$(date +%Y-%m-%d)" ~/.backlog-toolkit/services/logs/litellm.log
```

### By User (if using API keys)

```bash
# Filter by API key
grep "sk-litellm-your-key" ~/.backlog-toolkit/services/logs/litellm.log
```

## Privacy Considerations

**⚠️ Warning**: Logs contain full prompts and responses, which may include:
- Sensitive data
- API keys
- User information
- Proprietary code

**Best Practices:**
1. Secure log file permissions: `chmod 600 ~/.backlog-toolkit/services/logs/litellm.log`
2. Rotate logs regularly
3. Don't share logs publicly
4. Consider encrypting archived logs

## Debugging Common Issues

### No Logs Appearing

```bash
# Check if LiteLLM is running
ps aux | grep litellm

# Check log file location
ls -la ~/.backlog-toolkit/services/logs/

# Check file permissions
ls -l ~/.backlog-toolkit/services/logs/litellm.log
```

### Logs Too Verbose

Remove `--detailed_debug` flag from startup command in `scripts/services/start-services.sh`

### Want JSON Logs

Use `litellm --json-logs` flag for JSON-formatted logs (easier to parse)

## Integration with Tools

### Using `jq` for Analysis

```bash
# Extract all prompt contents
grep '"content"' ~/.backlog-toolkit/services/logs/litellm.log | jq '.content'

# Count requests by model
grep '"model"' ~/.backlog-toolkit/services/logs/litellm.log | \
  jq -r '.model' | sort | uniq -c
```

### Using `awk` for Statistics

```bash
# Average tokens per request
awk '/total_tokens/ {sum+=$2; count++} END {print sum/count}' \
  ~/.backlog-toolkit/services/logs/litellm.log
```

## Related Documentation

- [Service Verification](./SERVICE-VERIFICATION.md)
- [Troubleshooting](./TROUBLESHOOTING.md)
- [LiteLLM Configuration](../config/litellm/README.md)
