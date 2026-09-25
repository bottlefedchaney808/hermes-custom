# Task 3 Report: Standalone smoke test of claude_code_delegate and claude_code_research

Date: 2026-09-17
Environment: Windows 11, git-bash, claude CLI v2.1.274 (per plan pre-flight).
Test target: installed plugin at `C:/Users/bottl/.hermes/plugins/claude-code/__init__.py` (loaded via importlib from the install path / symlink — not a repo copy).

---

## Step 1: Smoke `claude_code_delegate` (bypassPermissions path)

Command (verbatim from brief):

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

Output (verbatim):

```
cli-found: True
status: completed exit: 0
PLUGIN-OK
```

Timing: real 3.838s. Process exit code: 0.

Result: **PASS** — matches expected (`cli-found: True`, `status: completed exit: 0`, output contains `PLUGIN-OK` exactly).

---

## Step 2: Smoke `claude_code_research` (`--tools` restricted path — KNOWN RISK)

Command (verbatim from brief):

```bash
cd "C:/Users/bottl/.hermes/plugins/claude-code" && python -c "
import json, importlib.util
spec = importlib.util.spec_from_file_location('hcc', '__init__.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
r = json.loads(m.handle_research({'question': 'In one line: what is the package name in package.json?', 'work_dir': 'C:/Users/bottl/hermes-custom/CLI_delegates/hermes-claude-code'}))
print('status:', r['status'], 'exit:', r['exit_code']); print(r['output'][:300])
" 2>&1
```

Output (verbatim, first 300 chars as printed by the script):

```
status: completed exit: 0
The package name is `hermes-claude-code` (`package.json:2`).

Also, some MCP servers need sign-in before they'll work, and this session can't do that. For the claude.ai connectors, that's Microsoft 365, which you can set up in your claude.ai connector settings. The plugin servers are amplitude, ampl
```

Timing: real 6.850s. Process exit code: 0.

Result: **PASS** — `status: completed`, exit 0, answer names `hermes-claude-code` with a `package.json:2` citation. **The known risk did not materialize: the `--tools Read Glob Grep Bash Agent` list (repo `__init__.py:162`) was accepted by claude v2.1.274 — no unknown-tool/flag error, no isolation run needed.**

---

## Step 3: Results recorded

Both steps captured verbatim above. No files created or modified (read-only test against the install). Repo `C:/Users/bottl/hermes-custom/CLI_delegates/hermes-claude-code` untouched.

## Concerns (non-blocking)

1. **Research output contains boilerplate noise.** Alongside the correct one-line answer, the research subprocess appended an unprompted paragraph about MCP servers needing sign-in (claude.ai connectors, "amplitude, ampl..." — truncated at the 300-char print cap). The handler still returned `status: completed exit: 0` and the answer is present, so the interface contract holds, but downstream consumers of `handle_research` output should expect trailing chatter from the claude session, not just the answer. Optional fix decision for controller: add a stricter prompt line (e.g. "Answer with one line only, no commentary") in the REPO copy if clean output matters.
2. `cli-found: True` confirmed the claude CLI resolves on PATH from the install context.
