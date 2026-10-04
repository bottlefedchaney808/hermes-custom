# hermes-custom — Scope & Spec
#
# STATUS: SUPERSEDED (2026-10-03). This document's inventory assumptions were
# found unreliable during install execution — several items were mis-scoped
# (e.g. hermes-hud/hudui are pip/browser apps, not plugins; skill-fuse does not
# exist; the canonical Hermes root is %LOCALAPPDATA%\hermes, not ~/.hermes).
# See docs/install-evidence/baseline/preflight.txt for the verified facts.
# Retained for provenance, not to be relied on.
#
Date: 2026-10-03 · Status: scope baseline for MoA planning
Repo: `C:\Users\bottl\hermes-custom` · branch `master` · 38 commits

---

## 0. The one-paragraph scope

`hermes-custom` is **not a single application**. It is a meta-repo / control plane that
declares, installs, syncs, and documents the whole Hermes environment on this machine:

- **What** gets installed **where** (4 profiles), enforced by a declarative manifest.
- A **retrieval layer** (RAG) over the Obsidian vault + swept agent sessions.
- A **wrapper CLI** that extends the classic Hermes CLI without patching upstream.
- A **local-model manager** for the on-GPU `llama-server`.
- A **desktop/web UI** that renders all of the above and exposes an open widget registry.

Everything is first-party, drop-in, and update-safe by construction: nothing here edits
the upstream `hermes-agent` checkout, so a re-clone of Hermes never touches this repo and
recovery is one command. **The upstream `hermes-agent` source and the ~11 cloned
third-party repos are explicitly out of scope** (see §7).

First-party code ≈ **5,527 LOC Python + 1,557 LOC TS/TSX**. First-party tests ≈ 25 files.

---

## 1. Scope boundary — what is IN and OUT

