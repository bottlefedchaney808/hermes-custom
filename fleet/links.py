"""Directory materialization primitives, with the Windows realities handled.

Three ways a package reaches a profile:

``link``    a directory symlink back into this repo. One edit reaches every
            profile and ``git log`` is the audit trail. This is the default and
            the one you want.
``copy``    a real tree. For packages that WRITE inside their own folder — a
            symlinked package writing to itself would dirty this repo.
``mirror``  file-by-file into a shared directory (skins land in ``skins/`` next
            to whatever else lives there, so the directory itself can't be a
            link).

On Windows, ``os.symlink`` needs Developer Mode or elevation. When it is
unavailable we fall back to a **junction** (``mklink /J``), which needs neither
and is transparent to Python, Node and the Hermes loaders alike. Copy is the
last resort, and we say so out loud rather than pretending the link worked —
a silent downgrade to copy is exactly how the drift this repo exists to fix got
started.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

LinkKind = Literal["symlink", "junction", "copy", "absent", "foreign"]


@dataclass(frozen=True)
class LinkState:
    """What is actually on disk at a path, and where it points."""

    kind: LinkKind
    target: Optional[Path] = None

    @property
    def is_link(self) -> bool:
        return self.kind in ("symlink", "junction")


def _denormalize(raw: str) -> Path:
    r"""Strip Windows' extended-length prefix from a link target.

    ``os.readlink`` on Windows hands back ``\\?\C:\Users\...`` for a symlink
    created through the normal API. ``Path(r'\\?\C:\x').resolve()`` is NOT equal
    to ``Path('C:/x').resolve()``, so comparing them raw makes a perfectly
    correct link look like it points somewhere else — which is how an idempotent
    sync ends up relinking the same target on every run.
    """
    if raw.startswith("\\\\?\\UNC\\"):
        return Path("\\\\" + raw[8:])
    if raw.startswith("\\\\?\\"):
        return Path(raw[4:])
    return Path(raw)


def inspect(path: Path) -> LinkState:
    """Classify `path` without following it.

    Junctions are reparse points that ``Path.is_symlink()`` reports False for on
    some Python versions, so we ask the OS for the reparse bit directly and only
    then decide.
    """
    if not path.exists() and not path.is_symlink():
        return LinkState("absent")

    if path.is_symlink():
        try:
            return LinkState("symlink", _denormalize(os.readlink(path)))
        except OSError:
            return LinkState("symlink")

    if os.name == "nt":
        try:
            # FILE_ATTRIBUTE_REPARSE_POINT — set for junctions as well as links.
            if os.lstat(path).st_file_attributes & 0x400:  # type: ignore[attr-defined]
                resolved = path.resolve()
                return LinkState("junction", resolved if resolved != path else None)
        except (OSError, AttributeError):
            pass

    if path.is_dir():
        return LinkState("copy", path)
    return LinkState("foreign", path)


def _remove(path: Path) -> None:
    """Remove a link or tree. Links are unlinked, never recursed into — deleting
    through a junction would delete the source in this repo."""
    state = inspect(path)
    if state.kind == "absent":
        return
    if state.is_link:
        # rmdir removes the reparse point itself; unlink handles file symlinks.
        try:
            os.rmdir(path)
        except OSError:
            path.unlink(missing_ok=True)
        return
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)


def link_dir(src: Path, dst: Path) -> LinkKind:
    """Point `dst` at `src`. Returns how it was actually achieved.

    Never raises for a missing privilege: it degrades symlink -> junction ->
    copy and reports which rung it landed on, so the caller can surface it.
    """
    src = src.resolve()
    dst.parent.mkdir(parents=True, exist_ok=True)

    current = inspect(dst)
    if current.is_link and current.target is not None:
        try:
            if current.target.resolve() == src:
                return current.kind  # already correct — idempotent no-op
        except OSError:
            pass
    _remove(dst)

    try:
        os.symlink(src, dst, target_is_directory=True)
        return "symlink"
    except (OSError, NotImplementedError):
        pass

    if os.name == "nt":
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(dst), str(src)],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return "junction"

    shutil.copytree(src, dst)
    return "copy"


def copy_dir(src: Path, dst: Path) -> LinkKind:
    """Replace `dst` with a fresh copy of `src`. Always a real tree."""
    src = src.resolve()
    dst.parent.mkdir(parents=True, exist_ok=True)
    _remove(dst)
    shutil.copytree(src, dst)
    return "copy"


def mirror_files(src: Path, dst: Path, pattern: str = "*") -> int:
    """Copy `src`'s matching files into `dst`, leaving `dst`'s other contents
    alone. Returns how many files were written (0 means already in sync)."""
    dst.mkdir(parents=True, exist_ok=True)
    written = 0
    for entry in sorted(src.glob(pattern)):
        if not entry.is_file():
            continue
        target = dst / entry.name
        if target.is_file() and target.read_bytes() == entry.read_bytes():
            continue
        shutil.copy2(entry, target)
        written += 1
    return written


def mirror_status(src: Path, dst: Path, pattern: str = "*") -> tuple[int, int]:
    """(in sync, total) for a mirror surface — the read-only twin of
    :func:`mirror_files`, so status never mutates anything."""
    total = 0
    synced = 0
    for entry in sorted(src.glob(pattern)):
        if not entry.is_file():
            continue
        total += 1
        target = dst / entry.name
        if target.is_file() and target.read_bytes() == entry.read_bytes():
            synced += 1
    return synced, total


def remove(path: Path) -> bool:
    """Public uninstall door. True when something was actually removed."""
    if inspect(path).kind == "absent":
        return False
    _remove(path)
    return True
