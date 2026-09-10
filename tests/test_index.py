import shutil
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


def _copy_vault(tmp_path: Path) -> Path:
    dest = tmp_path / "vault"
    shutil.copytree(VAULT, dest)
    return dest


def test_deleted_note_is_dropped_on_incremental(store, tmp_path):
    vault = _copy_vault(tmp_path)
    index_vault(vault, store, embed=False)
    rel = "Trading/Positions.md"
    assert store.known_hashes(rel)
    (vault / rel).unlink()
    index_vault(vault, store, embed=False)
    assert store.known_hashes(rel) == set()


def test_emptied_note_drops_old_chunks(store, tmp_path):
    vault = _copy_vault(tmp_path)
    index_vault(vault, store, embed=False)
    rel = "Trading/Positions.md"
    assert store.known_hashes(rel)
    (vault / rel).write_text("", encoding="utf-8")
    index_vault(vault, store, embed=False)
    assert store.known_hashes(rel) == set()


def test_unreadable_note_drops_stale_hashes(store, tmp_path):
    vault = _copy_vault(tmp_path)
    index_vault(vault, store, embed=False)
    rel = "Trading/Positions.md"
    old = store.known_hashes(rel)
    assert old
    (vault / rel).write_bytes(b"\xff\xfe not utf-8")
    index_vault(vault, store, embed=False)
    assert store.known_hashes(rel) == set()
    assert old.isdisjoint(store.known_hashes(rel))


def test_unknown_mode_is_rejected(store):
    with pytest.raises(ValueError):
        index_vault(VAULT, store, mode="delta", embed=False)
