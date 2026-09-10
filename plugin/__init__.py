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
