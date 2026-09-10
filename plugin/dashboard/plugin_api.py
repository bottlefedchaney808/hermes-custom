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
    vault = helpers.vault_path()
    if not vault.is_dir():
        raise HTTPException(status_code=503, detail=f"Vault clone not found: {vault}")
    try:
        engine = helpers.load()
        store = engine["store"].Store.open(helpers.index_path())
        try:
            result = engine["search"].search(
                store, body.query, leg=body.leg, after=body.after,
                before=body.before, source=body.source, k=body.k,
                vault_dir=vault,
            )
        finally:
            store.close()
        if "error" in result:
            raise HTTPException(status_code=503, detail=result["error"])
        return result
    except HTTPException:
        raise
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
