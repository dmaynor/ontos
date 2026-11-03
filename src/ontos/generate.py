"""Generate: draft an ontology from a source database's metadata.

Every table becomes an entity term, every column an attribute term, and
every foreign key a relationship term. Definitions are deterministic
templates derived from the metadata (optionally enriched by an LLM - see
enrich.py). Everything generate writes is a DRAFT. Drafts are labeled
everywhere they appear and are never served.
"""

from __future__ import annotations

from ontos import enrich, ingest
from ontos.store import Store, Term, now_iso


def singular(table: str) -> str:
    """Naive singular for term names: organizations -> organization."""
    if table.endswith("ies") and len(table) > 3:
        return table[:-3] + "y"
    if table.endswith("s") and not table.endswith("ss"):
        return table[:-1]
    return table


def plural(term: str) -> str:
    if term.endswith("y") and len(term) > 1 and term[-2] not in "aeiou":
        return term[:-1] + "ies"
    return term + "s"


def build_terms(tables: list[ingest.TableMeta]) -> list[Term]:
    entity_names = {t.name: singular(t.name) for t in tables}
    terms: list[Term] = []
    for table in tables:
        entity = entity_names[table.name]
        col_names = ", ".join(c.name for c in table.columns)
        terms.append(
            Term(
                name=entity,
                kind="entity",
                definition=(
                    f"A {entity} is one record in the `{table.name}` table "
                    f"({table.row_count} row(s) at generation time; columns: "
                    f"{col_names}). Template draft from schema metadata - "
                    "review and certify before it means anything."
                ),
                origin="template",
                source_table=table.name,
            )
        )
        for col in table.columns:
            terms.append(
                Term(
                    name=f"{entity}.{col.name}",
                    kind="attribute",
                    definition=(
                        f"The `{col.name}` column of the `{table.name}` table "
                        f"(type {col.type or 'unknown'}"
                        + (", primary key" if col.primary_key else "")
                        + "). Template draft from schema metadata."
                    ),
                    origin="template",
                    source_table=table.name,
                    source_column=col.name,
                )
            )
            if col.fk_table and col.fk_table in entity_names:
                target = entity_names[col.fk_table]
                terms.append(
                    Term(
                        name=f"{entity}.in_{target}",
                        kind="relationship",
                        definition=(
                            f"Links each {entity} to the {target} it belongs "
                            f"to, via `{table.name}.{col.name}` referencing "
                            f"`{col.fk_table}.{col.fk_column}`. Template draft "
                            "from schema metadata."
                        ),
                        origin="template",
                        source_table=table.name,
                        source_column=col.name,
                        related_term=target,
                    )
                )
    return terms


def run_generate(store: Store, source: str, env: dict | None = None) -> dict:
    """Generate drafts from `source` into `store`. Returns a summary."""
    tables = ingest.read_metadata(source)
    terms = build_terms(tables)
    config = enrich.llm_config(env)
    enriched = 0
    if config:
        enriched = enrich.enrich_definitions(terms, config, source)
    for term in terms:
        store.upsert_term(term)
    # Record local files by absolute path so serving processes launched
    # from another working directory (notably MCP servers) can find them.
    recorded_source = source
    if ingest.source_kind(source) == "sqlite":
        recorded_source = str(ingest.sqlite_path(source).resolve())
    store.set_meta("source", recorded_source)
    store.set_meta("source_kind", ingest.source_kind(source))
    store.set_meta("generated_at", now_iso())
    drafts = store.list_terms(state="draft")
    return {
        "source": source,
        "tables": [t.name for t in tables],
        "terms_written": len(terms),
        "enriched_by_llm": enriched,
        "draft_terms": len(drafts),
        "certified_terms": len(store.list_terms(state="certified")),
    }
