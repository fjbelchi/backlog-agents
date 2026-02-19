# AWS Bedrock API Keys - Quick Setup Guide

## Overview

**Best solution for development**: Use AWS Bedrock API Keys instead of requesting IAM permissions.

## Why This Is Better

| Aspect | API Keys | IAM Permissions |
|--------|----------|-----------------|
| **Setup Time** | 2 minutes | Days (approval process) |
| **Permissions Needed** | Console access only | IAM policy changes |
| **Complexity** | Very simple | Complex |
| **Best For** | Development, testing | Production |
| **Duration** | 30 days (renewable) | Permanent |

## Prerequisites

You need **console access** to AWS Bedrock. Check if you have it:

```bash
# Try opening the console
open https://console.aws.amazon.com/bedrock

# Or test with AWS CLI
aws bedrock list-foundation-models --region us-east-1 --profile cc
```

If you can access the console, you can generate API keys!

## Step-by-Step Setup

### Step 1: Generate API Key

1. **Sign in** to AWS Console with your SSO profile
2. **Go to**: https://console.aws.amazon.com/bedrock
3. **Click**: "API keys" in left navigation
4. **Click**: "Generate long-term API keys" tab
5. **Select**: "30 days" expiration
6. **Click**: "Generate API key"
7. **Copy**: The key immediately (⚠️ only shown once!)

### Step 2: Configure Environment

```bash
# Add to environment file
echo "export AWS_BEARER_TOKEN_BEDROCK='your-api-key-here'" >> ~/.backlog-toolkit-env

# Remove or comment out AWS access keys if present
# (API key replaces them for Bedrock access)
```

### Step 3: Update LiteLLM Config

No changes needed! Your existing Bedrock config in `~/.config/litellm/config.yaml` will work:

```yaml
model_list:
  - model_name: cheap
    litellm_params:
      model: bedrock/anthropic.claude-3-haiku-20240307-v1:0
      aws_region_name: us-east-1
      # API key is used automatically from AWS_BEARER_TOKEN_BEDROCK
```

### Step 4: Restart Services

```bash
# Reload environment
source ~/.backlog-toolkit-env

# Restart LiteLLM
./scripts/services/restart-services.sh

# Or restart manually
pkill -f "litellm --config"
sleep 2
BACKLOG_AWS_PROFILE=cc ./scripts/services/start-services.sh
```

### Step 5: Test

```bash
# Run verification
./scripts/services/verify-litellm.sh

# Or test manually
source ~/.backlog-toolkit-env
curl -s http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "cheap",
    "messages": [{"role": "user", "content": "Say: SUCCESS"}],
    "max_tokens": 10
  }' | jq -r '.choices[0].message.content'
```

Expected output: `SUCCESS`

## Using with LiteLLM

LiteLLM automatically detects `AWS_BEARER_TOKEN_BEDROCK` and uses it for Bedrock authentication. No code changes needed!

**How it works**:
1. LiteLLM checks for `AWS_BEARER_TOKEN_BEDROCK` env var
2. Uses Bearer token authentication instead of AWS SigV4
3. Sends requests to Bedrock with: `Authorization: Bearer <token>`

## Key Expiration & Renewal

**Duration**: 30 days

**When to renew**:
- You'll get authentication errors when expired
- Set a calendar reminder for 25 days

**How to renew**:
1. Generate new key (same steps as above)
2. Update `~/.backlog-toolkit-env`
3. Restart services

**Tip**: Generate the new key a few days before expiration for seamless transition.

## Security Best Practices

