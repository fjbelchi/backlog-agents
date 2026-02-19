# Iteration 7: Plugin Installation Method Fix

## Problem Found

During testing, plugin installation failed with:
```
[✗] Plugin installation failed (exit code: 1)
[INFO] Error details:
  Installing plugin "."...
  ✘ Failed to install plugin ".": Plugin "." not found in any configured marketplace
```

## Root Cause Analysis

### Investigation
```bash
# Checked claude plugin command syntax
claude plugin --help

Commands:
  install|i [options] <plugin>  Install a plugin from available marketplaces
```

**Discovery:** The `claude plugin install` command only installs plugins from **marketplaces**, not from local directories.

### The Real Installation Method

Found the correct installation script:
```bash
ls -la install.sh
-rwxr-xr-x  1 user  staff  5294 install.sh
```

Reading `install.sh`:
```bash
# Copies skill directories from this repo into Claude skills folder
./install.sh                    # all skills → ~/.claude/skills/
./install.sh --local            # all skills → .claude/skills/
./install.sh --skills init,ticket   # specific skills only
./install.sh --force            # overwrite without prompting
```

**Key Insight:** This toolkit uses the **Skills API**, not the Plugin marketplace. Skills are installed by copying directories to `~/.claude/skills/`.

## Solution Implemented

### Changed Installation Approach

**Before (Incorrect):**
```bash
# Tried to use plugin marketplace command
cd "$REPO_ROOT" && claude plugin install .
```

**After (Correct):**
```bash
# Use the provided install script
"$REPO_ROOT/install.sh" --force
```

### Code Changes

#### 1. Renamed Function & Updated Logic
```bash
# Before:
# ─── Step 7: Install Claude Code Plugin ────────────────────────────
install_plugin() {
    log_info "Installing Claude Code plugin..."
    ...
    if (cd "$REPO_ROOT" && claude plugin install .) > "$temp_output" 2>&1; then

# After:
# ─── Step 7: Install Claude Code Skills ────────────────────────────
install_plugin() {
    log_info "Installing Backlog Toolkit skills..."
    ...
    if "$REPO_ROOT/install.sh" --force > "$temp_output" 2>&1; then
```

#### 2. Updated Detection Logic
```bash
# Before:
local plugin_check_output=$(claude plugin list 2>&1)
if echo "$plugin_check_output" | grep -q "backlog-toolkit"; then

# After:
local skills_count=0
for skill in backlog-init backlog-ticket backlog-refinement backlog-implementer; do
    if [ -d "$HOME/.claude/skills/$skill" ]; then
        ((skills_count++))
    fi
done
```

#### 3. Better Installation Feedback
```bash
if [ "$skills_installed" = true ]; then
    log_success "Backlog skills appear to be already installed"
    read -p "Reinstall skills? (y/N): "
fi

# After installation:
log_info "Installed skills:"
ls -1 "$HOME/.claude/skills/" | grep "^backlog-" | sed 's/^/  - /'
```

#### 4. Updated Error Messages
```bash
# Before:
log_info "  1. Exit any active Claude Code sessions"
log_info "  2. Try manual install: cd $REPO_ROOT && claude plugin install ."
log_info "  3. Check plugin manifest..."

# After:
log_info "  1. Try manual install: $REPO_ROOT/install.sh"
log_info "  2. Check skills directory exists: ls -la $REPO_ROOT/skills/"
log_info "  3. Check permissions: ls -la ~/.claude/"
```

### Files Modified

1. **scripts/setup/complete-setup.sh**
   - Changed function name from plugin → skills focus
   - Updated installation method
   - New detection logic
   - Better error messages

2. **Verification logic**
   - Checks `~/.claude/skills/backlog-*` directories
   - Reports skills count (e.g., "4/4 installed")
   - Handles partial installations

3. **Summary output**
   - Changed "Plugin" → "Skills"
   - Shows skill count
   - Correct installation command

## Testing

### Test 1: Fresh Install
```bash
$ ./install.sh --force
Installing backlog-init → ~/.claude/skills/backlog-init
Installing backlog-ticket → ~/.claude/skills/backlog-ticket
Installing backlog-refinement → ~/.claude/skills/backlog-refinement
Installing backlog-implementer → ~/.claude/skills/backlog-implementer

Done! Installed 4 skills to ~/.claude/skills/
```

### Test 2: Verification
```bash
$ ls -1 ~/.claude/skills/ | grep "^backlog-"
backlog-implementer
backlog-init
backlog-refinement
backlog-ticket
```

### Test 3: Setup Script Integration
```bash
$ ./scripts/setup/complete-setup.sh
...
[INFO] Installing Backlog Toolkit skills...
[INFO] Installing skills to ~/.claude/skills/

[✓] Skills installed successfully

[INFO] Installed skills:
  - backlog-implementer
  - backlog-init
  - backlog-refinement
  - backlog-ticket
```

## Understanding Skills vs Plugins

### Skills API
- **Location:** `~/.claude/skills/` or `.claude/skills/`
- **Installation:** Copy directories directly
- **Format:** Markdown files with YAML frontmatter
- **Invocation:** Commands defined in skill files
- **This toolkit uses:** Skills ✓

### Plugin Marketplace
- **Location:** Plugin registry/marketplace
- **Installation:** `claude plugin install <name>`
- **Format:** npm-like packages
- **Invocation:** Via plugin manifest
- **This toolkit uses:** No ✗

## Results

✅ **Installation now works correctly**
- Skills copied to `~/.claude/skills/`
- All 4 skills detected and verified
- Clear feedback during installation
- Proper error handling

✅ **No more marketplace errors**
- Not trying to use `claude plugin install`
- Using correct installation method
- Following Claude Code patterns

✅ **Better user experience**
- Shows skill count (4/4)
- Lists installed skills
- Handles partial installations
- Clear instructions for manual install

## Documentation Updates Needed

Since this changes the installation method, need to update:
- ✅ Complete-setup.sh (done)
- ⏳ README.md installation instructions
- ⏳ PLUGIN-INSTALLATION.md (rename to SKILLS-INSTALLATION.md)
- ⏳ All references to "plugin install" commands

## Lessons Learned

1. **Always check the actual tooling**
   - Don't assume standard methods apply
   - Read the actual installation scripts
   - Test commands before implementing

2. **Skills vs Plugins are different**
   - Skills: Directory-based, copy to ~/.claude/skills/
   - Plugins: Marketplace-based, install via command
   - This toolkit is skills-based

3. **Verify installation methods**
   - Look for install scripts
   - Check existing patterns
   - Test before shipping

## Next Steps

1. ✅ Fix installation method (complete)
2. ✅ Update detection logic (complete)
3. ✅ Test installation (verified working)
4. ⏳ Update all documentation
5. ⏳ Test end-to-end setup flow

## Status

**Status:** ✅ Fixed and Tested
**Files Changed:** 1 (complete-setup.sh)
**Lines Modified:** ~80
**Tests Passing:** Yes

The installation now works correctly using the proper skills installation method.
