"""Plan and apply the manifest against the disk.

Everything is a two-step: :func:`plan` computes what SHOULD change and touches
nothing, :func:`apply` executes a plan. The CLI dry-runs by default, so the
destructive path is always something you asked for twice.

Idempotence is the contract. Running sync twice in a row must produce an
all-``ok`` plan the second time; if it doesn't, that's a bug in here, not a
quirk to work around.
"""

from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional

from . import links
from .manifest import Manifest, Package, Profile, Surface, expand

# Desktop plugins are GLOBAL — see the note at the top of fleet.yaml and
# apps/desktop/electron/desktop-plugins-root.ts. Never per profile.
DESKTOP_ROOT = expand("~/.hermes/desktop-plugins")

# Verdicts, ordered by how much they should worry you.
OK = "ok"              # disk already matches the manifest
CREATE = "create"      # missing; will be materialized
RELINK = "relink"      # a link pointing somewhere else
CONVERT = "convert"    # a real copy where the manifest wants a link (drift risk)
REFRESH = "refresh"    # mirror/copy contents differ
MANUAL = "manual"      # needs a human or another tool; reported, never touched
MISSING = "missing"    # upstream-managed and absent — we don't install it
STAGED = "staged"      # deliberately withheld until someone opts in
SEVERITY = {OK: 0, STAGED: 1, MANUAL: 2, MISSING: 3, REFRESH: 4, CONVERT: 5, RELINK: 6, CREATE: 7}

# `enable: staged` means different things per surface, and conflating them is a
# trap. A PLUGIN stages honestly: materialize it, leave it out of
# `plugins.enabled`, and it sits there inert until one switch flips.
#
# A SKILL does not work that way. There is no allow-list for skills — a skill
# directory that exists is a skill that is loaded and serialized into the skills
# prompt on every turn. So "install LifeOS's 73 skills but don't roll them in
# yet" cannot be honoured by installing them. Staging a skill surface means NOT
# materializing it at all, and saying so.
_STAGEABLE_IN_PLACE = {"agent-plugin"}


@dataclass
class Action:
    """One surface, in one place, and what it needs."""

    package: str
    kind: str
    profile: Optional[str]     # None for global surfaces
    source: Optional[Path]
    target: Path
    verdict: str
    detail: str = ""
    mode: str = "link"
    applied: Optional[str] = None

    @property
    def needs_work(self) -> bool:
        return self.verdict not in (OK, MANUAL, MISSING, STAGED)

    def as_dict(self) -> dict:
        return {
            "package": self.package,
            "kind": self.kind,
            "profile": self.profile,
            "source": str(self.source) if self.source else None,
            "target": str(self.target),
            "verdict": self.verdict,
            "detail": self.detail,
            "mode": self.mode,
            "applied": self.applied,
        }


@dataclass
class Plan:
    actions: List[Action] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def pending(self) -> List[Action]:
        return [a for a in self.actions if a.needs_work]

    def as_dict(self) -> dict:
        return {
            "actions": [a.as_dict() for a in self.actions],
            "errors": list(self.errors),
            "pending": len(self.pending),
            "total": len(self.actions),
        }


# ── path resolution ─────────────────────────────────────────────────────────

def _payload(pkg: Package, surface: Surface) -> Optional[Path]:
    """Where a surface's content lives in THIS repo."""
    if pkg.source is None:
        return None
    return pkg.source / surface.from_ if surface.from_ else pkg.source


def _skill_dirs(root: Path) -> List[Path]:
    """Every directory under `root` that is itself a skill (holds SKILL.md)."""
    if not root.is_dir():
        return []
    if (root / "SKILL.md").is_file():
        return [root]
    return sorted(d for d in root.iterdir() if d.is_dir() and (d / "SKILL.md").is_file())


def _mode(surface: Surface, manifest: Manifest) -> str:
    return surface.mode or manifest.default_mode


# ── planning one surface ────────────────────────────────────────────────────

