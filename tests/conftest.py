import pytest

from ontos.apex import create_apex_db
from ontos.generate import run_generate
from ontos.sample import create_sample_db
from ontos.store import Store

CERTIFY_SUBSET_A = [
    "finding", "finding.title", "finding.severity", "finding.in_run",
    "run", "run.in_exercise",
    "exercise", "exercise.in_organization",
    "organization",
]
CERTIFY_SUBSET_B = ["event", "event.occurred_at", "event.in_run"]

APEX_CERTIFY_SUBSET_A = [
    "model",
    "claim_run", "claim_run.in_model", "claim_run.in_probe_family",
    "claim_run.seed", "claim_run.verdict",
    "verdict.held",
]
APEX_CERTIFY_SUBSET_B = [
    "claim_run.started_at", "claim_run.campaign_id", "claim_run.host",
    "claim_run.served_digest",
    "cell", "cell.in_claim_run", "cell.in_probe", "cell.outcome",
    "probe",
]

LLM_ENV_KEYS = (
    "ONTOS_LLM_BASE_URL", "ONTOS_LLM_API_KEY", "ONTOS_LLM_MODEL",
    "OPENAI_BASE_URL", "OPENAI_API_KEY", "OPENAI_MODEL",
)


@pytest.fixture(autouse=True)
def no_llm_env(monkeypatch):
    """Generate must prove its credential-free fallback in every test."""
    for key in LLM_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


@pytest.fixture()
def workspace(tmp_path):
    """A sample database plus a freshly generated (all-draft) store."""
    source = tmp_path / "sample.db"
    create_sample_db(source)
    store = tmp_path / "ontology.db"
    with Store(store) as s:
        run_generate(s, str(source))
    return {"dir": tmp_path, "source": source, "store": store}


@pytest.fixture()
def apex_workspace(tmp_path):
    """The APEX dataset database plus a freshly generated (all-draft) store."""
    source = tmp_path / "apex.db"
    create_apex_db(source)
    store = tmp_path / "ontology.db"
    with Store(store) as s:
        run_generate(s, str(source))
    return {"dir": tmp_path, "source": source, "store": store}


def certify(store_path, names, by="Test Certifier"):
    with Store(store_path) as s:
        for name in names:
            s.certify(name, by)
