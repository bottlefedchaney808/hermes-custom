# Install plan: all skills + plugins in hermes-custom onto this box's Hermes

**Date:** 2026-10-03
**Status:** PLAN — nothing below is executed. No install, no test, no fix has happened yet.

**v4 changelog (2026-10-03, scope correction):**
- **Worker is out of scope.** `tiferet` and `gork` are owned by the worker's own migration
  kit (`zinko83@100.121.48.59`). This plan covers local box only: profiles `default` and
  `coder`. `fleet.yaml` entries for worker profiles are removed or guarded by L0. `jason`
  removed as phantom. Sync guard added: dry-run before `sync --apply`, gate on zero
  writes outside `default`/`coder` homes.
- **brain-rag MCP is a new integration, not a verify-existing.** `hermes mcp list` returns
  "No MCP servers configured" on both local profiles. Adding stdio-over-SSH needs operator
  approval + the worker Hermes venv python path (UNRESOLVED — system `python3` can't import
  `sqlite_vec`).
- **v3 overclaims corrected:** "all hermes listeners bind 127.0.0.1" was wrong (worker has
  public listeners on `100.121.48.59:9902`, `:4096`, `:54554`). "No crontab" ≠ "no
  schedules" (systemd timers, hermes cron possible). "No hermes on PATH" ≠ "no hermes"
  (probe only checked `command -v hermes`). Stray local `tiferet` dir flagged. `deploy.py`/
  `deploy.cmd` must NOT run from here (local `%LOCALAPPDATA%` targets).
- Lane L2: "RAG consumption" not "RAG deployment".

**v3 changelog (2026-10-03, worker probe):**
- U8 RESOLVED: worker = `zinko83@100.121.48.59` (Linux/Ubuntu). RAG already installed on
  worker's Hermes `tiferet` profile. brain.sqlite on worker. No HTTP endpoint. MCP transport
  = stdio-over-SSH. No crontab found (scheduled jobs unverified). Artifacts exist on worker.
- U5 RESOLVED: local profiles `default`/`coder`; worker profiles `tiferet`/`gork`. `jason`
  is phantom. Phase 1 reconciliation now per-host.
- Phase 4 MCP: `--url` replaced with stdio-over-SSH. Worker sub-plan replaced with verified
  state (already deployed — do NOT re-deploy). Scheduled jobs flagged unverified.
- Phase 2 brain-rag: corrected to "already on worker, local box gets MCP client only".
- Phase 3 GRAPH_PATH: artifact exists locally — desktop pane works as-is.
- Lane L2: unblocked.
- Phase 5: `python -m fleet port` corrected to `python -m fleet.cli port`.

**v2 changelog (2026-10-03 review):**
- RAG moved to a worker box (operator statement) -> new unknown U8; lane L2 now
  BLOCKED(worker topology unconfirmed); Phase 4 MCP becomes remote `--url`; Phase 2
  brain-rag deps corrected to sqlite-vec/httpx/fastapi/pydantic; worker-deploy sub-plan added.
- `python -m fleet` is wrong — `fleet/__main__.py` does not exist; the entrypoint is
  `python -m fleet.cli` (what `fleet.cmd` uses). Corrected throughout.
- Per-profile home resolution added to Task 0 (`get_hermes_home()` under `-p coder`);
  "nothing enabled today" corrected — `browser-browser-use` is enabled (bundled).
- Coverage: Superpowers is 17 skills not 14 (added multimodel-review, using-superpowers,
  writing-skills); token-optimizer is a plugin + 5 skills (rows added); Takeoff-Lens
  `count-engineering-drawing-symbols` skill added; `CLI_delegates/sdd-run` EXCLUDED.
- Rollback: Task 0 now creates REAL backups (not just hashes); Phase 7 references them.
- Task 0 bash-heredoc replaced with a runnable `.py` (Windows).
- port.py notes SKILL.md is byte-identical between Claude/Hermes -> Phase 6 adaptation is
  mostly tool-name rewriting (grep gate kept, over-engineering removed); `~/.hermes/profiles/local/`
  added to the profile-reconciliation list.
