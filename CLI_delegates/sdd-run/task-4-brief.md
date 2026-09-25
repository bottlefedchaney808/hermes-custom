# Plan context (verbatim from plan)

**Global Constraints (bind every task):**
- Shell is git-bash on Windows; native tools need C:/... paths.
- Never hand-edit ~/.hermes/config.yaml — use hermes plugins enable / hermes config set.
- Repo C:/Users/bottl/hermes-custom/CLI_delegates/hermes-claude-code must stay clean.
- Plugin default --permission-mode bypassPermissions is the spec's documented behavior.
- plugins.enabled is an explicit allow-list; enable step is mandatory.

---

### Task 4: Restart Hermes and verify tools surface

**Files:** none.

- [ ] **Step 1: Jason restarts the Hermes desktop app** (plugin discovery runs at startup; current session will NOT see the tools). This is the point where Jason takes over per his instruction.

- [ ] **Step 2: After restart, verify in a fresh Hermes session**

```
hermes plugins list 2>&1 | grep claude
```

and in the new session ask Hermes to run `claude_code_research` with the Task 3 Step 2 question. Expected: tool fires, returns the one-liner.

