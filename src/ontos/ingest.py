"""Ingest: read a source database's metadata (tables, columns, keys).

The demo path is SQLite - a file path or a ``sqlite:///`` URL. A Postgres
source (``postgresql://`` connection string) is supported for metadata
reading through the optional ``psycopg`` driver; if the driver is not
installed, the error says exactly what to install. Serving questions
against a Postgres source is a later slice; slice 1 serves the sample.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path


class IngestError(Exception):
    pass


@dataclass
class ColumnMeta:
    name: str
    type: str = ""
    primary_key: bool = False
    not_null: bool = False
    fk_table: str | None = None
    fk_column: str | None = None


@dataclass
class TableMeta:
    name: str
    columns: list[ColumnMeta] = field(default_factory=list)
    row_count: int | None = None

    def column(self, name: str) -> ColumnMeta | None:
        for col in self.columns:
            if col.name == name:
                return col
        return None


def source_kind(source: str) -> str:
    if source.startswith(("postgresql://", "postgres://")):
        return "postgres"
    return "sqlite"


def sqlite_path(source: str) -> Path:
    if source.startswith("sqlite:///"):
        return Path(source[len("sqlite:///"):])
    if source.startswith("sqlite://"):
        return Path(source[len("sqlite://"):])
    return Path(source)


def read_metadata(source: str) -> list[TableMeta]:
    if source_kind(source) == "postgres":
        return read_postgres_metadata(source)
    return read_sqlite_metadata(sqlite_path(source))


def read_sqlite_metadata(path: Path) -> list[TableMeta]:
    if not path.exists():
        raise IngestError(f"source database not found: {path}")
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        result: list[TableMeta] = []
        for table in tables:
            fks: dict[str, tuple[str, str]] = {}
            for fk in conn.execute(f"PRAGMA foreign_key_list({table})"):
                # (id, seq, table, from, to, on_update, on_delete, match)
                fks[fk[3]] = (fk[2], fk[4] or "id")
            columns = []
            for col in conn.execute(f"PRAGMA table_info({table})"):
                # (cid, name, type, notnull, dflt_value, pk)
                fk = fks.get(col[1])
                columns.append(
                    ColumnMeta(
                        name=col[1],
                        type=col[2] or "",
                        primary_key=bool(col[5]),
                        not_null=bool(col[3]),
                        fk_table=fk[0] if fk else None,
                        fk_column=fk[1] if fk else None,
                    )
                )
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            result.append(TableMeta(name=table, columns=columns, row_count=count))
        return result
    finally:
        conn.close()


def read_postgres_metadata(url: str) -> list[TableMeta]:
    try:
        import psycopg  # type: ignore
    except ImportError:
        try:
            import psycopg2 as psycopg  # type: ignore
        except ImportError as exc:
            raise IngestError(
                "Postgres ingest needs a driver: pip install 'psycopg[binary]' "
                "(the SQLite demo path needs no driver)"
            ) from exc
    conn = psycopg.connect(url)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' "
            "ORDER BY table_name"
        )
        tables = [r[0] for r in cur.fetchall()]
        fk_map: dict[tuple[str, str], tuple[str, str]] = {}
        cur.execute(
            "SELECT tc.table_name, kcu.column_name, ccu.table_name, ccu.column_name "
            "FROM information_schema.table_constraints tc "
            "JOIN information_schema.key_column_usage kcu "
            "  ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema "
            "JOIN information_schema.constraint_column_usage ccu "
            "  ON tc.constraint_name = ccu.constraint_name AND tc.table_schema = ccu.table_schema "
            "WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public'"
        )
        for tname, cname, ftable, fcol in cur.fetchall():
            fk_map[(tname, cname)] = (ftable, fcol)
        pk_map: set[tuple[str, str]] = set()
        cur.execute(
            "SELECT tc.table_name, kcu.column_name "
            "FROM information_schema.table_constraints tc "
            "JOIN information_schema.key_column_usage kcu "
            "  ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema "
            "WHERE tc.constraint_type = 'PRIMARY KEY' AND tc.table_schema = 'public'"
        )
        for tname, cname in cur.fetchall():
            pk_map.add((tname, cname))
        result: list[TableMeta] = []
        for table in tables:
            cur.execute(
                "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = %s ORDER BY ordinal_position",
                (table,),
            )
            columns = []
            for cname, ctype, nullable in cur.fetchall():
                fk = fk_map.get((table, cname))
                columns.append(
                    ColumnMeta(
                        name=cname,
                        type=ctype or "",
                        primary_key=(table, cname) in pk_map,
                        not_null=(nullable == "NO"),
                        fk_table=fk[0] if fk else None,
                        fk_column=fk[1] if fk else None,
                    )
                )
            cur.execute(f'SELECT COUNT(*) FROM "{table}"')
            count = cur.fetchone()[0]
            result.append(TableMeta(name=table, columns=columns, row_count=count))
        return result
    finally:
        conn.close()
