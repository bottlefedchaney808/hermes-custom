"""Walk the vault clone and keep the SQLite index in sync.

Incremental is the default: a file whose chunk hashes are already stored is
skipped without an embedding call. ``mode="full"`` clears each file's rows
first, which is what a model or chunker change requires.
"""
from __future__ import annotations

import fnmatch
import re
from pathlib import Path
from typing import Any, Sequence

from brain_rag.chunk import chunks_for_markdown, should_skip
from brain_rag.embed import embed_texts
from brain_rag.leg import leg_for_vault_path
from brain_rag.store import Store

EMBED_BATCH = 64
RAGIGNORE = ".ragignore"
_PRIVATE_FM = re.compile(r"\A---\s*\n(?:.*\n)*?private:\s*true\s*\n(?:.*\n)*?---", re.IGNORECASE)


def load_ignore(vault: Path) -> list[str]:
    """Patterns from ``<vault>/.ragignore`` (vault-relative globs, ``#`` comments)."""
    path = vault / RAGIGNORE
    if not path.is_file():
        return []
    patterns = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            patterns.append(line.replace("\\", "/"))
    return patterns


def is_private(rel: str, text: str, patterns: Sequence[str]) -> bool:
    """Never indexed, on any profile: reachable only by opening the file by name."""
    name = rel.rsplit("/", 1)[-1]
    if any(fnmatch.fnmatch(rel, p) or fnmatch.fnmatch(name, p) for p in patterns):
        return True
    return bool(_PRIVATE_FM.match(text))


def index_vault(
    vault_dir: str | Path,
    store: Store,
    *,
    mode: str = "incremental",
    embed: bool = True,
    legs: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Index every markdown note under ``vault_dir``.

    ``legs`` restricts the index to those top-level legs; notes outside them
    (including root notes) are never embedded, and any already stored are
    purged by the leftover sweep below.

    Raises FileNotFoundError when the clone is missing — indexing nothing
    silently would leave an empty index that answers every query with no
    hits (spec section 10).
    """
    vault = Path(vault_dir)
    if not vault.is_dir():
        raise FileNotFoundError(f"Vault clone not found: {vault}")
    if mode not in ("incremental", "full"):
        raise ValueError(f"Unknown index mode: {mode!r}")

    files_indexed = 0
    chunks_added = 0
    files_skipped = 0
    files_private = 0
    seen: set[str] = set()
    ignore = load_ignore(vault)

    for path in sorted(vault.rglob("*.md")):
        rel = path.relative_to(vault).as_posix()
        if should_skip(rel):
            continue
        if legs is not None and (leg_for_vault_path(rel) not in legs or "/Sessions/" in f"/{rel}"):
            continue  # restricted (customer-facing) brains get curated notes only, never transcripts
        seen.add(rel)
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            store.delete_path(rel)
            files_skipped += 1
            continue
        if is_private(rel, text, ignore):
            seen.discard(rel)  # the leftover sweep purges anything already stored
            files_private += 1
            continue

        chunks = chunks_for_markdown(rel, text, mtime=path.stat().st_mtime)
        if mode == "full":
            store.delete_path(rel)
        else:
            known = store.known_hashes(rel)
            if (
                chunks
                and known
                and len(chunks) == len(known)
                and all(c.content_hash in known for c in chunks)
            ):
                files_indexed += 1
                continue
            store.delete_path(rel)

        chunks_added += store.upsert_chunks(chunks)
        files_indexed += 1

    for leftover in store.indexed_paths() - seen:
        store.delete_path(leftover)

    embedded = _embed_pending(store) if embed else 0
    return {
        "files_indexed": files_indexed,
        "chunks_added": chunks_added,
        "chunks_embedded": embedded,
        "total_chunks": store.count(),
        "files_skipped": files_skipped,
        "files_private": files_private,
        "mode": mode,
    }


def _embed_pending(store: Store) -> int:
    """Embed every chunk still missing a vector."""
    total = 0
    while True:
        pending = store.unembedded(limit=EMBED_BATCH)
        if not pending:
            return total
        vectors = embed_texts([row["text"] for row in pending])
        for row, vector in zip(pending, vectors):
            store.set_embedding(row["id"], vector)
        total += len(pending)
