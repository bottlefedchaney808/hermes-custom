"""Weekly: sweep old sessions into the vault, then refresh the index.

Sweep first — a reindex before the sweep would miss the notes just written.
This script never deletes sessions from state.db.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brain_rag.sweep import sweep_sessions  # noqa: E402
from brain_rag.store import Store  # noqa: E402
from brain_rag.index import index_vault  # noqa: E402


def _hermes_home() -> Path:
    return Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")


def _vault() -> Path:
    return Path(os.environ.get("OBSIDIAN_VAULT_PATH") or Path.home() / "obsidian-vault")


def main() -> int:
    home = _hermes_home()
    report = {"sweep": None, "index": None}

    sweep_result = sweep_sessions(home / "state.db", _vault(), older_than_days=7)
    report["sweep"] = sweep_result

    store = Store.open(home / "rag" / "brain.sqlite")
    try:
        report["index"] = index_vault(_vault(), store, mode="incremental")
    finally:
        store.close()

    print(json.dumps(report, indent=2))
    return 1 if sweep_result.get("error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
