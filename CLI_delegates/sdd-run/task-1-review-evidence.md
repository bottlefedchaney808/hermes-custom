# Task 1 review evidence (controller-gathered, read-only)

## plugins dir entry
lrwxrwxrwx 1 bottl 197609   75 Sep 17 03:22 claude-code -> /c/Users/bottl/hermes-custom/CLI_delegates/hermes-claude-code/hermes-plugin

## symlink target read-through
total 21
drwxr-xr-x 1 bottl 197609     0 Sep 17 02:14 .
drwxr-xr-x 1 bottl 197609     0 Sep 17 03:22 ..
-rw-r--r-- 1 bottl 197609 14062 Sep 17 02:14 __init__.py
-rw-r--r-- 1 bottl 197609   251 Sep 17 02:14 plugin.yaml

## manifest via installed path
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

## hermes plugins list (claude rows)
│               │             │              │ claude-plugin… │               │
│ claude-code   │ not enabled │ 1.0.0        │ Delegate       │ user          │
│               │             │              │ to Claude Code │               │

## source repo git status (must be empty between markers)
--BEGIN--
--END--

## config.yaml plugins.enabled (must NOT contain claude-code yet)
plugins:
  enabled:
    - a2a-platform
    - agent-analytics
    - brain-rag
    - browser-browser-use
    - browser-firecrawl
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
  disabled: []
  entries:
