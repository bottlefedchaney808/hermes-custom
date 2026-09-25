"""Private notes are never indexed on any profile — reachable only by opening them by name."""
import shutil
from pathlib import Path

from brain_rag.index import index_vault
from brain_rag.store import Store

VAULT = Path(__file__).parent / "fixtures" / "vault"


def _vault(tmp_path):
    vault = tmp_path / "vault"
    shutil.copytree(VAULT, vault)
    (vault / "My debit card.md").write_text("# Card\n\nPAN 4111 1111 1111 1111\n", encoding="utf-8")
    (vault / "Construction" / "Secret bid.md").write_text(
        "---\ntype: note\nprivate: true\n---\n\n# Bid\n\nour margin is 31%\n", encoding="utf-8")
    return vault


def test_ragignore_and_private_frontmatter_are_never_indexed(tmp_path):
    vault = _vault(tmp_path)
    (vault / ".ragignore").write_text("# personal\nMy debit card.md\n", encoding="utf-8")
    store = Store.open(tmp_path / "brain.sqlite")
    result = index_vault(vault, store, embed=False)
    paths = store.indexed_paths()
    assert "My debit card.md" not in paths
    assert "Construction/Secret bid.md" not in paths
    assert "Construction/Tiferet.md" in paths
    assert result["files_private"] == 2
    store.close()


def test_marking_a_note_private_later_purges_it(tmp_path):
    vault = _vault(tmp_path)
    store = Store.open(tmp_path / "brain.sqlite")
    index_vault(vault, store, embed=False)
    assert "My debit card.md" in store.indexed_paths()
    (vault / ".ragignore").write_text("My debit*\n", encoding="utf-8")
    index_vault(vault, store, embed=False)
    assert "My debit card.md" not in store.indexed_paths()
    store.close()


def test_private_key_outside_frontmatter_does_not_hide_a_note(tmp_path):
    vault = _vault(tmp_path)
    (vault / "Development" / "Howto.md").write_text(
        "# Howto\n\nSet `private: true` in frontmatter to hide a note.\n", encoding="utf-8")
    store = Store.open(tmp_path / "brain.sqlite")
    index_vault(vault, store, embed=False)
    assert "Development/Howto.md" in store.indexed_paths()
    store.close()
