# Task 2 Report: Enable the claude-code Hermes plugin

Status: **DONE**

## Step 1 — Enable via CLI

Command (verbatim, no `--allow-tool-override`):

```bash
hermes plugins enable claude-code
```

Verbatim output:

```
✓ Plugin claude-code enabled. Takes effect on next session.
Allow this plugin to replace built-in tools (e.g. shell_exec, write_file)?
  This is a privileged capability: an override can intercept everything the
agent routes through that tool.
  Grant it?  claude-code may not override built-in tools. Re-run `hermes plugins enable
claude-code --allow-tool-override` to grant this later.
```

Notes: exit code 0. The tool-override question was auto-answered "no" by the CLI itself (the plugin's manifest declares no built-in overrides), which matches the requirement to NOT grant override. No interactive confirmation was needed; nothing was passed beyond the plugin name.

## Step 2 — Verify enablement

### `hermes plugins list 2>&1 | grep -i claude`

```
│               │             │              │ claude-plugin… │               │
│ claude-code   │ enabled     │ 1.0.0        │ Delegate       │ user          │
│               │             │              │ to Claude Code │               │
```

grep exit code: 0. Row shows `claude-code | enabled | 1.0.0`.

### `hermes plugins doctor claude-code 2>&1 | tail -20`

```
Plugin Doctor:
C:\Users\bottl\hermes-custom\CLI_delegates\hermes-claude-code\hermes-plugin
  manifest: claude-code 1.0.0 (standalone)
  OK: runtime discovery, manifest parsing, import, and registration passed
  registrations: 3 tool(s), 0 hook(s)
```

Doctor verdict: **OK** — no errors flagged. 3 tools registered, 0 hooks.

### config.yaml check (read-only)

`hermes config get plugins.enabled` returned the list; `claude-code` is present:

```
- a2a-platform
- agent-analytics
- brain-rag
- browser-browser-use
- browser-firecrawl
- claude-code
- disk-cleanup
- hades-coding-workflows
- hermes-achievements
- hermes-connector
- hermes-evolve
- hermes-memory-ui
- hermes-newswire
- hermes-resetwatch
- hermes-tailscale
- interactive-artifacts
- memory-wiki
- nous
- nous-prices
- nous-provider
- photon-platform
- qwen-late-system
- weather
- web-firecrawl
```

`plugins.enabled` **contains `claude-code`** — confirmed. config.yaml was never hand-edited; the change was made exclusively via `hermes plugins enable`.

## Constraints honored

- Enabled only via `hermes plugins enable claude-code` ✓
- No `--allow-tool-override` passed; override not granted ✓
- Smoke tests NOT run (Task 3's job) ✓
- Nothing restarted; no commits ✓
- Repo untouched ✓

## Concerns

None.

## Conclusion

Plugin `claude-code` is enabled, doctor passes (3 tools registered), and `plugins.enabled` includes it. Takes effect on next Hermes session. Ready for Task 3 (smoke tests).
