# Obsidian-brain RAG Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` (inline) or `subagent-driven-development` (fresh subagent per task) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. TDD throughout. Commit after every task.

**Goal:** Hybrid BM25 + vector retrieval over the obsidian-brain vault and swept Hermes sessions, exposed as the unified Hermes plugin `brain-rag` (`rag_search` / `rag_index`), with vault writes gated to weekly sweep + explicit remind.

**Architecture:** Engine is a Python package in this repo. A deploy script copies the `plugin/` tree to each profile's `$HERMES_HOME/plugins/brain-rag/`. The index lives at `$HERMES_HOME/rag/brain.sqlite` (per profile, never in git). Embeddings come from Nous Portal using Hermes' existing OAuth. Mem0 stays the memory provider. No `hermes-agent` core patch.

**Tech Stack:** Python 3.11, SQLite (FTS5 + sqlite-vec 0.1.9), FastAPI (`APIRouter`), pytest, uncompiled ESM for the desktop pane.

**Spec:** `docs/superpowers/specs/2026-09-10-obsidian-brain-rag-design.md` (commit `1048c32`). The spec is the contract. Where this plan and the spec disagree, the spec wins.

## Global Constraints

- Source of truth for code is `C:/Users/bottl/hermes-custom/RAG`. **Do not develop in `.worktrees/main`.**
- Runtime is `$HERMES_HOME/plugins/brain-rag/` — **profile-scoped**, never a single global path.
- Index path is `$HERMES_HOME/rag/brain.sqlite`. Profiles do not share an index.
- Embedding provider is Nous Portal only. No local embedding models. No new API key — reuse `hermes_cli.auth.resolve_nous_access_token()`.
- Mem0 remains the active memory provider. Do not register a `MemoryProvider`.
- Do not modify anything under `C:/Users/bottl/dev/hermes-agent`.
- Only two vault writers: sweep and explicit remind. Nothing else writes to `Construction/`, `Development/`, or `Trading/`.
- Never call `hermes sessions prune` from any code path — it deletes.
- Never write `MEMORY.md` from this system.
- Git identity for this repo is already set locally (`bottlefedchaney808` / `bottlefedchaney808@users.noreply.github.com`). Do not use `--global`.
- Legs are exactly `Construction`, `Development`, `Trading`.
- Citation fields are mandatory on every hit: `path`, `heading` or `session_id`, `date`, `leg`.

---

## File Structure

Locked before tasks begin. Each file has one responsibility.

| Path | Responsibility |
|---|---|
| `pyproject.toml` | Package metadata, pytest config, deps |
| `.gitignore` | `.worktrees/`, `__pycache__/`, `.venv/`, `*.sqlite` |
| `src/brain_rag/leg.py` | cwd/path → `Construction` \| `Development` \| `Trading` |
| `src/brain_rag/chunk.py` | Note `##` splitting, session turn pairing, skip rules |
| `src/brain_rag/store.py` | SQLite schema, FTS5, sqlite-vec, hash-keyed upsert |
| `src/brain_rag/embed.py` | Nous `/v1/embeddings` batch client + pinned model id |
| `src/brain_rag/index.py` | Vault walk, incremental vs full |
| `src/brain_rag/search.py` | BM25 + kNN + RRF + filters → `{hits}` |
| `src/brain_rag/sweep.py` | `state.db` → `{Leg}/Sessions/YYYY-MM-DD-<id>.md`, git commit |
| `src/brain_rag/remind.py` | Explicit thin note into a named leg |
| `plugin/plugin.yaml` | Manifest, `name: brain-rag` |
| `plugin/__init__.py` | `register(ctx)` → `rag_search`, `rag_index` |
| `plugin/_engine.py` | Path-based loader for `src/brain_rag` (no package context) |
| `plugin/dashboard/manifest.json` | `{"name":"brain-rag","api":"plugin_api.py"}` |
| `plugin/dashboard/plugin_api.py` | FastAPI router → `/search`, `/index`, `/status` |
| `plugin/desktop/plugin.js` | `jsx()` pane, `ctx.rest('/search')` |
| `scripts/deploy.cmd` | Copy `plugin/` to every profile root that should have RAG |
| `tests/` | Unit + fixture tests |
| `tests/fixtures/vault/` | Tiny Construction vs Trading vault |
| `tests/eval/golden.md` | The 10 spec questions (local-only run) |

**YAGNI — not in this plan:** Qdrant, reranker, wikilink graph expansion, auto-taxonomy, coach/timeline UI, PDF ingest, repo ingest, MEMORY.md writer.

---

### Task 0: Repo hygiene and package skeleton

**Files:**
- Create: `.gitignore`
- Create: `pyproject.toml`
- Create: `src/brain_rag/__init__.py`
- Create: `tests/__init__.py`

**Interfaces:**
- Consumes: nothing
- Produces: importable package `brain_rag`; `pytest` runnable from repo root

- [ ] **Step 1: Write `.gitignore`**

```gitignore
.worktrees/
__pycache__/
*.py[cod]
.venv/
venv/
*.sqlite
*.sqlite-shm
*.sqlite-wal
.pytest_cache/
*.egg-info/
```

- [ ] **Step 2: Write `pyproject.toml`**

```toml
[project]
name = "brain-rag"
version = "0.1.0"
description = "Hybrid retrieval over the obsidian-brain vault and swept Hermes sessions"
requires-python = ">=3.11"
dependencies = [
    "sqlite-vec>=0.1.9,<0.2",
    "httpx>=0.28.1,<1",
    "fastapi>=0.115,<1",
    "pydantic>=2.9,<3",
]

[project.optional-dependencies]
dev = ["pytest>=8.3,<9"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = [
    "golden: real-vault retrieval eval, local only (deselected by default)",
]
addopts = "-m 'not golden'"
```

- [ ] **Step 3: Create empty package markers**

```python
# src/brain_rag/__init__.py
"""Hybrid retrieval over the obsidian-brain vault and swept Hermes sessions."""

__version__ = "0.1.0"
```

```python
# tests/__init__.py
```

- [ ] **Step 4: Verify the package imports**

Run: `python -m pip install -e ".[dev]"`
Expected: `Successfully installed brain-rag-0.1.0`

Run: `python -c "import brain_rag; print(brain_rag.__version__)"`
Expected: `0.1.0`

- [ ] **Step 5: Commit**

```bash
git add .gitignore pyproject.toml src/brain_rag/__init__.py tests/__init__.py
git commit -m "chore(rag): package skeleton, pytest config, gitignore"
```

---

### Task 1: Spike — pin sqlite-vec loading and the Nous embedding model id

Verified during planning: `sqlite3` 3.40.1 with `enable_load_extension == True`, and `sqlite-vec` 0.1.9 is on PyPI. This task turns that into committed, tested constants.

**Files:**
- Create: `src/brain_rag/embed.py` (constants only in this task)
- Create: `tests/test_spike_env.py`

**Interfaces:**
- Consumes: nothing
- Produces: `NOUS_EMBED_MODEL: str`, `EMBED_DIM: int`, `load_vec_extension(conn) -> None`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_spike_env.py
import sqlite3

from brain_rag.embed import EMBED_DIM, NOUS_EMBED_MODEL, load_vec_extension


def test_sqlite_vec_loads_and_answers_a_knn_query():
    conn = sqlite3.connect(":memory:")
    load_vec_extension(conn)
    conn.execute(f"CREATE VIRTUAL TABLE v USING vec0(embedding float[{EMBED_DIM}])")
    conn.execute(
        "INSERT INTO v(rowid, embedding) VALUES (?, ?)",
        (1, _packed([0.1] * EMBED_DIM)),
    )
    rows = conn.execute(
        "SELECT rowid FROM v WHERE embedding MATCH ? ORDER BY distance LIMIT 1",
        (_packed([0.1] * EMBED_DIM),),
    ).fetchall()
    assert rows == [(1,)]


def test_embedding_model_is_pinned():
    assert NOUS_EMBED_MODEL
    assert EMBED_DIM > 0


def _packed(values):
    import struct

    return struct.pack(f"{len(values)}f", *values)
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `python -m pytest tests/test_spike_env.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'brain_rag.embed'`

- [ ] **Step 3: Discover the live embedding model id**

This is a real lookup, not a guess. Run it and read the output:

```bash
python - <<'PY'
import sys
sys.path.insert(0, "C:/Users/bottl/dev/hermes-agent")
import httpx
from hermes_cli.auth import resolve_nous_access_token

token = resolve_nous_access_token()
r = httpx.get(
    "https://inference-api.nousresearch.com/v1/models",
    headers={"Authorization": f"Bearer {token}"},
    timeout=30,
)
r.raise_for_status()
for m in r.json().get("data", []):
    mid = m.get("id", "")
    if "embed" in mid.lower():
        print(mid)
PY
```

Pick one id from that output. If the endpoint returns no embedding models, try the Portal base URL recorded in `~/.hermes/auth.json` before concluding anything, and record the outcome in the Risks section rather than inventing an id.

Confirm the dimension with one real call:

```bash
python - <<'PY'
import sys
sys.path.insert(0, "C:/Users/bottl/dev/hermes-agent")
import httpx
from hermes_cli.auth import resolve_nous_access_token

MODEL = "<id you picked>"
token = resolve_nous_access_token()
r = httpx.post(
    "https://inference-api.nousresearch.com/v1/embeddings",
    headers={"Authorization": f"Bearer {token}"},
    json={"model": MODEL, "input": ["hello"]},
    timeout=60,
)
r.raise_for_status()
print(MODEL, len(r.json()["data"][0]["embedding"]))
PY
```

- [ ] **Step 4: Write the constants and loader**

