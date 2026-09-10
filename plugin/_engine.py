"""Import the brain_rag engine from a plugin loaded without package context.

Hermes loads ``plugin_api.py`` standalone (no package), so a relative import
fails there. Both halves call :func:`load` and get the same modules.
"""
from __future__ import annotations

import sys
from pathlib import Path

ENGINE_SRC_ENV = "BRAIN_RAG_SRC"


def _candidate_roots() -> list[Path]:
    import os

    roots: list[Path] = []
    override = os.environ.get(ENGINE_SRC_ENV)
    if override:
        roots.append(Path(override))
    here = Path(__file__).resolve().parent
    roots.append(here / "vendor" / "src")          # deployed copy
    roots.append(here.parent / "src")              # repo checkout
    return roots


def load():
    """Return the engine namespace, importing it once."""
    for root in _candidate_roots():
        if (root / "brain_rag" / "__init__.py").exists():
            if str(root) not in sys.path:
                sys.path.insert(0, str(root))
            break
    from brain_rag import index as index_mod
    from brain_rag import remind as remind_mod
    from brain_rag import search as search_mod
    from brain_rag import store as store_mod

    return {
        "index": index_mod,
        "search": search_mod,
        "store": store_mod,
        "remind": remind_mod,
    }


def index_path() -> Path:
    """``$HERMES_HOME/rag/brain.sqlite`` — profile-scoped, never shared."""
    import os

    home = os.environ.get("HERMES_HOME")
    base = Path(home) if home else Path.home() / ".hermes"
    return base / "rag" / "brain.sqlite"


def vault_path() -> Path:
    import os

    return Path(os.environ.get("OBSIDIAN_VAULT_PATH") or Path.home() / "obsidian-vault")
