"""Turn vault notes and swept sessions into retrievable chunks.

Rules from spec section 7: split notes on ``##`` and deeper, keep a short
heading attached to its body, one chunk per user+assistant turn pair for
sessions, and never index .obsidian/, .git/, or binary attachments.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from brain_rag.leg import DEFAULT_LEG, leg_for_vault_path

# ~1500 tokens at the conventional 4-chars-per-token estimate.
MAX_CHUNK_CHARS = 6000

_HEADING_RE = re.compile(r"^(#{2,6})\s+(.*)$", re.MULTILINE)
_WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)")
_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
_TURN_HEADING_RE = re.compile(r"^(#{2,3})\s+(User|Assistant)\s*$", re.IGNORECASE | re.MULTILINE)

_SKIP_DIRS = (".obsidian/", ".git/")
_BINARY_SUFFIXES = (
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf",
    ".zip", ".xlsx", ".docx", ".mp4", ".mp3",
)


@dataclass(frozen=True)
class Chunk:
    text: str
    path: str
    heading: str | None
    leg: str
    source: str  # "note" | "session"
    date: str  # ISO date, always present for filtering + citation
    session_id: str | None = None
    wikilinks: tuple[str, ...] = field(default_factory=tuple)
    content_hash: str = ""


def should_skip(rel_path: str) -> bool:
    """True when a vault-relative path must never be indexed."""
    p = str(rel_path).replace("\\", "/")
    if any(p == d.rstrip("/") or p.startswith(d) for d in _SKIP_DIRS):
        return True
    lower = p.lower()
    if lower.endswith(_BINARY_SUFFIXES):
        return True
    return not lower.endswith(".md")


def _hash(*parts: str) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update(part.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def _iso_date(mtime: float) -> str:
    return datetime.fromtimestamp(mtime, tz=timezone.utc).date().isoformat()


def _wikilinks(text: str) -> tuple[str, ...]:
    seen: dict[str, None] = {}
    for match in _WIKILINK_RE.finditer(text):
        seen.setdefault(match.group(1).strip(), None)
    return tuple(seen)


def _split_oversized(text: str) -> list[str]:
    """Split on blank lines, packing paragraphs up to the cap."""
    if len(text) <= MAX_CHUNK_CHARS:
        return [text]
    out: list[str] = []
    buf = ""
    for para in text.split("\n\n"):
        candidate = f"{buf}\n\n{para}" if buf else para
        if len(candidate) > MAX_CHUNK_CHARS and buf:
            out.append(buf)
            buf = para
        else:
            buf = candidate
    if buf:
        out.append(buf)
    return out


def _frontmatter(text: str) -> dict[str, str]:
    match = _FRONTMATTER_RE.match(text or "")
    if not match:
        return {}
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip()
    return fields


def is_session_note(rel_path: str, text: str = "") -> bool:
    """True for swept session markdown: ``*/Sessions/*.md`` and/or ``type: session``."""
    posix = str(rel_path).replace("\\", "/")
    parts = posix.split("/")
    if "Sessions" in parts:
        return True
    return _frontmatter(text).get("type") == "session"


def _turns_from_session_body(body: str) -> list[dict]:
    matches = list(_TURN_HEADING_RE.finditer(body or ""))
    turns: list[dict] = []
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        turns.append({
            "role": match.group(2).strip().lower(),
            "content": body[match.end():end].strip(),
        })
    return turns


def chunks_for_markdown(rel_path: str, text: str, mtime: float) -> list[Chunk]:
    """Dispatch vault markdown to ``chunk_session`` or ``chunk_note``."""
    if is_session_note(rel_path, text):
        return chunk_session_note(rel_path, text, mtime)
    return chunk_note(rel_path, text, mtime)


def chunk_session_note(rel_path: str, text: str, mtime: float) -> list[Chunk]:
    """Parse a swept session note and emit turn-pair chunks."""
    posix = str(rel_path).replace("\\", "/")
    fields = _frontmatter(text)
    body = _FRONTMATTER_RE.sub("", text)
    stem = posix.rsplit("/", 1)[-1]
    if stem.lower().endswith(".md"):
        stem = stem[:-3]
    session_id = fields.get("session_id") or stem
    started = fields.get("started")
    if not started:
        started = stem[:10] if len(stem) >= 10 and stem[4:5] == "-" and stem[7:8] == "-" else _iso_date(mtime)
    leg = fields.get("leg") or leg_for_vault_path(posix) or DEFAULT_LEG
    return chunk_session(
        posix,
        _turns_from_session_body(body),
        leg=leg,
        session_id=session_id,
        started=started,
    )


def chunk_note(rel_path: str, text: str, mtime: float) -> list[Chunk]:
    """Split one note into chunks. Frontmatter rides with the first chunk."""
    leg = leg_for_vault_path(rel_path) or DEFAULT_LEG
    date = _iso_date(mtime)
    body = _FRONTMATTER_RE.sub("", text)

    matches = list(_HEADING_RE.finditer(body))
    sections: list[tuple[str | None, str]] = []
    if not matches:
        sections.append((None, body.strip()))
    else:
        preamble = body[: matches[0].start()].strip()
        if preamble:
            sections.append((None, preamble))
        for i, m in enumerate(matches):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
            heading = m.group(2).strip()
            section_text = body[m.start() : end].strip()
            sections.append((heading, section_text))

    chunks: list[Chunk] = []
    for heading, section_text in sections:
        if not section_text:
            continue
        for piece in _split_oversized(section_text):
            chunks.append(
                Chunk(
                    text=piece,
                    path=rel_path.replace("\\", "/"),
                    heading=heading,
                    leg=leg,
                    source="note",
                    date=date,
                    wikilinks=_wikilinks(piece),
                    content_hash=_hash(rel_path, heading or "", piece),
                )
            )
    return chunks


_TOOL_JSON_FENCE_RE = re.compile(r"```json\s*\n.*?\n```", re.DOTALL)


def strip_tool_json(text: str) -> str:
    """Drop fenced ```json blocks (tool payloads); keep other code fences.

    Session notes are for reasoning, not machine payloads (spec section 6).
    """
    return _TOOL_JSON_FENCE_RE.sub("", text or "").strip()


def chunk_session(
    rel_path: str,
    turns: list[dict],
    *,
    leg: str,
    session_id: str,
    started: str,
) -> list[Chunk]:
    """One chunk per user turn plus the assistant reply that follows it."""
    chunks: list[Chunk] = []
    pending_user: str | None = None

    def _emit(user_text: str, assistant_text: str | None) -> None:
        parts = [f"**User:** {user_text}"]
        if assistant_text:
            parts.append(f"**Assistant:** {assistant_text}")
        piece = "\n\n".join(parts)
        chunks.append(
            Chunk(
                text=piece,
                path=rel_path.replace("\\", "/"),
                heading=None,
                leg=leg,
                source="session",
                date=started,
                session_id=session_id,
                wikilinks=_wikilinks(piece),
                content_hash=_hash(session_id, str(len(chunks)), piece),
            )
        )

    for turn in turns:
        role = turn.get("role")
        content = strip_tool_json(turn.get("content") or "")
        if role == "user":
            if pending_user is not None:
                _emit(pending_user, None)
            pending_user = content
        elif role == "assistant" and pending_user is not None:
            _emit(pending_user, content)
            pending_user = None

    if pending_user is not None:
        _emit(pending_user, None)
    return chunks
