"""Ask: answer questions from CERTIFIED terms only, deterministically.

The serving path never calls a model. A question is matched to one of a
small set of parameterized query templates; each template declares the
terms it needs, and it runs only if every one of those terms is certified.
The SQL is built from the certified terms' own source mappings (table and
column names come from the terms, not from constants), so the term binding
is the product - free-form natural-language-to-SQL is a later slice.

If a needed term is a draft, rejected, or absent, the answer is a refusal
that names the term and its state. There is no flag to bypass this.

Slice-1 assumptions, stated plainly: join targets are surrogate ``id``
primary keys, and serving executes against SQLite sources (Postgres
metadata ingest exists; Postgres serving is a later slice).
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass

from ontos.generate import plural
from ontos.ingest import source_kind, sqlite_path
from ontos.store import Store

NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}

SUPPORTED_SHAPES = [
    'counts - "how many findings / runs / exercises / organizations / events"',
    'recurrence - "which findings recurred across runs" (optionally "across the last N runs")',
    'per-organization rollup - "how many findings per organization" (also runs, exercises)',
    'severity breakdown - "findings by severity"',
    'run timeline - "show the timeline of run 3" / "events in run 3"',
]


@dataclass
class Intent:
    shape: str
    entity: str | None = None
    last_n: int | None = None
    run_id: int | None = None


def _tokens(question: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", question.lower())


def _mentioned_entity(tokens: list[str], entities: list[str]) -> str | None:
    for entity in entities:
        if entity in tokens or plural(entity) in tokens:
            return entity
    return None


def parse_question(question: str, entities: list[str]) -> Intent | None:
    q = question.lower()
    tokens = _tokens(question)

    # Timeline first: it mentions both events and a specific run.
    run_match = re.search(r"run\s+#?(\d+)", q)
    if ("timeline" in q or "event" in tokens or "events" in tokens) and run_match:
        return Intent(shape="timeline", run_id=int(run_match.group(1)))

    # Recurrence.
    if "recurr" in q or "repeat" in q:
        last_n = None
        m = re.search(r"last\s+(\w+)\s+runs?", q)
        if m:
            word = m.group(1)
            last_n = int(word) if word.isdigit() else NUMBER_WORDS.get(word)
        return Intent(shape="recurrence", last_n=last_n)

    # Per-organization rollup.
    if "per organization" in q or "by organization" in q or "each organization" in q:
        entity = _mentioned_entity(tokens, entities) or "finding"
        return Intent(shape="per_org", entity=entity)

    # Severity breakdown.
    if "severity" in q:
        return Intent(shape="severity")

    # Count.
    if "how many" in q or "count" in q:
        entity = _mentioned_entity(tokens, entities)
        if entity:
            return Intent(shape="count", entity=entity)
        return None

    return None


def required_terms(intent: Intent) -> list[str]:
    if intent.shape == "count":
        return [intent.entity]  # type: ignore[list-item]
    if intent.shape == "recurrence":
        return ["finding", "finding.title", "finding.in_run", "run"]
    if intent.shape == "severity":
        return ["finding", "finding.severity"]
    if intent.shape == "timeline":
        return ["event", "event.occurred_at", "event.in_run", "run"]
    if intent.shape == "per_org":
        # Walk the relationship chain from the counted entity up to the
        # organization entity, e.g. finding -> run -> exercise -> organization.
        chain = {
            "finding": [
                "finding", "finding.in_run", "run", "run.in_exercise",
                "exercise", "exercise.in_organization", "organization",
            ],
            "run": [
                "run", "run.in_exercise", "exercise",
                "exercise.in_organization", "organization",
            ],
            "exercise": ["exercise", "exercise.in_organization", "organization"],
            "organization": ["organization"],
        }
        return chain.get(intent.entity or "finding", [])
    return []


def _table(store: Store, term_name: str) -> str:
    term = store.get_term(term_name)
    assert term is not None and term.source_table
    return term.source_table


def _column(store: Store, term_name: str) -> str:
    term = store.get_term(term_name)
    assert term is not None and term.source_column
    return term.source_column


def _build_sql(store: Store, intent: Intent) -> tuple[str, list]:
    """Build SQL from the certified terms' source mappings."""
    if intent.shape == "count":
        table = _table(store, intent.entity)  # type: ignore[arg-type]
        return f"SELECT COUNT(*) AS n FROM {table}", []

    if intent.shape == "recurrence":
        f_table = _table(store, "finding")
        r_table = _table(store, "run")
        title_col = _column(store, "finding.title")
        fk = _column(store, "finding.in_run")
        sql = (
            f"SELECT f.{title_col} AS title, COUNT(DISTINCT f.{fk}) AS run_count, "
            f"COUNT(*) AS occurrences FROM {f_table} f "
            f"JOIN {r_table} r ON r.id = f.{fk} "
        )
        params: list = []
        if intent.last_n:
            sql += f"WHERE f.{fk} IN (SELECT id FROM {r_table} ORDER BY id DESC LIMIT ?) "
            params.append(intent.last_n)
        sql += (
            f"GROUP BY f.{title_col} HAVING COUNT(DISTINCT f.{fk}) > 1 "
            "ORDER BY run_count DESC, occurrences DESC, title"
        )
        return sql, params

    if intent.shape == "severity":
        f_table = _table(store, "finding")
        sev_col = _column(store, "finding.severity")
        return (
            f"SELECT {sev_col} AS severity, COUNT(*) AS n FROM {f_table} "
            f"GROUP BY {sev_col} ORDER BY n DESC, severity"
        ), []

    if intent.shape == "timeline":
        e_table = _table(store, "event")
        fk = _column(store, "event.in_run")
        ts_col = _column(store, "event.occurred_at")
        return (
            f"SELECT * FROM {e_table} WHERE {fk} = ? ORDER BY {ts_col}, id",
            [intent.run_id],
        )

    if intent.shape == "per_org":
        entity = intent.entity or "finding"
        org_name_term = store.get_term("organization.name")
        org_name_col = (
            org_name_term.source_column if org_name_term and org_name_term.source_column else "id"
        )
        o_table = _table(store, "organization")
        if entity == "organization":
            return (
                f"SELECT {org_name_col} AS organization, 1 AS organization_count "
                f"FROM {o_table} ORDER BY organization"
            ), []
        # Join chain from the counted entity up to organizations.
        hops = {
            "finding": ["finding.in_run", "run.in_exercise", "exercise.in_organization"],
            "run": ["run.in_exercise", "exercise.in_organization"],
            "exercise": ["exercise.in_organization"],
        }[entity]
        base_table = _table(store, entity)
        sql = f"SELECT o.{org_name_col} AS organization, COUNT(DISTINCT x.id) AS {entity}_count "
        sql += f"FROM {base_table} x "
        current_table = base_table
        alias_seq = ["a", "b", "c"]
        for i, rel_name in enumerate(hops):
            rel = store.get_term(rel_name)
            assert rel is not None and rel.related_term
            target_table = _table(store, rel.related_term)
            alias = alias_seq[i]
            target_alias = "o" if rel.related_term == "organization" else alias
            sql += f"JOIN {target_table} {target_alias} ON {target_alias}.id = "
            sql += f"{'x' if i == 0 else alias_seq[i - 1]}.{rel.source_column} "
            current_table = target_table
        sql += f"GROUP BY o.{org_name_col} ORDER BY {entity}_count DESC, organization"
        return sql, []

    raise ValueError(f"unknown shape: {intent.shape}")


