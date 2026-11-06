"""Ask over the APEX dataset: same gate, same determinism, real data.

Three question shapes are served, each bound to certified terms exactly
like the slice-1 shapes in ask.py - the SQL is built from the certified
terms' own source mappings, and a question whose terms are not all
certified is refused with the missing terms named. The serving path
never calls a model.

- holds at every seed - "which models hold at every seed tested?"
- escapes on a probe - "show every escape on the encoded probe"
- model history - "show the full run history of qwen2.5:72b"

``answer_apex_question`` returns None when the question carries no APEX
intent, so the service layer can fall through to the slice-1 shapes.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass

from ontos.ingest import source_kind, sqlite_path
from ontos.store import Store

APEX_SUPPORTED_SHAPES = [
    'holds at every seed - "which models hold at every seed tested?"',
    'escapes on a probe - "show every escape on the front-door / encoded / role-override / boundary-proposal probe"',
    'model history - "show the full run history of qwen2.5:72b" (any recorded model name)',
]

# Probe names as recorded, plus the spaced spellings a human will type.
PROBE_ALIASES = [
    ("front-door", ("front-door", "front door")),
    ("encoded", ("encoded",)),
    ("role-override", ("role-override", "role override")),
    ("boundary-proposal", ("boundary-proposal", "boundary proposal", "boundary")),
]


@dataclass
class ApexIntent:
    shape: str
    probe: str | None = None
    model: str | None = None


def _match_probe(question: str) -> str | None:
    q = question.lower().replace("_", "-")
    for name, aliases in PROBE_ALIASES:
        if any(alias in q for alias in aliases):
            return name
    return None


def _match_model(question: str, models: list[str]) -> str | None:
    q = question.lower()
    for name in sorted(models, key=len, reverse=True):
        if name.lower() in q:
            return name
    return None


def parse_apex_question(question: str, models: list[str]) -> ApexIntent | None:
    q = question.lower()
    tokens = set(re.findall(r"[a-z0-9]+", q))

    # Holds at every seed.
    if ("hold" in q or "held" in q) and "seed" in tokens:
        return ApexIntent(shape="holds_all_seeds")

    # Escapes on a named probe.
    if "escape" in q:
        probe = _match_probe(question)
        if probe:
            return ApexIntent(shape="probe_escapes", probe=probe)
        return None

    # One model's run history.
    if "history" in q or ("runs" in tokens and ("of" in tokens or "for" in tokens)):
        return ApexIntent(shape="model_history", model=_match_model(question, models))

    return None


def required_apex_terms(intent: ApexIntent) -> list[str]:
    if intent.shape == "holds_all_seeds":
        return [
            "model", "claim_run", "claim_run.in_model", "claim_run.in_probe_family",
            "claim_run.seed", "claim_run.verdict", "verdict.held",
        ]
    if intent.shape == "probe_escapes":
        return [
            "model", "probe", "claim_run", "claim_run.in_model",
            "claim_run.in_probe_family", "cell", "cell.outcome",
            "cell.in_probe", "cell.in_claim_run",
        ]
    if intent.shape == "model_history":
        return [
            "model", "claim_run", "claim_run.in_model", "claim_run.in_probe_family",
            "claim_run.seed", "claim_run.verdict", "claim_run.started_at",
            "claim_run.campaign_id", "claim_run.host", "claim_run.served_digest",
            "cell", "cell.in_claim_run",
        ]
    return []


def _table(store: Store, term_name: str) -> str:
    term = store.get_term(term_name)
    assert term is not None and term.source_table
    return term.source_table


def _column(store: Store, term_name: str) -> str:
    term = store.get_term(term_name)
    assert term is not None and term.source_column
    return term.source_column


def _run_query(store: Store, intent: ApexIntent, conn: sqlite3.Connection) -> list[dict]:
    m_table = _table(store, "model")
    cr_table = _table(store, "claim_run")
    model_fk = _column(store, "claim_run.in_model")
    family_fk = _column(store, "claim_run.in_probe_family")
    verdict_col = _column(store, "claim_run.verdict")
    seed_col = _column(store, "claim_run.seed")

    if intent.shape == "holds_all_seeds":
        fam_table = _table(store, "probe_family")
        sql = (
            f"SELECT m.name AS model, m.display_name AS display_name, "
            f"f.name AS family, COUNT(*) AS runs, MIN(cr.{seed_col}) AS first_seed, "
            f"MAX(cr.{seed_col}) AS last_seed "
            f"FROM {m_table} m "
            f"JOIN {cr_table} cr ON cr.{model_fk} = m.id "
            f"JOIN {fam_table} f ON f.id = cr.{family_fk} "
            f"GROUP BY m.id, f.id "
            f"HAVING COUNT(*) = SUM(CASE WHEN cr.{verdict_col} = 'held' THEN 1 ELSE 0 END) "
            f"ORDER BY m.name, f.name"
        )
        return [dict(r) for r in conn.execute(sql)]

    if intent.shape == "probe_escapes":
        c_table = _table(store, "cell")
        p_table = _table(store, "probe")
        fam_table = _table(store, "probe_family")
        outcome_col = _column(store, "cell.outcome")
        probe_fk = _column(store, "cell.in_probe")
        run_fk = _column(store, "cell.in_claim_run")
        started_col = _column(store, "claim_run.started_at")
        campaign_col = _column(store, "claim_run.campaign_id")
        sql = (
            f"SELECT m.name AS model, m.display_name AS display_name, "
            f"f.name AS family, cr.{seed_col} AS seed, "
            f"cr.{started_col} AS started_at, cr.{campaign_col} AS campaign_id "
            f"FROM {c_table} c "
            f"JOIN {p_table} p ON p.id = c.{probe_fk} "
            f"JOIN {cr_table} cr ON cr.id = c.{run_fk} "
            f"JOIN {m_table} m ON m.id = cr.{model_fk} "
            f"JOIN {fam_table} f ON f.id = cr.{family_fk} "
            f"WHERE p.name = ? AND c.{outcome_col} = 'escaped' "
            f"ORDER BY cr.{started_col}, m.name, cr.{seed_col}"
        )
        return [dict(r) for r in conn.execute(sql, [intent.probe])]

    if intent.shape == "model_history":
        c_table = _table(store, "cell")
        p_table = _table(store, "probe")
        fam_table = _table(store, "probe_family")
        run_fk = _column(store, "cell.in_claim_run")
        probe_fk = _column(store, "cell.in_probe")
        outcome_col = _column(store, "cell.outcome")
        started_col = _column(store, "claim_run.started_at")
        campaign_col = _column(store, "claim_run.campaign_id")
        host_col = _column(store, "claim_run.host")
        digest_col = _column(store, "claim_run.served_digest")
        sql = (
            f"SELECT cr.id AS run_id, f.name AS family, cr.{seed_col} AS seed, "
            f"cr.{verdict_col} AS verdict, cr.{started_col} AS started_at, "
            f"cr.{campaign_col} AS campaign_id, cr.{host_col} AS host, "
            f"cr.{digest_col} AS served_digest "
            f"FROM {cr_table} cr "
            f"JOIN {fam_table} f ON f.id = cr.{family_fk} "
            f"JOIN {m_table} m ON m.id = cr.{model_fk} "
            f"WHERE m.name = ? ORDER BY f.name, cr.{seed_col}"
        )
        rows = [dict(r) for r in conn.execute(sql, [intent.model])]
        cell_sql = (
            f"SELECT p.name AS probe, c.{outcome_col} AS outcome "
            f"FROM {c_table} c JOIN {p_table} p ON p.id = c.{probe_fk} "
            f"WHERE c.{run_fk} = ? ORDER BY p.id"
        )
        for row in rows:
            cells = [dict(r) for r in conn.execute(cell_sql, [row.pop("run_id")])]
            row["cells"] = "/".join(c["outcome"] for c in cells)
            row["cell_detail"] = cells
        return rows

    raise ValueError(f"unknown shape: {intent.shape}")


def _format_answer(intent: ApexIntent, rows: list[dict]) -> str:
    if intent.shape == "holds_all_seeds":
        if not rows:
            return "No model held at every seed tested."
        lines = ["Models that held at every seed tested:"]
        for row in rows:
            lines.append(
                f"- {row['model']} ({row['display_name']}): {row['runs']} held "
                f"run(s) under {row['family']}, seeds {row['first_seed']}-"
                f"{row['last_seed']}."
            )
        return "\n".join(lines)
    if intent.shape == "probe_escapes":
        if not rows:
            return f"No escapes recorded on the {intent.probe} probe."
        lines = [f"Escapes on the {intent.probe} probe ({len(rows)}):"]
        for row in rows:
            campaign = row["campaign_id"] or "campaign not recorded"
            lines.append(
                f"- {row['model']} ({row['display_name']}), {row['family']}, "
                f"seed {row['seed']}, {row['started_at']}, {campaign}."
            )
        return "\n".join(lines)
    if intent.shape == "model_history":
        if not rows:
            return f"No runs recorded for {intent.model}."
        lines = [f"Run history for {intent.model} ({len(rows)} runs):"]
        for row in rows:
            digest = f", digest {row['served_digest']}" if row["served_digest"] else ""
            campaign = row["campaign_id"] or "campaign not recorded"
            lines.append(
                f"- {row['family']} seed {row['seed']}: {row['verdict']} - "
                f"cells {row['cells']} - {row['started_at']}, {campaign}, "
                f"host {row['host']}{digest}."
            )
        return "\n".join(lines)
    return ""


def _source_models(store: Store) -> list[str]:
    source = store.get_meta("source")
    if not source or source_kind(source) != "sqlite":
        return []
    try:
        conn = sqlite3.connect(f"file:{sqlite_path(source)}?mode=ro", uri=True)
        try:
            return [r[0] for r in conn.execute("SELECT name FROM models ORDER BY name")]
        finally:
            conn.close()
    except sqlite3.Error:
        return []


def answer_apex_question(store: Store, question: str) -> dict | None:
    """Answer an APEX-shaped question, certified terms only.

    Returns None when the question carries no APEX intent, so the caller
    can fall through to the other datasets' shapes.
    """
    intent = parse_apex_question(question, _source_models(store))
    if intent is None:
        return None

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
    if intent.shape == "model_history" and intent.model is None:
        result["note"] = (
            "Name one model exactly as recorded in the APEX record "
            "(for example qwen2.5:72b, llama3.3:70b, text2sql) and ask again."
        )
        result["answer"] = result["note"]
        return result

    needed = required_apex_terms(intent)
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
            "APEX serving executes against the SQLite dataset; this ontology "
            "was generated from a non-SQLite source."
        )
        result["answer"] = result["note"]
        return result

    conn = sqlite3.connect(f"file:{sqlite_path(source)}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = _run_query(store, intent, conn)
    finally:
        conn.close()

    result.update(
        status="answered",
        answer=_format_answer(intent, rows),
        rows=rows,
        terms_used=[t.provenance() for t in used_terms],
    )
    return result
