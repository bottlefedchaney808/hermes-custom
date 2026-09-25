"""Nightly brain upkeep — runs from Task Scheduler, no model involved.

  1. spill   built-in MEMORY.md / USER.md over 70% of cap -> vault Memory/ notes
  2. index   incremental re-index of every brain (only changed notes are embedded)
  3. sweep   ended sessions older than 7 days -> <Leg>/Sessions/ notes, secrets
             redacted (redact.py). Restricted brains (tiferet) never index them.

Brains (see HERMES.md):
  shared   ~/.hermes/rag            default + jason (jason/rag is a junction to it)
  tiferet  ~/.hermes/profiles/tiferet/rag   legs.txt = Construction only

Run with Hermes' venv python so the Nous token and sqlite_vec resolve:
  ~/.hermes/hermes-agent/venv/Scripts/python.exe scripts/nightly.py [--dry-run] [--no-sweep]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
# The Nous token resolver (hermes_cli.auth) imports Hermes' top-level `pm`
# package, which only resolves with the hermes-agent checkout on the path.
_AGENT = Path(os.environ.get("HERMES_ROOT") or Path.home() / ".hermes") / "hermes-agent"
sys.path.append(str(_AGENT))

from brain_rag.index import index_vault  # noqa: E402
from brain_rag.leg import LEGS  # noqa: E402
from brain_rag.spill import spill  # noqa: E402
from brain_rag.store import Store  # noqa: E402

HOME = Path(os.environ.get("HERMES_ROOT") or Path.home() / ".hermes")
VAULT = Path(os.environ.get("OBSIDIAN_VAULT_PATH") or Path.home() / "obsidian-vault")
BRAINS = {
    "shared": HOME / "rag",
    "tiferet": HOME / "profiles" / "tiferet" / "rag",
}
SWEEP_STATE_DBS = [HOME / "state.db", HOME / "profiles" / "jason" / "state.db"]
LOG = HOME / "rag" / "nightly.log"
LOG_KEEP_LINES = 400


def _legs(rag_dir: Path) -> tuple[str, ...] | None:
    path = rag_dir / "legs.txt"
    if not path.is_file():
        return None
    names = [l.split("#", 1)[0].strip() for l in path.read_text(encoding="utf-8").splitlines()]
    return tuple(n for n in names if n in LEGS)


def _log(report: dict) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    lines = LOG.read_text(encoding="utf-8").splitlines() if LOG.exists() else []
    lines.append(json.dumps(report))
    LOG.write_text("\n".join(lines[-LOG_KEEP_LINES:]) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="plan the spill, index nothing")
    ap.add_argument("--no-sweep", action="store_true", help="skip archiving old sessions into the vault")
    args = ap.parse_args()

    started = time.time()
    report: dict = {"at": time.strftime("%Y-%m-%d %H:%M:%S"), "dry_run": args.dry_run}
    failed = False

    report["spill"] = spill(HOME / "memories", VAULT, apply=not args.dry_run)
    failed |= bool(report["spill"].get("error"))

    if not args.no_sweep and not args.dry_run:
        from brain_rag.sweep import sweep_sessions
        report["sweep"] = [sweep_sessions(db, VAULT, push=True) for db in SWEEP_STATE_DBS if db.exists()]
        failed |= any(r.get("error") for r in report["sweep"])

    report["index"] = {}
    if not args.dry_run:
        for name, rag_dir in BRAINS.items():
            try:
                store = Store.open(rag_dir / "brain.sqlite")
                try:
                    report["index"][name] = index_vault(VAULT, store, mode="incremental", legs=_legs(rag_dir))
                finally:
                    store.close()
            except Exception as exc:  # noqa: BLE001 - one brain failing must not skip the other
                report["index"][name] = {"error": str(exc)}
                failed = True

    report["seconds"] = round(time.time() - started, 1)
    report["ok"] = not failed
    if not args.dry_run:
        _log(report)
    print(json.dumps(report, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
