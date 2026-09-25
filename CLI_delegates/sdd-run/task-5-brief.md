# Plan context (verbatim from plan)

**Global Constraints (bind every task):**
- Shell is git-bash on Windows; native tools need C:/... paths.
- Never hand-edit ~/.hermes/config.yaml — use hermes plugins enable / hermes config set.
- Repo C:/Users/bottl/hermes-custom/CLI_delegates/hermes-claude-code must stay clean.
- Plugin default --permission-mode bypassPermissions is the spec's documented behavior.
- plugins.enabled is an explicit allow-list; enable step is mandatory.

---

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