- Per-component smoke made reproducible: `hermes -p <profile> chat -q "<prompt>" --oneshot -s <skill>`.
**Scope:** every skill and plugin inventoried under `C:\Users\bottl\hermes-custom`, installed
appropriately for **this machine only** — profiles `default` and `coder`. Worker profiles
`tiferet` and `gork` are owned by the worker's own migration kit (`zinko83@100.121.48.59`)
and are **explicitly out of scope**. Nothing in this plan installs, enables, deploys, or
syncs on the worker. RAG is consumed from the worker via MCP-over-SSH (Phase 4).
Foreign (non-Hermes) assets get explicit adaptation sub-plans with their own tests.
Every item ends as one of: **INSTALLED+VALIDATED**, **ADAPTED+VALIDATED**, or
**BLOCKED(reason, resolution)**. Blocked is not passed.

## Goal and completion contract

Install and validate every inventoried skill/plugin appropriate to this machine's Hermes
surfaces, adapting foreign assets through explicit subplans. Do NOT blindly enable every
example, overlapping integration, destructive skill, or mutually-exclusive skin. Every asset
gets a disposition. Completion = Phase 7 passes, including a full inventory diff with zero
unaccounted rows.

## Evidence and unresolved facts

Confirmed by direct inspection on this box (2026-10-03):

- Plugin contract: directory plugin = `plugin.yaml` + `__init__.py` exposing `register(ctx)`.
  User plugins load from `<HERMES_HOME>/plugins/<name>/`. `manifest_version` optional, defaults v1.
  Enablement via `plugins.enabled` in the profile `config.yaml`.
- Validation CLI exists: `hermes plugins validate <path> --json [--install-deps]`,
  `hermes plugins doctor [--ci] <id|path>`, `hermes plugins enable <name>`,
  `hermes mcp add <name> --command ... --args ... --env K=V`.
