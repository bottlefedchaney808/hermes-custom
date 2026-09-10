"""Nous Portal embeddings + the sqlite-vec extension loader.

The model id and dimension below were pinned from a live
``/v1/models`` + ``/v1/embeddings`` probe (Task 1). Changing the model
changes the vector width, which invalidates every stored embedding —
a model change REQUIRES ``rag_index(mode="full")``.
"""
from __future__ import annotations

import sqlite3
from typing import Callable, Sequence

# Pinned in Task 1 from the live Portal catalog. Replace both together.
NOUS_EMBED_MODEL = "qwen/qwen3-embedding-8b"
EMBED_DIM = 4096

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
                embeddings = [item["embedding"] for item in data]
            except Exception as exc:  # noqa: BLE001
                raise EmbeddingsUnavailable(f"Nous embeddings failed: {exc}") from exc
            if len(embeddings) != len(batch) or any(
                embedding is None or len(embedding) != EMBED_DIM for embedding in embeddings
            ):
                raise EmbeddingsUnavailable(
                    "Nous embeddings returned wrong count or vector width"
                )
            vectors.extend(embeddings)
    finally:
        if owns_client:
            http.close()
    return vectors
