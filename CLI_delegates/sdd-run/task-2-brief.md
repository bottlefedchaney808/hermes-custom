# Plan context (verbatim from plan)

**Global Constraints (bind every task):**
- Shell is git-bash on Windows; native tools need C:/... paths.
- Never hand-edit ~/.hermes/config.yaml — use hermes plugins enable / hermes config set.
- Repo C:/Users/bottl/hermes-custom/CLI_delegates/hermes-claude-code must stay clean.
- Plugin default --permission-mode bypassPermissions is the spec's documented behavior.
- plugins.enabled is an explicit allow-list; enable step is mandatory.

---

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

