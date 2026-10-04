---
name: brain-rag-ops
description: Use when installing, indexing, checking, or fixing brain-rag vault search (rag_search / rag_index, vault path, MCP entry, deploy).
---

# brain-rag install and access check

brain-rag is `kind: external` in fleet.yaml: `fleet sync` does NOT install it and `fleet enable brain-rag` reports "nothing to toggle" (it loads via an `mcp_servers` entry, not `plugins.enabled`). `fleet status` shows MISS until its own deploy script runs.

## Check
1. `fleet status -v` (from the hermes-custom checkout with the fleet venv python: `-m fleet.cli`) - brain-rag row per profile.
2. Call `rag_search` through the MCP. `{"error": "Vault clone not found: <path>"}` means the server process cannot see the vault; the plugin install is not the problem.
3. Inspect `mcp_servers.brain-rag` in each profile's config.yaml (default: `$LOCALAPPDATA/hermes/config.yaml`; others: `profiles/<name>/config.yaml`). It is `ssh ... <server venv python> .../RAG/scripts/brain_mcp.py`, so brain lives on the worker server, not locally.

## Install (all target profiles in one run)
```bash
cd <hermes-custom>/RAG
L="$LOCALAPPDATA/hermes"
BRAIN_RAG_DEPLOY_ROOTS="$L/plugins/brain-rag;$L/profiles/<name>/plugins/brain-rag" \
  <fleet-venv>/Scripts/python.exe scripts/deploy.py
```
Pass `BRAIN_RAG_DEPLOY_ROOTS` explicitly (`;`-separated): the built-in default targets a stale profile name and would miss the real profile. It copies plugin/ + vendor src and never copies brain.sqlite.

## Vault path fix
The vault location comes from `OBSIDIAN_VAULT_PATH`, else `~/obsidian-vault` on the server. An ssh-launched command does not source `.profile`/`.bashrc`, so the env var set there is invisible. Inject it in the MCP args after the host, before the python path:
```
- <user>@<host>
- env
- OBSIDIAN_VAULT_PATH=<real vault path>
- <server venv python>
- .../RAG/scripts/brain_mcp.py
```
Find the real path with `ssh <host> 'grep -rn OBSIDIAN_VAULT_PATH ~/.profile ~/.hermes/.env'` and confirm with `ls`. Apply to every profile config carrying the entry; back each up first. Re-do this whenever the brain moves.

## Verify
On the server, from `RAG/scripts`: `env OBSIDIAN_VAULT_PATH=... <venv python> -c 'import brain_mcp; print(brain_mcp.rag_search("hermes memory"))'`; expect hits. The live MCP picks up config changes only after a Hermes restart, so state that instead of claiming the MCP path is verified. The index (`~/.hermes/rag/brain.sqlite`) is separate from the vault; check its mtime before deciding to run `rag_index`.

## Index
`rag_index` (MCP tool, no args = incremental) re-walks the vault and embeds only new/changed chunks. Healthy output: `files_indexed` > 0, `files_skipped` 0, `chunks_added` 0 when nothing changed. Use `mode: full` only after an embedding-model or chunker change. Weekly sweep + reindex: `python RAG/scripts/weekly_sweep.py` (see RAG/docs/runbook.md). A "Vault clone not found" error from either tool is the vault-path problem above, not an index problem.

## Hardening checklist
- Deploy with explicit `BRAIN_RAG_DEPLOY_ROOTS` (or the patched deploy.py, which now auto-discovers every profile dir).
- Back up each config.yaml before editing mcp_servers.
- After editing, restart Hermes, then run one `rag_search` through the MCP and one `rag_index`; report both results.
