#!/usr/bin/env python3
"""my_cli.py — a wrapper CLI that extends Hermes with custom widgets.

This lives OUTSIDE the hermes-agent checkout on purpose. It subclasses the
public extension seams instead of editing upstream source, so `hermes update`
can never conflict with it and a re-clone never loses it. See
local-tools/README.md: "Before adding a patch, check whether a plugin, skill,
hook, config key, or HERMES_* env var can do it instead."

It demonstrates four of the five documented seams on HermesCLI:

  _get_extra_tui_widgets()          -> a right sidebar above the status bar
  _register_extra_tui_keybindings() -> Ctrl-G toggles it
  process_command()                 -> /widget slash command
  _build_tui_style_dict()           -> colors for the panel

The fifth, _build_tui_layout_children(), is for reordering existing widgets and
is rarely needed — extra widgets are inserted for you, between the spacer and
the status bar.

IMPORTANT: these hooks are prompt_toolkit, so they apply to the CLASSIC CLI
(`hermes` / `hermes --cli`). They do NOT apply to `hermes --tui`, which is a
separate Ink/Node app (ui-tui/dist/entry.js). See README.md here.

The classic CLI is not full-screen: the transcript is stdout above the chrome.
A real "beside the chat" rail is impossible here. This sidebar is a right-hand
column in the chrome band above the status bar (empty on the left).

Run it with:   hermes-custom.cmd          (Windows)
               ./hermes-custom.sh         (bash)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

from prompt_toolkit.filters import Condition
from prompt_toolkit.layout import ConditionalContainer, FormattedTextControl, VSplit, Window

# Profile override MUST run before `import cli`. cli.py binds CLI_CONFIG at
# import time from HERMES_HOME. Stock `hermes` does this in hermes_cli.main
# (module-level `_apply_profile_override()`) before importing cli. Importing
# cli first is the stacked-profile bug: sticky `hermes profile use local-agent`
# paints the local-agent prompt while default's model/skills stay loaded.
from hermes_cli.main import main as hermes_main
from cli import HermesCLI


# ── the data your panel shows ────────────────────────────────────────────────
# Kept deliberately cheap: _fragments() runs on prompt_toolkit's render path,
# which repaints often. Anything that can block (a subprocess, a network call,
# a lock) must be cached, never called inline. The git branch below is the
# worked example — it shells out at most once every GIT_TTL seconds.

GIT_TTL = 5.0
SIDEBAR_WIDTH = 40
SIDEBAR_HEIGHT = 8
# Leave this many columns for the composer / transcript chrome on the left.
SIDEBAR_LEFT_MIN = 40


class _GitBranch:
    """Cheap, cached `git branch --show-current` for the panel."""

    def __init__(self) -> None:
        self._value = ""
        self._checked_at = 0.0

    def get(self) -> str:
        now = time.monotonic()
        if now - self._checked_at < GIT_TTL:
            return self._value
        self._checked_at = now
        try:
            out = subprocess.run(
                ["git", "branch", "--show-current"],
                capture_output=True, text=True, timeout=1.0,
                cwd=os.getcwd(),
            )
            self._value = out.stdout.strip() if out.returncode == 0 else ""
        except Exception:
            # Never let the panel break the REPL — a missing git, a non-repo
            # cwd, or a slow filesystem all just mean "no branch".
            self._value = ""
        return self._value


class MyCLI(HermesCLI):
    """Hermes with a right-hand status sidebar."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._panel_visible = True
        self._git = _GitBranch()
        self._panel_note = ""

    def _sidebar_width(self) -> int:
        try:
            cols = shutil.get_terminal_size((80, 24)).columns
        except Exception:
            cols = 80
        return max(28, min(SIDEBAR_WIDTH, cols - SIDEBAR_LEFT_MIN))

    def _sidebar_height(self) -> int:
        return SIDEBAR_HEIGHT

    # ── seam 1: the widget ───────────────────────────────────────────────────
    def _get_extra_tui_widgets(self) -> list:
        """Right rail inserted between the spacer and the status bar."""
        # Visibility is a ConditionalContainer wrapping the VSplit — Window
        # itself takes no `filter`. Same shape as the built-in status/voice bars
        # (cli_tui_mixin._tui_build_layout): toggle costs nothing and needs no
        # layout rebuild. Height is on every child so the HSplit reserves rows.
        height = self._sidebar_height
        width = self._sidebar_width
        return [
            ConditionalContainer(
                VSplit(
                    [
                        Window(height=height),
                        Window(
                            width=1,
                            height=height,
                            char="│",
                            style="class:mypanel.sep",
                            dont_extend_width=True,
                        ),
                        Window(
                            content=FormattedTextControl(self._panel_fragments),
                            width=width,
                            height=height,
                            wrap_lines=True,
                            dont_extend_width=True,
                            style="class:mypanel",
                        ),
                    ],
                    padding=0,
                ),
                filter=Condition(lambda: self._panel_visible),
            )
        ]

    def _clip(self, text: str) -> str:
        budget = max(8, self._sidebar_width() - 10)
        text = (text or "").replace("\n", " ")
        if len(text) <= budget:
            return text
        return text[: budget - 1] + "…"

    def _kv(self, key: str, value: str) -> list:
        return [
            ("class:mypanel.key", f" {key:<7}"),
            ("class:mypanel.value", f"{self._clip(value)}\n"),
        ]

    def _panel_fragments(self):
        """prompt_toolkit fragments — (style_class, text) pairs."""
        cwd = Path(os.getcwd()).name or os.getcwd()
        branch = self._git.get() or "—"
        model = str(getattr(self, "model", "?") or "?")

        fragments = [
            ("class:mypanel.label", " ⬡  "),
            ("class:mypanel.value", "sidebar\n"),
        ]
        fragments += self._kv("dir", cwd)
        fragments += self._kv("branch", branch)
        fragments += self._kv("model", model)
        if self._panel_note:
            fragments += self._kv("note", self._panel_note)
        return fragments

    # ── seam 2: the keybinding ───────────────────────────────────────────────
    def _register_extra_tui_keybindings(self, kb, *, input_area) -> None:
        """`kb` is the KeyBindings object; `input_area` is the main TextArea."""

        @kb.add("c-g")
        def _toggle_panel(event) -> None:
            self._panel_visible = not self._panel_visible
            # Repaint now rather than waiting for the next natural render.
            self._invalidate(min_interval=0.0)

    # ── seam 3: a slash command ──────────────────────────────────────────────
    def process_command(self, command: str) -> bool:
        """Return False to exit the REPL. Handle yours, then defer to Hermes."""
        word = command.lower().strip().split()[0].lstrip("/") if command.strip() else ""

        if word == "widget":
            arg = command.strip()[len("/widget"):].strip()
            if arg in {"on", "show"}:
                self._panel_visible = True
            elif arg in {"off", "hide"}:
                self._panel_visible = False
            elif arg.startswith("note"):
                self._panel_note = arg[len("note"):].strip()
            else:
                self._panel_visible = not self._panel_visible
            self._invalidate(min_interval=0.0)
            return True  # stay in the REPL

        # Anything we don't own goes to Hermes unchanged.
        return super().process_command(command)

    # ── seam 4: styling ──────────────────────────────────────────────────────
    def _build_tui_style_dict(self) -> dict[str, str]:
        """Layer our classes over the active skin's style.

        super() already merges the base TUI style, the skin overrides, and the
        light-mode remap, so start from it and only add. Note the remap skips
        any style that paints its own `bg:` — ours don't on the text classes,
        so they stay readable on a light terminal. The rail itself does set a
        dark bg so the column reads as a card against empty chrome.
        """
        style = super()._build_tui_style_dict()
        style.update({
            "mypanel": "bg:#141126",
            "mypanel.label": "#b48cff bold",
            "mypanel.key": "#6f6a8a",
            "mypanel.value": "#ece9f7 bold",
            "mypanel.sep": "#2a2440",
            "mypanel.note": "#3dffb4 italic",
        })
        return style


