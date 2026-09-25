"""hermes-fleet backend — mounted at ``/api/plugins/hermes-fleet/``.

One backend, two front ends: the web dashboard tab fetches these routes
directly, and the desktop pane reaches the same routes through ``ctx.rest``
(which is namespaced to exactly this prefix). Neither can disagree with the
other about what is installed, because neither has its own copy of the truth.

Write safety
------------
Reading the fleet is free. CHANGING it is not: ``fleet sync --apply`` links
packages into three live agent homes, and ``toggle`` edits a hand-tuned
``config.yaml``. So every mutating route is dry-run by default and requires an
explicit ``confirm: true`` in the body to actually write. There is no route that
takes a path, a command, or a package not already declared in ``fleet.yaml`` —
the manifest is the allowlist.

This module is only imported when ``hermes-fleet`` is in ``plugins.enabled``
(see ``_mount_plugin_api_routes`` in hermes_cli/web_server_dashboard.py), which
is the gate that keeps an installed-but-off plugin's Python from running.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# The plugin package root is this file's grandparent (…/hermes-fleet/dashboard/).
_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

from _repo import load_fleet  # noqa: E402

router = APIRouter()

# Snapshots walk every surface in three profiles. Cheap, but not free, and both
# UIs poll — so hold the result briefly rather than re-walking per widget.
_CACHE_TTL = 4.0
_cache: Dict[str, Any] = {"at": 0.0, "value": None}


def _fleet():
    try:
        return load_fleet()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _snapshot(force: bool = False) -> Dict[str, Any]:
    now = time.monotonic()
    if not force and _cache["value"] is not None and now - _cache["at"] < _CACHE_TTL:
        return _cache["value"]
    _, why, manifest_mod, state_mod, _sync = _fleet()
    snapshot = state_mod.snapshot(manifest_mod.load())
    snapshot["repo_discovered_by"] = why
    _cache.update(at=now, value=snapshot)
    return snapshot


# ── read ────────────────────────────────────────────────────────────────────

@router.get("/state")
async def get_state(force: bool = False):
    """Everything both UIs render from: profiles, packages, verdicts, drift."""
    return _snapshot(force=force)


@router.get("/manifest")
async def get_manifest():
    """The declared intent, without touching the disk — useful for showing what
    SHOULD be true when the disk walk itself is what's failing."""
    _, _why, manifest_mod, _state, _sync = _fleet()
    manifest = manifest_mod.load()
    return {
        "profiles": {
            name: {"home": str(p.home), "role": p.role}
            for name, p in manifest.profiles.items()
        },
        "packages": [
            {
                "name": pkg.name,
                "summary": pkg.summary,
                "notes": pkg.notes,
                "profiles": pkg.profiles,
                "global": pkg.is_global,
                "surfaces": [s.kind for s in pkg.surfaces],
            }
            for pkg in manifest.packages
        ],
    }


@router.get("/signals")
async def get_signals():
    """Per-package live signals for the grid's widgets.

    Every probe degrades to ``{"available": false, "reason": ...}`` instead of
    raising, so one uninstalled package never blanks the whole dashboard.
    """
    snapshot = _snapshot()
    homes = [Path(p["home"]) for p in snapshot["profiles"] if p["exists"]]
    return {
        "brain_rag": _probe_brain_rag(homes),
        "dynamic_workflows": _probe_dir(homes, "plugin-data/dynamic-workflows", "dynamic-workflows"),
        "token_optimizer": _probe_dir(homes, "plugin-data/token-optimizer", "token-optimizer"),
        "sessions": _probe_sessions(homes),
        "desktop": _probe_desktop(),
    }


def _probe_brain_rag(homes: List[Path]) -> Dict[str, Any]:
    for home in homes:
        rag = home / "rag"
        if not rag.is_dir():
            continue
        files = [f for f in rag.rglob("*") if f.is_file()]
        if not files:
            continue
        newest = max(f.stat().st_mtime for f in files)
        return {
            "available": True,
            "home": str(home),
            "files": len(files),
            "bytes": sum(f.stat().st_size for f in files),
            "updated_at": newest,
            "age_hours": round((time.time() - newest) / 3600, 1),
        }
    return {"available": False, "reason": "no rag/ index found in any profile"}


