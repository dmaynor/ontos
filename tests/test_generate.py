from ontos.generate import run_generate
from ontos.store import Store, Term


def test_generate_creates_entities_attributes_relationships(workspace):
    with Store(workspace["store"]) as store:
        entities = {t.name for t in store.list_terms(kind="entity")}
        assert entities == {"organization", "exercise", "run", "event", "finding"}

        attrs = {t.name for t in store.list_terms(kind="attribute")}
        assert {"finding.title", "finding.severity", "event.occurred_at", "run.started_at"} <= attrs

        rels = {t.name: t for t in store.list_terms(kind="relationship")}
        assert rels["finding.in_run"].related_term == "run"
        assert rels["finding.in_run"].source_table == "findings"
        assert rels["finding.in_run"].source_column == "run_id"
        assert rels["run.in_exercise"].related_term == "exercise"
        assert rels["exercise.in_organization"].related_term == "organization"
        assert rels["event.in_run"].related_term == "run"


def test_everything_generated_is_a_template_draft(workspace):
    with Store(workspace["store"]) as store:
        terms = store.list_terms()
        assert terms, "generate wrote no terms"
        assert all(t.state == "draft" for t in terms)
        # No LLM is configured in tests, so the deterministic fallback labels them.
        assert all(t.origin == "template" for t in terms)
        finding = store.get_term("finding")
        assert "findings" in finding.definition


def test_regenerate_never_clobbers_a_certification(workspace):
    with Store(workspace["store"]) as store:
        store.certify("finding", "Test Certifier")
        certified = store.get_term("finding")
        # A later generate proposing different text must not touch it.
        store.upsert_term(Term(name="finding", kind="entity",
                               definition="A totally different proposal.",
                               origin="llm", source_table="findings"))
        after = store.get_term("finding")
        assert after.state == "certified"
        assert after.definition == certified.definition
        assert after.certified_by == "Test Certifier"


def test_generate_records_source_in_meta(workspace):
    with Store(workspace["store"]) as store:
        assert store.get_meta("source") == str(workspace["source"])
        assert store.get_meta("source_kind") == "sqlite"
        assert store.get_meta("generated_at")


def test_run_generate_summary(workspace, tmp_path):
    store_path = tmp_path / "second.db"
    with Store(store_path) as store:
        summary = run_generate(store, str(workspace["source"]))
    assert summary["terms_written"] > 0
    assert summary["enriched_by_llm"] == 0
    assert summary["draft_terms"] == summary["terms_written"]
    assert set(summary["tables"]) == {"organizations", "exercises", "runs", "events", "findings"}
