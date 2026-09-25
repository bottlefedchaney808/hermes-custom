# brain-rag runbook

## Deploy

    scripts\deploy.cmd

Then, per profile that should have RAG:

1. Add `brain-rag` to `plugins.enabled` in that profile's `config.yaml`.
   Desktop Settings -> Plugins does **not** import the Python half.
2. Restart the supervised backend so `/api/plugins/brain-rag/*` mounts.
   Route mounts happen at process import; a plugin rescan does not remount.

Verify: `GET /api/plugins/brain-rag/status` returns `{"ok": true, ...}`.

## Paths

Index file: `$HERMES_HOME/rag/brain.sqlite` (per profile, never in git).

On Windows, if `HERMES_HOME` is unset, the default is `%LOCALAPPDATA%/hermes`
— not `~/.hermes`. Named profiles live under
`%LOCALAPPDATA%/hermes/profiles/<name>/`.

## Weekly cron (profile `default`, after the eval gate is green)

    hermes cron add "weekly sweep and reindex the brain" \
      --schedule "0 5 * * 1" \
      --command "python C:/Users/bottl/hermes-custom/RAG/scripts/weekly_sweep.py"

Exit 1 means the sweep hit an error; the commit may be local and unpushed.
Re-running is safe — existing session notes are skipped.

## Manual

    python scripts/weekly_sweep.py          # sweep + incremental index
    hermes chat -q "rag_index full"         # after a model or chunker change

## Backfill

Sessions already exported to
`C:/Users/bottl/hermes-salvage-20260909/session-exports/` are holding-pen
material, not vault content. Three hidden desktop sessions remain in
`state.db` (Bot Chat, Group: Connected Chat, dealer-model review) — they
become sweep fuel once they fall outside the window; no separate step.
