#!/usr/bin/env python3
"""
Data extraction for /improve command.
Pre-processes conversation history, session data, git logs, and Claude artifacts
into compressed JSON summaries that fit in sub-agent context windows.

Usage: python3 improve-extract.py [--harness claude|codex] [--days 30] [--output-dir /tmp]
"""

import argparse
import json
import os
import re
import sqlite3
import subprocess
import tempfile
import tomllib
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

CLAUDE_DIR = Path.home() / ".claude"
HISTORY_FILE = CLAUDE_DIR / "history.jsonl"
PROJECTS_DIR = CLAUDE_DIR / "projects"
GIT_DIR = Path.home() / "git"
DOMAIN_DIR = CLAUDE_DIR / "domain"
COMMANDS_DIR = CLAUDE_DIR / "commands"
SKILLS_DIR = CLAUDE_DIR / "skills"
AGENTS_DIR = CLAUDE_DIR / "agents"
SETTINGS_FILE = CLAUDE_DIR / "settings.json"
HANDOFF_FILE = CLAUDE_DIR / "handoff.json"

CODEX_DIR = Path.home() / ".codex"
CODEX_HISTORY_FILE = CODEX_DIR / "history.jsonl"
CODEX_STATE_DB = CODEX_DIR / "state_5.sqlite"
CODEX_LOGS_DB = CODEX_DIR / "logs_2.sqlite"
MAX_CODEX_SESSION_FILES = 250
MAX_CODEX_HISTORY_LINE_BYTES = 262_144
MAX_CODEX_HISTORY_BYTES = 67_108_864
MAX_CODEX_JSONL_LINE_BYTES = 262_144
MAX_CODEX_SESSION_BYTES = 536_870_912
MAX_CODEX_ERROR_SAMPLE_TARGETS = 10
MAX_CODEX_ERROR_SAMPLES_PER_TARGET = 5
MAX_CODEX_CONFIG_JSON_CHARS = 32_000
MAX_CODEX_AGENT_CONFIG_JSON_CHARS = 8_000

ERROR_KEYWORDS = re.compile(
    r"\b(fix|broken|wrong|not working|again|revert|undo|debug|"
    r"that's not|no don't|stop|why did|error|fail|bug|issue|"
    r"doesn't work|can't|won't|shouldn't)\b",
    re.IGNORECASE,
)
FRUSTRATION_KEYWORDS = re.compile(
    r"^(no|stop|undo|wrong|that's wrong|not that|don't|nope|"
    r"revert|go back|start over)[\s.!]*$",
    re.IGNORECASE,
)
SLASH_CMD_RE = re.compile(r"^/(\S+)")
COMMIT_TYPE_RE = re.compile(r"^(\w+)(?:\(([^)]+)\))?:\s*(.+)")

CODEX_WORLD_STATE_LINE_RE = re.compile(rb'"type"\s*:\s*"world_state"')
CODEX_COMPACTED_LINE_RE = re.compile(rb'"type"\s*:\s*"(?:compacted|context_compacted)"')
ASSISTANT_ADMISSION_PHRASES = (
    "i apologize",
    "my mistake",
    "i was wrong",
    "let me correct",
    "sorry, i",
)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Extract bounded /improve inputs")
    parser.add_argument(
        "--harness",
        choices=("claude", "codex", "hermes"),
        default="claude",
        help="local harness data to extract (default: claude)",
    )
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--output-dir", type=Path, default=Path(".improve-data"))
    args = parser.parse_args(argv)
    if args.days < 1:
        parser.error("--days must be at least 1")
    return args


def normalize_project_path(path_value):
    if not path_value:
        return "unknown"
    value = str(path_value)
    git_prefix = str(Path.home() / "git") + "/"
    home_prefix = str(Path.home()) + "/"
    if value.startswith(git_prefix):
        return value[len(git_prefix) :]
    if value.startswith(home_prefix):
        return "~/" + value[len(home_prefix) :]
    return value


def structured_error(code, detail):
    return {"code": code, "detail": str(detail)}


def open_sqlite_readonly(path):
    db_path = Path(path)
    if not db_path.is_file():
        raise FileNotFoundError(db_path)
    return sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True)


@contextmanager
def open_sqlite_snapshot(path):
    """Open a read-only database and hold one explicit snapshot for related reads."""
    conn = open_sqlite_readonly(path)
    try:
        conn.execute("BEGIN")
        yield conn
    finally:
        if conn.in_transaction:
            conn.rollback()
        conn.close()


@contextmanager
def use_sqlite_snapshot(source):
    """Reuse a caller-owned snapshot or create one for a database path."""
    if isinstance(source, sqlite3.Connection):
        yield source
        return
    with open_sqlite_snapshot(source) as conn:
        yield conn


def extract_codex_history(
    cutoff_s,
    history_file,
    thread_index,
    max_line_bytes=MAX_CODEX_HISTORY_LINE_BYTES,
    max_total_bytes=MAX_CODEX_HISTORY_BYTES,
):
    """Extract bounded prompt signals from Codex history.jsonl."""
    history_path = Path(history_file)
    if not history_path.is_file():
        return {
            "harness": "codex",
            "error": structured_error("history_file_missing", history_path),
            "total_prompts": 0,
            "session_count": 0,
            "history_rows_considered": 0,
        }

    project_counts = Counter()
    error_prompts = []
    all_prompts = []
    command_usage = Counter()
    sessions = set()
    rows_considered = 0
    malformed_rows = 0
    invalid_utf8_rows = 0
    oversize_rows = 0
    oversize_bytes = 0
    bytes_read = 0
    history_size = 0
    max_line_bytes = max(1, int(max_line_bytes))
    max_total_bytes = max(0, int(max_total_bytes))

    try:
        history_size = history_path.stat().st_size
        with history_path.open("rb") as history:
            while bytes_read < history_size and bytes_read < max_total_bytes:
                remaining_budget = max_total_bytes - bytes_read
                raw_line = history.readline(min(max_line_bytes + 1, remaining_budget))
                if not raw_line:
                    break
                bytes_read += len(raw_line)
                if len(raw_line) > max_line_bytes or (
                    not raw_line.endswith(b"\n") and bytes_read < history_size
                ):
                    oversize_bytes_this_line = len(raw_line)
                    while (
                        not raw_line.endswith(b"\n")
                        and bytes_read < history_size
                        and bytes_read < max_total_bytes
                    ):
                        remaining_budget = max_total_bytes - bytes_read
                        continuation = history.readline(
                            min(max_line_bytes + 1, remaining_budget)
                        )
                        if not continuation:
                            break
                        bytes_read += len(continuation)
                        oversize_bytes_this_line += len(continuation)
                        raw_line = continuation
                    oversize_bytes += oversize_bytes_this_line
                    oversize_rows += 1
                    continue
                if not raw_line.strip():
                    continue
                rows_considered += 1
                try:
                    line = raw_line.decode("utf-8")
                except UnicodeDecodeError:
                    invalid_utf8_rows += 1
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    malformed_rows += 1
                    continue

                ts = entry.get("ts", 0)
                if not isinstance(ts, (int, float)) or ts < cutoff_s:
                    continue
                display = entry.get("text", "")
                if not isinstance(display, str):
                    continue
                display = _redact_sensitive_text(display.strip())
                if not display:
                    continue

                session_id = str(entry.get("session_id", ""))
                thread = thread_index.get(session_id, {})
                project = normalize_project_path(thread.get("cwd"))
                project_counts[project] += 1
                sessions.add(session_id)
                prompt = {"display": display[:300], "project": project, "ts": ts}
                all_prompts.append(prompt)

                cmd_match = SLASH_CMD_RE.match(display)
                if cmd_match:
                    command_usage[cmd_match.group(1)] += 1
                if ERROR_KEYWORDS.search(display):
                    error_prompts.append(prompt)

    except (OSError, PermissionError) as exc:
        return {
            "harness": "codex",
            "error": structured_error("history_read_failed", exc),
            "total_prompts": 0,
            "session_count": 0,
            "history_rows_considered": rows_considered,
        }

    prompt_prefixes = Counter()
    for prompt in all_prompts:
        prefix = prompt["display"][:50].lower().strip()
        if len(prefix) > 10:
            prompt_prefixes[prefix] += 1
    repeated = {key: count for key, count in prompt_prefixes.items() if count >= 3}
    error_sample_cap = 100
    error_samples_dropped = max(0, len(error_prompts) - error_sample_cap)
    project_groups_dropped = max(0, len(project_counts) - 20)
    repeated_groups_dropped = max(0, len(repeated) - 20)
    command_groups_dropped = max(0, len(command_usage) - 30)
    dropped_counts = {
        "error_prompt_samples": error_samples_dropped,
        "project_groups": project_groups_dropped,
        "repeated_prompt_groups": repeated_groups_dropped,
        "command_groups": command_groups_dropped,
        "history_bytes": max(0, history_size - bytes_read) + oversize_bytes,
        "oversize_rows": oversize_rows,
        "invalid_utf8_rows": invalid_utf8_rows,
    }

    return {
        "harness": "codex",
        "total_prompts": len(all_prompts),
        "project_counts": dict(project_counts.most_common(20)),
        "error_prompts": error_prompts[:error_sample_cap],
        "repeated_prompts": dict(
            sorted(repeated.items(), key=lambda item: -item[1])[:20]
        ),
        "command_usage": dict(command_usage.most_common(30)),
        "session_count": len(sessions),
        "history_rows_considered": rows_considered,
        "malformed_rows_skipped": malformed_rows,
        "invalid_utf8_rows_skipped": invalid_utf8_rows,
        "oversize_rows_skipped": oversize_rows,
        "history_byte_budget": max_total_bytes,
        "history_bytes_analyzed": bytes_read,
        "history_bytes_unread": max(0, history_size - bytes_read),
        "oversize_bytes_skipped": oversize_bytes,
        "history_bytes_dropped": max(0, history_size - bytes_read) + oversize_bytes,
        "truncated": any(dropped_counts.values()),
        "dropped_counts": dropped_counts,
    }


