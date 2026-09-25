"""Keep Hermes' built-in memory roomy by spilling old entries into the vault.

MEMORY.md / USER.md are injected into every turn and capped (2200 / 1375
chars). Models fill them and never prune, so they freeze at ~100% and stop
learning. This runs on a schedule — no model judgment involved:

  1. drop near-duplicate entries (keep the longer wording)
  2. above HIGH_WATER of the cap, move the oldest entries into a vault note
     until the file is at LOW_WATER
  3. leave one pointer entry so the model knows where the detail went

Order matters for safety: the vault note is written and committed BEFORE the
entries leave the memory file, so a failed commit never loses anything.
Memory files are rewritten under Hermes' own lock protocol
(``<file>.lock`` + atomic replace, tools/memory_tool_store.py) with the same
``\\n§\\n`` delimiter, so a live session never sees a torn or "drifted" file.
"""
from __future__ import annotations

import difflib
import os
import subprocess
import tempfile
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any, Callable

ENTRY_DELIMITER = "\n§\n"
HIGH_WATER = 0.70
LOW_WATER = 0.50
DUP_RATIO = 0.70
ARCHIVE_DIR = "Memory"  # not a leg: personal profiles index it, tiferet never does
POINTER_MARK = "[auto-archive]"

TARGETS = {
    "MEMORY.md": ("Hermes Memory Archive", 2200),
    "USER.md": ("Hermes User Archive", 1375),
}


def parse(raw: str) -> list[str]:
    return [e.strip() for e in raw.split(ENTRY_DELIMITER) if e.strip()]


def size(entries: list[str]) -> int:
    return len(ENTRY_DELIMITER.join(entries))


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


def dedupe(entries: list[str]) -> tuple[list[str], list[str]]:
    """Drop near-duplicates, keeping the longer wording in the earlier slot."""
    kept: list[str] = []
    dropped: list[str] = []
    for entry in entries:
        match = next(
            (i for i, k in enumerate(kept)
             if difflib.SequenceMatcher(None, _norm(k), _norm(entry)).ratio() >= DUP_RATIO),
            None,
        )
        if match is None:
            kept.append(entry)
        elif len(entry) > len(kept[match]):
            dropped.append(kept[match])
            kept[match] = entry
        else:
            dropped.append(entry)
    return kept, dropped


def _is_pinned(entry: str) -> bool:
    """Pointers stay: our own archive pointer and hand-written vault pointers."""
    return POINTER_MARK in entry or ("[[" in entry and "vault" in entry.lower() and len(entry) < 400)


def plan(entries: list[str], limit: int, archive_title: str) -> dict[str, Any]:
    """Pure: what to keep, what to move. Nothing touches disk."""
    kept, duplicates = dedupe(entries)
    moved: list[str] = []
    if size(kept) > HIGH_WATER * limit:
        pointer = (f"{POINTER_MARK} Older notes moved to vault {ARCHIVE_DIR}/{archive_title}.md "
                   f"— use rag_search to find them.")
        if not any(POINTER_MARK in e for e in kept):
            kept.append(pointer)
        # Longest first: detail belongs in the vault; short hard rules
        # ("never github-copilot") are what earns a slot in every turn.
        for entry in sorted(kept, key=len, reverse=True):
            if size(kept) <= LOW_WATER * limit:
                break
            if _is_pinned(entry):
                continue
            kept.remove(entry)
            moved.append(entry)
    return {"keep": kept, "move": moved, "duplicates": duplicates,
            "before": size(entries), "after": size(kept), "limit": limit}


@contextmanager
def hermes_lock(path: Path):
    """Same lock Hermes' MemoryStore takes: byte 0 of ``<file>.lock``."""
    lock_path = path.with_suffix(path.suffix + ".lock")
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        if os.name == "nt":
            import msvcrt
            os.lseek(fd, 0, 0)
            msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        try:
            if os.name == "nt":
                import msvcrt
                os.lseek(fd, 0, 0)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def _atomic_write(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(prefix=".mem_", dir=str(path.parent))
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    os.replace(tmp, path)


def _append_archive(vault: Path, title: str, entries: list[str]) -> str:
    rel = f"{ARCHIVE_DIR}/{title}.md"
    target = vault / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    stamp = date.today().isoformat()
    body = "\n".join(f"- {e}" for e in entries)
    if target.exists():
        with target.open("a", encoding="utf-8") as fh:
            fh.write(f"\n\n## {stamp}\n\n{body}\n")
    else:
        target.write_text(
            f"---\ntype: memory-archive\ncreated: {stamp}\n---\n\n# {title}\n\n"
            f"Entries spilled from Hermes built-in memory when it passed "
            f"{int(HIGH_WATER * 100)}% of its cap.\n\n## {stamp}\n\n{body}\n",
            encoding="utf-8",
        )
    return rel


def _run_git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True)


def spill(
    memories_dir: str | Path,
    vault_dir: str | Path,
    *,
    apply: bool = False,
    push: bool = True,
    runner: Callable[[list[str], Path], None] | None = None,
) -> dict[str, Any]:
    """Plan (and with ``apply``, execute) a spill for MEMORY.md and USER.md."""
    memories, vault = Path(memories_dir), Path(vault_dir)
    git = runner or _run_git
    report: dict[str, Any] = {"files": {}, "committed": False, "pushed": False, "error": None}
    if not vault.is_dir():
        report["error"] = f"vault clone not found: {vault}"
        return report

    plans = {}
    for name, (title, limit) in TARGETS.items():
        path = memories / name
        if path.is_file():
            plans[name] = plan(parse(path.read_text(encoding="utf-8")), limit, title)
            report["files"][name] = {k: v for k, v in plans[name].items() if k != "keep"}
    changed = {n: p for n, p in plans.items() if p["move"] or p["duplicates"]}
    if not apply or not changed:
        return report

    try:
        git(["pull", "--rebase", "--autostash"], vault)  # the vault is usually dirty
    except Exception as exc:  # noqa: BLE001
        report["error"] = f"vault pull failed, memory untouched: {exc}"
        return report

    written = [_append_archive(vault, TARGETS[n][0], p["move"]) for n, p in changed.items() if p["move"]]
    if written:
        try:
            git(["add", *written], vault)
            git(["commit", "-m", "chore(vault): archive spilled Hermes memory"], vault)
            report["committed"] = True
        except Exception as exc:  # noqa: BLE001
            report["error"] = f"vault commit failed, memory untouched: {exc}"
            return report

    for name, p in changed.items():
        path = memories / name
        with hermes_lock(path):
            current = parse(path.read_text(encoding="utf-8"))
            # Re-plan under the lock: a session may have added entries since.
            fresh = plan(current, TARGETS[name][1], TARGETS[name][0])
            leftover = [e for e in fresh["move"] if e not in p["move"]]
            keep = fresh["keep"] + leftover  # never drop what wasn't archived
            _atomic_write(path, ENTRY_DELIMITER.join(keep))

    if written and push:
        try:
            git(["push"], vault)
            report["pushed"] = True
        except Exception as exc:  # noqa: BLE001
            report["error"] = f"vault push failed (commit is local): {exc}"
    return report
