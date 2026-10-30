from brain_rag.chunk import chunk_session, strip_tool_json

TURNS = [
    {"role": "user", "content": "what is the burdened rate"},
    {"role": "assistant", "content": "It is $58.40/hr."},
    {"role": "user", "content": "and for overtime"},
    {"role": "assistant", "content": "$87.60/hr."},
]


def test_one_chunk_per_user_assistant_pair():
    chunks = chunk_session(
        "Construction/Sessions/2026-09-01-abc123.md",
        TURNS,
        leg="Construction",
        session_id="20260901_120000_abc123",
        started="2026-09-01",
    )
    assert len(chunks) == 2
    assert "burdened rate" in chunks[0].text
    assert "58.40" in chunks[0].text
    assert "overtime" in chunks[1].text


def test_session_chunks_carry_citation_metadata():
    for c in chunk_session(
        "Construction/Sessions/2026-09-01-abc123.md",
        TURNS,
        leg="Construction",
        session_id="20260901_120000_abc123",
        started="2026-09-01",
    ):
        assert c.source == "session"
        assert c.session_id == "20260901_120000_abc123"
        assert c.date == "2026-09-01"
        assert c.leg == "Construction"


def test_trailing_user_turn_without_reply_still_chunks():
    chunks = chunk_session(
        "Development/Sessions/2026-09-01-x.md",
        [{"role": "user", "content": "unanswered question"}],
        leg="Development",
        session_id="s1",
        started="2026-09-01",
    )
    assert len(chunks) == 1
    assert "unanswered question" in chunks[0].text


def test_strip_tool_json_removes_fenced_json_blocks():
    text = 'before\n\n```json\n{"tool": "x", "args": {"a": 1}}\n```\n\nafter'
    out = strip_tool_json(text)
    assert "before" in out
    assert "after" in out
    assert '"tool"' not in out


def test_strip_tool_json_keeps_prose_code_blocks():
    text = "```python\nprint('hi')\n```"
    assert "print('hi')" in strip_tool_json(text)


# --- size cap: the embedder rejects a request over its context limit, so one
# oversized chunk blocks the whole index. Every chunk must stay under the cap.

import re

from brain_rag.chunk import MAX_CHUNK_CHARS, chunk_note


def _session(user: str, assistant: str):
    return chunk_session(
        "Development/Sessions/2026-10-05-abc123.md",
        [{"role": "user", "content": user}, {"role": "assistant", "content": assistant}],
        leg="Development",
        session_id="20261005_000000_abc123",
        started="2026-10-05",
    )


def test_a_long_assistant_reply_is_split_under_the_cap():
    reply = "\n\n".join(f"paragraph {i} " + ("x" * 400) for i in range(200))  # ~80k chars
    chunks = _session("explain", reply)
    assert len(chunks) > 1
    assert all(len(c.text) <= MAX_CHUNK_CHARS for c in chunks)


def test_a_huge_user_turn_is_split_under_the_cap():
    chunks = _session("delegation result " + ("y" * 50_000), "ok")
    assert all(len(c.text) <= MAX_CHUNK_CHARS for c in chunks)


def test_splitting_a_turn_loses_no_text():
    reply = "\n\n".join(f"unique-marker-{i:04d} " + ("z" * 300) for i in range(120))
    joined = "\n".join(c.text for c in _session("q", reply))
    for i in range(120):
        assert f"unique-marker-{i:04d}" in joined


def test_every_piece_keeps_the_session_metadata_and_a_distinct_hash():
    reply = "\n\n".join("p" * 500 for _ in range(100))
    chunks = _session("q", reply)
    assert len(chunks) > 2
    assert {c.session_id for c in chunks} == {"20261005_000000_abc123"}
    assert {c.source for c in chunks} == {"session"}
    assert len({c.content_hash for c in chunks}) == len(chunks)  # UNIQUE column: no piece may collide


def test_a_normal_turn_is_still_one_chunk_with_the_same_text():
    chunks = _session("what is the rate", "It is $58.40/hr.")
    assert len(chunks) == 1
    assert chunks[0].text == "**User:** what is the rate\n\n**Assistant:** It is $58.40/hr."


def test_a_single_paragraph_longer_than_the_cap_is_hard_split_in_a_note():
    blob = "w" * (MAX_CHUNK_CHARS * 3 + 17)  # no blank lines: paragraph splitting cannot help
    chunks = chunk_note("Development/blob.md", f"# T\n\n{blob}\n", mtime=1_756_000_000.0)
    assert all(len(c.text) <= MAX_CHUNK_CHARS for c in chunks)
    assert sum(c.text.count("w") for c in chunks) == len(blob)  # nothing dropped


def test_hard_split_prefers_a_line_break_over_cutting_mid_word():
    line = "word " * 30 + "\n"
    blob = line * 200  # one 'paragraph' (no blank line), many lines
    chunks = chunk_note("Development/lines.md", f"# T\n\n{blob}", mtime=1_756_000_000.0)
    assert all(len(c.text) <= MAX_CHUNK_CHARS for c in chunks)
    for c in chunks:
        assert not re.search(r"wor$|wo$", c.text.rstrip())  # no mid-word cut when a newline was available