def _codex_source_sql():
    return """
        CASE
            WHEN thread_source IS NOT NULL AND thread_source <> '' THEN thread_source
            WHEN LOWER(TRIM(source)) = 'mcp' THEN 'mcp'
            WHEN source LIKE '%\"subagent\"%' THEN 'subagent'
            ELSE 'user'
        END
    """


def _rows_to_count_map(rows):
    return {str(key): int(count) for key, count in rows}


def extract_codex_state(cutoff_s, state_db):
    """Return aggregate-only Codex thread state from a read-only SQLite snapshot."""
    result = {
        "harness": "codex",
        "extracted_at": datetime.now(timezone.utc).isoformat(),
    }
    source_sql = _codex_source_sql()
    try:
        with use_sqlite_snapshot(state_db) as conn:
            total_row = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(tokens_used), 0) "
                "FROM threads WHERE created_at >= ?",
                (cutoff_s,),
            ).fetchone()
            result["threads_total"] = int(total_row[0])
            result["tokens_used_total"] = int(total_row[1])
            result["by_source"] = _rows_to_count_map(
                conn.execute(
                    f"SELECT {source_sql} AS source_kind, COUNT(*) "
                    "FROM threads WHERE created_at >= ? "
                    "GROUP BY source_kind ORDER BY COUNT(*) DESC, source_kind",
                    (cutoff_s,),
                ).fetchall()
            )
            result["by_model_effort"] = _rows_to_count_map(
                conn.execute(
                    "SELECT COALESCE(model, 'unknown') || '/' || "
                    "COALESCE(reasoning_effort, 'unknown') AS model_effort, COUNT(*) "
                    "FROM threads WHERE created_at >= ? "
                    "GROUP BY model_effort ORDER BY COUNT(*) DESC, model_effort",
                    (cutoff_s,),
                ).fetchall()
            )
            result["by_agent_role"] = _rows_to_count_map(
                conn.execute(
                    "SELECT COALESCE(NULLIF(agent_role, ''), 'root') AS role, COUNT(*) "
                    "FROM threads WHERE created_at >= ? "
                    "GROUP BY role ORDER BY COUNT(*) DESC, role",
                    (cutoff_s,),
                ).fetchall()
            )
            cwd_group_count = conn.execute(
                "SELECT COUNT(*) FROM ("
                "SELECT cwd FROM threads WHERE created_at >= ? GROUP BY cwd"
                ")",
                (cutoff_s,),
            ).fetchone()[0]
            cwd_rows = conn.execute(
                "SELECT cwd, COUNT(*) FROM threads WHERE created_at >= ? "
                "GROUP BY cwd ORDER BY COUNT(*) DESC, cwd LIMIT 100",
                (cutoff_s,),
            ).fetchall()
            cwd_dropped = max(0, int(cwd_group_count) - len(cwd_rows))
            result["by_cwd"] = {
                normalize_project_path(cwd): int(count) for cwd, count in cwd_rows[:100]
            }
            result["truncated"] = cwd_dropped > 0
            result["dropped_counts"] = {"cwd_groups": cwd_dropped}
    except FileNotFoundError as exc:
        result.update(
            {
                "error": structured_error("state_db_missing", exc),
                "threads_total": 0,
                "tokens_used_total": 0,
            }
        )
    except (sqlite3.Error, OSError) as exc:
        result.update(
            {
                "error": structured_error("state_query_failed", exc),
                "threads_total": 0,
                "tokens_used_total": 0,
            }
        )
    return result


def load_codex_thread_rows(cutoff_s, state_db, max_rows=MAX_CODEX_SESSION_FILES):
    """Load only the newest root/user rollout locators needed for session inspection."""
    source_sql = _codex_source_sql()
    max_rows = max(0, int(max_rows))
    try:
        with use_sqlite_snapshot(state_db) as conn:
            eligible_count = conn.execute(
                f"SELECT COUNT(*) FROM threads WHERE created_at >= ? "
                f"AND ({source_sql}) = 'user'",
                (cutoff_s,),
            ).fetchone()[0]
            cursor = conn.execute(
                f"SELECT id, rollout_path, created_at, {source_sql} AS thread_source, cwd "
                "FROM threads WHERE created_at >= ? "
                f"AND ({source_sql}) = 'user' "
                "ORDER BY created_at DESC, id DESC LIMIT ?",
                (cutoff_s, max_rows),
            )
            columns = [column[0] for column in cursor.description]
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
            return {
                "rows": rows,
                "eligible_count": int(eligible_count),
                "dropped": max(0, int(eligible_count) - len(rows)),
            }
    except FileNotFoundError as exc:
        return {
            "rows": [],
            "eligible_count": 0,
            "dropped": 0,
            "error": structured_error("state_db_missing", exc),
        }
    except (sqlite3.Error, OSError) as exc:
        return {
            "rows": [],
            "eligible_count": 0,
            "dropped": 0,
            "error": structured_error("thread_index_query_failed", exc),
        }


