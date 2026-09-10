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


def test_malformed_200_json_raises_embeddings_unavailable():
    cases = [
        {},
        {"data": None},
        {"data": [{}]},
        {"data": [{"embedding": None}]},
    ]
    for payload in cases:
        def handler(request, payload=payload):
            return httpx.Response(200, json=payload)

        with pytest.raises(EmbeddingsUnavailable):
            embed_texts(["a"], token_provider=lambda: "t", client=_client(handler))


def test_wrong_count_or_width_raises_embeddings_unavailable():
    def too_few(request):
        return httpx.Response(200, json={"data": [{"embedding": [0.0] * EMBED_DIM}]})

    def too_many(request):
        vec = [0.0] * EMBED_DIM
        return httpx.Response(200, json={"data": [{"embedding": vec}, {"embedding": vec}]})

    def wrong_width(request):
        return httpx.Response(200, json={"data": [{"embedding": [0.0] * (EMBED_DIM - 1)}]})

    with pytest.raises(EmbeddingsUnavailable):
        embed_texts(["a", "b"], token_provider=lambda: "t", client=_client(too_few))
    with pytest.raises(EmbeddingsUnavailable):
        embed_texts(["a"], token_provider=lambda: "t", client=_client(too_many))
    with pytest.raises(EmbeddingsUnavailable):
        embed_texts(["a"], token_provider=lambda: "t", client=_client(wrong_width))
