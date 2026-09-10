from pathlib import Path

import pytest

from brain_rag.embed import EmbeddingsUnavailable
from brain_rag.index import index_vault
from brain_rag.store import Store

VAULT = Path(__file__).parent / "fixtures" / "vault"


@pytest.fixture()
def store(tmp_path):
    s = Store.open(tmp_path / "brain.sqlite")
    yield s
    s.close()


def test_indexes_notes_and_skips_obsidian_dir(store):
    result = index_vault(VAULT, store, embed=False)
    assert result["files_indexed"] == 3
    paths = {r["path"] for r in store.bm25("straddle OR mill OR profile", limit=50)}
    assert not any(p.startswith(".obsidian") for p in paths)


def test_second_incremental_run_indexes_nothing_new(store):
    index_vault(VAULT, store, embed=False)
    before = store.count()
    result = index_vault(VAULT, store, embed=False)
    assert result["chunks_added"] == 0
    assert store.count() == before


def test_full_mode_rebuilds(store):
    index_vault(VAULT, store, embed=False)
    before = store.count()
    result = index_vault(VAULT, store, mode="full", embed=False)
    assert result["chunks_added"] == before
    assert store.count() == before


def test_missing_vault_raises_rather_than_indexing_nothing(store):
    with pytest.raises(FileNotFoundError):
        index_vault(Path("C:/nope/not/a/vault"), store, embed=False)


def test_embedding_failure_propagates(store, monkeypatch):
    def boom(texts, **kwargs):
        raise EmbeddingsUnavailable("down")

    monkeypatch.setattr("brain_rag.index.embed_texts", boom)
    with pytest.raises(EmbeddingsUnavailable):
        index_vault(VAULT, store, embed=True)
