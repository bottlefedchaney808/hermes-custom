# Plan context (verbatim from plan)

**Global Constraints (bind every task):**
- Shell is git-bash on Windows; native tools need C:/... paths.
- Never hand-edit ~/.hermes/config.yaml — use hermes plugins enable / hermes config set.
- Repo C:/Users/bottl/hermes-custom/CLI_delegates/hermes-claude-code must stay clean.
- Plugin default --permission-mode bypassPermissions is the spec's documented behavior.
- plugins.enabled is an explicit allow-list; enable step is mandatory.

---

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