### ✅ Do
- Store key in `~/.backlog-toolkit-env` (not in code)
- Set file permissions: `chmod 600 ~/.backlog-toolkit-env`
- Generate new keys regularly (don't wait for expiration)
- Use different keys for different projects/environments
- Revoke old keys after generating new ones

### ❌ Don't
- Commit keys to git
- Share keys via email/Slack
- Use the same key across multiple machines
- Leave expired keys in config files

## Troubleshooting

### "Authentication failed" after setup

```bash
# Check if key is set
echo $AWS_BEARER_TOKEN_BEDROCK | head -c 20

# Check if services are using it
grep -i bearer ~/.backlog-toolkit/services/logs/litellm.log
```

### Key doesn't work

1. **Verify region**: API key is region-specific, use `us-east-1`
2. **Check expiration**: Keys expire after 30 days
3. **Regenerate**: Create a new key if unsure

### Console access denied

If you can't access the Bedrock console:

**Option A**: Request console access (easier than IAM policy)
- Ask for: Bedrock console read access
- Purpose: Generate API keys

**Option B**: Use Anthropic API instead
- Get key from: https://console.anthropic.com/
- See: `BEDROCK-PERMISSIONS.md` Option 2

## Comparison with Other Methods

### API Keys vs IAM Permissions

**API Keys** (This method):
```
✅ 2-minute setup
✅ No permission requests
✅ Console access only
⚠️ 30-day expiration
⚠️ Development/testing focus
```

**IAM Permissions**:
```
❌ Days/weeks approval
❌ Requires admin action
✅ Permanent
✅ Production-ready
```

### API Keys vs Anthropic API

**Bedrock API Keys**:
```
✅ AWS Bedrock pricing (cheaper)
✅ Regional deployment
✅ AWS compliance
⚠️ 30-day renewal
```

**Anthropic API**:
```
✅ No renewal needed
✅ Simpler auth
✅ Direct from Anthropic
⚠️ Higher costs
```

## Environment File Example

Your `~/.backlog-toolkit-env` should look like:

```bash
# LiteLLM Master Key
export LITELLM_MASTER_KEY='sk-litellm-42de3d0a5c8ba7a644f76fac357778b8'

# AWS Bedrock API Key (30-day)
export AWS_BEARER_TOKEN_BEDROCK='abcd1234...your-key-here'

# Optional: Still set for other AWS services
export BACKLOG_AWS_PROFILE='cc'
```

## Using with Python/SDK

If you're building scripts that use Bedrock:

```python
import boto3
import os

# Set the API key
os.environ['AWS_BEARER_TOKEN_BEDROCK'] = 'your-api-key'

# Use bedrock-runtime client
client = boto3.client(
    service_name='bedrock-runtime',
    region_name='us-east-1'
)

response = client.converse(
    modelId='us.anthropic.claude-3-5-haiku-20241022-v1:0',
    messages=[
        {'role': 'user', 'content': [{'text': 'Hello!'}]}
    ]
)

print(response['output']['message']['content'][0]['text'])
```

## Production Considerations

⚠️ **API keys are for development/testing only**

For production, transition to:
1. **IAM roles** (EC2, ECS, Lambda)
2. **Short-term Bedrock API keys** (< 30 days)
3. **STS temporary credentials**
4. **LLM Gateway** with centralized auth

## Next Steps

Once you have the API key working:

1. ✅ Test completions: `./scripts/services/verify-litellm.sh`
2. ✅ View prompts: `tail -f ~/.backlog-toolkit/services/logs/litellm.log`
3. ✅ Start using toolkit: `/backlog-init`
4. 📅 Set reminder to renew key in 25 days

## Related Documentation

- [Bedrock Permissions](BEDROCK-PERMISSIONS.md) - All authentication options
- [Service Verification](SERVICE-VERIFICATION.md) - How to test
- [Quick Reference](QUICK-REFERENCE.md) - Daily commands
- [LiteLLM Logging](LITELLM-PROMPTS-LOGGING.md) - Monitor API calls

## Official AWS Documentation

- [AWS Bedrock API Keys Guide](https://docs.aws.amazon.com/bedrock/latest/userguide/getting-started-api-keys.html)
- [AWS Bedrock Console](https://console.aws.amazon.com/bedrock)
- [Bedrock Model IDs](https://docs.aws.amazon.com/bedrock/latest/userguide/model-ids.html)
