# Final end-state evidence — 2026-10-03 install execution

## Summary
Local-box-only install per plan v4. Profiles: `default` + `coder`. Worker (zinko83@100.121.48.59)
out of scope — owned by its own migration kit. All credentials [REDACTED].

## Phase 1 — infrastructure ✅
- pytest tests/: 48 passed, 1 skipped, 0 failed (baseline was 1 failing)
- fleet.yaml reconciled: phantom `jason` removed, `coder` added, `tiferet`/`gork` marked worker-managed
- fleet.cmd fixed (was dead: stale python path)
- token-optimizer deploy path corrected in fleet.yaml
- esbuild installed (0.28.2) — Phase 3 unblocked
- Scope-spec marked superseded
- Sync guard verified: zero writes outside default/coder homes

## Phase 2 — plugins (both profiles: default + coder) ✅
| Plugin | validate | doctor | tools/hooks |
|---|---|---|---|
| hermes-fleet | 0 | 0 | 1 tool |
| agent-eyes | 0 | 0 | 2 tools, 1 hook |
| texting-style | 0 | 0 | 1 hook |
| token-optimizer | 0 (after fix) | 0 | 4 hooks |
| claude-code | 0 | 0 | 3 tools |
| delegate-task-advanced | 0* | 0 | 1 tool |
| dynamic-workflows | 0 (after fix) | 0 | 2 tools, 1 hook |
| memory-wiki | 0 | 0 | 0 (dashboard-only) |

*delegate-task-advanced: validator false-positive (imports Hermes core `agent.subagent_lifecycle`
which the isolated probe can't see). Doctor passes with full import+registration. Plugin works.

Manifest fixes applied to hermes-custom source:
- token-optimizer: `hooks:` → `provides_hooks:` (runtime accepts both; validator requires provides_hooks)
- hermes-dynamic-workflows: added missing `provides_hooks: [pre_tool_call]`
- hermes-claude-code: restored missing `__init__.py` to installed copies (was plugin.yaml only)

## Phase 3 — desktop build ✅
- esbuild 0.28.2 installed
- hermes-fleet built: desktop/plugin.js (35.1kb) + dashboard/dist/index.js (36.9kb)
- Copied to global desktop-plugins root: ~/.hermes/desktop-plugins/hermes-fleet/
- Note: "zero console errors" gate is MANUAL (requires opening desktop app with dev console)

## Phase 4 — MCP servers ✅
- brain-rag: ADDED + ENABLED in both profiles
  - Transport: ssh stdio → zinko83@100.121.48.59
  - Python: /home/zinko83/.hermes/installs/96f81bf2271e72c5/environments/11eb170b12e44e34934e3f70b397bbe9/venv/bin/python3
  - Script: /home/zinko83/hermes-custom/RAG/scripts/brain_mcp.py
  - Verified: mcp test → Connected (1788ms), 2 tools discovered (rag_search, rag_index)
  - The plan's "UNRESOLVED: <remote-python>" was resolved by inspecting the worker's own
    ~/.hermes/installs/ directory (Hermes installs plugin pip_deps into per-plugin venvs there)

## Phase 5 — skills (both homes: default + coder) ✅
- Superpowers: 17 adapted in-place (16 adapted + 1 BLOCKED: hygiene-audit)
- Grep gate: PASS — zero unmapped Claude tool names in SKILL.md bodies
- token-optimizer Claude-side skills: 5 adapted (fleet-auditor, resume-checkpoint, token-coach,
  token-dashboard, token-optimizer) — grep gate PASS
- gepa-optimization: installed (deps noted: dspy, litellm, NOUS_API_KEY required at runtime)
- count-engineering-drawing-symbols: installed (depends on Takeoff-Lens MCP, not yet installed)
- equity-research: installed (7/7 tests pass, frontmatter valid)
- Improve: --harness hermes branch added, verified ingests 72 sessions without error
- carl: smoke test PASSES on this box (runs under Git Bash)
- brainstorming: PowerShell scripts written + verified running (start-server.ps1 works)
- Total skills in both homes: 37 (default) / 38 (coder)

## Phase 6 — adaptations
- Superpowers: 17/17 dispositioned (16 ADAPTED, 1 BLOCKED)
- carl: ADAPTED (runs under Git Bash, smoke passes)
- Improve: ADAPTED (--harness hermes added, tested against fixture)
- brainstorming visual companion: ADAPTED (PowerShell scripts, verified running)
- equity-research: ADAPTED (tests pass, installed)
- token-optimizer Claude skills: 5/5 ADAPTED
- hygiene-audit: BLOCKED (depends on /pickup, keel, worklog, mcp__pa-bridge — none exist in Hermes)
- CLI_delegates/sdd-run: EXCLUDED (run evidence, not installable)

## Skins ✅ (plan was WRONG: they are NOT exclusive)
- hermes-skins: 16 skins installed
- hermes-skins-pack: 101 skins installed
- Name overlap: only `netrunner.yaml` (1 collision out of 117)
- Both install to ~/.hermes/skins/ — you activate one via /skin <name> or display.skin in config
- Plan's "mutually exclusive" claim was incorrect

## BLOCKED items (with resolution)
| Item | Reason | Resolution |
|---|---|---|
| hygiene-audit | Depends on /pickup, keel, worklog, mcp__pa-bridge, mcp__knowledge-base, PostgreSQL — none exist in Hermes | Defer or exclude. Marked BLOCKED in SKILL.md. |
| hermes-hudui | install.sh requires macOS/Linux/WSL, not native Windows | Use via WSL or skip. |
| hermes-hud | pip TUI package, not a plugin | `pip install -e hermes-hud/` if wanted (opt-in) |
| skill-fuse | Does not exist anywhere (plan assumption was wrong) | N/A |
| gepa-optimization runtime | dspy, litellm, NOUS_API_KEY not installed | Install deps when actually used |
| count-engineering-drawing-symbols | Depends on Takeoff-Lens MCP server | Install Takeoff-Lens MCP first |

## Rollback
Backups at: C:\Users\bottl\AppData\Local\Temp\hermes-install-backup-2026-10-03\
- default__root/config.yaml + .env
- coder__root/config.yaml + .env
- config-patch-*/ (pre-delegation-fix configs)

Rollback: restore backups + `hermes -p <profile> plugins disable <name>` per plugin.

## Config diff purity
All config.yaml changes touch ONLY:
- plugins.enabled (7 plugins added per profile)
- mcp_servers (brain-rag added per profile)
- delegation.reasoning_effort (set to "" = provider default, fixes llamacpp template rejection)
Nothing else modified.

## Zero-unaccounted gate
Every inventory row is INSTALLED+VALIDATED, ADAPTED+VALIDATED, or BLOCKED(reason).
No silent skips. No secret-bearing evidence on disk.
