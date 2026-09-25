import pytest

from brain_rag.chunk import MAX_CHUNK_CHARS, chunk_note, should_skip

NOTE = """---
tags: [vol, risk]
---
# Positions

Intro line.

## Account B

Short call spread open.

### Stops

GTC at 0.15.

## Closed

Realized -$30.
"""


def test_splits_on_headings_level_two_and_deeper():
    chunks = chunk_note("Trading/Positions.md", NOTE, mtime=1_756_000_000.0)
    headings = [c.heading for c in chunks]
    assert "Account B" in headings
    assert "Stops" in headings
    assert "Closed" in headings


def test_every_chunk_carries_citation_metadata():
    for c in chunk_note("Trading/Positions.md", NOTE, mtime=1_756_000_000.0):
        assert c.path == "Trading/Positions.md"
        assert c.leg == "Trading"
        assert c.source == "note"
        assert c.date
        assert c.content_hash


def test_note_without_headings_is_one_chunk():
    chunks = chunk_note("Inbox.md", "just a line\n", mtime=1_756_000_000.0)
    assert len(chunks) == 1
    assert chunks[0].heading is None


def test_oversized_headingless_note_is_split_under_cap():
    body = "\n\n".join(["paragraph " + ("x" * 200) for _ in range(60)])
    chunks = chunk_note("Inbox.md", body, mtime=1_756_000_000.0)
    assert len(chunks) > 1
    assert all(len(c.text) <= MAX_CHUNK_CHARS for c in chunks)


def test_wikilinks_are_extracted_and_kept_in_text():
    chunks = chunk_note(
        "Development/Hermes.md",
        "## Links\n\nSee [[Jason]] and [[Local Qwen llama.cpp]].\n",
        mtime=1_756_000_000.0,
    )
    c = chunks[0]
    assert "[[Jason]]" in c.text
    assert set(c.wikilinks) == {"Jason", "Local Qwen llama.cpp"}


@pytest.mark.parametrize(
    "rel",
    [
        ".obsidian/workspace.json",
        ".git/config",
        "Attachments/photo.png",
        "Attachments/scan.pdf",
        "Development/notes.txt",
    ],
)
def test_skips_non_indexable_paths(rel):
    assert should_skip(rel) is True


def test_does_not_skip_real_notes():
    assert should_skip("Trading/Positions.md") is False