```python
# src/brain_rag/embed.py
"""Nous Portal embeddings + the sqlite-vec extension loader.

The model id and dimension below were pinned from a live
``/v1/models`` + ``/v1/embeddings`` probe (Task 1). Changing the model
changes the vector width, which invalidates every stored embedding —
a model change REQUIRES ``rag_index(mode="full")``.
"""
from __future__ import annotations

import sqlite3

# Pinned in Task 1 from the live Portal catalog. Replace both together.
NOUS_EMBED_MODEL = "<id you picked>"
EMBED_DIM = 0  # <- the length printed by the probe

NOUS_BASE_URL = "https://inference-api.nousresearch.com/v1"


def load_vec_extension(conn: sqlite3.Connection) -> None:
    """Load sqlite-vec into ``conn``.

    Raises RuntimeError when the interpreter was built without extension
    loading. Callers must let that propagate: a silent BM25-only degrade
    would hide a broken install (spec section 10 is about a down API, not
    a broken build).
    """
    import sqlite_vec

    if not hasattr(conn, "enable_load_extension"):
        raise RuntimeError(
            "This Python's sqlite3 was built without extension loading; "
            "sqlite-vec cannot be used."
        )
    conn.enable_load_extension(True)
    try:
        sqlite_vec.load(conn)
    finally:
        conn.enable_load_extension(False)
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `python -m pytest tests/test_spike_env.py -v`
Expected: `2 passed`

- [ ] **Step 6: Commit**

```bash
git add src/brain_rag/embed.py tests/test_spike_env.py
git commit -m "feat(rag): pin sqlite-vec loader and Nous embedding model"
```

---

### Task 2: Leg resolution

**Files:**
- Create: `src/brain_rag/leg.py`
- Create: `tests/test_leg.py`

**Interfaces:**
- Consumes: nothing
- Produces: `LEGS: tuple[str, ...]`, `leg_for_cwd(cwd: str | None) -> str`, `leg_for_vault_path(rel_path: str) -> str | None`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_leg.py
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
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_leg.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'brain_rag.leg'`

- [ ] **Step 3: Write the implementation**

```python
# src/brain_rag/leg.py
"""Map a working directory or vault path to exactly one leg.

One note, one leg (spec section 6). Unknown work is Development, never a
fourth bucket and never a guess that lands trading notes in Construction.
"""
from __future__ import annotations

LEGS: tuple[str, ...] = ("Construction", "Development", "Trading")

# Checked in order; first match wins. Construction and Trading are the
# narrow, high-confidence cases — everything else is Development.
_CWD_MARKERS: tuple[tuple[str, str], ...] = (
    ("tiferet", "Construction"),
    ("constructiondevelopment", "Construction"),
    ("financialdevelopment", "Trading"),
    ("vol_suite", "Trading"),
    ("eventtrading", "Trading"),
)

DEFAULT_LEG = "Development"


def leg_for_cwd(cwd: str | None) -> str:
    """Leg for a session's working directory. Unknown -> Development."""
    if not cwd:
        return DEFAULT_LEG
    haystack = str(cwd).replace("\\", "/").lower()
    for marker, leg in _CWD_MARKERS:
        if marker in haystack:
            return leg
    return DEFAULT_LEG


def leg_for_vault_path(rel_path: str) -> str | None:
    """Leg from a vault-relative path's first segment; None when not in a leg."""
    if not rel_path:
        return None
    first = str(rel_path).replace("\\", "/").split("/")[0]
    return first if first in LEGS else None
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_leg.py -v`
Expected: `9 passed`

- [ ] **Step 5: Commit**

```bash
git add src/brain_rag/leg.py tests/test_leg.py
git commit -m "feat(rag): leg resolution from cwd and vault path"
```

---

### Task 3: Chunker — notes

**Files:**
- Create: `src/brain_rag/chunk.py`
- Create: `tests/test_chunk_notes.py`

**Interfaces:**
- Consumes: `brain_rag.leg.leg_for_vault_path`
- Produces: `@dataclass Chunk(text, path, heading, leg, source, date, session_id, wikilinks, content_hash)`; `chunk_note(rel_path, text, mtime) -> list[Chunk]`; `should_skip(rel_path) -> bool`; `MAX_CHUNK_CHARS: int`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_chunk_notes.py
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
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_chunk_notes.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'brain_rag.chunk'`

- [ ] **Step 3: Write the implementation**

```python
# src/brain_rag/chunk.py
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
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_chunk_notes.py -v`
Expected: `11 passed`

- [ ] **Step 5: Commit**

```bash
git add src/brain_rag/chunk.py tests/test_chunk_notes.py
git commit -m "feat(rag): note chunker with heading split and skip rules"
```

---

### Task 4: Chunker — sessions

**Files:**
- Modify: `src/brain_rag/chunk.py`
- Create: `tests/test_chunk_sessions.py`

**Interfaces:**
- Consumes: `Chunk`, `_hash`, `_wikilinks` from Task 3
- Produces: `chunk_session(rel_path, turns, leg, session_id, started) -> list[Chunk]`; `strip_tool_json(text) -> str`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_chunk_sessions.py
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
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_chunk_sessions.py -v`
Expected: FAIL — `ImportError: cannot import name 'chunk_session'`

- [ ] **Step 3: Append the implementation to `src/brain_rag/chunk.py`**

```python
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
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_chunk_sessions.py -v`
Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add src/brain_rag/chunk.py tests/test_chunk_sessions.py
git commit -m "feat(rag): session chunker pairing turns and dropping tool JSON"
```

---

### Task 5: Store — schema, FTS5, vectors, hash-keyed upsert

**Files:**
- Create: `src/brain_rag/store.py`
- Create: `tests/test_store.py`

**Interfaces:**
- Consumes: `brain_rag.chunk.Chunk`, `brain_rag.embed.load_vec_extension`, `EMBED_DIM`
- Produces: `class Store` with `open(path) -> Store`, `upsert_chunks(chunks) -> int`, `set_embedding(chunk_id, vector)`, `known_hashes(path) -> set[str]`, `delete_path(path)`, `bm25(query, limit) -> list[Row]`, `knn(vector, limit) -> list[Row]`, `count()`, `close()`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_store.py
import pytest

from brain_rag.chunk import Chunk
from brain_rag.store import Store


def _chunk(text="alpha beta", path="Trading/Positions.md", h="h1", leg="Trading"):
    return Chunk(
        text=text, path=path, heading="Account B", leg=leg, source="note",
        date="2026-09-01", wikilinks=("Jason",), content_hash=h,
    )


@pytest.fixture()
def store(tmp_path):
    s = Store.open(tmp_path / "brain.sqlite")
    yield s
    s.close()


def test_upsert_inserts_new_chunks(store):
    assert store.upsert_chunks([_chunk()]) == 1
    assert store.count() == 1


def test_upsert_is_idempotent_on_same_hash(store):
    store.upsert_chunks([_chunk()])
    assert store.upsert_chunks([_chunk()]) == 0
    assert store.count() == 1


def test_changed_hash_replaces_the_row(store):
    store.upsert_chunks([_chunk(text="old", h="h1")])
    store.delete_path("Trading/Positions.md")
    store.upsert_chunks([_chunk(text="new", h="h2")])
    assert store.count() == 1
    assert "new" in store.bm25("new", limit=5)[0]["text"]


def test_bm25_finds_by_keyword(store):
    store.upsert_chunks([_chunk(text="burdened labor rate"), _chunk(text="unrelated", h="h2")])
    rows = store.bm25("burdened", limit=5)
    assert rows and "burdened" in rows[0]["text"]


def test_bm25_returns_citation_fields(store):
    store.upsert_chunks([_chunk()])
    row = store.bm25("alpha", limit=1)[0]
    for key in ("path", "heading", "leg", "source", "date", "text"):
        assert key in row


def test_knn_returns_nearest_first(store):
    from brain_rag.embed import EMBED_DIM

    store.upsert_chunks([_chunk(text="near", h="h1"), _chunk(text="far", h="h2")])
    ids = [r["id"] for r in store.bm25("near OR far", limit=5)]
    near_id = [r["id"] for r in store.bm25("near", limit=1)][0]
    for cid in ids:
        store.set_embedding(cid, [1.0 if cid == near_id else 0.0] * EMBED_DIM)
    rows = store.knn([1.0] * EMBED_DIM, limit=1)
    assert rows[0]["id"] == near_id


def test_known_hashes_supports_incremental_skip(store):
    store.upsert_chunks([_chunk(h="h1"), _chunk(h="h2")])
    assert store.known_hashes("Trading/Positions.md") == {"h1", "h2"}
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'brain_rag.store'`

- [ ] **Step 3: Write the implementation**

