# AWS Bedrock Permissions Issue

## Problem Identified

The SSO role `ClaudeAccess` does NOT have permissions to use AWS Bedrock models.

**Error observed:**
```
litellm.AuthenticationError: BedrockException Invalid Authentication
{"message":"The security token included in the request is invalid."}
```

## Root Cause

Your AWS SSO role is configured for **Claude Code CLI** access, but does NOT include permissions for:
- `bedrock:InvokeModel`
- `bedrock:InvokeModelWithResponseStream`

## Two Solutions

### Option 1: Request Bedrock Permissions (Recommended for Enterprise)

Ask your AWS administrator to add these permissions to the `ClaudeAccess` role:

**Required IAM Policy:**
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream"
      ],
      "Resource": [
        "arn:aws:bedrock:*::foundation-model/anthropic.claude-3-haiku-*",
        "arn:aws:bedrock:*::foundation-model/anthropic.claude-3-5-sonnet-*",
        "arn:aws:bedrock:*::foundation-model/anthropic.claude-3-opus-*"
      ]
    }
  ]
}
```

### Option 2: Use Anthropic API Directly (Quick Fix)

Use Anthropic API directly instead of Bedrock.

#### Step 1: Get Anthropic API Key

1. Go to https://console.anthropic.com/
2. Create an API key
3. Copy the key (starts with `sk-ant-`)

#### Step 2: Configure Anthropic API

```bash
# Add to environment file
echo "export ANTHROPIC_API_KEY='sk-ant-your-key-here'" >> ~/.backlog-toolkit-env
```

#### Step 3: Update LiteLLM Config

Edit `~/.config/litellm/config.yaml`:

```yaml
# Comment out Bedrock models
# model_list:
#   - model_name: cheap
#     litellm_params:
#       model: bedrock/anthropic.claude-3-haiku-20240307-v1:0
#       aws_region_name: us-east-1

# Use Anthropic API instead
model_list:
  - model_name: cheap
    litellm_params:
      model: claude-3-haiku-20240307
      api_key: os.environ/ANTHROPIC_API_KEY

  - model_name: balanced
    litellm_params:
      model: claude-3-5-sonnet-20241022
      api_key: os.environ/ANTHROPIC_API_KEY

  - model_name: frontier
    litellm_params:
      model: claude-3-opus-20240229
      api_key: os.environ/ANTHROPIC_API_KEY
```

#### Step 4: Restart Services

```bash
./scripts/services/restart-services.sh
```

#### Step 5: Test

```bash
source ~/.backlog-toolkit-env

curl -s http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "cheap",
    "messages": [{"role": "user", "content": "Say: WORKS"}],
    "max_tokens": 10
  }' | jq -r '.choices[0].message.content'
```

Expected output: `WORKS`

## Comparison

| Aspect | Bedrock | Anthropic API |
|--------|---------|---------------|
| **Cost** | Usually cheaper | Standard pricing |
| **Latency** | Lower (regional) | Slightly higher |
| **Setup** | Needs IAM permissions | Just API key |
| **Enterprise** | Better for orgs | Individual use |
| **Compliance** | AWS controls | Anthropic direct |

## Recommendation

**For Individual Use**: Use Anthropic API (Option 2)
- Faster to setup
- No permission requests needed
- Works immediately

**For Team/Enterprise**: Request Bedrock permissions (Option 1)
- Better cost control
- Centralized billing
- Compliance requirements

## Current Status

✅ **SSO Working**: Your Claude Code SSO credentials work fine
❌ **Bedrock Blocked**: Role lacks `bedrock:InvokeModel` permission
✅ **Workaround Available**: Use Anthropic API directly

## Next Steps

1. Choose option above (Anthropic API recommended for quick start)
2. Update config
3. Restart services
4. Test completions
5. Continue with toolkit usage

## Related Documentation

- [Service Verification](./SERVICE-VERIFICATION.md)
- [AWS SSO Setup](./AWS-SSO-SETUP.md)
- [Troubleshooting](./TROUBLESHOOTING.md)
