# hermes-claude-code Install Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use executing-plans (inline) or subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Install the hermes-claude-code integration (plugin path, Option B) so Hermes gets `claude_code_delegate` / `claude_code_research` / `claude_code_batch` tools that spawn `claude -p` sub-agents.

**Architecture:** The repo's Hermes plugin (`hermes-plugin/__init__.py`) registers 3 tools via `ctx.register_tool()` — verified byte-compatible with current Hermes (`register_tool(name, toolset, schema, handler, check_fn, description, emoji)` in `hermes_cli/plugins.py:460`). Plugin dir goes under `~/.hermes/plugins/claude-code`, enabled via `hermes plugins enable`. The MCP server path is optional (only adds `claude_code_continue`); skipped by default because running both would put near-duplicate tool schemas on every API call.

**Tech Stack:** Python 3.11 plugin (stdlib only — no npm install needed for the plugin path), Claude Code CLI 2.1.274, Node v26.4.0 (only for optional MCP task).

## Global Constraints

- Shell is git-bash on Windows. Native tools (claude.exe, node) need `C:/...` paths; bash builtins accept `/c/...`.
- Never hand-edit `~/.hermes/config.yaml` — use `hermes plugins enable` / `hermes config set`.
- Repo `C:/Users/bottl/hermes-custom/CLI_delegates/hermes-claude-code` must stay clean (no plan/artifact files inside it).
- Plugin default `--permission-mode bypassPermissions` auto-approves ALL tool use inside the Claude Code sub-agent (file writes, bash, network). This is the spec's documented behavior; `claude_code_research` is restricted to `--tools Read Glob Grep Bash Agent`.
- Sub-agent runs consume Jason's Claude subscription quota (auth verified: `claude.ai` firstParty, loggedIn true).
- User plugins in this config are opt-in: `plugins.enabled` is an explicit allow-list (verified at config.yaml:305), so enable step is mandatory.

## Preflight — ALREADY VERIFIED (do not redo unless something changed)

- [x] claude CLI: `C:/Users/bottl/.local/bin/claude.exe` v2.1.274, auth OK (`claude auth status` → loggedIn true)
- [x] `claude -p "..." --permission-mode bypassPermissions --verbose 0` → exit 0 (the exact arg shape the plugin uses works on this claude version)
- [x] Node v26.4.0; repo cloned at `C:/Users/bottl/hermes-custom/CLI_delegates/hermes-claude-code`, clean tree, origin = github.com/DevvGwardo/hermes-claude-code
- [x] `~/.hermes/plugins/` exists with 15 working plugins (discovery confirmed live)
- [x] Plugin API compatibility confirmed against installed Hermes source

---

### Task 1: Install plugin directory into `~/.hermes/plugins`

