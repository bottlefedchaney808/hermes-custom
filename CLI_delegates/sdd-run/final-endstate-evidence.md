# Final end-state evidence (controller-gathered)

## 1. install entry
lrwxrwxrwx 1 bottl 197609   75 Sep 17 03:22 claude-code -> /c/Users/bottl/hermes-custom/CLI_delegates/hermes-claude-code/hermes-plugin

## 2. manifest through installed path
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

## 3. enabled + doctor
│ claude-code   │ enabled     │ 1.0.0        │ Delegate       │ user          │
Plugin Doctor: 
C:\Users\bottl\hermes-custom\CLI_delegates\hermes-claude-code\hermes-plugin
  manifest: claude-code 1.0.0 (standalone)
  OK: runtime discovery, manifest parsing, import, and registration passed
  registrations: 3 tool(s), 0 hook(s)

## 4. plugins.enabled resolved contains claude-code
1

## 5. source repo clean
--BEGIN--
--END--

## 6. plan + sdd-run artifact inventory
C:/Users/bottl/hermes-custom/CLI_delegates/:
2026-09-17-hermes-claude-code-install-plan.md
hermes-claude-code
sdd-run

C:/Users/bottl/hermes-custom/CLI_delegates/sdd-run/:
final-endstate-evidence.md
progress.md
task-1-brief.md
task-1-report.md
task-1-review-evidence.md
task-2-brief.md
task-2-report.md
task-2-review-evidence.md
task-3-brief.md
task-3-report.md
task-3-review-evidence.md
task-4-brief.md
task-4-report.md
task-4-review-evidence.md
task-5-brief.md

## 7. Task 3 smoke results (from report)
r = json.loads(m.handle_delegate({'task': 'Reply with exactly: PLUGIN-OK', 'work_dir': 'C:/Users/bottl/hermes-custom/CLI_delegates/hermes-claude-code'}))
print('status:', r['status'], 'exit:', r['exit_code']); print(r['output'][:200])
status: completed exit: 0
PLUGIN-OK
Timing: real 3.838s. Process exit code: 0.
Result: **PASS** — matches expected (`cli-found: True`, `status: completed exit: 0`, output contains `PLUGIN-OK` exactly).
r = json.loads(m.handle_research({'question': 'In one line: what is the package name in package.json?', 'work_dir': 'C:/Users/bottl/hermes-custom/CLI_delegates/hermes-claude-code'}))
print('status:', r['status'], 'exit:', r['exit_code']); print(r['output'][:300])
status: completed exit: 0
The package name is `hermes-claude-code` (`package.json:2`).
Timing: real 6.850s. Process exit code: 0.
Result: **PASS** — `status: completed`, exit 0, answer names `hermes-claude-code` with a `package.json:2` citation. **The known risk did not materialize: the `--tools Read Glob Grep Bash Agent` list (repo `__init__.py:162`) was accepted by claude v2.1.274 — no unknown-tool/flag error, no isolation run needed.**
