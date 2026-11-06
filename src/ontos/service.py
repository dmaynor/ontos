"""The service layer shared by the CLI and the MCP server.

Both surfaces open the store per call and go through exactly the same
code paths, so an agent asking over MCP gets the same gate, the same
deterministic queries, and the same provenance as a human at the CLI.
"""

from __future__ import annotations

from pathlib import Path

from ontos.apex_ask import answer_apex_question
from ontos.ask import answer_question
from ontos.store import Store


def ask(store_path: str | Path, question: str) -> dict:
    with Store(store_path) as store:
        result = answer_question(store, question)
        if result["status"] == "unsupported":
            # Not a slice-1 shape: try the APEX dataset's shapes. APEX
            # returns None when the question carries no APEX intent.
            apex_result = answer_apex_question(store, question)
            if apex_result is not None:
                return apex_result
        return result


def get_term(store_path: str | Path, name: str) -> dict:
    with Store(store_path) as store:
        term = store.get_term(name)
        if term is None:
            return {"name": name, "state": "absent", "note": "no such term in the ontology store"}
        return term.to_dict()


def list_terms(store_path: str | Path, state: str | None = None) -> list[dict]:
    with Store(store_path) as store:
        return [t.to_dict() for t in store.list_terms(state=state)]
