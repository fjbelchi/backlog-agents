# Quick Fix: Plugin Installation Command

## Issue

The plugin installation was failing with:
```
error: unknown option '--path'
```

## Root Cause

The `claude plugin install` command does **not** accept a `--path` option. The correct syntax is:

```bash
# Install from current directory
cd /path/to/plugin
claude plugin install .

# Or install from any directory
claude plugin install /path/to/plugin
```

## Fixed Syntax

### ❌ Old (Incorrect)
```bash
claude plugin install --path /Users/fbelchi/github/backlog-agents
```

### ✅ New (Correct)
```bash
# Option 1: cd to directory first
cd /Users/fbelchi/github/backlog-agents
claude plugin install .

# Option 2: specify path directly
claude plugin install /Users/fbelchi/github/backlog-agents
```

## What Was Updated

All scripts and documentation have been updated:

### Scripts
- `scripts/setup/complete-setup.sh` - Plugin installation logic

### Documentation
- `docs/PLUGIN-INSTALLATION.md` - Complete plugin guide
- `docs/TROUBLESHOOTING.md` - Troubleshooting steps
- `docs/tutorials/complete-setup-guide.md` - Setup tutorial
- `README.md` - Main installation instructions
- All other doc files (47 files total)

## Installation Now

To install the plugin after fixing:

```bash
# Exit any active Claude Code sessions
exit

# Navigate to plugin directory
cd /Users/fbelchi/github/backlog-agents

# Install plugin
claude plugin install .

# Verify installation
claude plugin list | grep backlog-toolkit
```

Should see:
```
backlog-toolkit (v1.0.0)
  Reusable backlog management toolkit for Claude Code
```

## If Still Having Issues

1. **Check Claude Code version:**
   ```bash
   claude --version
   ```
   Need version 2.0+

2. **Validate plugin structure:**
   ```bash
   cat .claude-plugin/plugin.json
   python3 -m json.tool .claude-plugin/plugin.json
   ```

3. **Try with verbose flag:**
   ```bash
   claude plugin install . --verbose
   ```

4. **Check for nested sessions:**
   ```bash
   # Make sure CLAUDECODE is not set
   unset CLAUDECODE
   claude plugin install .
   ```

## Alternative: Install from URL (if published)

If the plugin is published to a registry:
```bash
claude plugin install backlog-toolkit
```

But for local development/installation, use the path method above.
