import pytest

from brain_rag.remind import remind


@pytest.fixture()
def vault(tmp_path):
    v = tmp_path / "vault"
    for leg in ("Construction", "Development", "Trading"):
        (v / leg).mkdir(parents=True)
    return v


def test_writes_a_thin_note_into_the_named_leg(vault):
    result = remind(vault, leg="Trading", title="IV crush rule", body="Sell into events.",
                    runner=lambda args, cwd: None)
    assert result["path"] == "Trading/IV crush rule.md"
    text = (vault / result["path"]).read_text(encoding="utf-8")
    assert "leg: Trading" in text
    assert "Sell into events." in text


def test_missing_leg_is_refused(vault):
    result = remind(vault, leg="", title="x", body="y", runner=lambda args, cwd: None)
    assert result["error"]
    assert not list(vault.rglob("*.md"))


def test_unknown_leg_is_refused(vault):
    result = remind(vault, leg="Cooking", title="x", body="y", runner=lambda args, cwd: None)
    assert result["error"]
    assert not list(vault.rglob("*.md"))


def test_existing_note_is_appended_not_clobbered(vault):
    remind(vault, leg="Development", title="Note", body="first", runner=lambda a, c: None)
    remind(vault, leg="Development", title="Note", body="second", runner=lambda a, c: None)
    text = (vault / "Development/Note.md").read_text(encoding="utf-8")
    assert "first" in text and "second" in text
