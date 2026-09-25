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
