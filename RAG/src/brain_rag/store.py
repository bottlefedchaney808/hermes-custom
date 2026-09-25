"""SQLite storage: chunk rows, an FTS5 index, and a sqlite-vec vector table.

The index is disposable — it is rebuilt from the vault, never the other way
round — so it lives at ``$HERMES_HOME/rag/brain.sqlite`` and is gitignored.
"""
from __future__ import annotations

import sqlite3
import struct
from pathlib import Path
from typing import Any, Iterable, Sequence

from brain_rag.chunk import Chunk
from brain_rag.embed import EMBED_DIM, load_vec_extension

SCHEMA_VERSION = 1

_DDL = f"""
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chunks (
    id           INTEGER PRIMARY KEY,
    path         TEXT NOT NULL,
    heading      TEXT,
    text         TEXT NOT NULL,
    leg          TEXT NOT NULL,
    source       TEXT NOT NULL,
    date         TEXT NOT NULL,
    session_id   TEXT,
    wikilinks    TEXT NOT NULL DEFAULT '',
    content_hash TEXT NOT NULL UNIQUE,
    embedded     INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_chunks_path ON chunks(path);
CREATE INDEX IF NOT EXISTS idx_chunks_leg  ON chunks(leg);
CREATE INDEX IF NOT EXISTS idx_chunks_date ON chunks(date);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    text,
    content='chunks',
    content_rowid='id',
    tokenize='porter unicode61'
);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_vec USING vec0(
    embedding float[{EMBED_DIM}]
);
"""


def _pack(vector: Sequence[float]) -> bytes:
    return struct.pack(f"{len(vector)}f", *vector)


class Store:
    """Owns the connection. Callers use :meth:`open` and :meth:`close`."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    @classmethod
    def open(cls, path: str | Path) -> "Store":
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        load_vec_extension(conn)
        conn.executescript(_DDL)
        conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES ('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )
        conn.commit()
        return cls(conn)

    def close(self) -> None:
        self._conn.close()

    def count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0])

    def known_hashes(self, path: str) -> set[str]:
        rows = self._conn.execute(
            "SELECT content_hash FROM chunks WHERE path = ?", (path,)
        ).fetchall()
        return {r[0] for r in rows}

    def indexed_paths(self) -> set[str]:
        rows = self._conn.execute("SELECT DISTINCT path FROM chunks").fetchall()
        return {r[0] for r in rows}

    def delete_path(self, path: str) -> int:
        cur = self._conn.execute("SELECT id FROM chunks WHERE path = ?", (path,))
        ids = [r[0] for r in cur.fetchall()]
        for cid in ids:
            self._conn.execute("DELETE FROM chunks_fts WHERE rowid = ?", (cid,))
            self._conn.execute("DELETE FROM chunks_vec WHERE rowid = ?", (cid,))
            self._conn.execute("DELETE FROM chunks WHERE id = ?", (cid,))
        self._conn.commit()
        return len(ids)

    def upsert_chunks(self, chunks: Iterable[Chunk]) -> int:
        """Insert chunks whose hash is not already stored. Returns inserts."""
        inserted = 0
        for c in chunks:
            existing = self._conn.execute(
                "SELECT 1 FROM chunks WHERE content_hash = ?", (c.content_hash,)
            ).fetchone()
            if existing:
                continue
            cur = self._conn.execute(
                """INSERT INTO chunks
                   (path, heading, text, leg, source, date, session_id,
                    wikilinks, content_hash)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    c.path, c.heading, c.text, c.leg, c.source, c.date,
                    c.session_id, "|".join(c.wikilinks), c.content_hash,
                ),
            )
            self._conn.execute(
                "INSERT INTO chunks_fts(rowid, text) VALUES (?, ?)",
                (cur.lastrowid, c.text),
            )
            inserted += 1
        self._conn.commit()
        return inserted

    def set_embedding(self, chunk_id: int, vector: Sequence[float]) -> None:
        self._conn.execute("DELETE FROM chunks_vec WHERE rowid = ?", (chunk_id,))
        self._conn.execute(
            "INSERT INTO chunks_vec(rowid, embedding) VALUES (?, ?)",
            (chunk_id, _pack(vector)),
        )
        self._conn.execute("UPDATE chunks SET embedded = 1 WHERE id = ?", (chunk_id,))
        self._conn.commit()

    def unembedded(self, limit: int = 256) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT id, text FROM chunks WHERE embedded = 0 LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def bm25(self, query: str, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """SELECT c.*, bm25(chunks_fts) AS score
               FROM chunks_fts
               JOIN chunks c ON c.id = chunks_fts.rowid
               WHERE chunks_fts MATCH ?
               ORDER BY score LIMIT ?""",
            (query, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def knn(self, vector: Sequence[float], limit: int = 50) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """SELECT c.*, v.distance AS score
               FROM chunks_vec v
               JOIN chunks c ON c.id = v.rowid
               WHERE v.embedding MATCH ? AND k = ?
               ORDER BY v.distance""",
            (_pack(vector), limit),
        ).fetchall()
        return [dict(r) for r in rows]