```python
# src/brain_rag/store.py
"""SQLite storage: chunk rows, an FTS5 index, and a sqlite-vec vector table.

The index is disposable — it is rebuilt from the vault, never the other way
round — so it lives at ``$HERMES_HOME/rag/brain.sqlite`` and is gitignored.
"""
from __future__ import annotations

import sqlite3
import struct
from pathlib import Path
from typing import Any, Iterable, Sequence

from brain_rag.chunk import Chunk
from brain_rag.embed import EMBED_DIM, load_vec_extension

SCHEMA_VERSION = 1

_DDL = f"""
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chunks (
    id           INTEGER PRIMARY KEY,
    path         TEXT NOT NULL,
    heading      TEXT,
    text         TEXT NOT NULL,
    leg          TEXT NOT NULL,
    source       TEXT NOT NULL,
    date         TEXT NOT NULL,
    session_id   TEXT,
    wikilinks    TEXT NOT NULL DEFAULT '',
    content_hash TEXT NOT NULL UNIQUE,
    embedded     INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_chunks_path ON chunks(path);
CREATE INDEX IF NOT EXISTS idx_chunks_leg  ON chunks(leg);
CREATE INDEX IF NOT EXISTS idx_chunks_date ON chunks(date);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    text,
    content='chunks',
    content_rowid='id',
    tokenize='porter unicode61'
);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_vec USING vec0(
    embedding float[{EMBED_DIM}]
);
"""


def _pack(vector: Sequence[float]) -> bytes:
    return struct.pack(f"{len(vector)}f", *vector)


class Store:
    """Owns the connection. Callers use :meth:`open` and :meth:`close`."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    @classmethod
    def open(cls, path: str | Path) -> "Store":
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        load_vec_extension(conn)
        conn.executescript(_DDL)
        conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES ('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )
        conn.commit()
        return cls(conn)

    def close(self) -> None:
        self._conn.close()

    def count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0])

    def known_hashes(self, path: str) -> set[str]:
        rows = self._conn.execute(
            "SELECT content_hash FROM chunks WHERE path = ?", (path,)
        ).fetchall()
        return {r[0] for r in rows}

    def delete_path(self, path: str) -> int:
        cur = self._conn.execute("SELECT id FROM chunks WHERE path = ?", (path,))
        ids = [r[0] for r in cur.fetchall()]
        for cid in ids:
            self._conn.execute("DELETE FROM chunks_fts WHERE rowid = ?", (cid,))
            self._conn.execute("DELETE FROM chunks_vec WHERE rowid = ?", (cid,))
            self._conn.execute("DELETE FROM chunks WHERE id = ?", (cid,))
        self._conn.commit()
        return len(ids)

    def upsert_chunks(self, chunks: Iterable[Chunk]) -> int:
        """Insert chunks whose hash is not already stored. Returns inserts."""
        inserted = 0
        for c in chunks:
            existing = self._conn.execute(
                "SELECT 1 FROM chunks WHERE content_hash = ?", (c.content_hash,)
            ).fetchone()
            if existing:
                continue
            cur = self._conn.execute(
                """INSERT INTO chunks
                   (path, heading, text, leg, source, date, session_id,
                    wikilinks, content_hash)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    c.path, c.heading, c.text, c.leg, c.source, c.date,
                    c.session_id, "|".join(c.wikilinks), c.content_hash,
                ),
            )
            self._conn.execute(
                "INSERT INTO chunks_fts(rowid, text) VALUES (?, ?)",
                (cur.lastrowid, c.text),
            )
            inserted += 1
        self._conn.commit()
        return inserted

    def set_embedding(self, chunk_id: int, vector: Sequence[float]) -> None:
        self._conn.execute("DELETE FROM chunks_vec WHERE rowid = ?", (chunk_id,))
        self._conn.execute(
            "INSERT INTO chunks_vec(rowid, embedding) VALUES (?, ?)",
            (chunk_id, _pack(vector)),
        )
        self._conn.execute("UPDATE chunks SET embedded = 1 WHERE id = ?", (chunk_id,))
        self._conn.commit()

    def unembedded(self, limit: int = 256) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT id, text FROM chunks WHERE embedded = 0 LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def bm25(self, query: str, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """SELECT c.*, bm25(chunks_fts) AS score
               FROM chunks_fts
               JOIN chunks c ON c.id = chunks_fts.rowid
               WHERE chunks_fts MATCH ?
               ORDER BY score LIMIT ?""",
            (query, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def knn(self, vector: Sequence[float], limit: int = 50) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """SELECT c.*, v.distance AS score
               FROM chunks_vec v
               JOIN chunks c ON c.id = v.rowid
               WHERE v.embedding MATCH ? AND k = ?
               ORDER BY v.distance""",
            (_pack(vector), limit),
        ).fetchall()
        return [dict(r) for r in rows]
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_store.py -v`
Expected: `7 passed`

If the `knn` query errors on the `k = ?` clause, the installed sqlite-vec version wants
`LIMIT ?` instead. Adjust the SQL to match the version pinned in Task 1 and re-run — do not
change the pinned version to suit the query.

- [ ] **Step 5: Commit**

```bash
git add src/brain_rag/store.py tests/test_store.py
git commit -m "feat(rag): sqlite store with FTS5, vectors, hash-keyed upsert"
```

---

### Task 6: Embedding client

**Files:**
- Modify: `src/brain_rag/embed.py`
- Create: `tests/test_embed.py`

**Interfaces:**
- Consumes: `NOUS_EMBED_MODEL`, `NOUS_BASE_URL`
- Produces: `class EmbeddingsUnavailable(RuntimeError)`; `embed_texts(texts, *, token_provider=None, client=None) -> list[list[float]]`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_embed.py
import httpx
import pytest

from brain_rag.embed import EMBED_DIM, EmbeddingsUnavailable, embed_texts


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_returns_one_vector_per_input():
    def handler(request):
        payload = {"data": [{"embedding": [0.5] * EMBED_DIM} for _ in range(2)]}
        return httpx.Response(200, json=payload)

    out = embed_texts(["a", "b"], token_provider=lambda: "t", client=_client(handler))
    assert len(out) == 2
    assert len(out[0]) == EMBED_DIM


def test_sends_bearer_token_and_pinned_model():
    seen = {}

    def handler(request):
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = request.read().decode()
        return httpx.Response(200, json={"data": [{"embedding": [0.0] * EMBED_DIM}]})

    embed_texts(["a"], token_provider=lambda: "secret", client=_client(handler))
    assert seen["auth"] == "Bearer secret"
    assert "model" in seen["body"]


def test_http_error_raises_embeddings_unavailable():
    def handler(request):
        return httpx.Response(503, json={"error": "down"})

    with pytest.raises(EmbeddingsUnavailable):
        embed_texts(["a"], token_provider=lambda: "t", client=_client(handler))


def test_missing_token_raises_embeddings_unavailable():
    def boom():
        raise RuntimeError("not logged in")

    with pytest.raises(EmbeddingsUnavailable):
        embed_texts(["a"], token_provider=boom)


def test_empty_input_short_circuits_without_a_call():
    def handler(request):  # pragma: no cover - must not be reached
        raise AssertionError("network call for empty input")

    assert embed_texts([], token_provider=lambda: "t", client=_client(handler)) == []
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_embed.py -v`
Expected: FAIL — `ImportError: cannot import name 'embed_texts'`

- [ ] **Step 3: Append the implementation to `src/brain_rag/embed.py`**

```python
from typing import Callable, Sequence

BATCH_SIZE = 64
TIMEOUT_SECONDS = 60.0


class EmbeddingsUnavailable(RuntimeError):
    """Raised when embeddings cannot be produced.

    Search catches this and degrades to BM25-only with ``vector=skipped``
    (spec section 10). Indexing lets it propagate — a partial index is worse
    than a failed run you can retry.
    """


def _default_token_provider() -> str:
    """Reuse Hermes' Nous OAuth. Never a plugin-local API key."""
    from hermes_cli.auth import resolve_nous_access_token

    return resolve_nous_access_token()


def embed_texts(
    texts: Sequence[str],
    *,
    token_provider: Callable[[], str] | None = None,
    client=None,
) -> list[list[float]]:
    """Embed ``texts`` in batches. Returns one vector per input, in order."""
    if not texts:
        return []

    import httpx

    provider = token_provider or _default_token_provider
    try:
        token = provider()
    except Exception as exc:  # noqa: BLE001 - any auth failure is unavailability
        raise EmbeddingsUnavailable(f"Nous token unavailable: {exc}") from exc

    owns_client = client is None
    http = client or httpx.Client(timeout=TIMEOUT_SECONDS)
    vectors: list[list[float]] = []
    try:
        for start in range(0, len(texts), BATCH_SIZE):
            batch = list(texts[start : start + BATCH_SIZE])
            try:
                response = http.post(
                    f"{NOUS_BASE_URL}/embeddings",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"model": NOUS_EMBED_MODEL, "input": batch},
                )
                response.raise_for_status()
                data = response.json()["data"]
            except Exception as exc:  # noqa: BLE001
                raise EmbeddingsUnavailable(f"Nous embeddings failed: {exc}") from exc
            vectors.extend([item["embedding"] for item in data])
    finally:
        if owns_client:
            http.close()
    return vectors
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_embed.py -v`
Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add src/brain_rag/embed.py tests/test_embed.py
git commit -m "feat(rag): Nous embeddings client reusing Hermes OAuth"
```

---

### Task 7: Indexer

**Files:**
- Create: `src/brain_rag/index.py`
- Create: `tests/fixtures/vault/Trading/Positions.md`
- Create: `tests/fixtures/vault/Construction/Tiferet.md`
- Create: `tests/fixtures/vault/Development/Hermes.md`
- Create: `tests/fixtures/vault/.obsidian/workspace.json`
- Create: `tests/test_index.py`

**Interfaces:**
- Consumes: `Store`, `chunk_note`, `should_skip`, `embed_texts`, `EmbeddingsUnavailable`
- Produces: `index_vault(vault_dir, store, *, mode="incremental", embed=True) -> dict`

- [ ] **Step 1: Write the fixture vault**

```markdown
<!-- tests/fixtures/vault/Trading/Positions.md -->
# Positions

## Straddle policy

Straddles run unstopped by design; per-leg stops break a two-sided book.

## Volatility view

Implied under realized is the entry condition I trust most.
```

```markdown
<!-- tests/fixtures/vault/Construction/Tiferet.md -->
# Tiferet

## Wallcovering

Mill list price per yard governs the takeoff; a rep quote overrides the website.

## Straddle

Ladder straddle spacing on the scaffold plan, unrelated to options.
```

