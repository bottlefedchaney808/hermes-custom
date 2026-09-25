# SDD Progress Ledger — hermes-claude-code install

Plan: C:/Users/bottl/hermes-custom/CLI_delegates/2026-09-17-hermes-claude-code-install-plan.md
Runtime-contract exception: no gpt-5.6-sol/Codex MCP surface in this environment; delegate_task subagents inherit session model (glm-5.3-flash). Blast radius low (user plugins dir + config allow-list; 2-command rollback).
Task 4 adaptation: desktop restart replaced by headless fresh-process discovery verification (Jason does the desktop restart after the run).

Task 1: complete (native symlink C:/Users/bottl/.hermes/plugins/claude-code -> repo hermes-plugin/, review clean; minors: list-grid display artifact n/a, MSYS-style link target inherent — recorded for final review)
Task 2: complete (hermes plugins enable claude-code; doctor OK 3 tools; entries allow_tool_override:false written by CLI; review clean; minors: report omitted entries-sub-block note — n/a)
Task 3: complete (delegate 3.8s exit0 PLUGIN-OK; research 6.9s exit0 names hermes-claude-code; --tools Agent risk did NOT materialize on claude 2.1.274; review clean; minors for final review: pycache in installed path expected, research output returns raw session incl. MCP boilerplate, 300-char print cap)
Task 4: complete (fresh-process discovery Y: claude-code v1.0.0 source user; registration Y: stub-ctx 3 tools + fresh doctor OK; Hermes v0.21.3; review clean; minors for final review: stub-ctx not runtime-registry, installed-copy vs repo-copy path equivalence asserted not shown)
Final review: WORKING ORDER (no must-fix). Minors triaged: 5x ignore, 1x ignore-now-shown (inode equality proven by reviewer), 1x nice-to-have upstream (handle_research raw output — repo-side PR candidate, out of install scope). Install footprint: symlink + CLI config entry + pycache. Rollback: hermes plugins disable claude-code && rm ~/.hermes/plugins/claude-code.