- **Two Hermes roots exist:** `C:\Users\bottl\.hermes` and `C:\Users\bottl\AppData\Local\hermes`.
  Agent code lives at `AppData\Local\hermes\hermes-agent`; live profiles at
  `AppData\Local\hermes\profiles\` (`coder` confirmed). Which root a process resolves is
  decided by `hermes_constants.get_default_hermes_root` — **verify in Task 0, do not hardcode**.
- `fleet.yaml` profiles (`default`, `jason`, `tiferet`, `gork`) do NOT match the live profiles.
- `fleet.cmd` launcher is dead (stale python path).
- Skills = `SKILL.md` with frontmatter `name`/`description`, platform-gated.
  `tools/skills_sync_client.py:176` skips `SKILL.md.is_symlink()` — but that is CLOUD sync
  enumeration only; local discovery of directory junctions is UNVERIFIED. Proved by gate in
  Phase 5, not assumed.
- Fleet CLI verbs: `status`, `sync`, `enable/disable`, `env`, `json`, `port`, `docs`.
  Fleet tests lock three guarantees: idempotent sync; config edits touch only `plugins.enabled`;
  staged skills are withheld, not installed. `packages:` in `fleet.yaml` is a YAML list.
- Nested git repos (separate ownership/revision): `CLI_delegates/hermes-claude-code`,
  `delegate-task-advanced`, `token-optimizer`, `UI_Skins/hermes-skins-pack`, `Takeoff-Lens-Plugin`,
  `hermes-dynamic-workflows`, `Self-Evolution/hermes-agent-self-evolution`, `hermes-bot-kit`,
  `hermes-hud`, `hermes-hudui`, `hermes-skins`, `Example/hermes-example-plugins`.
  Not repos: `RAG`, `hermes-fleet`.
- brain-rag plugin: `register()` at `RAG/plugin/__init__.py:137`; dashboard manifest present.
  Its desktop `plugin.js` hardcodes `GRAPH_PATH = C:/Users/bottl/hermes-artifacts/...` —
  existence gate required (Phase 3).
- hermes-dynamic-workflows: root `__init__.py` re-exports `register`; ships
  `scripts/install-hermes-workflows.py`.
- Desktop plugins (ESM, import `@hermes/plugin-sdk`): `hermes-bot-kit/bubble-mode`,
  `hermes-bot-kit/agent-eyes`, `hermes-fleet/desktop` (built), `RAG/plugin/desktop`.
- `port.py` docstring: Claude and Hermes `SKILL.md` are byte-for-byte the same file —
  adaptation is mostly tool-name rewriting, not format conversion (keep the grep gate,
  don't over-engineer). `port.py` also references a `~/.hermes/profiles/local/` profile —
  add it to the Phase 1 profile-reconciliation list.
- **RAG runs on the worker** `zinko83@100.121.48.59` (Linux/Ubuntu, Tailscale peer
  `zinkoserver`). Verified 2026-10-03 probe. The worker has its own Hermes instance with
  profiles `tiferet` and `gork`, managed by the worker's own migration kit — **out of scope
  for this plan**. brain-rag installed at `~/.hermes/plugins/brain-rag` +
  `~/.hermes/profiles/tiferet/plugins/brain-rag` (worker). brain.sqlite at
  `~/.hermes/profiles/tiferet/rag/brain.sqlite`. Artifacts at
  `/home/zinko83/hermes-artifacts/artifacts/vault-graph/index.html`. Worker has public
  listeners (`100.121.48.59:9902`, `:4096`, `:54554`) — exact transport owned by the
  worker kit, not assumed to be RAG. The local box does NOT have brain-rag installed and
  **no MCP servers are configured on either local profile** (verified 2026-10-03:
  `hermes mcp list` and `hermes -p coder mcp list` both return "No MCP servers
  configured"). RAG consumption is a new MCP-over-SSH integration (Phase 4).
  `deploy.py`/`deploy.cmd` targets are local `%LOCALAPPDATA%` — **do NOT run them from
  here** (they would create a stray local brain-rag copy). The worker kit handles its own
  deployment. `GRAPH_PATH` target
  `C:/Users/bottl/hermes-artifacts/artifacts/vault-graph/index.html` EXISTS locally — the
  desktop pane can work from this box (rendering still needs the Phase 3 manual check).
- `coder` profile config has a `plugins:` block containing only `clone_timeout_seconds`;
  bundled plugin `browser-browser-use` is enabled and builtin skills are enabled — the live
  baseline is NOT "nothing enabled." Capture the full untruncated list in Task 0.
  (Absence of an explicit `enabled:` key ≠ inference about enablement semantics — bundled
  plugins load without one.)

UNRESOLVED — verify in Task 0, record, never assume:

| # | Fact | Where it matters |
|---|------|-----------------|
| U1 | Canonical root resolution (`get_default_hermes_root`, `get_process_hermes_home`) | every install target |
| U2 | Runtime venv python path + `yaml`/`ruamel` availability | fleet, deploy scripts |
| U3 | node + esbuild presence | hermes-fleet `build.cmd` |
| U4 | token-optimizer installer path: `fleet.yaml` claims `skills/token-optimizer/scripts/hermes_install.py`; actual file found at `token-optimizer/hermes/scripts/hermes_install.py` | Phase 5 |
| U5 | ~~Live profile names~~ — **RESOLVED 2026-10-03 probe.** Local: `default`, `coder` (both running). Worker (`zinko83@100.121.48.59`): `tiferet`, `gork`. `fleet.yaml` profiles `default`/`tiferet`/`gork` span both machines. `jason` is absent from every profile dir checked (local `%LOCALAPPDATA%\hermes\profiles`, legacy `~/.hermes\profiles`, worker `~/.hermes/profiles`) — phantom. | Phase 1 reconciliation |
| U6 | Whether junctioned skills appear in `hermes skills list` | Phase 5 gate |
| U7 | RAG `GRAPH_PATH` target existence | Phase 3 |
| U8 | ~~RAG worker topology~~ — **RESOLVED 2026-10-03 probe.** Worker = `zinko83@100.121.48.59` (Linux/Ubuntu, Tailscale peer `zinkoserver`). RAG runs on the worker's own Hermes `tiferet` profile. brain-rag plugin at `~/.hermes/plugins/brain-rag` + `~/.hermes/profiles/tiferet/plugins/brain-rag`. brain.sqlite at `~/.hermes/profiles/tiferet/rag/brain.sqlite`. Artifacts at `/home/zinko83/hermes-artifacts/artifacts/vault-graph/index.html`. Worker has public listeners (`100.121.48.59:9902`, `:4096`, `:54554`) — exact transport owned by the worker kit. Worker is **out of scope** for this plan (managed by its own migration kit). Local box consumes RAG via MCP-over-SSH (Phase 4). `<remote-python>` path UNRESOLVED — system `python3` cannot import `sqlite_vec`. | Phases 2, 3, 4, lane L2 |

## Task 0: machine preflight + authoritative inventory

**Files:** evidence dir `docs/install-evidence/` (new). No mutations.
**Commands (Windows — no bash heredoc; write a `.py` and run it with the verified runtime
python from U2):**
```bat
mkdir docs\install-evidence\baseline
hermes profile list  > docs\install-evidence\baseline\profiles.txt 2>&1
hermes plugins list  > docs\install-evidence\baseline\plugins.txt 2>&1   REM full, untruncated
hermes skills list   > docs\install-evidence\baseline\skills.txt 2>&1    REM full, untruncated
hermes -p coder plugins list > docs\install-evidence\baseline\coder-plugins.txt 2>&1
```
Write `docs/install-evidence/baseline/task0.py` and run it with the U2 python:
```python
import os, sys, subprocess
sys.path.insert(0, r"C:\Users\bottl\AppData\Local\hermes\hermes-agent")
from hermes_constants import get_default_hermes_root, get_process_hermes_home, get_hermes_home
print("default_root", get_default_hermes_root())
print("process_home", get_process_hermes_home())
print("HERMES_HOME env", os.environ.get("HERMES_HOME"))
# per-profile home resolution — plugin/skill dirs live under the profile home, not necessarily root
for p in ("default", "coder"):
    r = subprocess.run(["hermes", "-p", p, "plugins", "list"], capture_output=True, text=True)
    print(p, "plugins-list-exit", r.returncode)
