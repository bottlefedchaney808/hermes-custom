import pytest

from brain_rag.leg import LEGS, leg_for_cwd, leg_for_vault_path


@pytest.mark.parametrize(
    "cwd,expected",
    [
        ("C:/Users/bottl/OneDrive/Work/Tiferet/job-5945", "Construction"),
        ("C:/Users/bottl/FinancialDevelopment/Vol_Suite", "Trading"),
        ("C:/Users/bottl/hermes-custom/RAG", "Development"),
        ("C:/Users/bottl/obsidian-vault", "Development"),
        (None, "Development"),
        ("", "Development"),
    ],
)
def test_leg_for_cwd(cwd, expected):
    assert leg_for_cwd(cwd) == expected


def test_legs_are_exactly_the_three():
    assert LEGS == ("Construction", "Development", "Trading")


@pytest.mark.parametrize(
    "rel,expected",
    [
        ("Trading/Positions.md", "Trading"),
        ("Development/Hermes.md", "Development"),
        ("Construction/Sessions/2026-09-01-abc.md", "Construction"),
        ("Inbox.md", None),
        ("Attachments/x.png", None),
    ],
)
def test_leg_for_vault_path(rel, expected):
    assert leg_for_vault_path(rel) == expected