```markdown
<!-- tests/fixtures/vault/Development/Hermes.md -->
# Hermes

## Profiles

Desktop plugin roots are profile-scoped and drift silently.
```

```json
{"note": "tests/fixtures/vault/.obsidian/workspace.json - must never be indexed"}
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_index.py
from pathlib import Path

import pytest

from brain_rag.embed import EmbeddingsUnavailable
from brain_rag.index import index_vault
from brain_rag.store import Store

VAULT = Path(__file__).parent / "fixtures" / "vault"


@pytest.fixture()
def store(tmp_path):
    s = Store.open(tmp_path / "brain.sqlite")
    yield s
    s.close()


def test_indexes_notes_and_skips_obsidian_dir(store):
    result = index_vault(VAULT, store, embed=False)
    assert result["files_indexed"] == 3
    paths = {r["path"] for r in store.bm25("straddle OR mill OR profile", limit=50)}
    assert not any(p.startswith(".obsidian") for p in paths)


def test_second_incremental_run_indexes_nothing_new(store):
    index_vault(VAULT, store, embed=False)
    before = store.count()
    result = index_vault(VAULT, store, embed=False)
    assert result["chunks_added"] == 0
    assert store.count() == before


def test_full_mode_rebuilds(store):
    index_vault(VAULT, store, embed=False)
    before = store.count()
    result = index_vault(VAULT, store, mode="full", embed=False)
    assert result["chunks_added"] == before
    assert store.count() == before


def test_missing_vault_raises_rather_than_indexing_nothing(store):
    with pytest.raises(FileNotFoundError):
        index_vault(Path("C:/nope/not/a/vault"), store, embed=False)


def test_embedding_failure_propagates(store, monkeypatch):
    def boom(texts, **kwargs):
        raise EmbeddingsUnavailable("down")

    monkeypatch.setattr("brain_rag.index.embed_texts", boom)
    with pytest.raises(EmbeddingsUnavailable):
        index_vault(VAULT, store, embed=True)
```

- [ ] **Step 3: Run it to verify it fails**

Run: `python -m pytest tests/test_index.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'brain_rag.index'`

- [ ] **Step 4: Write the implementation**

```python
# src/brain_rag/index.py
"""Walk the vault clone and keep the SQLite index in sync.

Incremental is the default: a file whose chunk hashes are already stored is
skipped without an embedding call. ``mode="full"`` clears each file's rows
first, which is what a model or chunker change requires.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from brain_rag.chunk import chunk_note, should_skip
from brain_rag.embed import embed_texts
from brain_rag.store import Store

EMBED_BATCH = 64


def index_vault(
    vault_dir: str | Path,
    store: Store,
    *,
    mode: str = "incremental",
    embed: bool = True,
) -> dict[str, Any]:
    """Index every markdown note under ``vault_dir``.

    Raises FileNotFoundError when the clone is missing — indexing nothing
    silently would leave an empty index that answers every query with no
    hits (spec section 10).
    """
    vault = Path(vault_dir)
    if not vault.is_dir():
        raise FileNotFoundError(f"Vault clone not found: {vault}")

    files_indexed = 0
    chunks_added = 0

    for path in sorted(vault.rglob("*.md")):
        rel = path.relative_to(vault).as_posix()
        if should_skip(rel):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        chunks = chunk_note(rel, text, mtime=path.stat().st_mtime)
        if mode == "full":
            store.delete_path(rel)
        else:
            known = store.known_hashes(rel)
            if known and all(c.content_hash in known for c in chunks):
                files_indexed += 1
                continue
            store.delete_path(rel)

        chunks_added += store.upsert_chunks(chunks)
        files_indexed += 1

    embedded = _embed_pending(store) if embed else 0
    return {
        "files_indexed": files_indexed,
        "chunks_added": chunks_added,
        "chunks_embedded": embedded,
        "total_chunks": store.count(),
        "mode": mode,
    }


def _embed_pending(store: Store) -> int:
    """Embed every chunk still missing a vector."""
    total = 0
    while True:
        pending = store.unembedded(limit=EMBED_BATCH)
        if not pending:
            return total
        vectors = embed_texts([row["text"] for row in pending])
        for row, vector in zip(pending, vectors):
            store.set_embedding(row["id"], vector)
        total += len(pending)
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `python -m pytest tests/test_index.py -v`
Expected: `5 passed`

- [ ] **Step 6: Commit**

```bash
git add src/brain_rag/index.py tests/fixtures/vault tests/test_index.py
git commit -m "feat(rag): incremental and full vault indexer"
```

---

### Task 8: Search — hybrid, RRF, filters, citations (ship-blocker)

**Files:**
- Create: `src/brain_rag/search.py`
- Create: `tests/test_search.py`

**Interfaces:**
- Consumes: `Store`, `embed_texts`, `EmbeddingsUnavailable`
- Produces: `search(store, query, *, leg="all", after=None, before=None, source="all", k=8) -> dict`; `rrf_merge(*ranked_lists, k=60) -> list`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_search.py
from pathlib import Path

import pytest

from brain_rag.embed import EmbeddingsUnavailable
from brain_rag.index import index_vault
from brain_rag.search import rrf_merge, search
from brain_rag.store import Store

VAULT = Path(__file__).parent / "fixtures" / "vault"


@pytest.fixture()
def store(tmp_path):
    s = Store.open(tmp_path / "brain.sqlite")
    index_vault(VAULT, s, embed=False)
    yield s
    s.close()


def _no_vectors(texts, **kwargs):
    raise EmbeddingsUnavailable("offline in tests")


def test_leg_filter_prevents_cross_leg_leak(store, monkeypatch):
    """Construction-scoped search must never return Trading chunks."""
    monkeypatch.setattr("brain_rag.search.embed_texts", _no_vectors)
    result = search(store, "straddle", leg="Construction")
    assert result["hits"]
    assert all(h["leg"] == "Construction" for h in result["hits"])
    assert all(not h["path"].startswith("Trading/") for h in result["hits"])


def test_every_hit_carries_citation_fields(store, monkeypatch):
    monkeypatch.setattr("brain_rag.search.embed_texts", _no_vectors)
    for hit in search(store, "straddle")["hits"]:
        assert hit["path"]
        assert hit["heading"] or hit["session_id"]
        assert hit["date"]
        assert hit["leg"]


def test_no_match_returns_empty_hits_not_an_error(store, monkeypatch):
    monkeypatch.setattr("brain_rag.search.embed_texts", _no_vectors)
    result = search(store, "zzzznotinthevault")
    assert result["hits"] == []
    assert "error" not in result


def test_embeddings_down_degrades_to_bm25_and_flags_it(store, monkeypatch):
    monkeypatch.setattr("brain_rag.search.embed_texts", _no_vectors)
    result = search(store, "straddle")
    assert result["vector"] == "skipped"
    assert result["hits"]


def test_k_caps_the_hit_count(store, monkeypatch):
    monkeypatch.setattr("brain_rag.search.embed_texts", _no_vectors)
    assert len(search(store, "straddle OR mill OR profile", k=1)["hits"]) == 1


def test_date_filters_bound_results(store, monkeypatch):
    monkeypatch.setattr("brain_rag.search.embed_texts", _no_vectors)
    assert search(store, "straddle", before="1990-01-01")["hits"] == []
    assert search(store, "straddle", after="1990-01-01")["hits"]


def test_source_filter_restricts_to_notes(store, monkeypatch):
    monkeypatch.setattr("brain_rag.search.embed_texts", _no_vectors)
    assert all(h["source"] == "note" for h in search(store, "straddle", source="note")["hits"])


def test_rrf_merge_rewards_agreement_between_lists():
    bm25 = [{"id": 1}, {"id": 2}, {"id": 3}]
    knn = [{"id": 3}, {"id": 2}, {"id": 9}]
    merged = [row["id"] for row in rrf_merge(bm25, knn)]
    assert merged[0] in (2, 3)
    assert set(merged) == {1, 2, 3, 9}
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_search.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'brain_rag.search'`

- [ ] **Step 3: Write the implementation**

