# Plugin Installation Guide

## Why Plugin Installation Might Fail

The most common reason for plugin installation failure is:

> **"Claude Code cannot be launched inside another Claude Code session"**

This happens when you run the setup script from within an active Claude Code session. Claude Code has a safety mechanism to prevent nested sessions, which share runtime resources and can crash all active sessions.

## Solution

### Option 1: Exit and Install (Recommended)

1. **Exit Claude Code** (if you're currently in a session)
2. **Run the installation command:**
   ```bash
   cd /Users/fbelchi/github/backlog-agents && claude plugin install .
   ```
3. **Verify installation:**
   ```bash
   claude plugin list
   ```
   You should see `backlog-toolkit` in the list.

### Option 2: Install from Setup Script

If you run the setup script outside of Claude Code:

```bash
# Make sure you're NOT in a Claude session
./scripts/setup/complete-setup.sh
```

The setup script will:
- Detect if plugin is already installed
- Offer to reinstall if desired
- Install automatically if not present

### Option 3: Manual Installation Steps

If automatic installation fails:

1. **Check plugin manifest exists:**
   ```bash
   cat /Users/fbelchi/github/backlog-agents/.claude-plugin/plugin.json
   ```

2. **Validate JSON syntax:**
   ```bash
   python3 -m json.tool /Users/fbelchi/github/backlog-agents/.claude-plugin/plugin.json
   ```

3. **Check Claude Code version:**
   ```bash
   claude --version
   ```
   Need version 2.0 or higher.

4. **Try installation with verbose output:**
   ```bash
   cd /Users/fbelchi/github/backlog-agents && claude plugin install . --verbose
   ```

## Verification

After installation, verify the plugin works:

1. **List installed plugins:**
   ```bash
   claude plugin list
   ```
   Should show:
   ```
   backlog-toolkit (v1.0.0)
     Reusable backlog management toolkit for Claude Code
   ```

2. **Launch Claude Code:**
   ```bash
   source ~/.backlog-toolkit-env
   ./scripts/services/start-services.sh
   claude
   ```

3. **Test a command:**
   ```
   /backlog-toolkit:init
   ```

## Common Issues

### Issue 1: "Plugin already installed"

**Symptom:**
```
Error: Plugin 'backlog-toolkit' is already installed
```

**Solution:**
```bash
# Uninstall first
claude plugin uninstall backlog-toolkit

# Then reinstall
cd /Users/fbelchi/github/backlog-agents && claude plugin install .
```

### Issue 2: "Cannot find plugin.json"

**Symptom:**
```
Error: Cannot find plugin manifest at path
```

**Solution:**
Ensure you're pointing to the repository root, not a subdirectory:
```bash
# Correct
cd /Users/fbelchi/github/backlog-agents && claude plugin install .

# Wrong
cd /Users/fbelchi/github/backlog-agents && claude plugin install ./.claude-plugin
```

### Issue 3: "Invalid plugin manifest"

**Symptom:**
```
Error: Invalid plugin manifest: ...
```

**Solution:**
1. Check JSON syntax:
   ```bash
   python3 -m json.tool .claude-plugin/plugin.json
   ```

2. Common issues:
   - Trailing commas in JSON
   - Missing required fields (name, version)
   - Invalid command paths

3. Compare with template:
   ```bash
   cat .claude-plugin/plugin.json
   ```

### Issue 4: "Plugin installed but commands not working"

**Symptom:**
- Plugin shows in `claude plugin list`
- But `/backlog-toolkit:*` commands not found

**Solution:**
1. Restart Claude Code
2. Check command files exist:
   ```bash
   ls -la commands/*.md
   ```
3. Reinstall plugin:
   ```bash
   claude plugin uninstall backlog-toolkit
   cd /Users/fbelchi/github/backlog-agents && claude plugin install .
   ```

## Plugin Structure

The plugin expects this structure:

```
backlog-agents/
├── .claude-plugin/
│   ├── plugin.json          # Plugin manifest (required)
│   └── CLAUDE.md            # Plugin documentation
├── commands/                # Slash commands
│   ├── init.md
│   ├── ticket.md
│   ├── refinement.md
│   └── implementer.md
├── skills/                  # Full skill implementations
│   ├── backlog-init/
│   ├── backlog-ticket/
│   ├── backlog-refinement/
│   └── backlog-implementer/
└── ...
```

## Plugin Manifest Reference

```json
{
  "name": "backlog-toolkit",          // Plugin ID (must be unique)
  "description": "...",               // Short description
  "version": "1.0.0",                 // Semantic version
  "author": {
    "name": "fbelchi",
    "url": "https://github.com/fbelchi"
  },
  "repository": "...",                // Git repository URL
  "license": "MIT",
  "keywords": [...],                  // Search tags
  "commands": [                       // Command files
    "./commands/init.md",
    "./commands/ticket.md",
    // ...
  ],
  "skills": "./skills/"               // Skills directory
}
```

## Installation Scopes

### User Scope (Default)
Plugin available across all projects:
```bash
claude plugin install /path/to/plugin --scope user
```

Installed to: `~/.claude/plugins/`

### Project Scope
Plugin only for current project:
```bash
claude plugin install /path/to/plugin --scope project
```

Installed to: `.claude/plugins/` (committed to repo)

## Updating the Plugin

When you update the plugin code:

1. **No reinstall needed** if only changing:
   - Command files (`.md` files)
   - Skill implementations
   - Documentation

2. **Reinstall required** if changing:
   - `plugin.json` (manifest)
   - Command structure
   - Adding/removing commands

To update:
```bash
claude plugin uninstall backlog-toolkit
cd /Users/fbelchi/github/backlog-agents && claude plugin install .
```

## Development Mode

For active development, use development mode:

```bash
# Launch Claude with plugin directory
claude --plugin-dir /Users/fbelchi/github/backlog-agents

# Changes take effect immediately (no reinstall needed)
```

## Troubleshooting Commands

```bash
# Check if Claude Code is running
ps aux | grep claude

# Check plugin installation location
ls -la ~/.claude/plugins/

# Check plugin manifest directly
cat ~/.claude/plugins/backlog-toolkit/plugin.json

# View Claude Code logs
tail -f ~/.claude/logs/claude.log

# Force reinstall
claude plugin uninstall backlog-toolkit --force
cd /Users/fbelchi/github/backlog-agents && claude plugin install . --force
```

## Getting Help

If plugin installation continues to fail:

1. **Collect diagnostics:**
   ```bash
   claude plugin list > plugin-status.txt
   claude --version >> plugin-status.txt
   cat .claude-plugin/plugin.json >> plugin-status.txt
   ```

2. **Check setup logs:**
   ```bash
   cat setup.log | grep -i plugin
   ```

3. **Report issue with:**
   - Error message
   - Claude Code version
   - Operating system
   - Contents of `plugin.json`
   - Steps to reproduce

## Next Steps

Once plugin is installed:

1. **Load environment:**
   ```bash
   source ~/.backlog-toolkit-env
   ```

2. **Start services:**
   ```bash
   ./scripts/services/start-services.sh
   ```

3. **Launch Claude Code:**
   ```bash
   claude
   ```

4. **Initialize backlog:**
   ```
   /backlog-toolkit:init
   ```

See [README.md](../README.md) for full usage guide.
