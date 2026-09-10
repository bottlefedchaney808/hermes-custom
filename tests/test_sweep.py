import sqlite3
import time
from pathlib import Path

import pytest

from brain_rag.sweep import render_session_note, session_note_path, sweep_sessions


def _make_state_db(path: Path, *, age_days: float, cwd: str) -> str:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE sessions (
            id TEXT PRIMARY KEY, source TEXT, title TEXT, cwd TEXT,
            started_at REAL, ended_at REAL, archived INTEGER DEFAULT 0,
            profile_name TEXT
        );
        CREATE TABLE messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT,
            role TEXT, content TEXT, timestamp REAL
        );
        """
    )
    started = time.time() - age_days * 86400
    sid = "20260901_120000_abc123"
    conn.execute(
        "INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?)",
        (sid, "desktop", "Rate question", cwd, started, started + 600, 0, "default"),
    )
    for role, content in [
        ("user", "what is the burdened rate"),
        ("assistant", 'It is $58.40/hr.\n\n```json\n{"tool":"x"}\n```'),
    ]:
        conn.execute(
            "INSERT INTO messages(session_id, role, content, timestamp) VALUES (?,?,?,?)",
            (sid, role, content, started),
        )
    conn.commit()
    conn.close()
    return sid


@pytest.fixture()
def vault(tmp_path):
    v = tmp_path / "vault"
    for leg in ("Construction", "Development", "Trading"):
        (v / leg).mkdir(parents=True)
    return v


def test_session_note_path_is_leg_scoped():
    p = session_note_path("Trading", "2026-09-01", "20260901_120000_abc123")
    assert p == "Trading/Sessions/2026-09-01-abc123.md"


def test_render_includes_frontmatter_and_drops_tool_json():
    note = render_session_note(
        session_id="20260901_120000_abc123",
        leg="Development",
        profile="default",
        started="2026-09-01",
        source="desktop",
        title="Rate question",
        turns=[
            {"role": "user", "content": "q"},
            {"role": "assistant", "content": 'a\n\n```json\n{"tool":"x"}\n```'},
        ],
    )
    assert note.startswith("---\n")
    assert "type: session" in note
    assert "leg: Development" in note
    assert "session_id: 20260901_120000_abc123" in note
    assert '"tool"' not in note


def test_sweep_writes_note_into_the_cwd_derived_leg(tmp_path, vault):
    db = tmp_path / "state.db"
    _make_state_db(db, age_days=30, cwd="C:/Users/bottl/OneDrive/Work/Tiferet/job-1")
    calls = []
    result = sweep_sessions(db, vault, runner=lambda args, cwd: calls.append(args))
    written = Path(vault / "Construction/Sessions/2026-09-01-abc123.md")
    assert result["sessions_swept"] == 1
    assert written.exists() or list((vault / "Construction/Sessions").glob("*.md"))


def test_sweep_skips_sessions_newer_than_the_window(tmp_path, vault):
    db = tmp_path / "state.db"
    _make_state_db(db, age_days=1, cwd="C:/Users/bottl/hermes-custom")
    result = sweep_sessions(db, vault, older_than_days=7, runner=lambda args, cwd: None)
    assert result["sessions_swept"] == 0


def test_sweep_never_deletes_from_state_db(tmp_path, vault):
    db = tmp_path / "state.db"
    _make_state_db(db, age_days=30, cwd="C:/Users/bottl/hermes-custom")
    sweep_sessions(db, vault, runner=lambda args, cwd: None)
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 2
    conn.close()


def test_push_failure_leaves_commit_local_and_reports(tmp_path, vault):
    db = tmp_path / "state.db"
    _make_state_db(db, age_days=30, cwd="C:/Users/bottl/hermes-custom")

    def runner(args, cwd):
        if "push" in args:
            raise RuntimeError("no remote")

    result = sweep_sessions(db, vault, runner=runner)
    assert result["pushed"] is False
    assert result["error"]
    assert result["sessions_swept"] == 1