def _plan_tree(
    pkg: Package, surface: Surface, src: Path, dst: Path, profile: Optional[str], mode: str
) -> Action:
    """A surface materialized as one directory (plugin, skill, desktop plugin)."""
    action = Action(
        package=pkg.name, kind=surface.kind, profile=profile,
        source=src, target=dst, verdict=OK, mode=mode,
    )
    state = links.inspect(dst)

    if state.kind == "absent":
        action.verdict = CREATE
        action.detail = "not installed"
        return action

    if mode == "copy":
        action.verdict = OK if state.kind == "copy" else RELINK
        action.detail = "" if state.kind == "copy" else f"want a copy, found a {state.kind}"
        return action

    if state.is_link:
        try:
            same = state.target is not None and state.target.resolve() == src.resolve()
        except OSError:
            same = False
        if same:
            action.detail = state.kind
            return action
        action.verdict = RELINK
        action.detail = f"{state.kind} -> {state.target}"
        return action

    action.verdict = CONVERT
    action.detail = "real copy where the manifest wants a link"
    return action


def _plan_surface(manifest: Manifest, pkg: Package, surface: Surface, plan: Plan) -> None:
    kind = surface.kind
    mode = _mode(surface, manifest)
    src = _payload(pkg, surface)

    # A staged NON-plugin surface is withheld, not installed. See _STAGEABLE_IN_PLACE.
    if surface.enable == "staged" and kind not in _STAGEABLE_IN_PLACE:
        targets = manifest.targets(pkg) if surface.per_profile else []
        count = len(_skill_dirs(src)) if src and kind in ("skill", "skill-pack") else 1
        for profile in targets or [None]:
            plan.actions.append(Action(
                package=pkg.name, kind=kind,
                profile=profile.name if profile else None,
                source=src,
                target=(profile.skills_dir if profile else Path(pkg.name)),
                verdict=STAGED, mode="withheld",
                detail=(
                    f"{count} item(s) withheld — skills have no enable gate, so "
                    f"installing them IS loading them. `fleet enable {pkg.name}` to commit."
                ),
            ))
        return

    if kind == "external":
        # A package that owns its own installer. We never materialize it — but
        # when it says WHERE it lands (`install_as`), we can still report per
        # profile whether it actually got there, so the matrix stays honest
        # instead of showing a blank row for something that is half-installed.
        if surface.install_as:
            for profile in manifest.targets(pkg):
                target = profile.plugins_dir / surface.install_as
                present = links.inspect(target).kind != "absent"
                plan.actions.append(Action(
                    package=pkg.name, kind=kind, profile=profile.name, source=src,
                    target=target, verdict=OK if present else MISSING, mode="external",
                    detail="installed" if present else f"run its own installer: {surface.deploy}",
                ))
            return
        plan.actions.append(Action(
            package=pkg.name, kind=kind, profile=None, source=src,
            target=Path(str(src or pkg.name)), verdict=MANUAL, mode="n/a",
            detail=f"owns its own deploy script ({surface.deploy}); fleet reports only",
        ))
        return

    if kind == "python-package":
        spec = importlib.util.find_spec("evolution") if pkg.name == "self-evolution" else None
        installed = spec is not None
        plan.actions.append(Action(
            package=pkg.name, kind=kind, profile=None, source=src,
            target=expand(surface.venv or "~"), verdict=OK if installed else MANUAL,
            mode="editable",
            detail="editable install present" if installed
                   else "run: <venv>/python -m pip install -e <source>",
        ))
        return

    if kind == "mcp-server":
        plan.actions.append(Action(
            package=pkg.name, kind=kind, profile=None, source=src,
            target=Path(surface.name or pkg.name), verdict=MANUAL, mode="config",
            detail="register under mcp_servers in each profile's config.yaml — see HERMES.md",
        ))
        return

    if kind == "desktop-plugin":
        if src is None:
            plan.errors.append(f"{pkg.name}: desktop-plugin surface has no source")
            return
        name = surface.install_as or src.name
        plan.actions.append(_plan_tree(pkg, surface, src, DESKTOP_ROOT / name, None, mode))
        return

    if kind == "claude-skill":
        if src is None:
            plan.errors.append(f"{pkg.name}: claude-skill surface has no source")
            return
        for skill in _skill_dirs(src):
            plan.actions.append(
                _plan_tree(pkg, surface, skill, manifest.claude_skills_dir / skill.name, "claude", mode)
            )
        return

    # ── per-profile surfaces ──
    for profile in manifest.targets(pkg):
        if kind == "agent-plugin":
            name = surface.install_as or (src.name if src else pkg.name)
            target = profile.plugins_dir / name
            if surface.upstream_managed:
                present = links.inspect(target).kind != "absent"
                plan.actions.append(Action(
                    package=pkg.name, kind=kind, profile=profile.name, source=None,
                    target=target, verdict=OK if present else MISSING, mode="upstream",
                    detail="installed from upstream" if present
                           else f"install with: hermes plugins install {pkg.upstream}",
                ))
                continue
            if src is None:
                plan.errors.append(f"{pkg.name}: agent-plugin surface has no source")
                continue
            plan.actions.append(_plan_tree(pkg, surface, src, target, profile.name, mode))

        elif kind in ("skill", "skill-pack"):
            if src is None:
                plan.errors.append(f"{pkg.name}: {kind} surface has no source")
                continue
            base = profile.skills_dir / surface.category if surface.category else profile.skills_dir
            found = _skill_dirs(src)
            if not found:
                plan.errors.append(f"{pkg.name}: no SKILL.md found under {src}")
                continue
            for skill in found:
                plan.actions.append(_plan_tree(pkg, surface, skill, base / skill.name, profile.name, mode))

        elif kind == "skin-pack":
            if src is None:
                plan.errors.append(f"{pkg.name}: skin-pack surface has no source")
                continue
            synced, total = links.mirror_status(src, profile.skins_dir, "*.yaml")
            plan.actions.append(Action(
                package=pkg.name, kind=kind, profile=profile.name, source=src,
                target=profile.skins_dir, mode="mirror",
                verdict=OK if synced == total else REFRESH,
                detail=f"{synced}/{total} skins in sync",
            ))


