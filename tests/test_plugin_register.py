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
