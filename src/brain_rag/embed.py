"""Nous Portal embeddings + the sqlite-vec extension loader.

The model id and dimension below were pinned from a live
``/v1/models`` + ``/v1/embeddings`` probe (Task 1). Changing the model
changes the vector width, which invalidates every stored embedding —
a model change REQUIRES ``rag_index(mode="full")``.
"""
from __future__ import annotations

import sqlite3

# Pinned in Task 1 from the live Portal catalog. Replace both together.
NOUS_EMBED_MODEL = "qwen/qwen3-embedding-8b"
EMBED_DIM = 4096

NOUS_BASE_URL = "https://inference-api.nousresearch.com/v1"


def load_vec_extension(conn: sqlite3.Connection) -> None:
    """Load sqlite-vec into ``conn``.

    Raises RuntimeError when the interpreter was built without extension
    loading. Callers must let that propagate: a silent BM25-only degrade
    would hide a broken install (spec section 10 is about a down API, not
    a broken build).
    """
    import sqlite_vec

    if not hasattr(conn, "enable_load_extension"):
        raise RuntimeError(
            "This Python's sqlite3 was built without extension loading; "
            "sqlite-vec cannot be used."
        )
    conn.enable_load_extension(True)
    try:
        sqlite_vec.load(conn)
    finally:
        conn.enable_load_extension(False)
