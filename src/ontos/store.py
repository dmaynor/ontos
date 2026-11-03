"""The ontology store: terms, their states, and their certification records.

The store is a single SQLite file. It is the product's memory: a term exists
as a *draft* until a human certifies it, and only certified terms may be
served. Certification is recorded with who certified the term and when -
that record is the provenance every answer carries.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

STATES = ("draft", "certified", "rejected")
KINDS = ("entity", "attribute", "relationship")
ORIGINS = ("template", "llm", "human")


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Term:
    name: str
    kind: str  # entity | attribute | relationship
    definition: str
    origin: str = "template"  # template | llm | human
    state: str = "draft"  # draft | certified | rejected
    source_table: str | None = None
    source_column: str | None = None
    related_term: str | None = None  # for relationships: target entity term
    certified_by: str | None = None
    certified_at: str | None = None
    decided_by: str | None = None  # who rejected (or last decided) the term
    decided_at: str | None = None
    id: int | None = None
    created_at: str = ""
    updated_at: str = ""

    def provenance(self) -> dict:
        """The certification record an answer carries for this term."""
        return {
            "name": self.name,
            "kind": self.kind,
            "certified_by": self.certified_by,
            "certified_at": self.certified_at,
        }

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "definition": self.definition,
            "origin": self.origin,
            "state": self.state,
            "source_table": self.source_table,
            "source_column": self.source_column,
            "related_term": self.related_term,
            "certified_by": self.certified_by,
            "certified_at": self.certified_at,
            "decided_by": self.decided_by,
            "decided_at": self.decided_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


_SCHEMA = """
CREATE TABLE IF NOT EXISTS terms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL,
    definition TEXT NOT NULL,
    origin TEXT NOT NULL DEFAULT 'template',
    state TEXT NOT NULL DEFAULT 'draft',
    source_table TEXT,
    source_column TEXT,
    related_term TEXT,
    certified_by TEXT,
    certified_at TEXT,
    decided_by TEXT,
    decided_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- meta ------------------------------------------------------------
    def set_meta(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self.conn.commit()

    def get_meta(self, key: str, default: str | None = None) -> str | None:
        row = self.conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    # -- terms -----------------------------------------------------------
    def upsert_term(self, term: Term) -> Term:
        """Insert a generated term, or refresh it if it is still a draft.

        Certified and rejected terms are never clobbered by regeneration:
        a human decision outranks a fresh proposal.
        """
        existing = self.get_term(term.name)
        ts = now_iso()
        if existing is None:
            cur = self.conn.execute(
                "INSERT INTO terms(name, kind, definition, origin, state, "
                "source_table, source_column, related_term, created_at, updated_at) "
                "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    term.name,
                    term.kind,
                    term.definition,
                    term.origin,
                    term.state,
                    term.source_table,
                    term.source_column,
                    term.related_term,
                    ts,
                    ts,
                ),
            )
            self.conn.commit()
            term.id = cur.lastrowid
            term.created_at = ts
            term.updated_at = ts
            return term
        if existing.state == "draft":
            self.conn.execute(
                "UPDATE terms SET definition = ?, origin = ?, kind = ?, "
                "source_table = ?, source_column = ?, related_term = ?, updated_at = ? "
                "WHERE name = ?",
                (
                    term.definition,
                    term.origin,
                    term.kind,
                    term.source_table,
                    term.source_column,
                    term.related_term,
                    ts,
                    term.name,
                ),
            )
            self.conn.commit()
            return self.get_term(term.name)  # type: ignore[return-value]
        return existing

    def _row_to_term(self, row: sqlite3.Row) -> Term:
        return Term(
            id=row["id"],
            name=row["name"],
            kind=row["kind"],
            definition=row["definition"],
            origin=row["origin"],
            state=row["state"],
            source_table=row["source_table"],
            source_column=row["source_column"],
            related_term=row["related_term"],
            certified_by=row["certified_by"],
            certified_at=row["certified_at"],
            decided_by=row["decided_by"],
            decided_at=row["decided_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def get_term(self, name: str) -> Term | None:
        row = self.conn.execute("SELECT * FROM terms WHERE name = ?", (name,)).fetchone()
        return self._row_to_term(row) if row else None

    def list_terms(self, state: str | None = None, kind: str | None = None) -> list[Term]:
        sql = "SELECT * FROM terms"
        clauses, params = [], []
        if state:
            clauses.append("state = ?")
            params.append(state)
        if kind:
            clauses.append("kind = ?")
            params.append(kind)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY kind, name"
        return [self._row_to_term(r) for r in self.conn.execute(sql, params)]

    def certify(self, name: str, by: str) -> Term:
        term = self._require(name)
        ts = now_iso()
        self.conn.execute(
            "UPDATE terms SET state = 'certified', certified_by = ?, certified_at = ?, "
            "decided_by = ?, decided_at = ?, updated_at = ? WHERE name = ?",
            (by, ts, by, ts, ts, name),
        )
        self.conn.commit()
        return self.get_term(name)  # type: ignore[return-value]

    def reject(self, name: str, by: str) -> Term:
        term = self._require(name)
        ts = now_iso()
        self.conn.execute(
            "UPDATE terms SET state = 'rejected', decided_by = ?, decided_at = ?, "
            "updated_at = ? WHERE name = ?",
            (by, ts, ts, name),
        )
        self.conn.commit()
        return self.get_term(name)  # type: ignore[return-value]

    def edit_definition(self, name: str, definition: str, by: str) -> Term:
        """Edit a term's definition.

        Editing a *certified* term returns it to draft: the certified text
        is what was approved, so changed text must be certified again.
        """
        term = self._require(name)
        ts = now_iso()
        if term.state == "certified":
            self.conn.execute(
                "UPDATE terms SET definition = ?, origin = 'human', state = 'draft', "
                "certified_by = NULL, certified_at = NULL, updated_at = ? WHERE name = ?",
                (definition, ts, name),
            )
        else:
            self.conn.execute(
                "UPDATE terms SET definition = ?, origin = 'human', updated_at = ? "
                "WHERE name = ?",
                (definition, ts, name),
            )
        self.conn.commit()
        return self.get_term(name)  # type: ignore[return-value]

    def _require(self, name: str) -> Term:
        term = self.get_term(name)
        if term is None:
            raise KeyError(f"no such term: {name}")
        return term
