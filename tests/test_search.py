from pathlib import Path

import pytest

from brain_rag.embed import EmbeddingsUnavailable
from brain_rag.index import index_vault
from brain_rag.search import rrf_merge, search
from brain_rag.store import Store

VAULT = Path(__file__).parent / "fixtures" / "vault"


@pytest.fixture()
def store(tmp_path):
    s = Store.open(tmp_path / "brain.sqlite")
    index_vault(VAULT, s, embed=False)
    yield s
    s.close()


def _no_vectors(texts, **kwargs):
    raise EmbeddingsUnavailable("offline in tests")


def test_leg_filter_prevents_cross_leg_leak(store, monkeypatch):
    """Construction-scoped search must never return Trading chunks."""
    monkeypatch.setattr("brain_rag.search.embed_texts", _no_vectors)
    result = search(store, "straddle", leg="Construction")
    assert result["hits"]
    assert all(h["leg"] == "Construction" for h in result["hits"])
    assert all(not h["path"].startswith("Trading/") for h in result["hits"])


def test_every_hit_carries_citation_fields(store, monkeypatch):
    monkeypatch.setattr("brain_rag.search.embed_texts", _no_vectors)
    for hit in search(store, "straddle")["hits"]:
        assert hit["path"]
        assert hit["heading"] or hit["session_id"]
        assert hit["date"]
        assert hit["leg"]


def test_no_match_returns_empty_hits_not_an_error(store, monkeypatch):
    monkeypatch.setattr("brain_rag.search.embed_texts", _no_vectors)
    result = search(store, "zzzznotinthevault")
    assert result["hits"] == []
    assert "error" not in result


def test_embeddings_down_degrades_to_bm25_and_flags_it(store, monkeypatch):
    monkeypatch.setattr("brain_rag.search.embed_texts", _no_vectors)
    result = search(store, "straddle")
    assert result["vector"] == "skipped"
    assert result["hits"]


def test_k_caps_the_hit_count(store, monkeypatch):
    monkeypatch.setattr("brain_rag.search.embed_texts", _no_vectors)
    assert len(search(store, "straddle OR mill OR profile", k=1)["hits"]) == 1


def test_date_filters_bound_results(store, monkeypatch):
    monkeypatch.setattr("brain_rag.search.embed_texts", _no_vectors)
    assert search(store, "straddle", before="1990-01-01")["hits"] == []
    assert search(store, "straddle", after="1990-01-01")["hits"]


def test_source_filter_restricts_to_notes(store, monkeypatch):
    monkeypatch.setattr("brain_rag.search.embed_texts", _no_vectors)
    assert all(h["source"] == "note" for h in search(store, "straddle", source="note")["hits"])


def test_rrf_merge_rewards_agreement_between_lists():
    bm25 = [{"id": 1}, {"id": 2}, {"id": 3}]
    knn = [{"id": 3}, {"id": 2}, {"id": 9}]
    merged = [row["id"] for row in rrf_merge(bm25, knn)]
    assert merged[0] in (2, 3)
    assert set(merged) == {1, 2, 3, 9}