```python
# src/brain_rag/search.py
"""Hybrid retrieval: BM25 + vector kNN, merged with reciprocal rank fusion.

Every hit carries its citation. An empty result is an empty list, never a
fabricated answer — the caller must not invent (spec section 8).
"""
from __future__ import annotations

from typing import Any, Sequence

from brain_rag.embed import EmbeddingsUnavailable, embed_texts
from brain_rag.leg import LEGS
from brain_rag.store import Store

RRF_K = 60
CANDIDATE_LIMIT = 50


def rrf_merge(*ranked_lists: Sequence[dict], k: int = RRF_K) -> list[dict]:
    """Reciprocal rank fusion. Rank position only — never raw scores.

    BM25 and cosine distance are not on a comparable scale, so fusing on
    score would let one list silently dominate.
    """
    scores: dict[Any, float] = {}
    rows: dict[Any, dict] = {}
    for ranked in ranked_lists:
        for position, row in enumerate(ranked):
            rid = row["id"]
            scores[rid] = scores.get(rid, 0.0) + 1.0 / (k + position + 1)
            rows.setdefault(rid, row)
    ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    out = []
    for rid, score in ordered:
        row = dict(rows[rid])
        row["score"] = score
        out.append(row)
    return out


def _fts_query(query: str) -> str:
    """FTS5 chokes on bare punctuation; keep operators, drop the rest."""
    cleaned = "".join(ch if (ch.isalnum() or ch.isspace() or ch in '"*') else " " for ch in query)
    return cleaned.strip() or '""'


def _passes(row: dict, *, leg: str, after: str | None, before: str | None, source: str) -> bool:
    if leg != "all" and row["leg"] != leg:
        return False
    if source != "all" and row["source"] != source:
        return False
    if after and row["date"] < after:
        return False
    if before and row["date"] > before:
        return False
    return True


def _to_hit(row: dict) -> dict[str, Any]:
    return {
        "text": row["text"],
        "path": row["path"],
        "heading": row["heading"],
        "leg": row["leg"],
        "source": row["source"],
        "date": row["date"],
        "session_id": row["session_id"],
        "wikilinks": [w for w in (row["wikilinks"] or "").split("|") if w],
        "score": round(float(row.get("score", 0.0)), 6),
    }


def search(
    store: Store,
    query: str,
    *,
    leg: str = "all",
    after: str | None = None,
    before: str | None = None,
    source: str = "all",
    k: int = 8,
) -> dict[str, Any]:
    """Hybrid search. Returns ``{"hits": [...], "vector": "used"|"skipped"}``."""
    if leg != "all" and leg not in LEGS:
        return {"error": f"Unknown leg {leg!r}; expected one of {LEGS} or 'all'."}
    if not query or not query.strip():
        return {"error": "Empty query."}

    bm25_rows = store.bm25(_fts_query(query), limit=CANDIDATE_LIMIT)

    vector_state = "used"
    knn_rows: list[dict] = []
    try:
        vectors = embed_texts([query])
        if vectors:
            knn_rows = store.knn(vectors[0], limit=CANDIDATE_LIMIT)
    except EmbeddingsUnavailable:
        vector_state = "skipped"

    merged = rrf_merge(bm25_rows, knn_rows) if knn_rows else rrf_merge(bm25_rows)
    filtered = [
        row for row in merged
        if _passes(row, leg=leg, after=after, before=before, source=source)
    ]
    return {"hits": [_to_hit(r) for r in filtered[:k]], "vector": vector_state}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_search.py -v`
Expected: `8 passed`

- [ ] **Step 5: Run the whole suite**

Run: `python -m pytest -v`
Expected: all green

- [ ] **Step 6: Commit**

```bash
git add src/brain_rag/search.py tests/test_search.py
git commit -m "feat(rag): hybrid search with RRF, filters, and citations"
```

---

### Task 9: Sweep — sessions into the vault

**Files:**
- Create: `src/brain_rag/sweep.py`
- Create: `tests/test_sweep.py`

**Interfaces:**
- Consumes: `leg_for_cwd`, `strip_tool_json`
- Produces: `sweep_sessions(state_db, vault_dir, *, older_than_days=7, push=True, runner=None) -> dict`; `session_note_path(leg, started, session_id) -> str`; `render_session_note(...) -> str`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_sweep.py
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
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_sweep.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'brain_rag.sweep'`

- [ ] **Step 3: Write the implementation**

```python
# src/brain_rag/sweep.py
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
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_sweep.py -v`
Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add src/brain_rag/sweep.py tests/test_sweep.py
git commit -m "feat(rag): weekly session sweep into leg-scoped vault notes"
```

---

### Task 10: Remind — the explicit vault door

**Files:**
- Create: `src/brain_rag/remind.py`
- Create: `tests/test_remind.py`

**Interfaces:**
- Consumes: `brain_rag.leg.LEGS`
- Produces: `remind(vault_dir, *, leg, title, body, runner=None) -> dict`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_remind.py
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
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_remind.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'brain_rag.remind'`

- [ ] **Step 3: Write the implementation**

```python
# src/brain_rag/remind.py
"""The explicit vault door: 'put this in the brain'.

The second and last vault writer (spec section 5). A leg is mandatory —
refusing beats guessing, because a wrong leg is exactly the cross-leg mixing
the vault rule exists to prevent.
"""
from __future__ import annotations

import subprocess
from datetime import date
from pathlib import Path
from typing import Any, Callable

from brain_rag.leg import LEGS


def _run_git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True)


def _safe_title(title: str) -> str:
    cleaned = "".join(ch for ch in title if ch not in '\\/:*?"<>|').strip()
    return cleaned or "Untitled"


def remind(
    vault_dir: str | Path,
    *,
    leg: str,
    title: str,
    body: str,
    runner: Callable[[list[str], Path], None] | None = None,
) -> dict[str, Any]:
    """Write or append a thin note in one leg, then commit it."""
    vault = Path(vault_dir)
    git = runner or _run_git
    if leg not in LEGS:
        return {"error": f"A leg is required; expected one of {LEGS}, got {leg!r}."}
    if not body or not body.strip():
        return {"error": "Empty body; nothing to remember."}
    if not vault.is_dir():
        return {"error": f"vault clone not found: {vault}"}

    rel = f"{leg}/{_safe_title(title)}.md"
    target = vault / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    stamp = date.today().isoformat()

    if target.exists():
        with target.open("a", encoding="utf-8") as fh:
            fh.write(f"\n\n## {stamp}\n\n{body.strip()}\n")
    else:
        target.write_text(
            "\n".join([
                "---", "type: note", f"leg: {leg}", f"created: {stamp}", "---",
                "", f"# {_safe_title(title)}", "", f"## {stamp}", "", body.strip(), "",
            ]),
            encoding="utf-8",
        )

    try:
        git(["add", rel], vault)
        git(["commit", "-m", f"docs(vault): remind — {_safe_title(title)}"], vault)
    except Exception as exc:  # noqa: BLE001
        return {"path": rel, "committed": False, "error": f"commit failed: {exc}"}
    return {"path": rel, "committed": True, "error": None}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_remind.py -v`
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add src/brain_rag/remind.py tests/test_remind.py
git commit -m "feat(rag): explicit remind writer with mandatory leg"
```

---

### Task 11: Agent plugin — `register(ctx)` with two tools

`plugin_api.py` and `__init__.py` are loaded **without package context** by Hermes (confirmed
by reading `interactive-artifacts/dashboard/plugin_api.py`, which loads its sibling `_core.py`
by explicit path). `_engine.py` is that same trick for this plugin.

**Files:**
- Create: `plugin/plugin.yaml`
- Create: `plugin/_engine.py`
- Create: `plugin/__init__.py`
- Create: `tests/test_plugin_register.py`

**Interfaces:**
- Consumes: `brain_rag.search.search`, `brain_rag.index.index_vault`, `brain_rag.store.Store`
- Produces: `register(ctx)` registering `rag_search` and `rag_index`; `_engine.load()` returning the engine modules

- [ ] **Step 1: Write the failing test**

```python
# tests/test_plugin_register.py
import json
from pathlib import Path

import pytest

PLUGIN_DIR = Path(__file__).resolve().parents[1] / "plugin"


def _load_plugin():
    import importlib.util

    spec = importlib.util.spec_from_file_location("brain_rag_plugin", PLUGIN_DIR / "__init__.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FakeCtx:
    def __init__(self):
        self.tools = {}

    def register_tool(self, *, name, toolset, schema, handler, **kwargs):
        self.tools[name] = {"schema": schema, "handler": handler, "toolset": toolset}


def test_registers_exactly_the_two_spec_tools():
    ctx = FakeCtx()
    _load_plugin().register(ctx)
    assert set(ctx.tools) == {"rag_search", "rag_index"}


def test_rag_search_schema_matches_spec_parameters():
    ctx = FakeCtx()
    _load_plugin().register(ctx)
    props = ctx.tools["rag_search"]["schema"]["parameters"]["properties"]
    assert {"query", "leg", "after", "before", "source", "k"} <= set(props)
    assert ctx.tools["rag_search"]["schema"]["parameters"]["required"] == ["query"]


def test_handlers_return_json_strings_not_dicts():
    ctx = FakeCtx()
    _load_plugin().register(ctx)
    out = ctx.tools["rag_search"]["handler"]({"query": ""})
    assert isinstance(out, str)
    assert "error" in json.loads(out)


def test_plugin_yaml_names_the_plugin_brain_rag():
    text = (PLUGIN_DIR / "plugin.yaml").read_text(encoding="utf-8")
    assert "name: brain-rag" in text
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_plugin_register.py -v`
Expected: FAIL — plugin files do not exist

- [ ] **Step 3: Write `plugin/plugin.yaml`**

```yaml
name: brain-rag
version: "0.1.0"
description: "Hybrid BM25 + vector retrieval over the obsidian-brain vault and swept Hermes sessions. Cited snippets only."
author: bottlefedchaney808
```

- [ ] **Step 4: Write `plugin/_engine.py`**

```python
"""Import the brain_rag engine from a plugin loaded without package context.

Hermes loads ``plugin_api.py`` standalone (no package), so a relative import
fails there. Both halves call :func:`load` and get the same modules.
"""
from __future__ import annotations

import sys
from pathlib import Path

ENGINE_SRC_ENV = "BRAIN_RAG_SRC"


def _candidate_roots() -> list[Path]:
    import os

    roots: list[Path] = []
    override = os.environ.get(ENGINE_SRC_ENV)
    if override:
        roots.append(Path(override))
    here = Path(__file__).resolve().parent
    roots.append(here / "vendor" / "src")          # deployed copy
    roots.append(here.parent / "src")              # repo checkout
    return roots


def load():
    """Return the engine namespace, importing it once."""
    for root in _candidate_roots():
        if (root / "brain_rag" / "__init__.py").exists():
            if str(root) not in sys.path:
                sys.path.insert(0, str(root))
            break
    from brain_rag import index as index_mod
    from brain_rag import remind as remind_mod
    from brain_rag import search as search_mod
    from brain_rag import store as store_mod

    return {
        "index": index_mod,
        "search": search_mod,
        "store": store_mod,
        "remind": remind_mod,
    }


def index_path() -> Path:
    """``$HERMES_HOME/rag/brain.sqlite`` — profile-scoped, never shared."""
    import os

    home = os.environ.get("HERMES_HOME")
    base = Path(home) if home else Path.home() / ".hermes"
    return base / "rag" / "brain.sqlite"


def vault_path() -> Path:
    import os

    return Path(os.environ.get("OBSIDIAN_VAULT_PATH") or Path.home() / "obsidian-vault")
```