def _probe_dir(homes: List[Path], relative: str, label: str) -> Dict[str, Any]:
    for home in homes:
        target = home / relative
        if not target.is_dir():
            continue
        entries = sorted(target.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
        return {
            "available": True,
            "home": str(home),
            "path": str(target),
            "entries": len(entries),
            "latest": entries[0].name if entries else None,
            "updated_at": entries[0].stat().st_mtime if entries else None,
        }
    return {"available": False, "reason": f"{label} has no plugin-data yet"}


def _probe_sessions(homes: List[Path]) -> Dict[str, Any]:
    out = {}
    for home in homes:
        sessions = home / "sessions"
        if sessions.is_dir():
            try:
                out[home.name] = sum(1 for _ in sessions.iterdir())
            except OSError:
                pass
    return {"available": bool(out), "counts": out}


def _probe_desktop() -> Dict[str, Any]:
    _, _why, _manifest, _state, sync_mod = _fleet()
    root = sync_mod.DESKTOP_ROOT
    if not root.is_dir():
        return {"available": False, "reason": f"{root} does not exist"}
    plugins = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        plugins.append({
            "name": entry.name,
            "has_entry": (entry / "plugin.js").is_file(),
            "unified": (entry / ".hermes-package.json").is_file(),
        })
    return {"available": True, "root": str(root), "plugins": plugins}


# ── write (guarded) ─────────────────────────────────────────────────────────

class SyncRequest(BaseModel):
    confirm: bool = False
    package: Optional[str] = None
    profile: Optional[str] = None


@router.post("/sync")
async def post_sync(body: SyncRequest):
    """Dry run unless ``confirm`` is true. `package`/`profile` must already be
    declared in fleet.yaml — the manifest is the allowlist, so there is no way
    to point this at an arbitrary path."""
    _, _why, manifest_mod, _state, sync_mod = _fleet()
    manifest = manifest_mod.load()

    if body.package:
        try:
            manifest.package(body.package)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    if body.profile and body.profile not in manifest.profiles:
        raise HTTPException(status_code=400, detail=f"unknown profile {body.profile!r}")

    if body.confirm:
        sync_mod.ensure_dirs(manifest)
    plan = sync_mod.plan(
        manifest,
        only=[body.package] if body.package else None,
        profiles=[body.profile] if body.profile else None,
    )
    if body.confirm:
        sync_mod.apply(plan, manifest=manifest)
        _cache["value"] = None  # the disk just changed; never serve the stale walk
    result = plan.as_dict()
    result["applied"] = body.confirm
    return result


class ToggleRequest(BaseModel):
    package: str
    on: bool
    confirm: bool = False


@router.post("/toggle")
async def post_toggle(body: ToggleRequest):
    """Add or remove a package's plugin ids in each target profile's
    ``plugins.enabled``. Dry run unless ``confirm``; every write is preceded by
    a timestamped backup of the config file."""
    _, _why, manifest_mod, _state, _sync = _fleet()
    manifest = manifest_mod.load()
    try:
        pkg = manifest.package(body.package)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    sys.path.insert(0, str(_PLUGIN_ROOT))
    from fleet.config_edit import set_enabled  # noqa: PLC0415

    results = []
    for surface in pkg.surfaces:
        if surface.kind != "agent-plugin":
            continue
        plugin_id = surface.install_as or (surface.from_ or pkg.name).split("/")[-1]
        for profile in manifest.targets(pkg):
            results.append({
                "profile": profile.name,
                "plugin": plugin_id,
                "result": set_enabled(profile.config_path, plugin_id, on=body.on, apply=body.confirm),
            })
    # Surfaces sync is deliberately withholding. The config switch does NOT
    # release these — skills have no allow-list, so installing one IS loading
    # it. Returning them keeps the UI honest: without this, a "enable" action
    # button would report success while 72 skills stayed on disk in this repo.
    held = [
        {"kind": s.kind, "from": s.from_ or "."}
        for s in pkg.surfaces
        if s.enable == "staged" and s.kind != "agent-plugin"
    ]

    if body.confirm:
        _cache["value"] = None
    return {
        "applied": body.confirm,
        "results": results,
        "withheld": held,
        "withheld_note": (
            "Skills have no enable gate. To commit these, change `enable: staged` "
            "to `enable: true` for this package in fleet.yaml and re-sync."
        ) if held else None,
        "next": "restart the gateway for this to take effect: hermes gateway restart",
    }


@router.get("/health")
async def health():
    root, why, _m, _s, _sy = _fleet()
    return {"ok": True, "repo": str(root), "discovered_by": why, "pid": os.getpid()}
