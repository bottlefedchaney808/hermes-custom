import pytest

from brain_rag.chunk import Chunk
from brain_rag.store import Store


def _chunk(text="alpha beta", path="Trading/Positions.md", h="h1", leg="Trading"):
    return Chunk(
        text=text, path=path, heading="Account B", leg=leg, source="note",
        date="2026-09-01", wikilinks=("Jason",), content_hash=h,
    )


@pytest.fixture()
def store(tmp_path):
    s = Store.open(tmp_path / "brain.sqlite")
    yield s
    s.close()


def test_upsert_inserts_new_chunks(store):
    assert store.upsert_chunks([_chunk()]) == 1
    assert store.count() == 1


def test_upsert_is_idempotent_on_same_hash(store):
    store.upsert_chunks([_chunk()])
    assert store.upsert_chunks([_chunk()]) == 0
    assert store.count() == 1


def test_changed_hash_replaces_the_row(store):
    store.upsert_chunks([_chunk(text="old", h="h1")])
    store.delete_path("Trading/Positions.md")
    store.upsert_chunks([_chunk(text="new", h="h2")])
    assert store.count() == 1
    assert "new" in store.bm25("new", limit=5)[0]["text"]


def test_bm25_finds_by_keyword(store):
    store.upsert_chunks([_chunk(text="burdened labor rate"), _chunk(text="unrelated", h="h2")])
    rows = store.bm25("burdened", limit=5)
    assert rows and "burdened" in rows[0]["text"]


def test_bm25_returns_citation_fields(store):
    store.upsert_chunks([_chunk()])
    row = store.bm25("alpha", limit=1)[0]
    for key in ("path", "heading", "leg", "source", "date", "text"):
        assert key in row


def test_knn_returns_nearest_first(store):
    from brain_rag.embed import EMBED_DIM

    store.upsert_chunks([_chunk(text="near", h="h1"), _chunk(text="far", h="h2")])
    ids = [r["id"] for r in store.bm25("near OR far", limit=5)]
    near_id = [r["id"] for r in store.bm25("near", limit=1)][0]
    for cid in ids:
        store.set_embedding(cid, [1.0 if cid == near_id else 0.0] * EMBED_DIM)
    rows = store.knn([1.0] * EMBED_DIM, limit=1)
    assert rows[0]["id"] == near_id


def test_known_hashes_supports_incremental_skip(store):
    store.upsert_chunks([_chunk(h="h1"), _chunk(h="h2")])
    assert store.known_hashes("Trading/Positions.md") == {"h1", "h2"}
