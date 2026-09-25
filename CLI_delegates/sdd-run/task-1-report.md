# Task 1 Report: Install plugin directory into ~/.hermes/plugins

**Status: DONE — install-type: symlink**

## What was done
Created `C:/Users/bottl/.hermes/plugins/claude-code` as a native symlink pointing at the repo's `hermes-plugin/` subfolder (MSYS `winsymlinks:nativestrict` succeeded, so no copy fallback was needed). Verified the manifest reads through and Hermes discovery sees the plugin. Plugin NOT enabled; config.yaml untouched; nothing committed.

## Step 1: Native symlink
```
$ export MSYS=winsymlinks:nativestrict
$ ln -s "C:/Users/bottl/hermes-custom/CLI_delegates/hermes-claude-code/hermes-plugin" "C:/Users/bottl/.hermes/plugins/claude-code"
$ [ -L "C:/Users/bottl/.hermes/plugins/claude-code" ] && echo SYMLINK-OK
SYMLINK-OK
$ ls -la "C:/Users/bottl/.hermes/plugins/" | grep claude-code
lrwxrwxrwx 1 bottl 197609   75 Sep 17 03:22 claude-code -> /c/Users/bottl/hermes-custom/CLI_delegates/hermes-claude-code/hermes-plugin
```

## Step 2: Manifest reads through
```
$ cat "C:/Users/bottl/.hermes/plugins/claude-code/plugin.yaml"
name: claude-code
version: 1.0.0
description: Delegate coding tasks to Claude Code CLI sub-agents
author: DevvGwardo
requires_env: []
provides_tools:
  - claude_code_delegate
  - claude_code_research
  - claude_code_batch
provides_hooks: []
```
Manifest shape matches expectations: `name: claude-code`, `version: 1.0.0`, 3 `provides_tools`. Discovery-shaped read confirmed (no broken link).

## Step 3: Discovery sees it (before enabling)
```
$ hermes plugins list 2>&1 | grep -i claude
│ claude-code   │ not enabled │ 1.0.0        │ Delegate       │ user          │
│               │             │              │ to Claude Code │               │
```
Row present, `not enabled` (Task 2's job), sourced `user`.

## Constraint checks
- Source repo clean:
```
$ git -C "C:/Users/bottl/hermes-custom/CLI_delegates/hermes-claude-code" status --short
(no output, exit 0)
```
- config.yaml not touched. No enable performed. No commits made.

## Self-review
- Symlink target resolves to the repo's `hermes-plugin/` dir exactly as briefed (ls -la shows the target path).
- Read-through verified by `cat` of plugin.yaml — discovery-critical file present and correct.
- `hermes plugins list` lists claude-code as a user plugin, not enabled — exactly the expected pre-enable state.
- No fallback path exercised (native symlink worked).

## Concerns
- `hermes plugins list` output included a garbled overlapping row mentioning "claude-plugin…" in the grid — likely just table-width wrapping of adjacent columns; the claude-code row itself is clean and correct. No action needed.
- Note: symlink means `git pull` in the source repo updates the live plugin — intended per brief.
