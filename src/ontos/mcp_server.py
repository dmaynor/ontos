"""The MCP server: the ask capability, exposed to any agent harness.

A stdio MCP server (official Python SDK) over the same certified store
the CLI uses. Tools:

- ``ask`` - answer a question from certified terms only, with the query
  and term-level certification provenance. Refusals are returned, not
  raised: an agent should see *why* a question cannot be served.
- ``get_term`` - look up one term, labeled with its state (draft terms are
  visible here for review, clearly labeled; lookup is not serving).
- ``list_terms`` - list terms, optionally filtered by state.

The store path comes from ``--store`` / the ONTOS_STORE environment
variable, set when the server is launched (``ontos mcp-serve``).
"""

from __future__ import annotations

import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from ontos import service


def build_server(store_path: str | Path) -> FastMCP:
    store_path = str(store_path)
    server = FastMCP("ontos")

    @server.tool()
    def ask(question: str) -> dict:
        """Answer a question using certified ontology terms only.

        Returns the answer, the deterministic SQL that ran, and the terms
        used with their certification provenance - or a refusal naming the
        terms that are not certified yet.
        """
        return service.ask(store_path, question)

    @server.tool()
    def get_term(name: str) -> dict:
        """Look up one ontology term by name, labeled with its state."""
        return service.get_term(store_path, name)

    @server.tool()
    def list_terms(state: str | None = None) -> list[dict]:
        """List ontology terms, optionally filtered by state
        (draft / certified / rejected)."""
        return service.list_terms(store_path, state)

    return server


def run(store_path: str | Path | None = None) -> None:
    path = store_path or os.environ.get("ONTOS_STORE") or "ontology.db"
    build_server(path).run()  # stdio transport by default


if __name__ == "__main__":
    run()
