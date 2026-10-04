"""Copy plugin/ + vendor src into profile plugin roots. Never copy brain.sqlite."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

SKIP_NAMES = frozenset({"brain.sqlite"})


def _ignore(_directory: str, names: list[str]) -> set[str]:
    return set(SKIP_NAMES).intersection(names)


def copy_tree(src: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        if item.name in SKIP_NAMES:
            continue
        target = dest / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True, ignore=_ignore)
        else:
            shutil.copy2(item, target)


def deploy(src_root: Path, dest_roots: list[Path]) -> None:
    src_root = Path(src_root)
    plugin = src_root / "plugin"
    engine = src_root / "src"
    if not plugin.is_dir():
        raise FileNotFoundError(f"plugin dir missing: {plugin}")
    if not engine.is_dir():
        raise FileNotFoundError(f"src dir missing: {engine}")
    for dest in dest_roots:
        dest = Path(dest)
        print(f"Deploying to {dest}")
        dest.mkdir(parents=True, exist_ok=True)
        copy_tree(plugin, dest)
        copy_tree(engine, dest / "vendor" / "src")


def parse_roots(raw: str | None) -> list[Path]:
    if not raw or not raw.strip():
        local = Path(os.environ["LOCALAPPDATA"]) / "hermes"
        roots = [local / "plugins" / "brain-rag"]
        profiles = local / "profiles"
        if profiles.is_dir():
            roots += [
                d / "plugins" / "brain-rag"
                for d in sorted(profiles.iterdir())
                if d.is_dir()
            ]
        return roots
    return [Path(part.strip()) for part in raw.split(";") if part.strip()]


def main() -> int:
    if os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get(
        "BRAIN_RAG_DEPLOY_ROOTS"
    ):
        print("ERROR: refusing live-root deploy under pytest", file=sys.stderr)
        return 2
    src = Path(
        os.environ.get("BRAIN_RAG_DEPLOY_SRC")
        or Path(__file__).resolve().parent.parent
    )
    try:
        deploy(src, parse_roots(os.environ.get("BRAIN_RAG_DEPLOY_ROOTS")))
    except OSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
