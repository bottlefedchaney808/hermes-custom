"""Load and validate ``fleet.yaml`` into typed objects.

The manifest is the source of truth for what is installed where; everything
else in this package reads it and never guesses. Validation is strict and
fails loudly: a typo'd surface kind or an unknown profile name should stop the
run, not silently install nothing and report success.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO_ROOT / "fleet.yaml"

# Surfaces that install per profile, vs the ones that install exactly once.
PER_PROFILE_KINDS = {"agent-plugin", "skill", "skill-pack", "skin-pack", "mcp-server"}
GLOBAL_KINDS = {"desktop-plugin", "claude-skill", "python-package", "external"}
VALID_KINDS = PER_PROFILE_KINDS | GLOBAL_KINDS

VALID_MODES = {"link", "copy", "mirror"}
# `staged` means: materialize it, inventory it, leave it switched off.
VALID_ENABLE = {True, False, "staged"}


class ManifestError(RuntimeError):
    """fleet.yaml is malformed. Always fatal — never degrade to a partial run."""


def expand(raw: str) -> Path:
    """`~/.hermes/profiles/local` -> an absolute Path, on any platform."""
    return Path(os.path.expanduser(str(raw))).resolve()


@dataclass(frozen=True)
class Profile:
    name: str
    home: Path
    role: str = ""

    @property
    def plugins_dir(self) -> Path:
        return self.home / "plugins"

    @property
    def skills_dir(self) -> Path:
        return self.home / "skills"

    @property
    def skins_dir(self) -> Path:
        return self.home / "skins"

    @property
    def config_path(self) -> Path:
        return self.home / "config.yaml"


@dataclass(frozen=True)
class Surface:
    """One materializable thing inside a package.

    ``from_`` is relative to the package's ``source`` directory; when omitted
    the package directory itself is the payload (the common case for a plugin
    whose ``plugin.yaml`` sits at its root).
    """

    kind: str
    from_: Optional[str] = None
    install_as: Optional[str] = None
    category: Optional[str] = None
    name: Optional[str] = None
    mode: Optional[str] = None
    enable: Any = None
    managed: Optional[str] = None
    all: bool = False
    editable: bool = False
    venv: Optional[str] = None
    deploy: Optional[str] = None

    @property
    def per_profile(self) -> bool:
        return self.kind in PER_PROFILE_KINDS

    @property
    def upstream_managed(self) -> bool:
        """Installed by `hermes plugins install`, not by us. We report, not touch."""
        return self.managed == "upstream"


@dataclass(frozen=True)
class Package:
    name: str
    summary: str
    source: Optional[Path]
    surfaces: List[Surface]
    profiles: List[str] = field(default_factory=list)
    is_global: bool = False
    upstream: Optional[str] = None
    notes: str = ""


@dataclass(frozen=True)
class Manifest:
    profiles: Dict[str, Profile]
    packages: List[Package]
    default_mode: str
    claude_home: Path
    claude_skills_dir: Path
    claude_source: Path

    def package(self, name: str) -> Package:
        for pkg in self.packages:
            if pkg.name == name:
                return pkg
        raise ManifestError(f"no package named {name!r} in fleet.yaml")

    def targets(self, pkg: Package) -> List[Profile]:
        """Profiles this package's per-profile surfaces land in."""
        return [self.profiles[n] for n in pkg.profiles if n in self.profiles]


def _surface(raw: Dict[str, Any], pkg_name: str) -> Surface:
    kind = raw.get("kind")
    if kind not in VALID_KINDS:
        raise ManifestError(
            f"{pkg_name}: unknown surface kind {kind!r} "
            f"(valid: {', '.join(sorted(VALID_KINDS))})"
        )
    mode = raw.get("mode")
    if mode is not None and mode not in VALID_MODES:
        raise ManifestError(f"{pkg_name}: unknown mode {mode!r}")
    enable = raw.get("enable")
    if enable is not None and enable not in VALID_ENABLE:
        raise ManifestError(f"{pkg_name}: enable must be true, false or 'staged'")
    return Surface(
        kind=kind,
        from_=raw.get("from"),
        install_as=raw.get("install_as"),
        category=raw.get("category"),
        name=raw.get("name"),
        mode=mode,
        enable=enable,
        managed=raw.get("managed"),
        all=bool(raw.get("all", False)),
        editable=bool(raw.get("editable", False)),
        venv=raw.get("venv"),
        deploy=raw.get("deploy"),
    )


def load(path: Path = MANIFEST_PATH) -> Manifest:
    if not path.is_file():
        raise ManifestError(f"manifest not found: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    if raw.get("version") != 1:
        raise ManifestError(f"unsupported manifest version {raw.get('version')!r}; expected 1")

    profiles: Dict[str, Profile] = {}
    for name, body in (raw.get("profiles") or {}).items():
        home = expand(body["home"])
        profiles[name] = Profile(name=name, home=home, role=(body.get("role") or "").strip())
    if not profiles:
        raise ManifestError("fleet.yaml declares no profiles")

    default_mode = ((raw.get("defaults") or {}).get("mode")) or "link"
    if default_mode not in VALID_MODES:
        raise ManifestError(f"defaults.mode {default_mode!r} is not a valid mode")

    packages: List[Package] = []
    for body in raw.get("packages") or []:
        name = body.get("name")
        if not name:
            raise ManifestError("a package entry has no name")

        src_raw = body.get("source")
        source = (REPO_ROOT / src_raw) if src_raw else None
        if source is not None and not source.exists():
            raise ManifestError(f"{name}: source {source} does not exist")

        declared = body.get("profiles") or []
        for prof in declared:
            if prof not in profiles:
                raise ManifestError(f"{name}: unknown profile {prof!r}")

        surfaces = [_surface(s, name) for s in (body.get("surfaces") or [])]
        if not surfaces:
            raise ManifestError(f"{name}: declares no surfaces")

        # A package with per-profile surfaces must say which profiles.
        if any(s.per_profile for s in surfaces) and not declared and not body.get("global"):
            raise ManifestError(f"{name}: has per-profile surfaces but no `profiles:` list")

        packages.append(
            Package(
                name=name,
                summary=(body.get("summary") or "").strip(),
                source=source,
                surfaces=surfaces,
                profiles=list(declared),
                is_global=bool(body.get("global", False)),
                upstream=body.get("upstream"),
                notes=(body.get("notes") or "").strip(),
            )
        )

    claude = raw.get("claude") or {}
    claude_home = expand(claude.get("home", "~/.claude"))
    return Manifest(
        profiles=profiles,
        packages=packages,
        default_mode=default_mode,
        claude_home=claude_home,
        claude_skills_dir=expand(claude.get("skills_dir", "~/.claude/skills")),
        claude_source=REPO_ROOT / (claude.get("source") or "skills"),
    )
