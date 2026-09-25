"""Per-profile leg boundary (tiferet = Construction only) and query-path performance."""
import importlib.util
from pathlib import Path

from brain_rag.embed import EMBED_DIM, EmbeddingsUnavailable
from brain_rag.index import index_vault
from brain_rag import search as search_mod
from brain_rag.search import QUERY_TIMEOUT_SECONDS, search
from brain_rag.store import Store

VAULT = Path(__file__).parent / "fixtures" / "vault"
ENGINE = Path(__file__).resolve().parents[1] / "plugin" / "_engine.py"


def _no_vectors(texts, **kwargs):
    raise EmbeddingsUnavailable("offline in tests")


def _paths(store):
    return {p.split("/")[0] for p in store.indexed_paths()}


def test_index_with_legs_only_stores_those_legs(tmp_path):
    store = Store.open(tmp_path / "brain.sqlite")
    index_vault(VAULT, store, embed=False, legs=("Construction",))
    assert _paths(store) == {"Construction"}
    store.close()


def test_restricting_an_existing_index_purges_other_legs(tmp_path):
    store = Store.open(tmp_path / "brain.sqlite")
    index_vault(VAULT, store, embed=False)
    assert "Trading" in _paths(store)
    index_vault(VAULT, store, embed=False, legs=("Construction",))
    assert _paths(store) == {"Construction"}
    store.close()


def test_search_allowed_legs_blocks_other_legs_even_in_a_full_index(tmp_path, monkeypatch):
    monkeypatch.setattr("brain_rag.search.embed_texts", _no_vectors)
    store = Store.open(tmp_path / "brain.sqlite")
    index_vault(VAULT, store, embed=False)  # stale, unrestricted index
    result = search(store, "straddle", allowed_legs=("Construction",))
    assert all(h["leg"] == "Construction" for h in result["hits"])
    blocked = search(store, "straddle", leg="Trading", allowed_legs=("Construction",))
    assert blocked["hits"] == []
    store.close()


def test_query_embedding_uses_short_timeout_and_is_cached(tmp_path, monkeypatch):
    calls = []

    def fake(texts, **kwargs):
        calls.append(kwargs.get("timeout"))
        return [[0.0] * EMBED_DIM for _ in texts]

    monkeypatch.setattr("brain_rag.search.embed_texts", fake)
    store = Store.open(tmp_path / "brain.sqlite")
    index_vault(VAULT, store, embed=False)
    search(store, "straddle")
    search(store, "  straddle ")
    assert calls == [QUERY_TIMEOUT_SECONDS]
    store.close()


def test_failed_query_embedding_is_not_cached(tmp_path, monkeypatch):
    monkeypatch.setattr("brain_rag.search.embed_texts", _no_vectors)
    store = Store.open(tmp_path / "brain.sqlite")
    index_vault(VAULT, store, embed=False)
    assert search(store, "straddle")["vector"] == "skipped"
    assert search_mod._query_cache == {}
    store.close()


def _engine(monkeypatch, home):
    monkeypatch.setenv("HERMES_HOME", str(home))
    spec = importlib.util.spec_from_file_location("brain_rag_engine_legs", ENGINE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_no_legs_file_means_every_leg(tmp_path, monkeypatch):
    assert _engine(monkeypatch, tmp_path).allowed_legs() is None


def test_legs_file_is_parsed_with_comments(tmp_path, monkeypatch):
    (tmp_path / "rag").mkdir()
    (tmp_path / "rag" / "legs.txt").write_text("# customer-facing\nConstruction  # only\n", encoding="utf-8")
    assert _engine(monkeypatch, tmp_path).allowed_legs() == ("Construction",)


def test_legs_file_with_no_valid_leg_fails_closed(tmp_path, monkeypatch):
    (tmp_path / "rag").mkdir()
    (tmp_path / "rag" / "legs.txt").write_text("construction\nPersonal\n", encoding="utf-8")
    assert _engine(monkeypatch, tmp_path).allowed_legs() == ()


def test_restricted_brain_never_indexes_session_transcripts(tmp_path):
    import shutil
    vault = tmp_path / "vault"
    shutil.copytree(VAULT, vault)
    (vault / "Construction" / "Sessions").mkdir()
    (vault / "Construction" / "Sessions" / "2026-09-01-abc.md").write_text(
        "---\ntype: session\n---\n\n# chat\n\n## User\n\nprivate chatter\n", encoding="utf-8")
    store = Store.open(tmp_path / "brain.sqlite")
    index_vault(vault, store, embed=False, legs=("Construction",))
    assert not any("/Sessions/" in p for p in store.indexed_paths())
    index_vault(vault, store, embed=False)
    assert any("/Sessions/" in p for p in store.indexed_paths())  # unrestricted brains do
    store.close()
