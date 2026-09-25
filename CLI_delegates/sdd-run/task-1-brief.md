# Plan context (verbatim from plan)

**Global Constraints (bind every task):**
- Shell is git-bash on Windows; native tools need C:/... paths.
- Never hand-edit ~/.hermes/config.yaml — use hermes plugins enable / hermes config set.
- Repo C:/Users/bottl/hermes-custom/CLI_delegates/hermes-claude-code must stay clean.
- Plugin default --permission-mode bypassPermissions is the spec's documented behavior.
- plugins.enabled is an explicit allow-list; enable step is mandatory.

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

