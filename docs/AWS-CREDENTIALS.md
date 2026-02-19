# AWS Credentials Configuration for Backlog Toolkit

## Overview

The Backlog Toolkit uses **AWS Bedrock** for LLM access through LiteLLM proxy. This requires **static AWS credentials**, not SSO profiles.

## Important: Claude Code vs Backlog Toolkit Credentials

### Different Services, Different Credentials

- **Claude Code CLI** (`claude` command): Uses SSO profile (e.g., `cc`)
  - This is for your personal Claude Code access
  - Managed through AWS SSO
  - **NOT** used by the Backlog Toolkit

- **Backlog Toolkit** (this project): Needs Bedrock credentials
  - Used by LiteLLM proxy to access AWS Bedrock models
  - Requires static AWS credentials (Access Key ID + Secret)
  - **Cannot** use SSO profiles

## Configuration Methods

### Method 1: Using ~/.aws/credentials (Recommended)

1. Create or edit `~/.aws/credentials`:

```ini
[bedrock]
aws_access_key_id = AKIAIOSFODNN7EXAMPLE
aws_secret_access_key = wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
```

2. Create or edit `~/.aws/config`:

```ini
[profile bedrock]
region = us-east-1
output = json
```

3. Tell the toolkit to use this profile:

```bash
export BACKLOG_AWS_PROFILE=bedrock
./scripts/services/start-services.sh
```

### Method 2: Environment Variables

Set credentials directly:

```bash
export AWS_ACCESS_KEY_ID="AKIAIOSFODNN7EXAMPLE"
export AWS_SECRET_ACCESS_KEY="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
export AWS_REGION="us-east-1"

./scripts/services/start-services.sh
```

### Method 3: Toolkit Configuration File

Edit `~/.backlog-toolkit-env`:

```bash
export AWS_ACCESS_KEY_ID='AKIAIOSFODNN7EXAMPLE'
export AWS_SECRET_ACCESS_KEY='wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY'
export AWS_REGION='us-east-1'
```

## Getting Bedrock Credentials

### Option 1: Create IAM User (Recommended for Development)

1. Go to AWS Console → IAM → Users
2. Create new user: `bedrock-toolkit`
3. Attach policy: `AmazonBedrockFullAccess`
4. Create access key → Download credentials
5. Add to `~/.aws/credentials` as shown above

### Option 2: Use Existing IAM Role

If you have an IAM role with Bedrock access:

1. Create temporary credentials:
   ```bash
   aws sts assume-role --role-arn arn:aws:iam::ACCOUNT:role/ROLE_NAME \
     --role-session-name backlog-toolkit
   ```

2. Use the temporary credentials in your environment

### Option 3: Request from Your Team

Ask your AWS administrator for:
- IAM user credentials OR
- STS temporary credentials OR
- Cross-account role access

With the policy: `AmazonBedrockFullAccess`

## Credential Priority

The toolkit checks credentials in this order:

1. **BACKLOG_AWS_PROFILE** environment variable
2. **AWS_PROFILE** environment variable (if profile has static credentials)
3. **default** profile in `~/.aws/credentials`
4. **First available profile** with static credentials
5. **Interactive selection** (if running interactively)

## Testing Your Configuration

```bash
# Test that AWS credentials work
aws bedrock list-foundation-models --region us-east-1

# Test the toolkit services
./scripts/services/start-services.sh

# Check loaded credentials (shows first 15 chars)
env | grep AWS_
```

## Common Issues

### "Profile 'cc' has no static credentials"

**Problem**: The toolkit is trying to use your Claude Code SSO profile.

**Solution**:
```bash
# Use a different profile
export BACKLOG_AWS_PROFILE=bedrock

# Or unset AWS_PROFILE to let it auto-detect
unset AWS_PROFILE

# Then start services
./scripts/services/start-services.sh
```

### "No AWS profiles with static credentials found"

**Problem**: No static credentials in `~/.aws/credentials`.

**Solution**: Create credentials as shown in Method 1 above.

### "Auto-detected AWS profile: luxito"

**Warning**: The toolkit auto-detected a profile. This might not be the right one.

**Solution**: Explicitly set the profile you want:
```bash
export BACKLOG_AWS_PROFILE=bedrock
```

## Security Best Practices

1. **Never commit credentials** to version control
2. **Use separate credentials** for different projects
3. **Rotate credentials** regularly
4. **Limit IAM permissions** to only Bedrock access
5. **Use AWS Secrets Manager** for production deployments

## Alternative: Using Anthropic API

If you don't want to use AWS Bedrock, you can use Anthropic API directly:

1. Get an API key from https://console.anthropic.com/
2. Set in environment:
   ```bash
   export ANTHROPIC_API_KEY='sk-ant-...'
   ```
3. Update LiteLLM config to use Anthropic directly instead of Bedrock

## Help

If you're still having issues:

1. Check logs: `tail -f ~/.backlog-toolkit/services/logs/litellm.log`
2. Verify credentials: `aws sts get-caller-identity`
3. See troubleshooting: `docs/TROUBLESHOOTING.md`
4. Run setup wizard: `./scripts/setup/complete-setup.sh`
