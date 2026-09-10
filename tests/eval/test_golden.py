import os
from pathlib import Path

import pytest

from brain_rag.index import index_vault
from brain_rag.leg import LEGS
from brain_rag.search import search
from brain_rag.store import Store

QUESTIONS = [
    "Why did I stop using strategy X?",
    "What are my strongest risk-management conclusions?",
    "What lessons repeatedly appear after losses?",
    "What indicators do I trust most?",
    "What recurring themes exist across successful trades?",
    "What mistakes do I repeatedly make?",
    "What are my best trading insights about volatility?",
    "How has my thinking on factor investing changed over time?",
    "What did I believe before drawdown Y?",
    "Find observations about earnings reactions.",
]


def _vault() -> Path:
    return Path(os.environ.get("OBSIDIAN_VAULT_PATH") or Path.home() / "obsidian-vault")


@pytest.fixture(scope="module")
def store(tmp_path_factory):
    vault = _vault()
    if not vault.is_dir():
        pytest.skip(f"No vault clone at {vault}")
    s = Store.open(tmp_path_factory.mktemp("eval") / "brain.sqlite")
    index_vault(vault, s)
    yield s
    s.close()


@pytest.mark.golden
@pytest.mark.parametrize("question", QUESTIONS)
def test_golden_question_returns_citable_hits(question, store):
    result = search(store, question, k=8)
    assert result["hits"], f"No hits for: {question}"
    for hit in result["hits"]:
        assert hit["path"], f"Missing citation path for: {question}"
        assert hit["heading"] or hit["session_id"]
        assert hit["date"]
        assert hit["leg"] in LEGS
