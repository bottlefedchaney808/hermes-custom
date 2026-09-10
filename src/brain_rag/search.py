"""Hybrid retrieval: BM25 + vector kNN, merged with reciprocal rank fusion.

Every hit carries its citation. An empty result is an empty list, never a
fabricated answer — the caller must not invent (spec section 8).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Sequence

from brain_rag.embed import EmbeddingsUnavailable, embed_texts
from brain_rag.leg import LEGS
from brain_rag.store import Store

RRF_K = 60
CANDIDATE_LIMIT = 50
DEFAULT_K = 8
MAX_K = 50


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


def _clamp_k(k: int) -> int:
    try:
        value = int(k)
    except (TypeError, ValueError):
        return DEFAULT_K
    if value < 1:
        return DEFAULT_K
    return min(value, MAX_K)


def _missing_vault_error(vault_dir: str | Path | None) -> str | None:
    resolved: Path | None = Path(vault_dir) if vault_dir is not None else None
    if resolved is None:
        env = os.environ.get("OBSIDIAN_VAULT_PATH")
        if env:
            resolved = Path(env)
    if resolved is not None and not resolved.is_dir():
        return f"Vault clone not found: {resolved}"
    return None


def search(
    store: Store,
    query: str,
    *,
    leg: str = "all",
    after: str | None = None,
    before: str | None = None,
    source: str = "all",
    k: int = 8,
    vault_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Hybrid search. Returns ``{"hits": [...], "vector": "used"|"skipped"}``."""
    missing = _missing_vault_error(vault_dir)
    if missing:
        return {"error": missing}
    if leg != "all" and leg not in LEGS:
        return {"error": f"Unknown leg {leg!r}; expected one of {LEGS} or 'all'."}
    if not query or not query.strip():
        return {"error": "Empty query."}
    k = _clamp_k(k)

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
