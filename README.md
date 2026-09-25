# hermes-custom

Separate things live here, and they do not overlap:

| | What it is | Start at |
|---|---|---|
| **The fleet** | Declarative install management across all three Hermes profiles, plus the `hermes-fleet` UI. Everything in `fleet.yaml`, every vendored package, both skill trees. | **[FLEET.md](FLEET.md)** |
| **The brain** | `RAG/` — the obsidian-brain RAG plugin (hybrid BM25 + vector search over the vault and swept sessions), the `BrainRAG_Nightly` job, and `scripts/brain_mcp.py` which exposes it to Claude Code as MCP server `brain`. | **[RAG/HERMES.md](RAG/HERMES.md)** |
| **`local-model`** | `local_model.py` — status / unload / stop for the managed llama-server. | the file's docstring |
| **The wrapper CLI** | `my_cli.py` — a `HermesCLI` subclass that adds a sidebar to the CLASSIC CLI via its documented extension seams. Unrelated to the fleet. | the rest of this file |

## Third-party repos

These are cloned into this directory but are **not part of this repo** (see
`.gitignore`). Each keeps its own upstream. Re-clone into the same path:

| Path | Upstream |
|---|---|
| `CLI_delegates/hermes-claude-code/` | https://github.com/DevvGwardo/hermes-claude-code |
| `Example/hermes-example-plugins/` | https://github.com/NousResearch/hermes-example-plugins |
| `Self-Evolution/hermes-agent-self-evolution/` | https://github.com/NousResearch/hermes-agent-self-evolution |
| `Takeoff-Lens-Plugin/` | https://github.com/anekhirun/Takeoff-Lens-Plugin |
| `UI_Skins/hermes-skins-pack/` | https://github.com/bchop-studio/hermes-skins-pack |
| `delegate-task-advanced/` | https://github.com/kxlion/delegate-task-advanced |
| `hermes-bot-kit/` | https://github.com/thomasbek3/hermes-bot-kit |
| `hermes-dynamic-workflows/` | https://github.com/lingjiuu/hermes-dynamic-workflows |
| `hermes-hud/` | https://github.com/joeynyc/hermes-hud |
| `hermes-hudui/` | https://github.com/joeynyc/hermes-hudui |
| `hermes-skins/` | https://github.com/joeynyc/hermes-skins |
| `token-optimizer/` | https://github.com/alexgreensh/token-optimizer |

Local edits inside those clones are not backed up by this repo.

```bash
fleet status        # what is installed where, and what has drifted
fleet sync          # dry run
fleet sync --apply
```

---

`my_cli.py` is a **wrapper CLI**: it subclasses `HermesCLI` and overrides the
documented extension seams instead of editing upstream source.

It lives here, not in `C:\Users\bottl\dev\hermes-agent`, on purpose. Per that
repo's `local-tools/README.md`, anything a plugin, skill, hook, config key, or
env var can do should stay out of the patch series — a patch has to be rebased
on every update forever, this does not. A re-clone of Hermes never touches this
directory.

Run it with `hermes-custom.cmd` (which sets `PYTHONPATH` to the checkout and
uses its venv Python). Every upstream flag AND subcommand works unchanged — it
calls Hermes's real entry point (`hermes_cli.main:main`) and only swaps the class.

> **Do not "simplify" `main()` to `fire.Fire(cli.main)`.** Those are two
> different functions. `cli.main` is only the *chat* handler and its first
> positional parameter is `query`, so routing through it turns
> `hermes profile use local-agent` into a chat seeded with the word "profile"
> and silently deletes all ~40 subcommands. This was a real regression; the
> docstring in `my_cli.py::main` records the call chain that makes the class
> swap work without it.
>
> **Do not import `cli` before `hermes_cli.main`.** `cli.py` binds
> `CLI_CONFIG = load_cli_config()` at import time. Stock `hermes` applies
> `_apply_profile_override()` first so a sticky `active_profile` re-homes
> `HERMES_HOME` before that load. Import `cli` first and the prompt says
> `local-agent` while the model/skills stay default's (grok-4.6 on top of
> Qwen). `tests/test_cli_bootstrap.py` locks the order.

## ⚠️ This extends the CLASSIC CLI, not `hermes --tui`

Hermes has **two separate terminal interfaces**, and this only affects one:

| Command | What runs | Extend it with |
|---|---|---|
| `hermes`, `hermes --cli` | **Classic CLI** — Python, prompt_toolkit (`cli.py` + `hermes_cli/cli_tui_mixin.py`) | **these hooks** |
| `hermes --tui` | **Ink TUI** — a separate Node/TypeScript app (`ui-tui/dist/entry.js`, package `@hermes/ink`) | React/Ink components in `ui-tui/`; nothing here applies |