def extract_codex_logs(cutoff_s, logs_db):
    """Aggregate bounded Codex log telemetry from a read-only SQLite snapshot."""
    result = {
        "harness": "codex",
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "rows_by_level": {},
        "warning_error_by_target": {},
        "error_samples": {},
        "reducer_drops": {
            "tool_item_event_dropped": 0,
            "turn_tool_count_dropped": 0,
            "turn_analytics_event_dropped": 0,
        },
        "rollout_reconstruction_warnings": 0,
        "analytics_counts_lower_bound": False,
        "truncated": False,
        "dropped_counts": {},
    }
    try:
        with use_sqlite_snapshot(logs_db) as conn:
            result["rows_by_level"] = _rows_to_count_map(
                conn.execute(
                    "SELECT UPPER(level), COUNT(*) FROM logs WHERE ts >= ? "
                    "GROUP BY UPPER(level) ORDER BY COUNT(*) DESC, UPPER(level)",
                    (cutoff_s,),
                ).fetchall()
            )
            target_group_count = conn.execute(
                "SELECT COUNT(*) FROM ("
                "SELECT target FROM logs WHERE ts >= ? "
                "AND UPPER(level) IN ('WARN', 'WARNING', 'ERROR') GROUP BY target"
                ")",
                (cutoff_s,),
            ).fetchone()[0]
            target_rows = conn.execute(
                "SELECT target, COUNT(*) FROM logs WHERE ts >= ? "
                "AND UPPER(level) IN ('WARN', 'WARNING', 'ERROR') "
                "GROUP BY target ORDER BY COUNT(*) DESC, target LIMIT 20",
                (cutoff_s,),
            ).fetchall()
            target_groups_dropped = max(0, int(target_group_count) - len(target_rows))
            result["warning_error_by_target"] = _rows_to_count_map(target_rows)

            body = "LOWER(COALESCE(feedback_log_body, ''))"
            drop_row = conn.execute(
                f"""
                SELECT
                    COALESCE(SUM(CASE WHEN {body} LIKE '%tool item event dropped%'
                        OR {body} LIKE '%tool_item_event%dropped%' THEN 1 ELSE 0 END), 0),
                    COALESCE(SUM(CASE WHEN {body} LIKE '%turn tool count dropped%'
                        OR {body} LIKE '%turn_tool_count%dropped%' THEN 1 ELSE 0 END), 0),
                    COALESCE(SUM(CASE WHEN {body} LIKE '%turn analytics event dropped%'
                        OR {body} LIKE '%turn_analytics_event%dropped%' THEN 1 ELSE 0 END), 0),
                    COALESCE(SUM(CASE WHEN UPPER(level) IN ('WARN', 'WARNING', 'ERROR')
                        AND ({body} LIKE '%rollout reconstruction warning%'
                            OR {body} LIKE '%failed to reconstruct rollout%')
                        THEN 1 ELSE 0 END), 0)
                FROM logs WHERE ts >= ?
                """,
                (cutoff_s,),
            ).fetchone()
            result["reducer_drops"] = {
                "tool_item_event_dropped": int(drop_row[0]),
                "turn_tool_count_dropped": int(drop_row[1]),
                "turn_analytics_event_dropped": int(drop_row[2]),
            }
            result["rollout_reconstruction_warnings"] = int(drop_row[3])
            result["analytics_counts_lower_bound"] = any(
                result["reducer_drops"].values()
            )

            warning_error_total = conn.execute(
                "SELECT COUNT(*) FROM logs WHERE ts >= ? "
                "AND UPPER(level) IN ('WARN', 'WARNING', 'ERROR')",
                (cutoff_s,),
            ).fetchone()[0]
            sample_targets = [target for target, _ in target_rows][
                :MAX_CODEX_ERROR_SAMPLE_TARGETS
            ]
            if sample_targets:
                placeholders = ", ".join("?" for _ in sample_targets)
                sample_rows = conn.execute(
                    f"""
                    WITH ranked AS (
                        SELECT
                            target,
                            SUBSTR(REPLACE(REPLACE(
                                COALESCE(feedback_log_body, ''), CHAR(10), ' '
                            ), CHAR(13), ' '), 1, 240) AS snippet,
                            ROW_NUMBER() OVER (
                                PARTITION BY target ORDER BY ts DESC, id DESC
                            ) AS sample_rank
                        FROM logs
                        WHERE ts >= ?
                          AND UPPER(level) IN ('WARN', 'WARNING', 'ERROR')
                          AND target IN ({placeholders})
                    )
                    SELECT target, snippet
                    FROM ranked
                    WHERE sample_rank <= ?
                    ORDER BY target, sample_rank
                    """,
                    (
                        cutoff_s,
                        *sample_targets,
                        MAX_CODEX_ERROR_SAMPLES_PER_TARGET,
                    ),
                ).fetchall()
            else:
                sample_rows = []
            samples = defaultdict(list)
            for target, snippet in sample_rows:
                if (
                    len(samples) >= MAX_CODEX_ERROR_SAMPLE_TARGETS
                    and target not in samples
                ):
                    continue
                if len(samples[target]) < MAX_CODEX_ERROR_SAMPLES_PER_TARGET:
                    samples[target].append(
                        _redact_sensitive_text((snippet or "").strip())
                    )
            result["error_samples"] = dict(samples)
            samples_kept = sum(len(values) for values in samples.values())
            samples_dropped = max(0, int(warning_error_total) - samples_kept)
            result["dropped_counts"] = {
                "warning_error_target_groups": target_groups_dropped,
                "warning_error_samples": samples_dropped,
            }
            result["truncated"] = any(result["dropped_counts"].values())
    except FileNotFoundError as exc:
        result["error"] = structured_error("logs_db_missing", exc)
    except (sqlite3.Error, OSError) as exc:
        result["error"] = structured_error("logs_query_failed", exc)
    return result


def extract_history(cutoff_ms):
    """Extract user prompts from history.jsonl, filtered by timestamp."""
    if not HISTORY_FILE.exists():
        return {"error": "history.jsonl not found"}

    project_counts = Counter()
    error_prompts = []
    all_prompts = []
    command_usage = Counter()
    session_topics = defaultdict(list)

    with open(HISTORY_FILE) as f:
        for line in f:
            try:
                entry = json.loads(line.strip())
            except json.JSONDecodeError:
                continue

            ts = entry.get("timestamp", 0)
            if ts < cutoff_ms:
                continue

            display = entry.get("display", "").strip()
            project = entry.get("project", "unknown")
            session_id = entry.get("sessionId", "")

            # Normalize project path
            project = project.replace(str(Path.home() / "git") + "/", "").replace(
                str(Path.home()) + "/", ""
            )

            if not display or len(display) < 3:
                continue

            project_counts[project] += 1
            all_prompts.append({"display": display[:300], "project": project, "ts": ts})

            # Slash commands
            cmd_match = SLASH_CMD_RE.match(display)
            if cmd_match:
                command_usage[cmd_match.group(1)] += 1

            # Error keywords
            if ERROR_KEYWORDS.search(display):
                error_prompts.append(
                    {"display": display[:300], "project": project, "ts": ts}
                )

            # Track topics per session
            session_topics[session_id].append(display[:100])

    # Detect repeated prompts (fuzzy: same first 50 chars)
    prompt_prefixes = Counter()
    for p in all_prompts:
        prefix = p["display"][:50].lower().strip()
        if len(prefix) > 10:
            prompt_prefixes[prefix] += 1
    repeated = {k: v for k, v in prompt_prefixes.items() if v >= 3}

    return {
        "total_prompts": len(all_prompts),
        "project_counts": dict(project_counts.most_common(20)),
        "error_prompts": error_prompts[:100],  # Cap at 100
        "repeated_prompts": dict(sorted(repeated.items(), key=lambda x: -x[1])[:20]),
        "command_usage": dict(command_usage.most_common(30)),
        "session_count": len(session_topics),
    }