**Files:**
- Create: `C:/Users/bottl/.hermes/plugins/claude-code` (symlink → repo's `hermes-plugin/`, or a copy if native symlinks unavailable)

**Interfaces:**
- Produces: `<~/.hermes/plugins>/claude-code/plugin.yaml` readable — this is what Hermes discovery scans for (`scan_directory` in `hermes_cli/plugins_discovery.py` accepts `plugin.yaml`/`plugin.yml` in `~/.hermes/plugins/<name>/`).

- [ ] **Step 1: Try a native symlink first (keeps `git pull` updates live)**

```bash
export MSYS=winsymlinks:nativestrict
ln -s "C:/Users/bottl/hermes-custom/CLI_delegates/hermes-claude-code/hermes-plugin" "C:/Users/bottl/.hermes/plugins/claude-code"
[ -L "C:/Users/bottl/.hermes/plugins/claude-code" ] && echo SYMLINK-OK
```

Expected: `SYMLINK-OK`. If `[ -L ]` fails (MSYS fell back to a copy — that copy is still functional, just not live-linked), proceed to Step 2's verification anyway and note `install-type: copy`.

- [ ] **Step 2: Verify discovery-shaped manifest is readable through the new path**

```bash
cat "C:/Users/bottl/.hermes/plugins/claude-code/plugin.yaml"
```

Expected: manifest with `name: claude-code`, `version: 1.0.0`, 3 `provides_tools`. If missing → the symlink is broken; `rm` it and fall back to `cp -r "C:/Users/bottl/hermes-custom/CLI_delegates/hermes-claude-code/hermes-plugin" "C:/Users/bottl/.hermes/plugins/claude-code"`, then re-cat.

- [ ] **Step 3: Confirm discovery sees it (BEFORE enabling)**

```bash
hermes plugins list 2>&1 | grep -i claude
```

Expected: a row for `claude-code` (may show as not enabled / disabled — that's Task 2). If absent entirely, stop and check `hermes plugins doctor claude-code` output before proceeding.

### Task 2: Enable the plugin

**Files:**
- Modify: `~/.hermes/config.yaml` `plugins.enabled` list — ONLY via the CLI command below.

**Interfaces:**
- Consumes: manifest name `claude-code` from Task 1.
- Produces: `plugins.enabled` contains `claude-code`; plugin loads at next Hermes start.

- [ ] **Step 1: Enable via CLI (never edit the yaml by hand)**

```bash
hermes plugins enable claude-code
```

Expected: success message. Do NOT pass `--allow-tool-override` (plugin registers new tool names, it does not shadow built-ins).

- [ ] **Step 2: Verify enablement + validation**

```bash
hermes plugins list 2>&1 | grep -i claude
hermes plugins doctor claude-code 2>&1 | tail -20
```

Expected: enabled; doctor reports valid registration contracts. If doctor flags an error, fix the cause before Task 3 (do not rationalize past it).

### Task 3: Standalone smoke test of the handlers (real subprocess, no Hermes restart needed)

**Files:** none created. Read-only test against the repo.

**Interfaces:**
- Consumes: installed plugin `__init__.py` (Task 1), claude CLI (preflight).
- Produces: proof that `handle_delegate` and `handle_research` return `status: completed` with exit 0.

- [ ] **Step 1: Smoke `claude_code_delegate` (the real bypassPermissions path)**

```bash
cd "C:/Users/bottl/.hermes/plugins/claude-code" && python -c "
import json, importlib.util
spec = importlib.util.spec_from_file_location('hcc', '__init__.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
print('cli-found:', m.check_claude_code())
r = json.loads(m.handle_delegate({'task': 'Reply with exactly: PLUGIN-OK', 'work_dir': 'C:/Users/bottl/hermes-custom/CLI_delegates/hermes-claude-code'}))
print('status:', r['status'], 'exit:', r['exit_code']); print(r['output'][:200])
" 2>&1
```

Expected: `cli-found: True`, `status: completed exit: 0`, output contains `PLUGIN-OK`. Timeout 300s (claude cold start).

- [ ] **Step 2: Smoke `claude_code_research` (the `--tools` restricted path — KNOWN RISK)**

```bash
cd "C:/Users/bottl/.hermes/plugins/claude-code" && python -c "
import json, importlib.util
spec = importlib.util.spec_from_file_location('hcc', '__init__.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
r = json.loads(m.handle_research({'question': 'In one line: what is the package name in package.json?', 'work_dir': 'C:/Users/bottl/hermes-custom/CLI_delegates/hermes-claude-code'}))
print('status:', r['status'], 'exit:', r['exit_code']); print(r['output'][:300])
" 2>&1
```

Expected: `status: completed`, answer names `hermes-claude-code`.

**If it fails** with an unknown-tool / flag error: the `--tools Read Glob Grep Bash Agent` list (repo `__init__.py:162`) contains a name this claude build rejects (likely `Agent`). Finding, not failure — record the exact stderr, patch the list in the REPO copy (`git diff` stays reviewable), re-run the symlink/copy refresh from Task 1 Step 1, re-test. Do not silently edit the installed copy only.

- [ ] **Step 3: Record results**

Print nothing extra — capture both outputs verbatim in the completion report (status lines + first 200 chars).

### Task 4: Restart Hermes and verify tools surface

**Files:** none.

- [ ] **Step 1: Jason restarts the Hermes desktop app** (plugin discovery runs at startup; current session will NOT see the tools). This is the point where Jason takes over per his instruction.

- [ ] **Step 2: After restart, verify in a fresh Hermes session**

```
hermes plugins list 2>&1 | grep claude
```

and in the new session ask Hermes to run `claude_code_research` with the Task 3 Step 2 question. Expected: tool fires, returns the one-liner.

### Task 5 (OPTIONAL — skip by default): MCP server for `claude_code_continue`

Only if Jason wants session-continuity (`claude_code_continue` is MCP-only). Do NOT register both plugin and MCP — duplicate tool surfaces on every API call.

- [ ] `cd "C:/Users/bottl/hermes-custom/CLI_delegates/hermes-claude-code" && npm install --production`
- [ ] `hermes mcp add claude-code -- node "C:/Users/bottl/hermes-custom/CLI_delegates/hermes-claude-code/server.mjs"` (then `hermes mcp list` to verify; suggested Hermes-side timeout 660)
- [ ] If enabled, disable the plugin's overlapping tools via `hermes mcp configure` tool selection, or disable the plugin entirely — pick ONE surface, decide before registering.

### Rollback

```bash
hermes plugins disable claude-code
rm -rf "C:/Users/bottl/.hermes/plugins/claude-code"
```

Restart Hermes. Nothing else was modified (config change via CLI is reverted by disable; no core files touched).

---

## Self-Review

- **Spec coverage:** plugin install (Task 1), enable (Task 2), working tools (Task 3-4), MCP option preserved (Task 5), rollback — matches README Option B + install.sh `plugin` mode; MCP left optional by design decision above.
- **Placeholder scan:** every command is exact; no TBDs.
- **Type consistency:** plugin name/key `claude-code` used identically in manifest, enable, doctor, list, rollback.
