"""Serving tests, including the negative controls for the certification
gate: an uncertified term must never be served, and the refusal must say
exactly which terms are missing and in what state."""

from conftest import CERTIFY_SUBSET_A, CERTIFY_SUBSET_B, certify

from ontos import service
from ontos.store import Store

BRIEF_QUESTION = "which findings recurred across the last three runs?"


# ------------------------------------------------------------ the gate
def test_ask_before_any_certification_is_refused(workspace):
    result = service.ask(workspace["store"], "how many findings are there?")
    assert result["status"] == "refused"
    assert result["rows"] == []
    assert result["sql"] is None
    missing = {m["name"]: m["state"] for m in result["missing_terms"]}
    assert missing == {"finding": "draft"}
    assert "Refused" in result["answer"]


def test_recurrence_question_refused_with_all_missing_terms_listed(workspace):
    result = service.ask(workspace["store"], BRIEF_QUESTION)
    assert result["status"] == "refused"
    missing = {m["name"] for m in result["missing_terms"]}
    assert missing == {"finding", "finding.title", "finding.in_run", "run"}


def test_certifying_one_entity_unlocks_only_its_own_questions(workspace):
    certify(workspace["store"], ["finding"])
    count = service.ask(workspace["store"], "how many findings are there?")
    assert count["status"] == "answered"
    recurrence = service.ask(workspace["store"], BRIEF_QUESTION)
    assert recurrence["status"] == "refused"
    missing = {m["name"] for m in recurrence["missing_terms"]}
    assert missing == {"finding.title", "finding.in_run", "run"}


def test_timeline_refused_until_event_terms_are_certified(workspace):
    certify(workspace["store"], CERTIFY_SUBSET_A)
    refused = service.ask(workspace["store"], "show the timeline of run 3")
    assert refused["status"] == "refused"
    missing = {m["name"] for m in refused["missing_terms"]}
    assert missing == {"event", "event.occurred_at", "event.in_run"}

    certify(workspace["store"], CERTIFY_SUBSET_B)
    answered = service.ask(workspace["store"], "show the timeline of run 3")
    assert answered["status"] == "answered"
    assert len(answered["rows"]) == 5
    stamps = [r["occurred_at"] for r in answered["rows"]]
    assert stamps == sorted(stamps)
    assert answered["rows"][0]["kind"] == "run_started"
    assert answered["rows"][-1]["kind"] == "run_ended"


def test_rejected_term_is_not_served(workspace):
    with Store(workspace["store"]) as store:
        store.reject("finding", "Test Certifier")
    result = service.ask(workspace["store"], "how many findings are there?")
    assert result["status"] == "refused"
    assert result["missing_terms"] == [{"name": "finding", "state": "rejected"}]


# ------------------------------------------------------------- answers
def test_count_with_provenance(workspace):
    certify(workspace["store"], ["finding"])
    result = service.ask(workspace["store"], "how many findings are there?")
    assert result["status"] == "answered"
    assert result["rows"] == [{"n": 17}]
    assert "17 findings" in result["answer"]
    assert result["sql"] == "SELECT COUNT(*) AS n FROM findings"
    assert result["terms_used"] == [
        {
            "name": "finding",
            "kind": "entity",
            "certified_by": "Test Certifier",
            "certified_at": result["terms_used"][0]["certified_at"],
        }
    ]
    assert result["terms_used"][0]["certified_at"]


def test_counts_for_other_entities(workspace):
    certify(workspace["store"], ["run", "organization", "exercise"])
    assert service.ask(workspace["store"], "how many runs?")["rows"] == [{"n": 7}]
    assert service.ask(workspace["store"], "how many organizations?")["rows"] == [{"n": 3}]
    assert service.ask(workspace["store"], "count of exercises")["rows"] == [{"n": 4}]


def test_recurrence_across_all_runs(workspace):
    certify(workspace["store"], CERTIFY_SUBSET_A)
    result = service.ask(workspace["store"], "which findings recurred across runs?")
    assert result["status"] == "answered"
    by_title = {r["title"]: r for r in result["rows"]}
    assert len(by_title) == 5
    assert by_title["Phishing email not reported by staff"]["run_count"] == 3
    assert by_title["Incident commander unreachable at night"]["run_count"] == 2
    assert by_title["Backups not verified before patch window"]["run_count"] == 2
    assert by_title["Vendor contact list out of date"]["run_count"] == 2
    assert by_title["Public status page not updated"]["run_count"] == 2
    assert result["rows"][0]["title"] == "Phishing email not reported by staff"
    used = {t["name"] for t in result["terms_used"]}
    assert used == {"finding", "finding.title", "finding.in_run", "run"}


def test_recurrence_last_three_runs_the_briefs_question(workspace):
    certify(workspace["store"], CERTIFY_SUBSET_A)
    result = service.ask(workspace["store"], BRIEF_QUESTION)
    assert result["status"] == "answered"
    assert len(result["rows"]) == 1
    row = result["rows"][0]
    assert row["title"] == "Public status page not updated"
    assert row["run_count"] == 2
    assert result["params"] == [3]


def test_findings_per_organization(workspace):
    certify(workspace["store"], CERTIFY_SUBSET_A)
    result = service.ask(workspace["store"], "how many findings per organization?")
    assert result["status"] == "answered"
    rollup = {r["organization"]: r["finding_count"] for r in result["rows"]}
    assert rollup == {
        "HarborPoint Health": 11,
        "Northgate Retail Group": 4,
        "City of Bayside": 2,
    }


def test_findings_by_severity(workspace):
    certify(workspace["store"], CERTIFY_SUBSET_A)
    result = service.ask(workspace["store"], "findings by severity")
    assert result["status"] == "answered"
    breakdown = {r["severity"]: r["n"] for r in result["rows"]}
    assert breakdown == {"critical": 3, "high": 5, "medium": 6, "low": 3}
    assert sum(breakdown.values()) == 17


def test_unsupported_question_explains_the_supported_shapes(workspace):
    certify(workspace["store"], CERTIFY_SUBSET_A)
    result = service.ask(workspace["store"], "what is the meaning of life?")
    assert result["status"] == "unsupported"
    assert "recurrence" in result["note"]
    unknown = service.ask(workspace["store"], "how many users are there?")
    assert unknown["status"] == "unsupported"