- [ ] **Step 5: Write `plugin/__init__.py`**

```python
"""brain-rag agent half: rag_search and rag_index.

Handlers return JSON strings and report failures as ``{"error": ...}``;
they never raise into the tool loop.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_ENGINE_MODULE = "brain_rag_plugin_engine"


def _engine_helpers():
    existing = sys.modules.get(_ENGINE_MODULE)
    if existing is not None:
        return existing
    path = Path(__file__).resolve().parent / "_engine.py"
    spec = importlib.util.spec_from_file_location(_ENGINE_MODULE, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[_ENGINE_MODULE] = mod
    spec.loader.exec_module(mod)
    return mod


RAG_SEARCH_SCHEMA = {
    "name": "rag_search",
    "description": (
        "Search the Obsidian brain (notes + swept sessions) and return cited "
        "snippets. Every hit carries its path, leg, and date. An empty result "
        "means the brain has nothing — do not invent an answer."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "What to look for."},
            "leg": {
                "type": "string",
                "enum": ["all", "Construction", "Development", "Trading"],
                "description": "Restrict to one leg (default: all).",
                "default": "all",
            },
            "after": {"type": "string", "description": "ISO date lower bound (inclusive)."},
            "before": {"type": "string", "description": "ISO date upper bound (inclusive)."},
            "source": {
                "type": "string",
                "enum": ["all", "note", "session"],
                "description": "Restrict to notes or swept sessions.",
                "default": "all",
            },
            "k": {"type": "integer", "description": "Max hits (default 8).", "default": 8},
        },
        "required": ["query"],
    },
}

RAG_INDEX_SCHEMA = {
    "name": "rag_index",
    "description": (
        "Rebuild the brain index from the vault clone. 'incremental' skips "
        "unchanged files; 'full' re-chunks and re-embeds everything."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["incremental", "full"],
                "description": "Index mode (default: incremental).",
                "default": "incremental",
            }
        },
        "required": [],
    },
}


def _handle_rag_search(args, **_kwargs) -> str:
    helpers = _engine_helpers()
    query = (args or {}).get("query") or ""
    if not query.strip():
        return json.dumps({"error": "Empty query."})
    try:
        engine = helpers.load()
        store = engine["store"].Store.open(helpers.index_path())
        try:
            result = engine["search"].search(
                store,
                query,
                leg=args.get("leg", "all"),
                after=args.get("after"),
                before=args.get("before"),
                source=args.get("source", "all"),
                k=int(args.get("k", 8)),
            )
        finally:
            store.close()
        return json.dumps(result)
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": f"rag_search failed: {exc}"})


def _handle_rag_index(args, **_kwargs) -> str:
    helpers = _engine_helpers()
    mode = (args or {}).get("mode", "incremental")
    try:
        engine = helpers.load()
        store = engine["store"].Store.open(helpers.index_path())
        try:
            result = engine["index"].index_vault(helpers.vault_path(), store, mode=mode)
        finally:
            store.close()
        return json.dumps(result)
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": f"rag_index failed: {exc}"})


def register(ctx) -> None:
    """Called once by the Hermes plugin loader."""
    ctx.register_tool(
        name="rag_search", toolset="brain_rag",
        schema=RAG_SEARCH_SCHEMA, handler=_handle_rag_search,
    )
    ctx.register_tool(
        name="rag_index", toolset="brain_rag",
        schema=RAG_INDEX_SCHEMA, handler=_handle_rag_index,
    )
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `python -m pytest tests/test_plugin_register.py -v`
Expected: `4 passed`

- [ ] **Step 7: Commit**

```bash
git add plugin/plugin.yaml plugin/_engine.py plugin/__init__.py tests/test_plugin_register.py
git commit -m "feat(rag): agent plugin registering rag_search and rag_index"
```

---

### Task 12: Backend routes (`plugin_api.py`)

**Files:**
- Create: `plugin/dashboard/manifest.json`
- Create: `plugin/dashboard/plugin_api.py`
- Create: `tests/test_plugin_api.py`

**Interfaces:**
- Consumes: `plugin/_engine.py`
- Produces: `router: APIRouter` with `POST /search`, `POST /index`, `GET /status`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_plugin_api.py
import importlib.util
from pathlib import Path

import pytest

API = Path(__file__).resolve().parents[1] / "plugin" / "dashboard" / "plugin_api.py"


def _load_api():
    spec = importlib.util.spec_from_file_location("brain_rag_plugin_api", API)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_router_exposes_the_three_routes():
    paths = {r.path for r in _load_api().router.routes}
    assert {"/search", "/index", "/status"} <= paths


def test_manifest_points_at_plugin_api():
    import json

    manifest = json.loads((API.parent / "manifest.json").read_text(encoding="utf-8"))
    assert manifest == {"name": "brain-rag", "api": "plugin_api.py"}


def test_search_rejects_unknown_fields():
    mod = _load_api()
    with pytest.raises(Exception):
        mod.SearchRequest(query="x", sneaky="value")


def test_search_rejects_an_unknown_leg():
    mod = _load_api()
    with pytest.raises(Exception):
        mod.SearchRequest(query="x", leg="Cooking")


def test_k_is_bounded():
    mod = _load_api()
    with pytest.raises(Exception):
        mod.SearchRequest(query="x", k=9999)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_plugin_api.py -v`
Expected: FAIL — file does not exist

- [ ] **Step 3: Write `plugin/dashboard/manifest.json`**

```json
{
  "name": "brain-rag",
  "api": "plugin_api.py"
}
```

- [ ] **Step 4: Write `plugin/dashboard/plugin_api.py`**

```python
"""Plugin-scoped backend for brain-rag. Mounts at /api/plugins/brain-rag/.

Loaded standalone by the web server (no package context), so the engine is
reached through ``_engine.py`` by explicit path. Responses carry retrieval
results only — never tokens, never absolute filesystem paths.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter()

_ENGINE_MODULE = "brain_rag_plugin_engine"


def _engine_helpers():
    existing = sys.modules.get(_ENGINE_MODULE)
    if existing is not None:
        return existing
    path = Path(__file__).resolve().parent.parent / "_engine.py"
    spec = importlib.util.spec_from_file_location(_ENGINE_MODULE, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load brain-rag engine helpers from {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[_ENGINE_MODULE] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception:
        sys.modules.pop(_ENGINE_MODULE, None)
        raise
    return mod


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=2000)
    leg: Literal["all", "Construction", "Development", "Trading"] = "all"
    after: Optional[str] = Field(default=None, max_length=10)
    before: Optional[str] = Field(default=None, max_length=10)
    source: Literal["all", "note", "session"] = "all"
    k: int = Field(default=8, ge=1, le=50)


class IndexRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["incremental", "full"] = "incremental"


@router.post("/search")
async def search_endpoint(body: SearchRequest):
    helpers = _engine_helpers()
    try:
        engine = helpers.load()
        store = engine["store"].Store.open(helpers.index_path())
        try:
            return engine["search"].search(
                store, body.query, leg=body.leg, after=body.after,
                before=body.before, source=body.source, k=body.k,
            )
        finally:
            store.close()
    except Exception:
        raise HTTPException(status_code=503, detail="brain-rag index unavailable")


@router.post("/index")
async def index_endpoint(body: IndexRequest):
    helpers = _engine_helpers()
    try:
        engine = helpers.load()
        store = engine["store"].Store.open(helpers.index_path())
        try:
            return engine["index"].index_vault(
                helpers.vault_path(), store, mode=body.mode
            )
        finally:
            store.close()
    except Exception:
        raise HTTPException(status_code=503, detail="brain-rag index run failed")


@router.get("/status")
async def status_endpoint():
    helpers = _engine_helpers()
    try:
        engine = helpers.load()
        store = engine["store"].Store.open(helpers.index_path())
        try:
            return {"ok": True, "chunks": store.count()}
        finally:
            store.close()
    except Exception:
        return {"ok": False, "chunks": 0}
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `python -m pytest tests/test_plugin_api.py -v`
Expected: `5 passed`

- [ ] **Step 6: Commit**

```bash
git add plugin/dashboard tests/test_plugin_api.py
git commit -m "feat(rag): plugin-scoped backend routes for search, index, status"
```

---

### Task 13: Desktop pane

**Files:**
- Create: `plugin/desktop/plugin.js`
- Create: `tests/test_desktop_plugin_shape.py`

**Interfaces:**
- Consumes: `ctx.rest('/search')` from Task 12
- Produces: default-exported `HermesPlugin` with `id: 'brain-rag'`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_desktop_plugin_shape.py
import re
import shutil
import subprocess
from pathlib import Path

import pytest

PLUGIN_JS = Path(__file__).resolve().parents[1] / "plugin" / "desktop" / "plugin.js"


def test_no_jsx_syntax_only_jsx_calls():
    """The disk plugin loads uncompiled; JSX syntax would fail to parse."""
    source = PLUGIN_JS.read_text(encoding="utf-8")
    assert not re.search(r"<[A-Za-z][A-Za-z0-9]*\s*[/>]", source)
    assert "jsx(" in source


def test_only_allowed_specifiers_are_imported():
    source = PLUGIN_JS.read_text(encoding="utf-8")
    imports = set(re.findall(r"from\s+['\"]([^'\"]+)['\"]", source))
    assert imports <= {"@hermes/plugin-sdk", "react", "react/jsx-runtime"}


def test_declares_the_brain_rag_id():
    assert "id: 'brain-rag'" in PLUGIN_JS.read_text(encoding="utf-8")


def test_no_hardcoded_colors():
    source = PLUGIN_JS.read_text(encoding="utf-8")
    assert not re.search(r"#[0-9a-fA-F]{3,6}\b", source)
    assert "rgb(" not in source


@pytest.mark.skipif(shutil.which("node") is None, reason="node not on PATH")
def test_node_syntax_check_passes():
    result = subprocess.run(["node", "--check", str(PLUGIN_JS)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_desktop_plugin_shape.py -v`
