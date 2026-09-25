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


class _FakeStore:
    def close(self):
        return None


def _store_mod(open_impl=None):
    opener = open_impl or (lambda _p: _FakeStore())
    return type("StoreMod", (), {"Store": type("Store", (), {"open": staticmethod(opener)})})


def test_rag_search_does_not_pass_negative_k_as_tail_slice(monkeypatch, tmp_path):
    captured = {}

    class FakeEngineHelpers:
        def allowed_legs(self):
            return None

        def load(self):
            return {
                "store": _store_mod(),
                "search": type(
                    "R",
                    (),
                    {
                        "search": staticmethod(
                            lambda store, query, **kwargs: captured.update(kwargs)
                            or {"hits": [], "vector": "skipped"}
                        )
                    },
                ),
            }

        def index_path(self):
            return tmp_path / "brain.sqlite"

        def vault_path(self):
            return tmp_path / "vault"

    (tmp_path / "vault").mkdir()
    plugin = _load_plugin()
    monkeypatch.setattr(plugin, "_engine_helpers", lambda: FakeEngineHelpers())
    ctx = FakeCtx()
    plugin.register(ctx)
    out = ctx.tools["rag_search"]["handler"]({"query": "straddle", "k": -1})
    payload = json.loads(out)
    assert "error" not in payload
    assert captured["k"] >= 1


def test_rag_search_errors_when_vault_missing(monkeypatch, tmp_path):
    class FakeEngineHelpers:
        def allowed_legs(self):
            return None

        def load(self):
            def fake_search(*_a, **_k):
                return {
                    "hits": [{
                        "text": "stale sqlite hit",
                        "path": "Trading/X.md",
                        "heading": "h",
                        "leg": "Trading",
                        "source": "note",
                        "date": "2026-01-01",
                        "session_id": None,
                        "wikilinks": [],
                        "score": 1.0,
                    }],
                    "vector": "skipped",
                }

            return {
                "store": _store_mod(),
                "search": type("R", (), {"search": staticmethod(fake_search)}),
            }

        def index_path(self):
            return tmp_path / "brain.sqlite"

        def vault_path(self):
            return tmp_path / "missing-vault"

    plugin = _load_plugin()
    monkeypatch.setattr(plugin, "_engine_helpers", lambda: FakeEngineHelpers())
    ctx = FakeCtx()
    plugin.register(ctx)
    out = ctx.tools["rag_search"]["handler"]({"query": "straddle"})
    payload = json.loads(out)
    assert "error" in payload
    assert not payload.get("hits")
    assert "stale sqlite hit" not in out
