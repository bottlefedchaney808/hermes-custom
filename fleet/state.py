"""The read-only view of the fleet, shaped for a UI.

Both the CLI's ``status`` and the desktop plugin's ``/api/plugins/hermes-fleet``
backend render from this. One shape, one set of facts, no chance of the terminal
and the pane disagreeing about what is installed.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import sync
from .config_edit import read_enabled
from .manifest import Manifest, Profile, expand

HERMES_HOME = expand("~/.hermes")


def _dir_count(path: Path) -> int:
    try:
        return sum(1 for entry in path.iterdir() if entry.is_dir())
    except OSError:
        return 0


def _skill_count(skills_dir: Path) -> int:
    """Skills are either ``skills/<name>/SKILL.md`` or nested one category deep
    (``skills/development/<name>/SKILL.md``). Count the leaves, not the folders."""
    if not skills_dir.is_dir():
        return 0
    total = 0
    for entry in skills_dir.iterdir():
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        if (entry / "SKILL.md").is_file():
            total += 1
            continue
        try:
            total += sum(1 for sub in entry.iterdir() if sub.is_dir() and (sub / "SKILL.md").is_file())
        except OSError:
            pass
    return total


def _bytes(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def active_profile() -> str:
    """Which profile Hermes is currently pointed at (``~/.hermes/active_profile``)."""
    marker = HERMES_HOME / "active_profile"
    try:
        name = marker.read_text(encoding="utf-8").strip()
        return name or "default"
    except OSError:
        return "default"


def profile_facts(profile: Profile) -> Dict[str, Any]:
    """What this profile costs and carries, in numbers you can act on.

    ``prompt_snapshot_bytes`` is the one worth watching: it is the serialized
    skills prompt Hermes rebuilds for the model, and it is paid on every turn.
    Default sits around 62 KB and tiferet around 40 KB — the gap IS the tiering
    decision, made visible.
    """
    snapshot = profile.home / ".skills_prompt_snapshot.json"
    return {
        "name": profile.name,
        "home": str(profile.home),
        "role": profile.role,
        "exists": profile.home.is_dir(),
        "active": profile.name == active_profile(),
        "plugins_installed": _dir_count(profile.plugins_dir),
        "plugins_enabled": sorted(read_enabled(profile.config_path)),
        "skills": _skill_count(profile.skills_dir),
        "skins": len(list(profile.skins_dir.glob("*.yaml"))) if profile.skins_dir.is_dir() else 0,
        "prompt_snapshot_bytes": _bytes(snapshot),
    }


def _install_metadata(profile: Profile) -> Dict[str, Any]:
    """`hermes plugins install` records repo + revision here. Useful for telling
    an upstream install apart from a hand-copied folder."""
    path = profile.plugins_dir / ".install-metadata.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def snapshot(manifest: Manifest, *, include_plan: bool = True) -> Dict[str, Any]:
    """Everything the Fleet pane needs in one call."""
    plan = sync.plan(manifest) if include_plan else sync.Plan()

    by_package: Dict[str, List[Dict[str, Any]]] = {}
    for action in plan.actions:
        by_package.setdefault(action.package, []).append(action.as_dict())

    packages = []
    for pkg in manifest.packages:
        actions = by_package.get(pkg.name, [])
        worst = max((sync.SEVERITY.get(a["verdict"], 0) for a in actions), default=0)
        verdict = next(
            (v for v, s in sync.SEVERITY.items() if s == worst),
            sync.OK,
        )
        packages.append({
            "name": pkg.name,
            "summary": pkg.summary,
            "notes": pkg.notes,
            "source": str(pkg.source) if pkg.source else None,
            "upstream": pkg.upstream,
            "global": pkg.is_global,
            "profiles": pkg.profiles,
            "surfaces": [s.kind for s in pkg.surfaces],
            "verdict": verdict,
            "actions": actions,
        })

    profiles = []
    for profile in manifest.profiles.values():
        facts = profile_facts(profile)
        facts["install_metadata"] = sorted(_install_metadata(profile).keys())
        profiles.append(facts)

    return {
        "generated_at": _now(),
        "active_profile": active_profile(),
        "hermes_home": str(HERMES_HOME),
        "desktop_root": str(sync.DESKTOP_ROOT),
        "profiles": profiles,
        "packages": packages,
        "pending": len(plan.pending),
        "errors": plan.errors,
    }


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds")
