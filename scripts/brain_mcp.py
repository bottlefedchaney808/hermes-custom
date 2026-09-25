"""brain-rag as an MCP stdio server, so Claude Code (or any MCP client) can search the brain.

Thin wrapper: the tool handlers are the Hermes plugin's own ``_handle_rag_search`` /
``_handle_rag_index``, so results, leg boundaries and error shapes match what Hermes sees.

Run with the hermes-agent venv (it has sqlite-vec, mcp, and hermes_cli for the Nous
embeddings token). HERMES_HOME picks the index: ``$HERMES_HOME/rag/brain.sqlite``.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

HERMES_HOME = Path(os.environ.setdefault("HERMES_HOME", str(Path.home() / ".hermes")))
# hermes_cli.auth resolves the Nous token for query embeddings; without it search is BM25-only.
sys.path.insert(0, str(HERMES_HOME / "hermes-agent"))

_spec = importlib.util.spec_from_file_location(
    "brain_rag_plugin", HERMES_HOME / "plugins" / "brain-rag" / "__init__.py")
plugin = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(plugin)

from mcp.server import MCPServer  # noqa: E402  (mcp 2.0; was FastMCP)

mcp = MCPServer("brain")


@mcp.tool(description=plugin.RAG_SEARCH_SCHEMA["description"])
def rag_search(query: str, leg: str = "all", after: str | None = None,
               before: str | None = None, source: str = "all", k: int = 8) -> str:
    """leg: all|Construction|Development|Trading. source: all|note|session.
    after/before: ISO dates (inclusive). k: max hits (1-50)."""
    return plugin._handle_rag_search({"query": query, "leg": leg, "after": after,
                                      "before": before, "source": source, "k": k})


@mcp.tool(description=plugin.RAG_INDEX_SCHEMA["description"])
def rag_index(mode: str = "incremental") -> str:
    """mode: incremental|full."""
    return plugin._handle_rag_index({"mode": mode})


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        print(json.dumps(json.loads(rag_search("PrismML llama.cpp repin", k=3)), indent=1)[:1500])
    else:
        mcp.run()
