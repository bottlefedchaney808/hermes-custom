"""hermes-fleet — the agent half.

One tool, ``fleet_status``: what is installed across every profile and what has
drifted from ``fleet.yaml``. Read-only by design. Changing the fleet is a
deliberate act performed by a human at a terminal (``fleet sync --apply``) or
through the desktop pane's explicit buttons — never something an agent does
because a conversation drifted that way. Symlinking a package into three live
profiles is not a reversible edit, and an agent should not reach for it.

The full JSON is large (three profiles x every surface), so the tool summarizes
by default and only expands what you ask for.
"""

from __future__ import annotations

import json
from typing import Any, Dict

from ._repo import load_fleet

SCHEMA = {
    "type": "object",
    "properties": {
        "detail": {
            "type": "string",
            "enum": ["summary", "drift", "full"],
            "description": (
                "summary: per-profile counts and one line per package (default). "
                "drift: only the surfaces that do not match fleet.yaml. "
                "full: the complete JSON snapshot — large, ask for it explicitly."
            ),
            "default": "summary",
        },
        "package": {
            "type": "string",
            "description": "Limit the report to one package name from fleet.yaml.",
        },
    },
    "additionalProperties": False,
}

DESCRIPTION = (
    "Report what is installed across every Hermes profile (default, local, tiferet), "
    "which packages have drifted from the declared fleet.yaml, and what each profile "
    "costs in skills-prompt context. Read-only: it never installs, links, enables or "
    "removes anything."
)


def _summarize(snapshot: Dict[str, Any], package: str | None) -> Dict[str, Any]:
    packages = snapshot["packages"]
    if package:
        packages = [p for p in packages if p["name"] == package]
    return {
        "active_profile": snapshot["active_profile"],
        "profiles": [
            {
                "name": p["name"],
                "skills": p["skills"],
                "plugins": p["plugins_installed"],
                "skins": p["skins"],
                "prompt_snapshot_kb": round(p["prompt_snapshot_bytes"] / 1024, 1),
                "role": p["role"],
            }
            for p in snapshot["profiles"]
        ],
        "packages": [
            {
                "name": p["name"],
                "verdict": p["verdict"],
                "scope": "global" if p["global"] else p["profiles"],
                "summary": p["summary"],
            }
            for p in packages
        ],
        "pending": snapshot["pending"],
        "errors": snapshot["errors"],
    }


def _drift(snapshot: Dict[str, Any], package: str | None) -> Dict[str, Any]:
    rows = []
    for pkg in snapshot["packages"]:
        if package and pkg["name"] != package:
            continue
        for action in pkg["actions"]:
            if action["verdict"] == "ok":
                continue
            rows.append({
                "package": pkg["name"],
                "profile": action["profile"] or "global",
                "kind": action["kind"],
                "verdict": action["verdict"],
                "target": action["target"],
                "detail": action["detail"],
            })
    return {
        "drift": rows,
        "count": len(rows),
        "fix": "run `fleet sync --apply` in the hermes-custom checkout",
    }


class FleetStatus:
    name = "fleet_status"
    toolset = "system"
    emoji = "🛰️"
    schema = SCHEMA
    description = DESCRIPTION

    def __init__(self, ctx: Any) -> None:
        self._ctx = ctx

    def _config(self, key: str, fallback: Any) -> Any:
        getter = getattr(self._ctx, "get_config", None)
        if callable(getter):
            try:
                value = getter(key)
                if value not in (None, ""):
                    return value
            except Exception:
                pass
        return fallback

    def handle(self, detail: str = "summary", package: str | None = None) -> str:
        try:
            _, _, _manifest, state_mod, _sync = load_fleet(self._config("repo_root", "") or None)
            manifest = _manifest.load()
        except Exception as exc:
            return json.dumps({"error": str(exc)}, indent=2)

        include_plan = detail != "summary" or bool(self._config("include_plan", True))
        snapshot = state_mod.snapshot(manifest, include_plan=include_plan)

        if detail == "full":
            payload = snapshot
        elif detail == "drift":
            payload = _drift(snapshot, package)
        else:
            payload = _summarize(snapshot, package)
        return json.dumps(payload, indent=2)


def register(ctx) -> None:
    tool = FleetStatus(ctx)
    ctx.register_tool(
        name=tool.name,
        toolset=tool.toolset,
        schema=tool.schema,
        handler=tool.handle,
        check_fn=lambda: True,
        description=tool.description,
        emoji=tool.emoji,
    )
