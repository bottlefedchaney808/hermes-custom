import sqlite3

from brain_rag.embed import EMBED_DIM, NOUS_EMBED_MODEL, load_vec_extension


def test_sqlite_vec_loads_and_answers_a_knn_query():
    conn = sqlite3.connect(":memory:")
    load_vec_extension(conn)
    conn.execute(f"CREATE VIRTUAL TABLE v USING vec0(embedding float[{EMBED_DIM}])")
    conn.execute(
        "INSERT INTO v(rowid, embedding) VALUES (?, ?)",
        (1, _packed([0.1] * EMBED_DIM)),
    )
    rows = conn.execute(
        "SELECT rowid FROM v WHERE embedding MATCH ? ORDER BY distance LIMIT 1",
        (_packed([0.1] * EMBED_DIM),),
    ).fetchall()
    assert rows == [(1,)]


def test_embedding_model_is_pinned():
    assert NOUS_EMBED_MODEL
    assert EMBED_DIM > 0


def _packed(values):
    import struct

    return struct.pack(f"{len(values)}f", *values)
