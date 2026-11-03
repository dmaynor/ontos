import subprocess
import sys

from ontos.store import Store


def _cli(store, *argv):
    return subprocess.run(
        [sys.executable, "-m", "ontos", "--store", str(store), *argv],
        capture_output=True, text=True,
    )


def test_certify_records_who_and_when(workspace):
    with Store(workspace["store"]) as store:
        term = store.certify("finding", "Ada")
        assert term.state == "certified"
        assert term.certified_by == "Ada"
        assert term.certified_at  # an ISO timestamp was recorded


def test_reject_records_the_decision(workspace):
    with Store(workspace["store"]) as store:
        term = store.reject("finding.title", "Ada")
        assert term.state == "rejected"
        assert term.decided_by == "Ada"
        assert term.decided_at


def test_edit_draft_definition(workspace):
    with Store(workspace["store"]) as store:
        term = store.edit_definition("finding", "A verified problem observed during a run.", "Ada")
        assert term.state == "draft"
        assert term.origin == "human"
        assert "verified problem" in term.definition


def test_editing_a_certified_term_returns_it_to_draft(workspace):
    with Store(workspace["store"]) as store:
        store.certify("finding", "Ada")
        term = store.edit_definition("finding", "Changed after certification.", "Ada")
        assert term.state == "draft"
        assert term.certified_by is None
        assert term.certified_at is None


def test_cli_scripted_certify_and_list(workspace):
    store = workspace["store"]
    listed = _cli(store, "certify", "--list")
    assert listed.returncode == 0
    assert "finding" in listed.stdout

    accepted = _cli(store, "certify", "--as", "CLI Certifier", "--accept", "finding", "run")
    assert accepted.returncode == 0
    assert "certified: finding (by CLI Certifier" in accepted.stdout

    with Store(store) as s:
        assert s.get_term("finding").state == "certified"
        assert s.get_term("run").certified_by == "CLI Certifier"
        assert s.get_term("event").state == "draft"


def test_cli_certify_without_terminal_requires_scripted_flags(workspace):
    # subprocess stdin is not a TTY, so bare `certify` must refuse politely.
    proc = _cli(workspace["store"], "certify")
    assert proc.returncode == 1
    assert "needs a terminal" in proc.stderr


def test_cli_certify_unknown_term_errors(workspace):
    proc = _cli(workspace["store"], "certify", "--accept", "nope")
    assert proc.returncode == 1
    assert "no such term" in proc.stderr