def extract_sessions(cutoff_iso, max_per_project=3):
    """Extract key signals from session JSONL files (full conversations)."""
    if not PROJECTS_DIR.exists():
        return {"error": "projects dir not found"}

    tool_failures = Counter()
    tool_failure_samples: dict[str, list[dict]] = defaultdict(list)
    user_corrections = []
    assistant_errors = []
    topics_by_project = {}

    for project_dir in sorted(PROJECTS_DIR.iterdir()):
        if not project_dir.is_dir():
            continue

        project_name = project_dir.name.replace("-home-rj-git-", "").replace(
            "-home-rj-", "~/"
        )

        # Find JSONL files, sorted by modification time (newest first)
        jsonl_files = sorted(
            project_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True
        )

        # Only process the N most recent sessions
        session_files = jsonl_files[:max_per_project]
        project_topics = []

        for session_file in session_files:
            try:
                with open(session_file) as f:
                    lines = f.readlines()
            except (OSError, PermissionError):
                continue

            session_user_msgs = []
            prev_was_long_assistant = False
            tool_use_name_by_id: dict[str, str] = {}

            for line in lines:
                try:
                    entry = json.loads(line.strip())
                except json.JSONDecodeError:
                    continue

                # Check timestamp cutoff
                ts_str = entry.get("timestamp", "")
                if isinstance(ts_str, str) and ts_str:
                    try:
                        entry_time = datetime.fromisoformat(
                            ts_str.replace("Z", "+00:00")
                        )
                        cutoff_time = datetime.fromisoformat(cutoff_iso)
                        if entry_time < cutoff_time:
                            continue
                    except (ValueError, TypeError):
                        pass

                entry_type = entry.get("type", "")

                # Tool failures — newer Claude Code stores tool_result inside a
                # user-typed entry's message.content list, not as a top-level type.
                # Handle both shapes.
                def _scan_tool_result_block(block):
                    if not isinstance(block, dict):
                        return
                    if block.get("type") != "tool_result":
                        return
                    is_error = block.get("is_error", False)
                    content = block.get("content", "")
                    # Tool result content can be a string OR a list of {type, text} parts
                    if isinstance(content, list):
                        content = " ".join(
                            p.get("text", "")
                            for p in content
                            if isinstance(p, dict) and p.get("type") == "text"
                        )
                    if not isinstance(content, str):
                        return
                    lowered = content.lower()
                    looks_failed = is_error or any(
                        kw in lowered
                        for kw in ["error", "failed", "exception", "traceback"]
                    )
                    if not looks_failed:
                        return
                    tool_use_id = block.get("tool_use_id", "")
                    tool_name = tool_use_name_by_id.get(tool_use_id, "unknown")
                    tool_failures[tool_name] += 1
                    # F (sample failure content per tool, cap 5 per tool to keep payload small)
                    if len(tool_failure_samples[tool_name]) < 5:
                        snippet = content[:240].replace("\n", " ").strip()
                        tool_failure_samples[tool_name].append(
                            {
                                "snippet": snippet,
                                "project": project_name,
                                "session": session_file.stem[:8],
                            }
                        )

                if entry_type == "tool_result":
                    # Legacy shape — keep working.
                    content = entry.get("content", "")
                    if isinstance(content, str) and any(
                        kw in content.lower()
                        for kw in ["error", "failed", "exception", "traceback"]
                    ):
                        tool_name = entry.get("tool_name", "unknown")
                        tool_failures[tool_name] += 1
                elif entry_type == "user":
                    msg = entry.get("message", {})
                    content = msg.get("content", "")
                    if isinstance(content, list):
                        for block in content:
                            _scan_tool_result_block(block)

                # User messages - check for corrections
                if entry_type == "user":
                    msg = entry.get("message", {})
                    content = msg.get("content", "")
                    if isinstance(content, str):
                        text = content[:200]
                        session_user_msgs.append(text)

                        # Short correction after long assistant response
                        if prev_was_long_assistant and FRUSTRATION_KEYWORDS.match(
                            text.strip()
                        ):
                            user_corrections.append(
                                {
                                    "text": text[:100],
                                    "project": project_name,
                                    "session": session_file.stem[:8],
                                }
                            )
                    elif isinstance(content, list):
                        # Multi-part content
                        for part in content:
                            if isinstance(part, dict) and part.get("type") == "text":
                                text = part.get("text", "")[:200]
                                if (
                                    prev_was_long_assistant
                                    and FRUSTRATION_KEYWORDS.match(text.strip())
                                ):
                                    user_corrections.append(
                                        {
                                            "text": text[:100],
                                            "project": project_name,
                                            "session": session_file.stem[:8],
                                        }
                                    )

                    prev_was_long_assistant = False

                # Assistant messages - track length for frustration detection
                # AND build tool_use_id -> tool_name map for failure attribution.
                if entry_type == "assistant":
                    msg = entry.get("message", {})
                    content = msg.get("content", "")
                    if isinstance(content, str):
                        prev_was_long_assistant = len(content) > 500
                    elif isinstance(content, list):
                        total_len = sum(
                            len(p.get("text", ""))
                            for p in content
                            if isinstance(p, dict)
                        )
                        prev_was_long_assistant = total_len > 500
                        for part in content:
                            if (
                                isinstance(part, dict)
                                and part.get("type") == "tool_use"
                                and part.get("id")
                            ):
                                tool_use_name_by_id[part["id"]] = part.get(
                                    "name", "unknown"
                                )

                    # Check for assistant self-corrections / error admissions
                    if isinstance(content, str) and any(
                        phrase in content.lower()
                        for phrase in [
                            "i apologize",
                            "my mistake",
                            "i was wrong",
                            "let me correct",
                            "sorry, i",
                        ]
                    ):
                        assistant_errors.append(
                            {
                                "snippet": content[:150],
                                "project": project_name,
                                "session": session_file.stem[:8],
                            }
                        )

            # Extract session topic from first substantial user message
            for msg in session_user_msgs:
                if len(msg) > 20 and not msg.startswith("/"):
                    project_topics.append(msg[:100])
                    break

        if project_topics:
            topics_by_project[project_name] = project_topics

    return {
        "tool_failures": dict(tool_failures.most_common(20)),
        "tool_failure_samples": {
            k: tool_failure_samples[k] for k, _ in tool_failures.most_common(10)
        },
        "user_corrections": user_corrections[:50],
        "assistant_errors": assistant_errors[:30],
        "topics_by_project": topics_by_project,
        "sessions_analyzed": sum(
            min(len(list(d.glob("*.jsonl"))), max_per_project)
            for d in PROJECTS_DIR.iterdir()
            if d.is_dir()
        ),
    }


def _codex_message_text(payload):
    if not isinstance(payload, dict) or payload.get("type") != "message":
        return ""
    content = payload.get("content", [])
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = []
    for part in content:
        if not isinstance(part, dict):
            continue
        text = part.get("text")
        if isinstance(text, str) and part.get("type") in {
            "input_text",
            "output_text",
            "text",
        }:
            parts.append(text)
    return "\n".join(parts)


def _codex_tool_output_text(output):
    if not isinstance(output, str):
        return json.dumps(output, default=str)
    try:
        parsed = json.loads(output)
    except json.JSONDecodeError:
        return output
    if isinstance(parsed, list):
        parts = [
            item.get("text", "")
            for item in parsed
            if isinstance(item, dict) and isinstance(item.get("text"), str)
        ]
        if parts:
            return "\n".join(parts)
    if isinstance(parsed, dict):
        content = parsed.get("content")
        if isinstance(content, list):
            parts = [
                item.get("text", "")
                for item in content
                if isinstance(item, dict) and isinstance(item.get("text"), str)
            ]
            if parts:
                return "\n".join(parts)
    return output


def _codex_tool_output_failed(output):
    raw = output if isinstance(output, str) else json.dumps(output, default=str)
    if re.search(r'"?isError"?\s*[:=]\s*true', raw, re.IGNORECASE):
        return True
    if re.search(r"\bexit_code\s*[:=]\s*[1-9]\d*\b", raw, re.IGNORECASE):
        return True
    if re.search(
        r"\bprocess exited with (?:status|code) [1-9]\d*\b", raw, re.IGNORECASE
    ):
        return True
    rendered = _codex_tool_output_text(output).strip()
    if "Script failed" in rendered:
        return True
    return rendered.startswith(
        ("Error:", "Exception:", "Traceback (most recent call last):")
    )


def _codex_thread_is_user(thread):
    source = str(thread.get("thread_source") or "").strip().lower()
    if source:
        return source == "user"
    raw_source = str(thread.get("source") or "")
    return '"subagent"' not in raw_source


