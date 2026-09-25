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


def test_swept_session_note_indexes_as_session_with_session_id(store, tmp_path, monkeypatch):
    """Swept {Leg}/Sessions/*.md notes must use chunk_session, not chunk_note."""
    from brain_rag.embed import EmbeddingsUnavailable
    from brain_rag.search import search
    from brain_rag.sweep import render_session_note

    vault = _copy_vault(tmp_path)
    rel = "Construction/Sessions/2026-09-01-abc123.md"
    (vault / "Construction" / "Sessions").mkdir(parents=True, exist_ok=True)
    (vault / rel).write_text(
        render_session_note(
            session_id="20260901_120000_abc123",
            leg="Construction",
            profile="default",
            started="2026-09-01",
            source="desktop",
            title="Rate question",
            turns=[
                {"role": "user", "content": "what is the burdened rate"},
                {"role": "assistant", "content": "It is $58.40/hr."},
            ],
        ),
        encoding="utf-8",
    )

    index_vault(vault, store, embed=False)
    rows = [r for r in store.bm25("burdened", limit=20) if r["path"] == rel]
    assert rows
    assert all(r["source"] == "session" for r in rows)
    assert all(r["session_id"] == "20260901_120000_abc123" for r in rows)
    assert all(r["date"] == "2026-09-01" for r in rows)

    def _offline(texts, **kwargs):
        raise EmbeddingsUnavailable("offline in tests")

    monkeypatch.setattr("brain_rag.search.embed_texts", _offline)
    construction = search(store, "burdened", leg="Construction")
    assert construction["hits"]
    assert all(h["leg"] == "Construction" for h in construction["hits"])
    assert all(not h["path"].startswith("Trading/") for h in construction["hits"])
    for hit in construction["hits"]:
        assert hit["path"]
        assert hit["heading"] or hit["session_id"]
        assert hit["date"]
        assert hit["leg"]
    trading = search(store, "burdened", leg="Trading")
    assert all(h["leg"] == "Trading" for h in trading.get("hits", []))
