# Task 2 review evidence (controller-gathered, read-only)

## plugins list (claude rows)
│               │             │              │ claude-plugin… │               │
│ claude-code   │ enabled     │ 1.0.0        │ Delegate       │ user          │
│               │             │              │ to Claude Code │               │

## plugins doctor claude-code (full)
Plugin Doctor: 
C:\Users\bottl\hermes-custom\CLI_delegates\hermes-claude-code\hermes-plugin
  manifest: claude-code 1.0.0 (standalone)
  OK: runtime discovery, manifest parsing, import, and registration passed
  registrations: 3 tool(s), 0 hook(s)

## plugins.enabled (resolved)
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

## plugins.disabled (should be [])
[]

## config.yaml mtime vs now (change must predate this review)
2026-09-17 03:25:25.425021900 -0500 C:/Users/bottl/.hermes/config.yaml
Thu, Sep 17, 2026  3:26:37 AM

## claude-code entries section in raw config (verbatim)
308-    - browser-browser-use
309-    - browser-firecrawl
310:    - claude-code
311-    - disk-cleanup
312-    - hades-coding-workflows
313-    - hermes-achievements
--
335-    brain-rag:
336-      allow_tool_override: false
337:    claude-code:
338-      allow_tool_override: false
339-  hermes-memory-store:
340-    db_path: ~/.hermes/memory_store.db
