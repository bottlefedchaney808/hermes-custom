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
_FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)

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