def extract_codex_sessions(
    cutoff_s,
    thread_rows,
    max_files=MAX_CODEX_SESSION_FILES,
    max_line_bytes=MAX_CODEX_JSONL_LINE_BYTES,
    max_total_bytes=MAX_CODEX_SESSION_BYTES,
    eligible_count=None,
):
    """Extract bounded correction and failure signals from root/user rollouts."""
    eligible = [
        row
        for row in thread_rows
        if int(row.get("created_at") or 0) >= cutoff_s
        and _codex_thread_is_user(row)
        and row.get("rollout_path")
    ]
    eligible.sort(
        key=lambda row: (int(row.get("created_at") or 0), str(row.get("id") or "")),
        reverse=True,
    )
    max_files = max(0, int(max_files))
    max_line_bytes = max(1, int(max_line_bytes))
    max_total_bytes = max(0, int(max_total_bytes))
    selected = eligible[:max_files]
    considered = max(len(eligible), int(eligible_count or 0))
    file_cap_dropped = max(0, considered - len(selected))

    tool_failures = Counter()
    tool_failure_samples = defaultdict(list)
    user_corrections = []
    assistant_errors = []
    topics_by_project = defaultdict(list)
    sessions_analyzed = 0
    missing_session_files = 0
    unreadable_session_files = 0
    world_state_lines_skipped = 0
    compacted_lines_skipped = 0
    malformed_lines_skipped = 0
    oversize_lines_skipped = 0
    correction_samples_dropped = 0
    assistant_error_samples_dropped = 0
    tool_failure_samples_dropped = 0
    session_byte_budget_files = 0
    session_byte_budget_bytes = 0
    session_bytes_considered = 0
    session_bytes_analyzed = 0
    session_bytes_unavailable = 0

    selected_for_read = []
    remaining_byte_budget = max_total_bytes
    byte_budget_exhausted = False
    for thread in selected:
        session_file = Path(str(thread["rollout_path"]))
        try:
            if not session_file.is_file():
                missing_session_files += 1
                continue
            session_size = session_file.stat().st_size
        except OSError:
            unreadable_session_files += 1
            continue

        session_bytes_considered += session_size
        if byte_budget_exhausted or session_size > remaining_byte_budget:
            byte_budget_exhausted = True
            session_byte_budget_files += 1
            session_byte_budget_bytes += session_size
            continue
        selected_for_read.append((thread, session_size))
        remaining_byte_budget -= session_size

    for thread, session_size in selected_for_read:
        session_file = Path(str(thread["rollout_path"]))
        project_name = normalize_project_path(thread.get("cwd"))
        session_label = str(thread.get("id") or session_file.stem)[:8]
        prev_was_long_assistant = False
        first_topic_captured = False
        tool_name_by_call_id = {}
        bytes_read_this_file = 0

        try:
            with session_file.open("rb") as rollout:
                sessions_analyzed += 1
                while bytes_read_this_file < session_size:
                    bytes_remaining = session_size - bytes_read_this_file
                    raw_line = rollout.readline(
                        min(max_line_bytes + 1, bytes_remaining)
                    )
                    if not raw_line:
                        break
                    bytes_read_this_file += len(raw_line)
                    if len(raw_line) > max_line_bytes:
                        while (
                            not raw_line.endswith(b"\n")
                            and bytes_read_this_file < session_size
                        ):
                            bytes_remaining = session_size - bytes_read_this_file
                            continuation = rollout.readline(
                                min(max_line_bytes + 1, bytes_remaining)
                            )
                            if not continuation:
                                break
                            bytes_read_this_file += len(continuation)
                            if continuation.endswith(b"\n"):
                                break
                        oversize_lines_skipped += 1
                        continue
                    if CODEX_WORLD_STATE_LINE_RE.search(raw_line):
                        world_state_lines_skipped += 1
                        continue
                    if CODEX_COMPACTED_LINE_RE.search(raw_line):
                        compacted_lines_skipped += 1
                        continue
                    try:
                        entry = json.loads(raw_line.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        malformed_lines_skipped += 1
                        continue

                    if entry.get("type") != "response_item":
                        continue
                    payload = entry.get("payload", {})
                    payload_type = (
                        payload.get("type") if isinstance(payload, dict) else ""
                    )

                    if payload_type == "custom_tool_call":
                        call_id = payload.get("call_id") or payload.get("id")
                        if call_id:
                            tool_name_by_call_id[str(call_id)] = str(
                                payload.get("name") or "unknown"
                            )
                        continue

                    if payload_type == "custom_tool_call_output":
                        output = payload.get("output", "")
                        rendered_output = _codex_tool_output_text(output)
                        if _codex_tool_output_failed(output):
                            call_id = str(payload.get("call_id") or "")
                            tool_name = tool_name_by_call_id.get(call_id, "unknown")
                            tool_failures[tool_name] += 1
                            if len(tool_failure_samples[tool_name]) < 5:
                                tool_failure_samples[tool_name].append(
                                    {
                                        "snippet": _redact_sensitive_text(
                                            rendered_output[:240]
                                        )
                                        .replace("\n", " ")
                                        .replace("\r", " ")
                                        .strip(),
                                        "project": project_name,
                                        "session": session_label,
                                    }
                                )
                            else:
                                tool_failure_samples_dropped += 1
                        continue

                    text = _codex_message_text(payload)
                    role = payload.get("role") if isinstance(payload, dict) else None
                    if role == "assistant":
                        prev_was_long_assistant = len(text) > 500
                        if text and any(
                            phrase in text.lower()
                            for phrase in ASSISTANT_ADMISSION_PHRASES
                        ):
                            if len(assistant_errors) < 30:
                                assistant_errors.append(
                                    {
                                        "snippet": _redact_sensitive_text(text[:150]),
                                        "project": project_name,
                                        "session": session_label,
                                    }
                                )
                            else:
                                assistant_error_samples_dropped += 1
                        continue

                    if role != "user" or not text:
                        continue
                    stripped = text.strip()
                    if prev_was_long_assistant and FRUSTRATION_KEYWORDS.match(stripped):
                        if len(user_corrections) < 50:
                            user_corrections.append(
                                {
                                    "text": stripped[:100],
                                    "project": project_name,
                                    "session": session_label,
                                }
                            )
                        else:
                            correction_samples_dropped += 1
                    if (
                        not first_topic_captured
                        and len(stripped) > 20
                        and not stripped.startswith("/")
                    ):
                        topics_by_project[project_name].append(stripped[:100])
                        first_topic_captured = True
                    prev_was_long_assistant = False
        except (OSError, PermissionError):
            unreadable_session_files += 1
        session_bytes_analyzed += bytes_read_this_file
        session_bytes_unavailable += max(0, session_size - bytes_read_this_file)

    session_files_dropped = file_cap_dropped + session_byte_budget_files
    session_bytes_dropped = session_byte_budget_bytes + session_bytes_unavailable

    dropped_counts = {
        "session_files": session_files_dropped,
        "session_file_cap": file_cap_dropped,
        "session_byte_budget_files": session_byte_budget_files,
        "session_byte_budget_bytes": session_byte_budget_bytes,
        "session_bytes": session_bytes_dropped,
        "missing_session_files": missing_session_files,
        "unreadable_session_files": unreadable_session_files,
        "world_state_lines": world_state_lines_skipped,
        "compacted_lines": compacted_lines_skipped,
        "malformed_lines": malformed_lines_skipped,
        "oversize_lines": oversize_lines_skipped,
        "user_correction_samples": correction_samples_dropped,
        "assistant_error_samples": assistant_error_samples_dropped,
        "tool_failure_samples": tool_failure_samples_dropped,
        "tool_failure_groups": max(0, len(tool_failures) - 20),
        "tool_failure_sample_groups": max(0, len(tool_failures) - 10),
    }
    result = {
        "harness": "codex",
        "tool_failures": dict(tool_failures.most_common(20)),
        "tool_failure_samples": {
            name: tool_failure_samples[name]
            for name, _ in tool_failures.most_common(10)
        },
        "user_corrections": user_corrections,
        "assistant_errors": assistant_errors,
        "topics_by_project": dict(topics_by_project),
        "sessions_analyzed": sessions_analyzed,
        "session_files_considered": considered,
        "session_files_analyzed": sessions_analyzed,
        "session_files_dropped": session_files_dropped,
        "session_byte_budget": max_total_bytes,
        "session_bytes_considered": session_bytes_considered,
        "session_bytes_analyzed": session_bytes_analyzed,
        "session_bytes_dropped": session_bytes_dropped,
        "world_state_lines_skipped": world_state_lines_skipped,
        "compacted_lines_skipped": compacted_lines_skipped,
        "malformed_lines_skipped": malformed_lines_skipped,
        "oversize_lines_skipped": oversize_lines_skipped,
        "truncated": any(dropped_counts.values()),
        "dropped_counts": dropped_counts,
    }
    if selected and sessions_analyzed == 0:
        if missing_session_files == len(selected):
            result["error"] = structured_error(
                "session_files_missing",
                f"{missing_session_files} selected rollout files were missing",
            )
        elif unreadable_session_files:
            result["error"] = structured_error(
                "session_files_unreadable",
                f"{unreadable_session_files} selected rollout files were unreadable",
            )
    return result


REVERT_SHAPED_RE = re.compile(
    r"(post-#\d+\s+audit|missed\s+in\s+#\d+|revert|undo)", re.IGNORECASE
)


def extract_git(cutoff_date, days=30):
    """Extract git logs from all repos, categorized by type."""
    if not GIT_DIR.exists():
        return {"error": "git dir not found"}

    repo_activity = {}
    fix_hotspots: dict[str, dict] = {}
    revert_patterns = []

    for repo_dir in sorted(GIT_DIR.iterdir()):
        git_dir = repo_dir / ".git"
        if not git_dir.exists():
            continue

        repo_name = repo_dir.name

        try:
            result = subprocess.run(
                [
                    "git",
                    "log",
                    f"--since={cutoff_date}",
                    "--format=%ai|%s",
                    "--no-merges",
                ],
                cwd=str(repo_dir),
                capture_output=True,
                text=True,
                timeout=10,
            )
            lines = [
                line.strip()
                for line in result.stdout.strip().split("\n")
                if line.strip()
            ]
        except (subprocess.TimeoutExpired, FileNotFoundError):
            continue

        if not lines:
            continue

        commits = []
        type_counts = Counter()
        prev_msg = ""

        for line in lines:
            parts = line.split("|", 1)
            if len(parts) != 2:
                continue
            date_str, msg = parts

            # Categorize commit
            type_match = COMMIT_TYPE_RE.match(msg)
            if type_match:
                ctype = type_match.group(1).lower()
                scope = type_match.group(2) or ""
            else:
                ctype = "other"
                scope = ""

            type_counts[ctype] += 1
            commits.append({"date": date_str[:10], "type": ctype, "msg": msg[:120]})

            # Track fix hotspots by scope
            key = f"{repo_name}/{scope}" if scope else repo_name
            if key not in fix_hotspots:
                fix_hotspots[key] = {"fixes": 0, "total": 0, "messages": []}
            fix_hotspots[key]["total"] += 1
            if ctype == "fix":
                fix_hotspots[key]["fixes"] += 1
                fix_hotspots[key]["messages"].append(msg[:80])

            # Detect reverts AND revert-shaped fixes (post-#N audit / missed in #N)
            if REVERT_SHAPED_RE.search(msg):
                revert_patterns.append(
                    {"repo": repo_name, "msg": msg[:120], "prev": prev_msg[:120]}
                )

            prev_msg = msg

        repo_activity[repo_name] = {
            "total_commits": len(commits),
            "type_breakdown": dict(type_counts),
            "recent_commits": commits[:10],  # Last 10 only
        }

    # Filter fix hotspots — window-aware threshold so short (2-7d) windows aren't
    # silently empty. 2-7d window → >=2 fixes; longer windows → >=3 fixes.
    fixes_threshold = 2 if days <= 7 else 3
    significant_hotspots = {
        k: v
        for k, v in fix_hotspots.items()
        if v["fixes"] >= fixes_threshold
        and v["total"] > 0
        and v["fixes"] / v["total"] > 0.3
    }
    # Truncate messages lists
    for v in significant_hotspots.values():
        v["messages"] = v["messages"][:5]

    return {
        "repo_activity": repo_activity,
        "fix_hotspots": significant_hotspots,
        "revert_patterns": revert_patterns[:20],
        "total_repos": len(repo_activity),
        "total_commits": sum(r["total_commits"] for r in repo_activity.values()),
    }


def extract_artifacts():
    """Inventory all Claude configuration artifacts."""

    # CLAUDE.md files
    claude_md_files = {}
    for md_file in GIT_DIR.rglob("CLAUDE.md"):
        # Only top-level and one level deep
        rel = md_file.relative_to(GIT_DIR)
        if len(rel.parts) > 3:
            continue
        try:
            stat = md_file.stat()
            content = md_file.read_text()
            claude_md_files[str(md_file)] = {
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat()[:10],
                "lines": content.count("\n"),
                "content": content,
            }
        except (OSError, PermissionError):
            continue

    # Domain docs
    domain_docs = {}
    if DOMAIN_DIR.exists():
        for doc in sorted(DOMAIN_DIR.iterdir()):
            if doc.suffix == ".md":
                try:
                    content = doc.read_text()
                    domain_docs[doc.name] = {
                        "size": doc.stat().st_size,
                        "lines": content.count("\n"),
                        "content": content,
                    }
                except (OSError, PermissionError):
                    continue

    # Memory files
    memories = {}
    for project_dir in sorted(PROJECTS_DIR.iterdir()):
        memory_dir = project_dir / "memory"
        if not memory_dir.is_dir():
            continue
        project_name = project_dir.name
        for mem_file in sorted(memory_dir.iterdir()):
            if mem_file.is_file():
                try:
                    content = mem_file.read_text()
                    memories[f"{project_name}/{mem_file.name}"] = {
                        "size": mem_file.stat().st_size,
                        "lines": content.count("\n"),
                        "content": content,
                    }
                except (OSError, PermissionError):
                    continue

    # Commands (headers + first 20 lines)
    commands = {}
    if COMMANDS_DIR.exists():
        for cmd in sorted(COMMANDS_DIR.iterdir()):
            if cmd.suffix == ".md":
                try:
                    lines = cmd.read_text().split("\n")
                    commands[cmd.name] = {
                        "size": cmd.stat().st_size,
                        "preview": "\n".join(lines[:20]),
                    }
                except (OSError, PermissionError):
                    continue

    # Skills — enumerate both ~/.claude/skills/*.md AND plugin SKILL.md
    # under ~/.claude/plugins/**/skills/*/SKILL.md. The user-visible skill
    # surface in Claude Code includes both; enumerating only the first
    # dramatically underrepresents available skills.
    skills = {}
    if SKILLS_DIR.exists():
        for skill in sorted(SKILLS_DIR.iterdir()):
            if skill.suffix == ".md":
                try:
                    skills[skill.name] = {
                        "source": "local",
                        "size": skill.stat().st_size,
                        "content": skill.read_text(),
                    }
                except (OSError, PermissionError):
                    continue

    plugins_dir = CLAUDE_DIR / "plugins"
    if plugins_dir.exists():
        for skill_md in plugins_dir.rglob("skills/*/SKILL.md"):
            try:
                rel = skill_md.relative_to(plugins_dir)
                key = f"plugins/{rel}"
                skills[key] = {
                    "source": "plugin",
                    "size": skill_md.stat().st_size,
                    "content": skill_md.read_text()[:4000],  # cap for size
                }
            except (OSError, PermissionError, ValueError):
                continue

    # Agents
    agents = {}
    if AGENTS_DIR.exists():
        for agent in sorted(AGENTS_DIR.iterdir()):
            if agent.suffix == ".md":
                try:
                    content = agent.read_text()
                    agents[agent.name] = {
                        "size": agent.stat().st_size,
                        "preview": content[:500],
                    }
                except (OSError, PermissionError):
                    continue

    # Settings
    settings = {}
    if SETTINGS_FILE.exists():
        try:
            settings = json.loads(SETTINGS_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    # Handoff
    handoff = {}
    if HANDOFF_FILE.exists():
        try:
            handoff = json.loads(HANDOFF_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    return {
        "claude_md_files": claude_md_files,
        "domain_docs": domain_docs,
        "memories": memories,
        "commands": commands,
        "skills": skills,
        "agents": agents,
        "settings": settings,
        "handoff": handoff,
    }


# Config redaction is BEST-EFFORT DENYLIST, not a guarantee: dict values are
# redacted on key-name match or known value-prefix match, and list items by
# value-pattern only (no key context). Secrets under unrecognized key names,
# secret-bearing argv lists, and internal endpoint URLs can survive into the
# packet. Packet stays 0600/local-only; treat contents as sensitive. Follow-up
# (tracked on workstream codex-local-self-improvement): move [mcp_servers.*]
# env/args handling to an allowlist of known-safe keys.
SENSITIVE_CONFIG_KEY_RE = re.compile(
    r"(?:token|secret|password|credential|api[_-]?key|authorization)", re.IGNORECASE
)
SENSITIVE_VALUE_RES = (
    re.compile(
        r"\b(?:authorization|proxy-authorization)\s*[:=]\s*"
        r"(?:bearer|basic)?\s*\S+",
        re.IGNORECASE,
    ),
    re.compile(
        r"[\"']?(?:api[_-]?key|access[_-]?token|token|secret|password|credential|"
        r"aws_secret_access_key)[\"']?\s*[:=]\s*[\"']?[^\s,}\"']+",
        re.IGNORECASE,
    ),
    re.compile(r"\bsk-(?:[A-Za-z0-9_-]{8,})"),
    re.compile(r"\b(?:gh[pousr]_|github_pat_)[A-Za-z0-9_]{20,}"),
    re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
    re.compile(r"\bAIza[A-Za-z0-9_-]{20,}"),
    re.compile(r"\bxox[bp]-[A-Za-z0-9-]{10,}"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
    re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"),
)


def _redact_sensitive_text(value):
    if not isinstance(value, str):
        return value
    if any(pattern.search(value) for pattern in SENSITIVE_VALUE_RES):
        return "<redacted>"
    return value


def _redact_config(value, key=""):
    if key and SENSITIVE_CONFIG_KEY_RE.search(key):
        return "<redacted>"
    if isinstance(value, dict):
        return {str(k): _redact_config(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_config(item) for item in value]
    return _redact_sensitive_text(value)


def _bounded_config_values(value, max_chars):
    max_chars = max(2, int(max_chars))
    redacted = _redact_config(value)
    rendered = json.dumps(redacted, sort_keys=True, default=str)
    if len(rendered) <= max_chars:
        return redacted, False, 0

    summary = {
        "truncated": True,
        "original_chars": len(rendered),
        "sensitive_values_redacted": "<redacted>" in rendered,
    }
    if summary["sensitive_values_redacted"]:
        summary["redaction_marker"] = "<redacted>"
    summary_chars = len(json.dumps(summary, sort_keys=True, default=str))
    if summary_chars > max_chars:
        summary = {"truncated": True}
        summary_chars = len(json.dumps(summary, sort_keys=True, default=str))
    if summary_chars > max_chars:
        summary = {}
        summary_chars = 2
    return summary, True, max(0, len(rendered) - summary_chars)


def _bounded_text_artifact(path, content_limit):
    content = path.read_text(errors="replace")
    return {
        "size": path.stat().st_size,
        "lines": content.count("\n"),
        "content": content[:content_limit],
        "content_truncated": len(content) > content_limit,
    }


def extract_codex_artifacts(codex_dir, git_dir):
    """Inventory bounded Codex configuration and instruction artifacts."""
    codex_root = Path(codex_dir)
    git_root = Path(git_dir)
    config = {}
    agents = {}
    skills = {}
    instruction_files = {}
    read_errors = []
    dropped_counts = {
        "agent_profiles": 0,
        "skills": 0,
        "instruction_files": 0,
        "artifact_content": 0,
        "config_chars": 0,
        "agent_config_chars": 0,
    }

    config_path = codex_root / "config.toml"
    if config_path.is_file():
        try:
            parsed = tomllib.loads(config_path.read_text())
            values, values_truncated, chars_dropped = _bounded_config_values(
                parsed, MAX_CODEX_CONFIG_JSON_CHARS
            )
            config = {
                "path": str(config_path),
                "size": config_path.stat().st_size,
                "values": values,
                "values_truncated": values_truncated,
            }
            dropped_counts["config_chars"] = chars_dropped
        except (OSError, PermissionError, tomllib.TOMLDecodeError) as exc:
            read_errors.append(
                {
                    "path": str(config_path),
                    "code": "config_read_failed",
                    "detail": str(exc),
                }
            )

    agents_dir = codex_root / "agents"
    agent_paths = sorted(agents_dir.glob("*.toml")) if agents_dir.is_dir() else []
    for agent_path in agent_paths[:50]:
        try:
            values, values_truncated, chars_dropped = _bounded_config_values(
                tomllib.loads(agent_path.read_text()),
                MAX_CODEX_AGENT_CONFIG_JSON_CHARS,
            )
            agents[agent_path.name] = {
                "path": str(agent_path),
                "size": agent_path.stat().st_size,
                "values": values,
                "values_truncated": values_truncated,
            }
            dropped_counts["agent_config_chars"] += chars_dropped
        except (OSError, PermissionError, tomllib.TOMLDecodeError) as exc:
            read_errors.append(
                {
                    "path": str(agent_path),
                    "code": "agent_read_failed",
                    "detail": str(exc),
                }
            )
    dropped_counts["agent_profiles"] = max(0, len(agent_paths) - 50)

    skills_dir = codex_root / "skills"
    skill_paths = sorted(skills_dir.rglob("SKILL.md")) if skills_dir.is_dir() else []
    for skill_path in skill_paths[:100]:
        try:
            artifact = _bounded_text_artifact(skill_path, 4_000)
            skills[str(skill_path.relative_to(skills_dir))] = artifact
            if artifact["content_truncated"]:
                dropped_counts["artifact_content"] += 1
        except (OSError, PermissionError, ValueError) as exc:
            read_errors.append(
                {
                    "path": str(skill_path),
                    "code": "skill_read_failed",
                    "detail": str(exc),
                }
            )
    dropped_counts["skills"] = max(0, len(skill_paths) - 100)

    instruction_candidates = []
    search_roots = [git_root]
    if git_root.is_dir():
        try:
            search_roots.extend(path for path in git_root.iterdir() if path.is_dir())
        except (OSError, PermissionError):
            pass
    for root in search_roots:
        for relative in (
            Path("AGENTS.md"),
            Path("AGENTS.codex.md"),
            Path("overlay") / "codex-overlay.md",
        ):
            candidate = root / relative
            if candidate.is_file():
                instruction_candidates.append(candidate)
    instruction_candidates = sorted(set(instruction_candidates))
    for instruction_path in instruction_candidates[:100]:
        try:
            artifact = _bounded_text_artifact(instruction_path, 8_000)
            instruction_files[str(instruction_path)] = artifact
            if artifact["content_truncated"]:
                dropped_counts["artifact_content"] += 1
        except (OSError, PermissionError) as exc:
            read_errors.append(
                {
                    "path": str(instruction_path),
                    "code": "instruction_read_failed",
                    "detail": str(exc),
                }
            )
    dropped_counts["instruction_files"] = max(0, len(instruction_candidates) - 100)

    return {
        "harness": "codex",
        "config": config,
        "agents": agents,
        "skills": skills,
        "instruction_files": instruction_files,
        "read_errors": read_errors[:20],
        "truncated": any(dropped_counts.values()) or len(read_errors) > 20,
        "dropped_counts": {
            **dropped_counts,
            "read_errors": max(0, len(read_errors) - 20),
        },
    }


def _write_private_json(path, payload):
    path = Path(path)
    rendered = json.dumps(payload, indent=2, default=str)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as output:
            fd = None
            output.write(rendered)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_name, path)
        temporary_name = None
    finally:
        if fd is not None:
            os.close(fd)
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)


def extract_codex_state_and_threads(cutoff_s, state_db, max_rows):
    """Read thread locators and aggregates from the same state DB snapshot."""
    try:
        with open_sqlite_snapshot(state_db) as conn:
            selection = load_codex_thread_rows(cutoff_s, conn, max_rows=max_rows)
            state = extract_codex_state(cutoff_s, conn)
            selection["snapshot_coherent"] = True
            state["snapshot_coherent"] = True
            return selection, state
    except (FileNotFoundError, sqlite3.Error, OSError):
        selection = load_codex_thread_rows(cutoff_s, state_db, max_rows=max_rows)
        state = extract_codex_state(cutoff_s, state_db)
        selection["snapshot_coherent"] = False
        state["snapshot_coherent"] = False
        return selection, state


HERMES_DIR = Path.home() / ".hermes"

def extract_hermes_history(cutoff_ms):
    """Extract user prompts from Hermes delegation live-transcript logs + request dumps."""
    import glob
    from datetime import datetime, timezone
    project_counts = Counter()
    all_prompts = []
    sessions = set()
    hermes_live = HERMES_DIR / "profiles" / "coder" / "cache" / "delegation" / "live"
    hermes_sessions = HERMES_DIR / "sessions"
    # 1. Delegation live transcripts (user turns)
    for log in glob.glob(str(hermes_live / "**" / "task-*.log"), recursive=True):
        try:
            st = Path(log).stat()
            if st.st_mtime * 1000 < cutoff_ms: continue
            with open(log) as f:
                for line in f:
                    if " user " in line or line.startswith(" user "):
                        # transcript format: "HH:MM:SS user     | kickoff: ..."
                        import re as _re
                        m = _re.match(r'\d{2}:\d{2}:\d{2}\s+user\s+\|\s+(.*)', line)
                        if m:
                            display = m.group(1).strip()
                            if len(display) >= 3:
                                all_prompts.append({"display": display[:300], "project": "hermes-delegation", "ts": int(st.st_mtime*1000)})
                                sessions.add(Path(log).parent.name)
        except (OSError, UnicodeDecodeError): continue
    # 2. Request dumps (error prompts)
    for dump in glob.glob(str(hermes_sessions / "request_dump_*.json")):
        try:
            st = Path(dump).stat()
            if st.st_mtime * 1000 < cutoff_ms: continue
            entry = json.loads(Path(dump).read_text())
            ts_ms = int(datetime.fromisoformat(entry.get("timestamp","2000")).replace(tzinfo=timezone.utc).timestamp()*1000)
            req = entry.get("request",{})
            content = req.get("content","") if isinstance(req.get("content"),str) else json.dumps(req)[:200]
            if content and len(content)>=3:
                all_prompts.append({"display": content[:300], "project": "hermes-session", "ts": ts_ms})
                sessions.add(entry.get("session_id","unknown"))
        except (OSError, json.JSONDecodeError, KeyError): continue
    return {
        "harness": "hermes",
        "total_prompts": len(all_prompts),
        "project_counts": dict(Counter([p["project"] for p in all_prompts]).most_common(20)),
        "error_prompts": [],
        "repeated_prompts": {},
        "command_usage": {},
        "session_count": len(sessions),
    }


def main(argv=None):
    args = parse_args(argv)
    days = args.days
    output_dir = args.output_dir
    output_dir_preexisted = output_dir.exists()
    output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Only tighten permissions on directories this run created; an
    # unconditional chmod on a pre-existing dir (e.g. an explicit
    # --output-dir /tmp) would crash for non-root or break shared dirs.
    # Packet files themselves are always written 0600 (_write_private_json).
    if not output_dir_preexisted:
        output_dir.chmod(0o700)

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    cutoff_ms = int(cutoff.timestamp() * 1000)
    cutoff_iso = cutoff.isoformat()
    cutoff_date = cutoff.strftime("%Y-%m-%d")

    if args.harness == "codex":
        print(f"Extracting codex data for last {days} days (since {cutoff_date})...")
    else:
        print(f"Extracting data for last {days} days (since {cutoff_date})...")

    if args.harness == "codex":
        thread_selection, state = extract_codex_state_and_threads(
            int(cutoff.timestamp()),
            CODEX_STATE_DB,
            MAX_CODEX_SESSION_FILES,
        )
        thread_rows = thread_selection["rows"]
        thread_index = {str(row["id"]): row for row in thread_rows}

        print("  [1/4] Codex history & prompts...", end=" ", flush=True)
        history = extract_codex_history(
            int(cutoff.timestamp()),
            CODEX_HISTORY_FILE,
            thread_index,
        )
        history["thread_index_rows"] = len(thread_rows)
        history["thread_index_rows_dropped"] = thread_selection["dropped"]
        if thread_selection.get("error"):
            history["thread_index_error"] = thread_selection["error"]
        if thread_selection["dropped"]:
            history["truncated"] = True
            history.setdefault("dropped_counts", {})["thread_index_rows"] = (
                thread_selection["dropped"]
            )
    elif args.harness == "hermes":
        print("  [1/4] Hermes history & prompts...", end=" ", flush=True)
        history = extract_hermes_history(cutoff_ms)
    else:
        print("  [1/4] History & prompts...", end=" ", flush=True)
        history = extract_history(cutoff_ms)
    history_path = output_dir / "improve-history.json"
    _write_private_json(history_path, history)
    print(f"done ({history.get('total_prompts', 0)} prompts)")

    if args.harness == "codex":
        print("  [2/4] Codex state, logs & sessions...", end=" ", flush=True)
        telemetry = extract_codex_logs(int(cutoff.timestamp()), CODEX_LOGS_DB)
        sessions = extract_codex_sessions(
            int(cutoff.timestamp()),
            thread_rows,
            max_files=MAX_CODEX_SESSION_FILES,
            max_line_bytes=MAX_CODEX_JSONL_LINE_BYTES,
            max_total_bytes=MAX_CODEX_SESSION_BYTES,
            eligible_count=thread_selection["eligible_count"],
        )
        sessions["thread_snapshot"] = state
        sessions["telemetry_integrity"] = telemetry
        if thread_selection.get("error"):
            sessions["session_index_error"] = thread_selection["error"]
    else:
        print("  [2/4] Session conversations...", end=" ", flush=True)
        sessions = extract_sessions(cutoff_iso, max_per_project=5)
    sessions_path = output_dir / "improve-sessions.json"
    _write_private_json(sessions_path, sessions)
    print(f"done ({sessions.get('sessions_analyzed', 0)} sessions)")

    print("  [3/4] Git activity...", end=" ", flush=True)
    git_data = extract_git(cutoff_date, days=days)
    if args.harness == "codex":
        git_data["harness"] = "codex"
    git_path = output_dir / "improve-git.json"
    _write_private_json(git_path, git_data)
    print(
        f"done ({git_data.get('total_commits', 0)} commits across {git_data.get('total_repos', 0)} repos)"
    )

    print(f"  [4/4] {args.harness.capitalize()} artifacts...", end=" ", flush=True)
    if args.harness == "codex":
        artifacts = extract_codex_artifacts(CODEX_DIR, GIT_DIR)
    else:
        artifacts = extract_artifacts()
    artifacts_path = output_dir / "improve-artifacts.json"
    _write_private_json(artifacts_path, artifacts)
    if args.harness == "codex":
        artifact_counts = (
            f"{len(artifacts.get('instruction_files', {}))} instruction files, "
            f"{len(artifacts.get('skills', {}))} skills, "
            f"{len(artifacts.get('agents', {}))} agents"
        )
    else:
        artifact_counts = (
            f"{len(artifacts.get('claude_md_files', {}))} CLAUDE.md, "
            f"{len(artifacts.get('domain_docs', {}))} domain docs, "
            f"{len(artifacts.get('memories', {}))} memories, "
            f"{len(artifacts.get('commands', {}))} commands, "
            f"{len(artifacts.get('skills', {}))} skills, "
            f"{len(artifacts.get('agents', {}))} agents"
        )
    print(f"done ({artifact_counts})")

    # Report sizes
    print("\nOutput files:")
    output_names = [
        "improve-history.json",
        "improve-sessions.json",
        "improve-git.json",
        "improve-artifacts.json",
    ]
    for name in output_names:
        path = output_dir / name
        size_kb = path.stat().st_size / 1024
        print(f"  {name}: {size_kb:.1f} KB")

    total_kb = sum((output_dir / name).stat().st_size for name in output_names) / 1024
    print(f"\nTotal: {total_kb:.1f} KB")


if __name__ == "__main__":
    main()