The hook names are misleading: `_get_extra_tui_widgets()` says "tui" but returns
**prompt_toolkit** widgets for the classic CLI. It has no effect on `hermes --tui`.

Which one you get, in precedence order (`hermes_cli/main_tui_launch.py::_resolve_use_tui`):

1. `--cli` → classic (always wins)
2. `--tui` → Ink TUI
3. not a TTY → classic (load-bearing: keeps piped `hermes chat -q`, kanban workers and cron working)
4. `HERMES_TUI=1` → Ink TUI
5. `display.interface: tui` in config.yaml → Ink TUI
6. otherwise → classic

So if you normally live in `hermes --tui`, run `hermes-custom.cmd --cli` to see
these widgets.

### The TUI port lives elsewhere

`hermes --tui` has its OWN widget SDK with the same update-safe contract (a
drop-in file outside the checkout, not a patch): a `<name>.mjs` in
`$HERMES_HOME/tui-widgets/` that default-exports `register(sdk)`.

This sidebar is ported there as **`~/.hermes/tui-widgets/sidebar.mjs`** —
`/sidebar` to toggle, `/sidebar note <text>`, `/sidebar clear`. Plain ESM, no
JSX (`sdk.h` is `React.createElement`), no build step; the TUI watches the
directory and hot-reloads on save. It uses `mode: 'ambient'` + `zone`, which
gives it the real right-hand placement the classic CLI structurally cannot do.

Two Hermes-specific gotchas that file documents, worth knowing before you write
another one:

- **`process.cwd()` is wrong.** `_launch_tui` spawns node with `cwd=ui-tui/`,
  so the bundle directory is the cwd. Use `process.env.HERMES_CWD`.
- **`$HERMES_HOME/config.yaml` is not always the active profile's.**
  HERMES_HOME may be the hermes root, whose config is *default's*. Follow
  `active_profile` first unless HERMES_HOME's parent is already `profiles` —
  the same stacked-profile trap the import-order rule above guards against.

## What the example does

A right-hand sidebar in the chrome band above the status bar (40 cols × 8 rows,
clamped so the composer keeps at least 40 columns). Classic CLI is not
full-screen — the transcript is stdout above the chrome — so this cannot sit
beside old chat lines. It reserves a right rail; the left of that band is empty.

```
                          │ ⬡  sidebar
                          │ dir    hermes-custom
                          │ branch —
                          │ model  grok-4.6
```

- **Ctrl-G** toggles it
- `/widget on` / `off` / bare `/widget` toggles it
- `/widget note <text>` appends a note to the panel

Layout constants live at the top of `my_cli.py` (`SIDEBAR_WIDTH`, `SIDEBAR_HEIGHT`).
Restart the CLI after changing them — this process already imported the module.

## The five seams

| Hook | Purpose | Used here |
|---|---|---|
| `_get_extra_tui_widgets()` | Inject widgets between the spacer and status bar | ✅ the sidebar |
| `_register_extra_tui_keybindings(kb, *, input_area)` | Add hotkeys | ✅ Ctrl-G |
| `process_command(command)` | Custom slash commands | ✅ `/widget` |
| `_build_tui_style_dict()` | prompt_toolkit styles | ✅ `mypanel.*` classes |
| `_build_tui_layout_children(**widgets)` | Reorder/wrap existing widgets | ✗ rare — only for full control of ordering |

## Rules worth keeping as you extend it

- **`_panel_fragments()` runs on the render path.** It repaints often, so never
  block in it — no subprocesses, network calls, or locks inline. `_GitBranch`
  is the worked example: it shells out at most once every 5s and caches.
- **Return `(style_class, text)` pairs**, and register every `class:` you use in
  `_build_tui_style_dict()` or it renders unstyled.
- **Always call `super()._build_tui_style_dict()` first** — it merges the base
  style, the active skin, and the light-terminal remap. Only add on top.
- **`process_command` must fall through**: handle what you own, then
  `return super().process_command(command)`. Returning `False` exits the REPL.
- **Visibility is a `ConditionalContainer`**, not a `Window(filter=…)` — `Window`
  takes no `filter` argument. Same shape the built-in status/voice bars use.
- Call `self._invalidate(min_interval=0.0)` after changing state so it repaints
  immediately rather than on the next natural render.

## If you move the checkout

`hermes-custom.cmd` has one line to update: `HERMES_CHECKOUT`.
