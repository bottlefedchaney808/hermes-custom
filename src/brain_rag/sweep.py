"""Weekly sweep: older Hermes sessions become leg-scoped vault notes.

This is one of exactly two vault writers (spec section 5). It READS
``state.db`` and never deletes from it — ``hermes sessions prune`` deletes
transcripts and is not an intake path.
"""
from __future__ import annotations

import sqlite3
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from brain_rag.chunk import strip_tool_json
from brain_rag.leg import leg_for_cwd

DEFAULT_OLDER_THAN_DAYS = 7


def _run_git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True)


def session_note_path(leg: str, started: str, session_id: str) -> str:
    """``{Leg}/Sessions/YYYY-MM-DD-<short-id>.md`` (spec section 6)."""
    short = session_id.split("_")[-1]
    return f"{leg}/Sessions/{started}-{short}.md"


def render_session_note(
    *,
    session_id: str,
    leg: str,
    profile: str,
    started: str,
    source: str,
    title: str | None,
    turns: list[dict],
) -> str:
    """Frontmatter + user/assistant prose. Tool JSON is dropped."""
    lines = [
        "---",
        "type: session",
        f"leg: {leg}",
        f"profile: {profile}",
        f"session_id: {session_id}",
        f"started: {started}",
        f"source: {source}",
        "---",
        "",
        f"# {title or 'Session'} ({started})",
        "",
    ]
    for turn in turns:
        content = strip_tool_json(turn.get("content") or "")
        if not content:
            continue
        role = turn.get("role")
        if role == "user":
            lines += ["## User", "", content, ""]
        elif role == "assistant":
            lines += ["### Assistant", "", content, ""]
    return "\n".join(lines).rstrip() + "\n"


def sweep_sessions(
    state_db: str | Path,
    vault_dir: str | Path,
    *,
    older_than_days: float = DEFAULT_OLDER_THAN_DAYS,
    push: bool = True,
    runner: Callable[[list[str], Path], None] | None = None,
) -> dict[str, Any]:
    """Write ended sessions older than the window into the vault, then commit."""
    state_db = Path(state_db)
    vault = Path(vault_dir)
    git = runner or _run_git
    result: dict[str, Any] = {
        "sessions_swept": 0, "files_written": [], "pushed": False, "error": None,
    }
    if not state_db.exists():
        result["error"] = f"state.db not found: {state_db}"
        return result
    if not vault.is_dir():
        result["error"] = f"vault clone not found: {vault}"
        return result

    try:
        git(["pull", "--rebase"], vault)
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"vault pull failed: {exc}"
        return result

    cutoff = time.time() - older_than_days * 86400
    conn = sqlite3.connect(f"file:{state_db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """SELECT id, source, title, cwd, started_at, profile_name
               FROM sessions
               WHERE ended_at IS NOT NULL AND started_at < ?
               ORDER BY started_at""",
            (cutoff,),
        ).fetchall()
        for row in rows:
            turns = [
                dict(m) for m in conn.execute(
                    """SELECT role, content FROM messages
                       WHERE session_id = ? AND role IN ('user','assistant')
                       ORDER BY id""",
                    (row["id"],),
                ).fetchall()
            ]
            if not turns:
                continue
            leg = leg_for_cwd(row["cwd"])
            started = datetime.fromtimestamp(
                row["started_at"], tz=timezone.utc
            ).date().isoformat()
            rel = session_note_path(leg, started, row["id"])
            target = vault / rel
            if target.exists():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                render_session_note(
                    session_id=row["id"],
                    leg=leg,
                    profile=row["profile_name"] or "default",
                    started=started,
                    source=row["source"] or "unknown",
                    title=row["title"],
                    turns=turns,
                ),
                encoding="utf-8",
            )
            result["files_written"].append(rel)
            result["sessions_swept"] += 1
    finally:
        conn.close()

    if not result["files_written"]:
        return result

    try:
        git(["add", *result["files_written"]], vault)
        git(["commit", "-m", f"chore(vault): sweep {result['sessions_swept']} session(s)"], vault)
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"vault commit failed: {exc}"
        return result

    if push:
        try:
            git(["push"], vault)
            result["pushed"] = True
        except Exception as exc:  # noqa: BLE001
            # Commit stays local; the next run pushes it. Never a rollback.
            result["error"] = f"vault push failed (commit is local): {exc}"
    return result