| IN scope (first-party, owned by this repo) | OUT of scope (do not plan here) |
|---|---|
| `fleet/` engine + `fleet.yaml` manifest | Upstream `hermes-agent` source tree (`C:\Users\bottl\dev\hermes-agent`) |
| `hermes-fleet/` UI (agent plugin + desktop pane + widget grid) | The 11 cloned third-party repos (`.gitignore`d; each keeps its own upstream — see README table) |
| `RAG/` — brain_rag lib, plugin, scripts, tests, MCP bridge | `C:\Users\bottl\obsidian-vault` (the data, cloned separately) |
| `local_model.py` + `local-model.cmd` | Hermes core runtime, Mem0, Nous Portal |
| `my_cli.py` + `hermes-custom.cmd/.ps1` | Installed-plugin runtime state under `~/.hermes/**` (fleet *manages* it but doesn't own the code) |
| `skills/claude` + `skills/hermes` (the hermes-fleet skill pair) | `~/.hermes/tui-widgets/sidebar.mjs` (the TUI port — lives in `$HERMES_HOME`, not this repo) |
| `tests/` (fleet + cli-bootstrap tests) | `Example/`, `Self-Evolution/`, `hermes-bot-kit/`, etc. (reference clones) |

**The invariant that defines the whole repo:** drop-in, never-a-patch. Anything a
plugin / skill / hook / config key / env var can do stays here as an extension seam, so a
re-clone of Hermes is a one-command recovery and `git log` is the audit trail.

---

## 2. The managed target: four Hermes profiles

Hermes resolves plugins/skills/skins from exactly one place per profile
(`get_hermes_home()/plugins`, no shared path). `hermes-custom` is the single source of
truth that makes four physical trees agree.

| Profile | home | role | gets the lab? |
|---|---|---|---|
| `default` | `~/.hermes` | daily driver | ✅ |
| `jason` | `~/.hermes/profiles/jason` | personal (replaced `local`, 2026-09); shares memory brain with default | ✅ |
| `tiferet` | `~/.hermes/profiles/tiferet` | **construction only, company-facing** — deliberately narrow, customers talk to it | ❌ |
| `gork` | `~/.hermes/profiles/gork` | Grok generalist, lab-adjacent; gets agent-eyes so the human can see what it looks at | ✅ (agent-eyes) |

**Desktop plugins are GLOBAL** (`~/.hermes/desktop-plugins/`), installed once, never per
profile — the app migrates them out of profile folders. This is a load-bearing rule.

---

## 3. Component inventory (first-party)

### 3a. The fleet — declarative install manager  · `fleet/` (≈2450 LOC) + `fleet.yaml`
**Purpose:** make the disk match `fleet.yaml`. Nothing is installed by hand.

- **Engine modules:** `cli.py`, `sync.py`, `port.py`, `manifest.py`, `env_sync.py`,
  `config_edit.py`, `docs.py`, `links.py`, `state.py`.
- **Manifest:** `fleet.yaml` — profiles, defaults, and a `packages:` section (~13 distinct
  third-party sources + the hermes-fleet RAG/skills entries).
- **Verdicts:** `ok / NEW / LINK / CONV / SYNC / HELD / MISS / man`.
- **Install modes:** `link` (default, git is audit trail), `copy` (package writes to
  itself), `external` (owns its own installer — e.g. token-optimizer).
- **`skills/claude → skills/hermes`** is **generated** by `fleet port` (do not hand-edit
  the hermes tree).
- **Commands:** `status` · `sync [--apply] [-p profile] [-k package]` · `enable/disable`
  `port` · `docs` · `json`. **Everything dry-runs by default.**
- **Guarantees:** idempotent · dry-run by default · manifest is the allowlist (no command
  takes an arbitrary path/shell/unlisted package) · backups before every config write ·
  does **not** manage upstream `hermes plugins install` · does **not** register MCP servers.

### 3b. hermes-fleet — the UI  · `hermes-fleet/` (≈1557 LOC TS/TSX)
**Purpose:** render the fleet as a pane. An **open widget grid** (drag/resize/swap/trash,
themed off `--home-accent`) with a **public widget registry** other plugins register into;
the package×profile matrix, live drift vs `fleet.yaml`, per-profile context budget.

- **Unified package:** agent half (`plugin.yaml` + `plugin_api.py`) installs per profile;
  desktop half (`desktop/plugin.js`) the app copies out to the global root on mtime change.
- **Built artifact** is what the app watches (`ui-src/` changes need a rebuild).
- `ui-src/`: `plugin.tsx`, `grid.tsx`, `widgets.tsx`, `api.ts`, `registry.ts`, `css.ts`,
  `dashboard.tsx`.

### 3c. The brain — RAG over Obsidian + sessions  · `RAG/` (≈1398 LOC src)
**Purpose:** cited-snippet retrieval over the Obsidian vault and swept Hermes sessions.
Local-first, hybrid **BM25 (FTS5) + vector (sqlite-vec)**, merged with reciprocal rank
fusion. "What did I know, when, why, and how did it change?" — the vault is the memory.

- **Library** `src/brain_rag/`: `chunk.py`, `embed.py`, `index.py`, `search.py`,
  `store.py`, `redact.py`, `spill.py`, `sweep.py`, `leg.py`, `remind.py`.
- **Surfaces (unified plugin `brain-rag`):** agent tools `rag_search` / `rag_index`,
  `dashboard/plugin_api.py` (`/api/plugins/brain-rag/{search,index,status}`),
  `desktop/plugin.js`.
- **Memory model (2 layers, no holographic provider):** built-in MEMORY.md/USER.md
  (always-in-context, shared default+jason via junction) + this brain (searched on demand).
  Brains: `shared` = `~/.hermes/rag` (default+jason); `tiferet` = own index, restricted by
  `rag/legs.txt` to Construction, never indexes `Sessions/`. Vault `.ragignore` /
  `private: true` keeps a note out of **every** brain.
- **Upkeep:** Task Scheduler `BrainRAG_Nightly` (03:30) → `scripts/nightly.py` =
  (1) spill MEMORY/USER over 70% to vault `Memory/`, (2) sweep ended sessions >7d to
  `<Leg>/Sessions/` with secrets redacted, (3) incremental re-index. Log: `rag/nightly.log`.
  Query embeddings time out at 5 s → BM25-only; embeddings cached.
- **MCP bridge:** `scripts/brain_mcp.py` exposes the brain to Claude Code as MCP server
  `brain`.
- **Non-goals (v1):** no fine-tuning, no Qdrant/graph/reranker, no coach/timeline
  products, no replacing Mem0, no patching hermes core, no local embedding models, agents
  never write vault legs directly.

### 3d. local-model — managed llama-server  · `local_model.py` (≈281 LOC) + `local-model.cmd`
**Purpose:** status / unload / stop for the on-GPU `llama-server`. Thin control shim, not
an inference engine.

### 3e. Wrapper CLI — extends the CLASSIC CLI  · `my_cli.py` (≈265 LOC) + `hermes-custom.cmd/.ps1`
**Purpose:** a `HermesCLI` subclass that adds a right-hand sidebar to the classic CLI via
its documented extension seams — no upstream edits. All upstream flags/subcommands work
unchanged (calls `hermes_cli.main:main`, swaps only the class).

- **The five seams:** `_get_extra_tui_widgets()` (the sidebar),
  `_register_extra_tui_keybindings()` (Ctrl-G), `process_command()` (`/widget`),
  `_build_tui_style_dict()` (`mypanel.*`), `_build_tui_layout_children()` (unused).
- **Out of scope of this component:** `hermes --tui` (Ink/React) — the TUI port lives in
  `~/.hermes/tui-widgets/sidebar.mjs`, not here.

### 3f. Skills trees  · `skills/claude/`, `skills/hermes/`
- `skills/claude/hermes-fleet` ↔ `skills/hermes/hermes-fleet` — the Claude↔Hermes twin
  pair, hermes side **generated by `fleet port`**.
- `skills/Superpowers/` — 17 skills (brainstorming, carl, dispatching-parallel-agents,
  executing-plans, systematic-debugging, TDD, writing-plans, writing-skills, …) —
  the working methodology for this repo's own development.

### 3g. Tests  · `tests/`
First-party test files: `test_fleet.py`, `test_fleet_env.py`, `test_cli_bootstrap.py`
(+ the 22 RAG test files under `RAG/tests/`). `test_cli_bootstrap.py` locks the
import-order rule in `my_cli.py`.

---

## 4. Dependency map

```
            fleet.yaml  (single source of truth)
                 │  fleet sync --apply
                 ▼
   ┌─────────────┴──────────────┐   (link / copy / external)
   ▼            ▼              ▼
 default     jason          tiferet   gork     ← 4 profile trees
   │            │              │
   └── shared memory brain (~/.hermes/rag, junction) ──┘   (default+jason)
                         │
        hermes-fleet UI  ◄── reads `fleet json` (whole state, machine-readable)
        (agent pane + desktop grid; open widget registry)

   RAG/brain_rag  ◄── vault (obsidian-vault, separate clone) + swept sessions
        │  nightly.py: spill → sweep → re-index   (Task Scheduler, 03:30)
        └─► scripts/brain_mcp.py  ──► Claude Code as MCP `brain`

   local_model.py  ◄── managed llama-server (on-GPU)
   my_cli.py       ◄── hermes_cli (upstream, not edited)
```

External (NOT owned here): `obsidian-vault` (data), Nous Portal `/v1/embeddings`,
upstream `hermes-agent`, Mem0.

---

## 5. Risks & gotchas (documented, load-bearing)

1. **Import order in `my_cli.py`:** never import `cli` before `hermes_cli.main`.
   `cli.py` binds `CLI_CONFIG = load_cli_config()` at import time; stock `hermes`
   applies `_apply_profile_override()` first to re-home `HERMES_HOME`. Importing `cli`
   first makes the prompt say `local-agent` while model/skills stay default's.
   `tests/test_cli_bootstrap.py` locks this.
2. **Do not "simplify" `main()` to `fire.Fire(cli.main)`.** `cli.main` is only the chat
   handler (first arg `query`) — that would turn `hermes profile use X` into a chat seeded
   with "profile" and silently delete ~40 subcommands. Real regression, recorded in the
   docstring.
3. **Desktop plugins are global, never per profile.** The app migrates them out of profile
   folders. Never install one into a profile.
4. **Skills are `copy`, plugins are `link`.** Hermes skill sync skips symlinked SKILL.md,
   so links ping-pong between profiles.
5. **Dry-run everywhere; manifest is the allowlist.** No command takes an arbitrary path,
   shell command, or unlisted package. Backups before every config write.
6. **Staged ≠ inert for skills.** A skill that exists is loaded and serialized into the
   prompt every turn — a staged skill is *withheld* (`HELD`), not installed.
7. **Fail-closed retrieval.** Embeddings down → BM25-only (tagged); vault pull failed → do
   not index; corrupt SQLite → refuse, don't wipe; no hits → `{hits: []}`, never invent.
8. **Leg boundaries.** `tiferet` indexes Construction only, never `Sessions/`; `.ragignore`
   / `private:true` excludes from every brain. Wrong-leg leak = eval gate **fail**.
9. **`process_command` must fall through** to `super()`, or returning `False` exits the REPL.
   `_panel_fragments()` runs on the render path — never block in it (subprocess/network).
10. **Rebuild to change the UI.** The app watches the built artifact's mtime, not `ui-src/`.

---

## 6. Open questions for MoA planning

1. **What is the actual task?** Scope above is the *system*; the spec is incomplete until
   the change is named. (New package to add? RAG feature? fleet bug? new profile?)
2. **`gork` tiering** — fleet.yaml notes `agent-eyes` was just added to gork; confirm the
   intended lab tier for gork is stable before planning around it.
3. **Vault clone path** `C:\Users\bottl\obsidian-vault` is a planning dependency for any
   RAG change — confirm it exists / is current, and that the `obsidian-brain` remote is
   reachable.
4. **Embedding model pin** — design says "pin model id from live catalog at implement
   time." Confirm the pinned Nous Portal embedding model before any embedding work.
5. **`skills/Superpowers/carl`** has `adapters/`, `bin/`, `commands/`, `examples/`,
   `tests/` — is carl first-party here or a reference? Not listed in the README third-party
   table. (Likely first-party, unconfirmed.)
6. **Eval-gate scope** — the golden-set eval runs against the real vault clone local-only,
   not CI. If the plan touches retrieval quality, confirm the eval gate is green first
   (it is a ship blocker).
7. **`hermes-custom.ps1` vs `.cmd`** — both wrap the CLI; confirm which is canonical for
   automation (`.cmd` sets PYTHONPATH + venv Python; `.ps1` is the 86-line variant).

---

*Generated by scope pass. First-party LOC, file lists, git state, profile tiering, and the
RAG design are from direct inspection of the repo (README, FLEET.md, RAG/HERMES.md,
fleet.yaml, RAG design spec, per-module file enumeration).*