def plan(manifest: Manifest, *, only: Optional[Iterable[str]] = None,
         profiles: Optional[Iterable[str]] = None) -> Plan:
    """Compute what needs to change. Reads the disk; writes nothing."""
    wanted = set(only) if only else None
    result = Plan()

    if profiles:
        keep = set(profiles)
        manifest = Manifest(
            profiles={k: v for k, v in manifest.profiles.items() if k in keep},
            packages=manifest.packages, default_mode=manifest.default_mode,
            claude_home=manifest.claude_home, claude_skills_dir=manifest.claude_skills_dir,
            claude_source=manifest.claude_source,
        )

    for pkg in manifest.packages:
        if wanted and pkg.name not in wanted:
            continue
        for surface in pkg.surfaces:
            try:
                _plan_surface(manifest, pkg, surface, result)
            except OSError as exc:
                result.errors.append(f"{pkg.name}/{surface.kind}: {exc}")
    return result


# ── applying ────────────────────────────────────────────────────────────────

def apply(plan_: Plan, *, manifest: Manifest) -> Plan:
    """Execute every pending action in `plan_`, recording what actually happened."""
    for action in plan_.actions:
        if not action.needs_work:
            continue
        try:
            if action.kind == "skin-pack" and action.source is not None:
                written = links.mirror_files(action.source, action.target, "*.yaml")
                action.applied = f"mirrored {written} skin(s)"
            elif action.source is not None:
                if action.mode == "copy":
                    got = links.copy_dir(action.source, action.target)
                else:
                    got = links.link_dir(action.source, action.target)
                action.applied = got
                if action.mode == "link" and got == "copy":
                    action.detail = (
                        "FELL BACK TO COPY — no symlink privilege and mklink /J failed; "
                        "this target will drift"
                    )
            else:
                action.applied = "skipped (no source)"
        except OSError as exc:
            plan_.errors.append(f"{action.package} -> {action.target}: {exc}")
            action.applied = f"failed: {exc}"
    return plan_


def ensure_dirs(manifest: Manifest) -> None:
    """Create the per-profile directories sync writes into, so a fresh profile
    (tiferet had no `skins/` at all) doesn't fail on the first run."""
    DESKTOP_ROOT.mkdir(parents=True, exist_ok=True)
    for profile in manifest.profiles.values():
        for path in (profile.plugins_dir, profile.skills_dir, profile.skins_dir):
            path.mkdir(parents=True, exist_ok=True)