def main() -> None:
    """Delegate to Hermes's REAL entry point; only swap the class.

    `hermes` is `hermes_cli.main:main` (pyproject [project.scripts]) — an
    argparse CLI with ~40 subcommands. `cli.main` is a DIFFERENT function: the
    chat handler, whose first positional parameter is `query`.

    An earlier version of this file ran `fire.Fire(cli.main)`. That silently
    replaced the entire command surface with chat, so `hermes profile use
    local-agent` parsed as query="profile", q="use", oneshot="local-agent" and
    seeded a chat instead of switching profiles. Do not reintroduce it.

    Rebinding the class is still all that is needed to get our widgets:

        hermes_cli.main.main()      argparse dispatch, all subcommands
          -> cmd_chat(args)         (main.py:1667)
          -> from cli import main   (main.py:1730) — lazy, so it sees our rebind
          -> _build_cli_from_args   (cli.py:4505)
          -> HermesCLI(...)         (cli.py:4245) — module-global, resolved at
                                    call time, which is why this works

    So: every upstream subcommand and flag behaves exactly as documented, and
    an interactive classic-CLI chat gets MyCLI.

    Import order is load-bearing: `hermes_cli.main` is imported at module
    level *before* `cli`, so sticky `active_profile` re-homes HERMES_HOME
    before `CLI_CONFIG = load_cli_config()`.
    """
    import cli as hermes_cli_module

    hermes_cli_module.HermesCLI = MyCLI
    hermes_main()


if __name__ == "__main__":
    main()