```
Record: canonical root, **per-profile home** (plugin + skill dirs per profile), runtime
python (U2), node/esbuild (U3), token-optimizer path (U4), profile list (U5), RAG GRAPH_PATH
(U7), RAG worker topology (U8). U6 (junction visibility) is resolved in Phase 5 itself,
not before — it is a discovery gate, not a pre-mutation requirement. **Create real backups** (not just hashes) of every `config.yaml` and `.env` any later
task will touch — into `$TEMP\hermes-install-backup-2026-10-03\<profile>__<root>\`
(a private location OUTSIDE this repo, never in `docs/`, so it can never be committed).
Record only redacted metadata + SHA-256 hashes in `docs/install-evidence/baseline/`
(present/size/hash only — **never print secret values**; redact as `[REDACTED]`). Phase 7
restores from the private backup dir.

**Gate:** every U1–U8 resolved and written to
`docs/install-evidence/baseline/preflight.txt`; backups exist on disk. Root ambiguity gone
before any mutation.

## Phase 1: correct the installation infrastructure

**Files:** `fleet.yaml`, `fleet.cmd`, `docs/hermes-custom-scope-spec.md` (marked superseded where
wrong), `tests/` (unchanged — it is the regression lock). No plugin installs in this phase.

1. Declare ONE canonical Hermes root from Task 0 evidence (U1). Document the other root as
   quarantined (do NOT delete it). Every later task targets the canonical root only.
   **Known leftover:** `~/.hermes/profiles/tiferet` exists in the legacy root — residue
   from an earlier migration. Quarantine it (don't sync into it, don't delete it). Note:
   `hermes -p tiferet` on THIS machine would resolve to that leftover dir if the legacy
   root were active — there is no cross-machine profile resolution. The worker's
   `tiferet` is a separate profile on a separate machine. The step-2 sync guard (zero
   writes outside `default`/`coder` homes) is what keeps sync from touching the leftover.
2. Reconcile `fleet.yaml` profiles. `fleet.yaml` names `default`, `jason`, `tiferet`, `gork`.
   `default` and `coder` are local. `tiferet` and `gork` belong to the **worker's own
   migration kit** (`zinko83@100.121.48.59`) — L0 removes them from `fleet.yaml` or marks
   them `host: worker` / `managed-elsewhere` so `fleet.cli sync` never touches them.
   `jason` is phantom (absent from every profile dir checked) — remove it.
   **Sync guard (before any `fleet.cli sync --apply`):** run a dry run first. Gate:
   zero planned writes outside the `default` and `coder` profile homes. This catches
   the case where `fleet.yaml` still names `tiferet`/`gork` and a sync would create
   stray local profile dirs for them.
3. Fix `fleet.cmd` — it is dead on a stale python path. Reproduce the failure first
   (run it, capture stderr), then point it at the verified runtime python (U2).
4. Fix wrong manifest source paths. Known-bad: token-optimizer — `fleet.yaml` claims
   `skills/token-optimizer/scripts/hermes_install.py`; actual file is at
   `token-optimizer/hermes/scripts/hermes_install.py` (U4). Correct `fleet.yaml`.
5. Mark `docs/hermes-custom-scope-spec.md` superseded where its inventory assumptions were wrong.
6. `pytest tests/` — `test_fleet.py`, `test_fleet_env.py`, `test_cli_bootstrap.py` must pass
   against the real root. These lock: idempotent sync, config edits touch only
   `plugins.enabled`, staged skills withheld.

**Gate:** `pytest tests/` green; `python -m fleet.cli status` runs clean against the canonical
root (`fleet/__main__.py` does not exist — the entrypoint is `python -m fleet.cli`, what
`fleet.cmd` uses); exactly one canonical root named in
`docs/install-evidence/baseline/preflight.txt`.

## Phase 2: Hermes-native Python plugins

One task per package. Same six steps each — no exceptions:

1. `hermes plugins validate <path> --json` (add `--install-deps` where pydeps exist) → exit 0
2. Install: `fleet sync` or copy/link into `<canonical-root>/plugins/<name>/`
3. `hermes plugins enable <name>` for the target profile(s)
4. `hermes plugins doctor --ci <name>` → exit 0
5. Tool smoke in a fresh session (tool is listed; one real call returns sane output)
6. Run the package's own tests

Per-package specifics:

- **brain-rag** (`RAG/plugin/`): `register()` at `__init__.py:137`. The local box does NOT
  install the brain-rag plugin or engine — RAG runs on the worker, managed by its own kit.
  The local box accesses RAG via MCP-over-SSH (Phase 4, new integration). Local validation
  only: `pytest RAG/tests/` (pyproject deselects the `golden` marker by default — keep
  that). Smoke: `rag_search` returns JSON on a **fixture vault**
  (`RAG/tests/fixtures/vault/`), never the real Obsidian vault. Do NOT run
  `deploy.py`/`deploy.cmd` from here (they target local `%LOCALAPPDATA%` and would create
  a stray copy). Do NOT provision the engine or duplicate the live index locally.
- **hermes-fleet backend** (`hermes-fleet/`): validate + enable; its desktop surface is
  Phase 3 (do not build here).
- **hermes-dynamic-workflows** (`hermes-dynamic-workflows/`): root `__init__.py` re-exports
  `register`; smoke = its tool registers in a fresh session. Its workflow SKILLS install in
  Phase 5 via `scripts/install-hermes-workflows.py` (separate task, separate gate).
- **delegate-task-advanced** (`delegate-task-advanced/`): validate, install, enable,
  doctor, smoke the delegate tool.
- **hermes-claude-code plugin** (`CLI_delegates/hermes-claude-code/hermes-plugin/`): validate,
  install, enable, doctor. Requires `claude` CLI on PATH — if absent, mark
  BLOCKED(claude CLI missing), do not fake the smoke.
- **texting-style** (`hermes-bot-kit/texting-style/`): validate, install, enable.
- **agent-eyes agent-plugin** (`hermes-bot-kit/agent-eyes/agent-plugin/agent-eyes/`):
  validate, install, enable, doctor. Desktop surface is Phase 3.
- **Example plugins** (`Example/hermes-example-plugins/`): **opt-in. Default = NOT enabled.**
  Validate-only unless the operator names one to enable.
- **hermes-hud** (`hermes-hud/`): validate; if it is a plugin, install + enable as opt-in
  (UI surface). `hermes-hudui` treated the same — opt-in.
- **token-optimizer** (`token-optimizer/hermes/`): this is a **plugin** (has `plugin.yaml`
  + `__init__.py`), not just a skill installer — validate + install + enable it here. Its 5
  Claude-side skills are Phase 6.

**Gate per plugin:** validate exit 0; doctor `--ci` exit 0; tool listed in a fresh session;
package tests pass; config diff touches **only** `plugins.enabled`. Evidence appended to
`docs/install-evidence/plugins/<name>.txt`.

## Phase 3: desktop plugins

**Build first:** `hermes-fleet/build.cmd` — requires node + esbuild (U3, verified in Task 0).
Gate: `dist/` regenerated, `desktop/plugin.js` bundle non-empty and newer than source.
If esbuild is missing, that is a correction task (install esbuild into
`<agent-code>/node_modules/@esbuild/`), not a skip.

**Install:** each desktop plugin lands in the global desktop-plugins location that
`fleet/sync.py` uses (read `sync.py` first and record the exact path — do not invent it).
Plugins: `hermes-fleet/desktop` (built), `hermes-bot-kit/bubble-mode`,
`hermes-bot-kit/agent-eyes`, `RAG/plugin/desktop`.

**RAG GRAPH_PATH gate (U7):** `RAG/plugin/desktop/plugin.js` hardcodes
`C:/Users/bottl/hermes-artifacts/artifacts/vault-graph/index.html`. If the target does not
exist, correction task: make the path configurable or point it at the worker-served
artifact (U8 — a worker filesystem path is not reachable from the desktop as a file URL).
Do not ship a pane that points at a missing file silently.

**Gate:** app loads each pane with **zero console errors** — this is a MANUAL checklist,
checked in the desktop app with the dev console open. Recorded per plugin in
`docs/install-evidence/desktop/<name>.txt`.

## Phase 4: MCP servers

- **brain-rag MCP (worker):** RAG runs on the worker's Hermes `tiferet` profile.
  **No MCP servers are currently configured on either local profile** (verified 2026-10-03:
  `hermes mcp list` and `hermes -p coder mcp list` both return "No MCP servers configured").
  Adding brain-rag MCP is a **new integration** requiring operator approval.
  
  Transport: **stdio-over-SSH** (the worker's Hermes processes are not directly reachable
  as HTTP from this box; SSH key auth is already configured):
  ```
  hermes mcp add brain-rag \
    --command ssh \
    --args -o BatchMode=yes zinko83@100.121.48.59 <remote-python> <remote>/RAG/scripts/brain_mcp.py
  ```
  **UNRESOLVED:** `<remote-python>` — the worker's system `python3` cannot import
  `sqlite_vec` (verified by probe). The server needs the worker Hermes venv's python.
  Get this path from the worker kit, do NOT guess. `<remote>/RAG/` is the worker's RAG
  source root (also from the worker kit).
  
  **Negative test:** worker unreachable gives a clean error within the connect timeout,
  not a hang. Credentials `[REDACTED]`.
- **Takeoff-Lens** (`Takeoff-Lens-Plugin/start-mcp.ps1`): requires its `.venv` to exist
  (verified in Task 0). If the venv is absent, provision it as a correction task first.

**Worker state (probe 2026-10-03 — worker is managed by its own migration kit, this plan
does NOT deploy or configure it):**
- brain-rag plugin present at `~/.hermes/plugins/brain-rag` +
  `~/.hermes/profiles/tiferet/plugins/brain-rag` (worker)
- brain.sqlite at `~/.hermes/profiles/tiferet/rag/brain.sqlite` + `~/.hermes/rag/brain.sqlite`
- Artifacts at `/home/zinko83/hermes-artifacts/artifacts/vault-graph/index.html`
- Worker has public listeners (`100.121.48.59:9902`, `:4096`, `:54554`) — the exact
  transport these expose is owned by the worker kit, not this plan
- `deploy.py`/`deploy.cmd` targets are local `%LOCALAPPDATA%` paths — **do NOT run them
  from here**; they would create a stray local brain-rag copy. The worker kit handles
  its own deployment.
- Scheduled jobs (`nightly.py`, `weekly_sweep.py`) are the worker kit's concern, not
  this plan's. Do not probe or configure them.

**Gate per server:** `hermes mcp` list/test shows tools discovered within the connect
timeout (worker reachable). Evidence in `docs/install-evidence/mcp/<name>.txt`.

## Phase 5: Hermes-native skills

**Install order:** (1) `skills/hermes/hermes-fleet` — run `python -m fleet.cli port` first (via the fixed
`fleet.cmd`), diff the generated result against `skills/claude/hermes-fleet` (the source),
then install the generated copy. (2) Skins — resolve the overlap between `hermes-skins` and `UI_Skins/hermes-skins-pack`
by declaring a winner; they are mutually exclusive. **USER DECISION POINT: which skin set
wins.** (3) Dynamic-workflows workflow skills via
`hermes-dynamic-workflows/scripts/install-hermes-workflows.py`. (4) token-optimizer via
`hermes_install.py` (corrected path from Phase 1, U4). (5) gepa-optimization from
`Self-Evolution/hermes-agent-self-evolution/_skills/gepa-optimization/`. (6)
`Takeoff-Lens-Plugin/skills/count-engineering-drawing-symbols`.

**Gate per skill:** appears in `hermes skills list`; `skill_view <name>` returns its body;
frontmatter parses (`name`/`description` present). If a skill is junctioned/symlinked, also
prove it is listed (U6) — `tools/skills_sync_client.py:176` skips `SKILL.md.is_symlink()` for
CLOUD sync enumeration only; local discovery of a directory junction is verified here, not
assumed. Evidence in `docs/install-evidence/skills/<name>.txt`.

## Phase 6: adaptation sub-plans for non-Hermes assets

One sub-plan per family. Every sub-plan has: a tool-mapping table (Claude -> Hermes),
frontmatter normalization, removal or stubbing of missing infrastructure, staging through
`fleet port` (so an unadapted skill is never installed live), and a validation test.

- **Superpowers (17 skills, verified)** — written for Claude Code. They reference `Agent`,
  `TodoWrite`, `model: inherit`, and sonnet subagents. Use
  `using-superpowers/references/*-tools.md` as the mapping pattern and write a
  `hermes-tools.md` reference: `Agent`/`Task` -> `delegate_task`, `TodoWrite` -> the todo
  tool, `Bash` -> `terminal`, `Read` -> `read_file`. The full set is: writing-plans,
  executing-plans, requesting-code-review, receiving-code-review,
  dispatching-parallel-agents, subagent-driven-development, finishing-a-development-branch,
  using-git-worktrees, systematic-debugging, test-driven-development,
  verification-before-completion, **multimodel-review, using-superpowers, writing-skills,
  brainstorming, carl, hygiene-audit** (the last three are itemized below as separate items).
  All 17 need a disposition row — none silent.
  - **Per-skill grep gate:** zero unmapped Claude tool names remain after the port.
  - **Smoke:** one representative skill (`writing-plans`) actually runs and produces output.
  - `using-git-worktrees`, `systematic-debugging`, `test-driven-development`,
    `verification-before-completion`, `writing-plans`, `executing-plans`,
    `requesting-code-review`, `receiving-code-review`, `dispatching-parallel-agents`,
    `subagent-driven-development`, `finishing-a-development-branch` all get the same mechanical
    port + grep gate.
- **hygiene-audit** — depends on `/pickup`, worklog, and keel infrastructure that do NOT exist
  in Hermes. **Recommend defer or exclude.** Put the decision to the operator rather than
  faking an adaptation. Do NOT enable it read-write by default; if adapted, it runs
  read-only / dry-run only.
- **brainstorming visual companion** — `server.cjs` plus `.sh` scripts need PowerShell or node
  equivalents, or are marked unsupported on Windows. Gate: it runs, or it is explicitly
  marked unsupported with reason.
- **carl** — bash `install.sh` and `smoke.sh` are a Windows problem. Port them to PowerShell or
  Python, or run under Git Bash. **Gate: `smoke` passes on this box.**
- **Improve** — `improve-extract.py` is 1833 lines and harness-specific. Check its assumptions
  (state.db path, claude/codex branches) against the Hermes session store, add a
  `--harness hermes` path if needed, and test against a fixture. Gate: it ingests a Hermes
  session fixture without error.
- **equity-research zip** (`skills/equity-research-skill-v3.0.0.zip`) — extract to a staging
  area, run its bundled tests (`tests/test_check_research_output.py`), normalize frontmatter,
  then install. **Gate: its tests pass and the skill lists.**
- **token-optimizer Claude-side skills** (`token-optimizer/skills/`: `fleet-auditor`,
  `resume-checkpoint`, `token-coach`, `token-dashboard`, `token-optimizer`) — same port +
  grep gate as Superpowers. The hermes plugin half is Phase 2.
- **CLI_delegates/sdd-run** — EXCLUDED (not installable; it is run evidence, not a skill or
  plugin). Recorded so the zero-unaccounted gate stays honest.

## Phase 7: end-to-end verification + rollback

1. Fresh session in each target profile.
2. Full inventory diff against the expected list — **zero unaccounted rows**.
3. `python -m fleet.cli status` reports zero drift.
4. Second `python -m fleet.cli sync` is a clean no-op (idempotent).
5. All test suites green (`pytest tests/`, `pytest RAG/tests/`, each repo's own tests).
6. Write `docs/install-evidence/final-endstate-evidence.md`, modeled on the existing
   `tests/2026-09-17-hermes-claude-code-install-plan.md` + `final-endstate-evidence.md`
   pattern.

**Rollback (recorded, not performed):** restore the Task 0 backups from
`$TEMP\hermes-install-backup-2026-10-03\` (created as real copies in a private location
outside the repo) and `hermes -p <profile> plugins disable <name>` per package.

## MoA execution map

Disjoint lanes, run in parallel once Phase 0 is done. Phase 1 (infrastructure + root
resolution) MUST complete before any live deployment.

| Lane | Owns (disjoint) |
|------|---------------|
| L0 infra | Task 0 evidence, Phase 1 corrections, `fleet.yaml`, `fleet.cmd`, root resolution. **This lane owns `fleet.yaml` and all config changes — the integrator.** |
| L1 skill-portability | Superpowers, carl, Improve, equity-research, dynamic-workflows skills, token-optimizer, gepa. |
| L2 RAG | brain-rag MCP-over-SSH wiring (new integration, needs operator approval + worker python path) + desktop pane verification (artifact exists locally) + `GRAPH_PATH` gate. Worker is out of scope (managed by its own kit). |
| L3 delegation/workflows | hermes-dynamic-workflows plugin, delegate-task-advanced, hermes-claude-code plugin. |
| L4 desktop/skins | hermes-fleet build + desktop, bubble-mode, agent-eyes desktop, skins winner. |
| L5 ancillary | texting-style, agent-eyes agent-plugin, example plugins, hud/hudui, Takeoff-Lens. |
| L6 integration review | cross-lane review: ownership collisions, config diff purity, idempotency, negative tests. |

**Shared-file coordination:** only L0 touches `fleet.yaml`, profile `config.yaml`, and
`fleet.cmd`. Lanes 1-5 stage their assets into owned destinations and hand back a manifest.
L6 owns the final inventory diff and the end-state evidence.

**Each lane returns:** changed files, exact commands, results, evidence paths, unresolved
blockers, and rollback instructions. A lane may not claim an install is done without its gate
passing.

## Pitfalls

- Never print `.env` values — redact as `[REDACTED]`.
- Windows junctions/symlinks: prove BOTH the sync enumeration and the local loader see a
  linked skill (Phase 5 gate, U6). Do not assume.
- Example plugins and hud/hudui UIs are **opt-in**, never auto-enabled.
- Values whose output was lost in earlier turns (esbuild presence, token-optimizer path,
  live profile names, runtime python) are marked "verify in Task 0" and must NOT be asserted.
- Placeholder `register(ctx): pass` tests and a successful filesystem copy are NOT operational
  proof — a tool must be listed in a fresh session and return sane output.
- Provider-dependent tests (hermes-claude-code needs the `claude` CLI; Takeoff-Lens needs its
  `.venv`) are conditional and recorded as unverified/BLOCKED when the prerequisite is absent.

## Coverage gate (definition of done)

Every inventory row is **INSTALLED+VALIDATED**, **ADAPTED+VALIDATED**, or
**BLOCKED(reason, resolution)** — no silent skips. No secret-bearing evidence on disk. No
unsupported edits to upstream checkouts (Self-Evolution must not modify its live upstream by
default). Rollback is reproducible from `docs/install-evidence/baseline/`.

## Acceptance checklist (per component)

- [ ] Manifest/frontmatter + dependency validation passes
- [ ] Registered/discovered in the intended profile
- [ ] Deterministic behavioral smoke test passes on a fixture
- [ ] Surface-specific verification (desktop pane / dashboard route / MCP handshake / tool call)
- [ ] Negative test (missing dep, no creds, invalid config, disabled, cross-profile leak)
- [ ] Restart/persistence survives; second sync is a no-op
- [ ] Uninstall/rollback path recorded and tested on a fixture

---

**Status: PLAN.** Nothing above is executed. No install, no test, no fix has occurred yet.
Every gate is a pass condition to be satisfied during execution, not evidence of completion.