def _format_answer(intent: Intent, rows: list[dict]) -> str:
    if intent.shape == "count":
        n = rows[0]["n"] if rows else 0
        return f"There are {n} {plural(intent.entity or 'record')}."
    if intent.shape == "recurrence":
        scope = f" in the last {intent.last_n} runs" if intent.last_n else ""
        if not rows:
            return f"No findings recurred across more than one run{scope}."
        lines = [f"Findings that recurred across more than one run{scope}:"]
        for row in rows:
            lines.append(
                f"- '{row['title']}' recurred in {row['run_count']} runs "
                f"({row['occurrences']} occurrences)."
            )
        return "\n".join(lines)
    if intent.shape == "severity":
        lines = ["Findings by severity:"]
        for row in rows:
            lines.append(f"- {row['severity']}: {row['n']}")
        return "\n".join(lines)
    if intent.shape == "timeline":
        if not rows:
            return f"No events found for run {intent.run_id}."
        lines = [f"Timeline of run {intent.run_id} ({len(rows)} events):"]
        for row in rows:
            ts = row.get("occurred_at", "")
            kind = row.get("kind", "")
            actor = row.get("actor", "")
            summary = row.get("summary", "")
            lines.append(f"- {ts} [{kind}] {actor}: {summary}")
        return "\n".join(lines)
    if intent.shape == "per_org":
        entity = intent.entity or "finding"
        key = f"{entity}_count"
        lines = [f"{entity.capitalize()}s per organization:"]
        for row in rows:
            lines.append(f"- {row['organization']}: {row[key]}")
        return "\n".join(lines)
    return ""


def answer_question(store: Store, question: str) -> dict:
    """Answer `question` against the store's source, certified terms only."""
    result: dict = {
        "question": question,
        "status": "unsupported",
        "answer": "",
        "rows": [],
        "sql": None,
        "params": [],
        "terms_used": [],
        "missing_terms": [],
        "note": "",
    }
    entities = [t.name for t in store.list_terms(kind="entity")]
    intent = parse_question(question, entities)
    if intent is None:
        result["note"] = (
            "This question does not match a supported shape. Slice 1 serves "
            "deterministic templates bound to certified terms; free-form "
            "question answering is a later slice. Supported shapes: "
            + "; ".join(SUPPORTED_SHAPES)
        )
        return result

    needed = required_terms(intent)
    missing = []
    used_terms = []
    for name in needed:
        term = store.get_term(name)
        if term is None:
            missing.append({"name": name, "state": "absent"})
        elif term.state != "certified":
            missing.append({"name": name, "state": term.state})
        else:
            used_terms.append(term)
    if missing:
        result["status"] = "refused"
        names = ", ".join(f"{m['name']} ({m['state']})" for m in missing)
        result["missing_terms"] = missing
        result["note"] = (
            f"Refused: this question needs certified terms, and these are "
            f"not certified: {names}. Ontos never serves uncertified terms "
            f"- certify them with `ontos certify` and ask again."
        )
        result["answer"] = result["note"]
        return result

    source = store.get_meta("source")
    if not source:
        result["status"] = "refused"
        result["note"] = "Refused: the ontology store has no source recorded - run `ontos generate` first."
        result["answer"] = result["note"]
        return result
    if source_kind(source) != "sqlite":
        result["status"] = "unsupported"
        result["note"] = (
            "Slice 1 serves SQLite sources; this ontology was generated "
            "from a Postgres source, and Postgres serving is a later slice."
        )
        result["answer"] = result["note"]
        return result

    sql, params = _build_sql(store, intent)
    conn = sqlite3.connect(f"file:{sqlite_path(source)}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = [dict(r) for r in conn.execute(sql, params)]
    finally:
        conn.close()

    result.update(
        status="answered",
        answer=_format_answer(intent, rows),
        rows=rows,
        sql=sql,
        params=params,
        terms_used=[t.provenance() for t in used_terms],
    )
    return result
