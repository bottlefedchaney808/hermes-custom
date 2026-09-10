"""Walk the vault clone and keep the SQLite index in sync.

Incremental is the default: a file whose chunk hashes are already stored is
skipped without an embedding call. ``mode="full"`` clears each file's rows
first, which is what a model or chunker change requires.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from brain_rag.chunk import chunk_note, should_skip
from brain_rag.embed import embed_texts
from brain_rag.store import Store

EMBED_BATCH = 64


def index_vault(
    vault_dir: str | Path,
    store: Store,
    *,
    mode: str = "incremental",
    embed: bool = True,
) -> dict[str, Any]:
    """Index every markdown note under ``vault_dir``.

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
    seen: set[str] = set()

    for path in sorted(vault.rglob("*.md")):
        rel = path.relative_to(vault).as_posix()
        if should_skip(rel):
            continue
        seen.add(rel)
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            store.delete_path(rel)
            files_skipped += 1
            continue

        chunks = chunk_note(rel, text, mtime=path.stat().st_mtime)
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