Expected: FAIL — file does not exist

- [ ] **Step 3: Write `plugin/desktop/plugin.js`**

```javascript
// brain-rag desktop pane — search the Obsidian brain from the app.
// Loaded UNCOMPILED: jsx() calls only, no JSX syntax.
import { host } from '@hermes/plugin-sdk'
import { useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

const LEGS = ['all', 'Construction', 'Development', 'Trading']

function BrainRagPane(props) {
  const rest = props.rest
  const [query, setQuery] = useState('')
  const [leg, setLeg] = useState('all')
  const [hits, setHits] = useState([])
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState('')

  async function runSearch() {
    if (!query.trim()) return
    setBusy(true)
    setNote('')
    try {
      const result = await rest('/search', {
        method: 'POST',
        body: { query: query, leg: leg, k: 8 }
      })
      const found = (result && result.hits) || []
      setHits(found)
      if (found.length === 0) setNote('No hits in the brain.')
      else if (result.vector === 'skipped') setNote('Keyword only — embeddings unavailable.')
    } catch (err) {
      setHits([])
      setNote('brain-rag backend unavailable.')
    } finally {
      setBusy(false)
    }
  }

  const rows = hits.map(function (hit, i) {
    const where = hit.heading ? hit.path + ' § ' + hit.heading : hit.path
    return jsxs('div', {
      className: 'flex flex-col gap-1 border-b border-(--ui-stroke-secondary) py-2',
      children: [
        jsx('div', {
          className: 'text-[0.6875rem] text-(--ui-text-tertiary)',
          children: hit.leg + ' · ' + hit.date + ' · ' + where
        }),
        jsx('div', {
          className: 'text-xs text-(--ui-text-secondary)',
          children: String(hit.text || '').slice(0, 300)
        })
      ]
    }, hit.path + ':' + i)
  })

  return jsxs('div', {
    className: 'flex h-full flex-col gap-2 p-3 text-sm',
    children: [
      jsxs('div', {
        className: 'flex gap-2',
        children: [
          jsx('input', {
            className: 'flex-1 rounded border border-(--ui-stroke-secondary) px-2 py-1 text-xs',
            placeholder: 'search the brain',
            value: query,
            onChange: function (e) { setQuery(e.target.value) },
            onKeyDown: function (e) { if (e.key === 'Enter') void runSearch() }
          }),
          jsx('select', {
            className: 'rounded border border-(--ui-stroke-secondary) px-1 text-xs',
            value: leg,
            onChange: function (e) { setLeg(e.target.value) },
            children: LEGS.map(function (l) {
              return jsx('option', { value: l, children: l }, l)
            })
          })
        ]
      }),
      note
        ? jsx('div', { className: 'text-[0.6875rem] text-(--ui-text-quaternary)', children: note })
        : null,
      jsx('div', {
        className: 'flex-1 overflow-auto',
        children: busy
          ? jsx('div', { className: 'text-xs text-(--ui-text-tertiary)', children: 'searching…' })
          : rows
      })
    ]
  })
}

export default {
  id: 'brain-rag',
  name: 'Brain RAG',
  register(ctx) {
    ctx.register({
      id: 'pane',
      area: 'panes',
      title: 'brain',
      data: { placement: 'right', width: '320px' },
      render: function () { return jsx(BrainRagPane, { rest: ctx.rest }) }
    })
    ctx.register({
      id: 'reindex',
      area: 'palette',
      data: {
        title: 'Brain RAG: reindex vault',
        run: async function () {
          try {
            await ctx.rest('/index', { method: 'POST', body: { mode: 'incremental' } })
            host.notify({ kind: 'info', message: 'brain-rag reindexed' })
          } catch (err) {
            host.notify({ kind: 'error', message: 'brain-rag reindex failed' })
          }
        }
      }
    })
  }
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_desktop_plugin_shape.py -v`
Expected: `5 passed` (or `4 passed, 1 skipped` without node)

- [ ] **Step 5: Commit**

```bash
git add plugin/desktop/plugin.js tests/test_desktop_plugin_shape.py
git commit -m "feat(rag): desktop pane with leg filter and cited hits"
```

---

### Task 14: Deploy script — every profile root

**Files:**
- Create: `scripts/deploy.cmd`
- Create: `tests/test_deploy_script.py`

**Interfaces:**
- Consumes: `plugin/` tree, `src/brain_rag/`
- Produces: deployed copies under each profile's `$HERMES_HOME/plugins/brain-rag/`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_deploy_script.py
from pathlib import Path

DEPLOY = Path(__file__).resolve().parents[1] / "scripts" / "deploy.cmd"


def test_deploys_to_the_default_profile_root():
    text = DEPLOY.read_text(encoding="utf-8")
    assert r"%LOCALAPPDATA%\hermes\plugins\brain-rag" in text


def test_deploys_to_named_profile_roots():
    """The 2026-09-09 silent-drift bug: global-only copy leaves profiles stale."""
    text = DEPLOY.read_text(encoding="utf-8")
    assert r"profiles\local-agent\plugins\brain-rag" in text


def test_vendors_the_engine_next_to_the_plugin():
    text = DEPLOY.read_text(encoding="utf-8")
    assert "vendor" in text


def test_prints_the_plugins_enabled_reminder():
    text = DEPLOY.read_text(encoding="utf-8").lower()
    assert "plugins.enabled" in text
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_deploy_script.py -v`
Expected: FAIL — file does not exist

- [ ] **Step 3: Write `scripts/deploy.cmd`**

```bat
@echo off
REM Deploy brain-rag to EVERY profile root that should have it.
REM The desktop/agent plugin root is profile-scoped: copying only the global
REM root leaves named profiles running a stale copy with no error anywhere.

setlocal
set SRC=%~dp0..
set ROOTS=%LOCALAPPDATA%\hermes\plugins\brain-rag
set ROOTS=%ROOTS%;%LOCALAPPDATA%\hermes\profiles\local-agent\plugins\brain-rag

for %%R in ("%ROOTS:;=" "%") do (
    echo Deploying to %%~R
    if not exist "%%~R" mkdir "%%~R"
    xcopy /Y /E /I /Q "%SRC%\plugin\*" "%%~R\" >nul
    if not exist "%%~R\vendor\src" mkdir "%%~R\vendor\src"
    xcopy /Y /E /I /Q "%SRC%\src\*" "%%~R\vendor\src\" >nul
)

echo.
echo Deployed. Two more steps, both required:
echo   1. Add brain-rag to plugins.enabled in EACH profile's config.yaml.
echo      Desktop Settings -^> Plugins does NOT import the Python half;
echo      without plugins.enabled every ctx.rest call answers 405.
echo   2. Restart the supervised backend so the routes mount
echo      (route mounts happen at process import; a rescan does not remount).
endlocal
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_deploy_script.py -v`
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add scripts/deploy.cmd tests/test_deploy_script.py
git commit -m "feat(rag): deploy script covering every profile plugin root"
```

---

### Task 15: Eval gate

**Files:**
- Create: `tests/eval/__init__.py`
- Create: `tests/eval/golden.md`
- Create: `tests/eval/test_golden.py`
- Create: `tests/test_eval_gate.py`

**Interfaces:**
- Consumes: `search`, `index_vault`, `Store`
- Produces: `pytest -m golden` local-only eval; always-on fixture gate

- [ ] **Step 1: Write the golden question list**

```markdown
<!-- tests/eval/golden.md -->
# Golden retrieval questions

Run locally against the real vault clone:

    python -m pytest tests/eval -m golden -v

Scored per question: correct note retrieved, leg correct, citation present.
Wrong-leg leak or a citation-less hit is a FAIL, not a warning.

1. Why did I stop using strategy X?
2. What are my strongest risk-management conclusions?
3. What lessons repeatedly appear after losses?
4. What indicators do I trust most?
5. What recurring themes exist across successful trades?
6. What mistakes do I repeatedly make?
7. What are my best trading insights about volatility?
8. How has my thinking on factor investing changed over time?
9. What did I believe before drawdown Y?
10. Find observations about earnings reactions.
```

- [ ] **Step 2: Write the always-on fixture gate**

```python
# tests/test_eval_gate.py
from pathlib import Path

import pytest

from brain_rag.embed import EmbeddingsUnavailable
from brain_rag.index import index_vault
from brain_rag.search import search
from brain_rag.store import Store

VAULT = Path(__file__).parent / "fixtures" / "vault"


@pytest.fixture()
def store(tmp_path):
    s = Store.open(tmp_path / "brain.sqlite")
    index_vault(VAULT, s, embed=False)
    yield s
    s.close()


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    def boom(texts, **kwargs):
        raise EmbeddingsUnavailable("offline in tests")

    monkeypatch.setattr("brain_rag.search.embed_texts", boom)


def test_gate_no_cross_leg_leak_in_either_direction(store):
    """'straddle' exists in BOTH Trading and Construction fixtures."""
    for leg in ("Trading", "Construction"):
        for hit in search(store, "straddle", leg=leg)["hits"]:
            assert hit["leg"] == leg


def test_gate_every_hit_is_citable(store):
    for query in ("straddle", "mill", "profile"):
        for hit in search(store, query)["hits"]:
            assert hit["path"]
            assert hit["heading"] or hit["session_id"]
            assert hit["date"]
            assert hit["leg"]


def test_gate_unknown_query_yields_no_fabricated_hits(store):
    assert search(store, "quarterly unicorn provisioning")["hits"] == []
```

