from pathlib import Path

import pytest

from brain_rag.embed import EmbeddingsUnavailable
from brain_rag.index import index_vault
from brain_rag.search import search
from brain_rag.store import Store

VAULT = Path(__file__).parent / "fixtures" / "vault"


@pytest.fixture()
def store(tmp_path):
    s = Store.open(tmp_path / "brain.sqlite")
    index_vault(VAULT, s, embed=False)
    yield s
    s.close()


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    def boom(texts, **kwargs):
        raise EmbeddingsUnavailable("offline in tests")

    monkeypatch.setattr("brain_rag.search.embed_texts", boom)


def test_gate_no_cross_leg_leak_in_either_direction(store):
    """'straddle' exists in BOTH Trading and Construction fixtures."""
    for leg in ("Trading", "Construction"):
        for hit in search(store, "straddle", leg=leg)["hits"]:
            assert hit["leg"] == leg


def test_gate_every_hit_is_citable(store):
    for query in ("straddle", "mill", "profile"):
        for hit in search(store, query)["hits"]:
            assert hit["path"]
            assert hit["heading"] or hit["session_id"]
            assert hit["date"]
            assert hit["leg"]


def test_gate_unknown_query_yields_no_fabricated_hits(store):
    assert search(store, "quarterly unicorn provisioning")["hits"] == []
