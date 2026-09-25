import pytest


@pytest.fixture(autouse=True)
def _fresh_query_cache():
    """The query-vector cache is module state; never let one test's vectors leak into another."""
    from brain_rag.search import clear_query_cache

    clear_query_cache()
    yield
    clear_query_cache()