- [ ] **Step 3: Write the local-only golden eval**

```python
# tests/eval/test_golden.py
import os
from pathlib import Path

import pytest

from brain_rag.index import index_vault
from brain_rag.leg import LEGS
from brain_rag.search import search
from brain_rag.store import Store

QUESTIONS = [
    "Why did I stop using strategy X?",
    "What are my strongest risk-management conclusions?",
    "What lessons repeatedly appear after losses?",
    "What indicators do I trust most?",
    "What recurring themes exist across successful trades?",
    "What mistakes do I repeatedly make?",
    "What are my best trading insights about volatility?",
    "How has my thinking on factor investing changed over time?",
    "What did I believe before drawdown Y?",
    "Find observations about earnings reactions.",
]


def _vault() -> Path:
    return Path(os.environ.get("OBSIDIAN_VAULT_PATH") or Path.home() / "obsidian-vault")


@pytest.fixture(scope="module")
def store(tmp_path_factory):
    vault = _vault()
    if not vault.is_dir():
        pytest.skip(f"No vault clone at {vault}")
    s = Store.open(tmp_path_factory.mktemp("eval") / "brain.sqlite")
    index_vault(vault, s)
    yield s
    s.close()


@pytest.mark.golden
@pytest.mark.parametrize("question", QUESTIONS)
def test_golden_question_returns_citable_hits(question, store):
    result = search(store, question, k=8)
    assert result["hits"], f"No hits for: {question}"
    for hit in result["hits"]:
        assert hit["path"], f"Missing citation path for: {question}"
        assert hit["heading"] or hit["session_id"]
        assert hit["date"]
        assert hit["leg"] in LEGS
```

```python
# tests/eval/__init__.py
```

- [ ] **Step 4: Run both layers**

Run: `python -m pytest tests/test_eval_gate.py -v`
Expected: `3 passed`

Run: `python -m pytest tests/eval -m golden -v`
Expected: `10 passed` (or skipped without a vault clone). Any failure blocks the ship.

Run: `python -m pytest -v`
Expected: full suite green, golden deselected by default.

- [ ] **Step 5: Commit**

```bash
git add tests/eval tests/test_eval_gate.py
git commit -m "test(rag): eval gate for leg isolation and citation coverage"
```

---

### Task 16: Wire the weekly cron (only after 9 and 15 are green)

**Files:**
- Create: `scripts/weekly_sweep.py`
- Create: `docs/runbook.md`
- Create: `tests/test_weekly_sweep_script.py`

**Interfaces:**
- Consumes: `sweep_sessions`, `index_vault`, `Store`
- Produces: `main() -> int` — sweep then reindex, one exit code

- [ ] **Step 1: Write the failing test**

```python
# tests/test_weekly_sweep_script.py
import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "weekly_sweep.py"


def _load():
    spec = importlib.util.spec_from_file_location("weekly_sweep", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_exposes_main():
    assert callable(_load().main)


def test_never_calls_prune():
    """Prune deletes transcripts; it is not an intake path."""
    assert "prune" not in SCRIPT.read_text(encoding="utf-8").lower()


def test_sweeps_before_reindexing():
    text = SCRIPT.read_text(encoding="utf-8")
    assert text.index("sweep_sessions") < text.index("index_vault")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_weekly_sweep_script.py -v`
Expected: FAIL — file does not exist

- [ ] **Step 3: Write `scripts/weekly_sweep.py`**

```python
"""Weekly: sweep old sessions into the vault, then refresh the index.

Sweep first — a reindex before the sweep would miss the notes just written.
This script never deletes sessions from state.db.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brain_rag.index import index_vault  # noqa: E402
from brain_rag.store import Store  # noqa: E402
from brain_rag.sweep import sweep_sessions  # noqa: E402


def _hermes_home() -> Path:
    return Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")


def _vault() -> Path:
    return Path(os.environ.get("OBSIDIAN_VAULT_PATH") or Path.home() / "obsidian-vault")


def main() -> int:
    home = _hermes_home()
    report = {"sweep": None, "index": None}

    sweep_result = sweep_sessions(home / "state.db", _vault(), older_than_days=7)
    report["sweep"] = sweep_result

    store = Store.open(home / "rag" / "brain.sqlite")
    try:
        report["index"] = index_vault(_vault(), store, mode="incremental")
    finally:
        store.close()

    print(json.dumps(report, indent=2))
    return 1 if sweep_result.get("error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Write `docs/runbook.md`**

```markdown
# brain-rag runbook

## Deploy

    scripts\deploy.cmd

Then, per profile that should have RAG:

1. Add `brain-rag` to `plugins.enabled` in that profile's `config.yaml`.
   Desktop Settings -> Plugins does **not** import the Python half.
2. Restart the supervised backend so `/api/plugins/brain-rag/*` mounts.
   Route mounts happen at process import; a plugin rescan does not remount.

Verify: `GET /api/plugins/brain-rag/status` returns `{"ok": true, ...}`.

## Weekly cron (profile `default`, after the eval gate is green)

    hermes cron add "weekly sweep and reindex the brain" \
      --schedule "0 5 * * 1" \
      --command "python C:/Users/bottl/hermes-custom/RAG/scripts/weekly_sweep.py"

Exit 1 means the sweep hit an error; the commit may be local and unpushed.
Re-running is safe — existing session notes are skipped.

## Manual

    python scripts/weekly_sweep.py          # sweep + incremental index
    hermes chat -q "rag_index full"         # after a model or chunker change

## Backfill

Sessions already exported to
`C:/Users/bottl/hermes-salvage-20260909/session-exports/` are holding-pen
material, not vault content. Three hidden desktop sessions remain in
`state.db` (Bot Chat, Group: Connected Chat, dealer-model review) — they
become sweep fuel once they fall outside the window; no separate step.
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `python -m pytest tests/test_weekly_sweep_script.py -v`
Expected: `3 passed`

- [ ] **Step 6: Run the full suite**

Run: `python -m pytest -v`
Expected: all green

- [ ] **Step 7: Commit**

```bash
git add scripts/weekly_sweep.py docs/runbook.md tests/test_weekly_sweep_script.py
git commit -m "feat(rag): weekly sweep entrypoint and deployment runbook"
```

---

## Spec coverage

| Spec section | Task |
|---|---|
| 1 Purpose — cited snippets | 8, 15 |
| 2 Non-goals | File Structure YAGNI list |
| 3 Unified plugin | 11, 12, 13 |
| 3 Mem0 stays | Global Constraints (no `MemoryProvider` anywhere) |
| 3 Nous embeddings | 1, 6 |
| 3 Per-profile sqlite | 5, 11 (`_engine.index_path`) |
| 4 Profile-scoped deploy | 14 |
| 5 Two vault doors | 9, 10 |
| 6 Session path + frontmatter | 9 |
| 7 Chunking + skip rules | 3, 4 |
| 8 Hybrid + RRF + filters + citations | 8 |
| 9 Tool contracts | 11 |
| 10 Fail closed | 6, 7, 8, 9, 12 |
| 11 Eval gate | 15 |
| 12 MEMORY.md pointers only | Global Constraints (nothing writes it) |
| 13 No core patch | Global Constraints |
| 14 Later | Excluded |

## Risks

- **Profile-scoped plugin roots.** Deploying only to the global root leaves named profiles on a stale copy with no error anywhere — this cost ~40 minutes on 2026-09-09. Task 14 covers every root; add a root there when a new profile should have RAG.
- **`plugins.enabled` is the real Python gate.** Enabling in Desktop Settings does not import `plugin_api.py` (GHSA-mcfc-hp25-cjv7). Symptom is 405 on every `ctx.rest` call. The deploy script prints this; the runbook repeats it.
- **Routes mount at process import.** A plugin rescan does not remount. Restart the supervised backend after deploying.
- **`plugin.js` loads uncompiled.** JSX syntax will not parse. Task 13 asserts this rather than trusting review.
- **Engine import has no package context.** Both plugin halves load `_engine.py` by explicit path, mirroring how `interactive-artifacts` loads its `_core.py`.
- **Embedding model changes invalidate stored vectors.** `EMBED_DIM` is baked into the vec table. Changing `NOUS_EMBED_MODEL` requires `rag_index(mode="full")` against a fresh index file.
- **sqlite-vec query dialect.** Verified installable (0.1.9) with `enable_load_extension == True` on this interpreter. If `MATCH ? AND k = ?` errors, adjust the SQL to the pinned version — do not float the version.
- **Sweep must not resurrect stale snapshots.** Live `Trading/Positions.md` is newer than the parked stash at `hermes-salvage-20260909/session-exports/vault-stash-Trading-Positions.md`. Sweep only writes new files under `{Leg}/Sessions/` and skips existing paths; it never rewrites a leg note.
- **`hermes sessions prune` deletes.** Task 16 asserts the string never appears in the sweep script.
- **Git identity is repo-local.** Already set here to match the vault. Never `--global`.
- **Golden eval is local-only.** It reads the real vault; the fixture gate is what runs by default.

## Open questions

1. Which profiles beyond `default` and `local-agent` should carry RAG? Task 14 currently deploys to those two.
2. Should the holding pen move from `hermes-salvage-20260909/session-exports/` to a dedicated intake dir before the first real sweep? The spec leaves this as "until a dedicated intake dir is wired."
