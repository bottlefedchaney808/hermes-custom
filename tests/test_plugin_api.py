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
