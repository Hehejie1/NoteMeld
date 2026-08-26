import pathlib
import sys

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.db.engine import Base  # noqa: E402
from app.db.candidate_migrations import ensure_candidate_migration_registry  # noqa: E402
from app.db.models.candidate import Candidate, CandidateArtifact, CandidateDecision, CandidateEvaluation, CandidateEvidence, CandidateMigration  # noqa: E402,F401
from app.db.models.plugin import PluginInstallation  # noqa: E402
from app.services.candidates.service import CandidateNotApprovable, CandidateService  # noqa: E402


def valid_payload(**overrides):
    payload = {
        "kind": "application", "title": "safe UI candidate",
        "scope": {"kind": "application", "targets": ["frontend/src/pages/SettingPage/Candidates.tsx"]},
        "evidence": [{"source": "review-1", "claim": "diff is bounded"}],
        "trace": [{"turn_id": "turn-1", "event": "candidate.created"}],
        "artifact": {"manifest": "candidate.v1", "sha256": "a" * 64},
        "patch": {"files": ["frontend/src/pages/SettingPage/Candidates.tsx"]},
        "tests": [{"name": "focused deny suite", "status": "passed"}],
        "risks": [{"id": "R1", "severity": "low", "mitigation": "manual review"}],
        "permissions": ["application.read", "application.test"],
        "rollback": {"plan": "remove approved release pointer", "verified": True},
        "model_safety_claim": "the model says this is safe",
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def service(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'candidate.db'}")
    Base.metadata.create_all(engine, tables=[Candidate.__table__, CandidateArtifact.__table__, CandidateDecision.__table__, CandidateEvaluation.__table__, CandidateEvidence.__table__, CandidateMigration.__table__, PluginInstallation.__table__])
    return CandidateService(sessionmaker(bind=engine))


def test_candidate_is_not_approvable_without_evidence_test_rollback(service):
    candidate = service.create(valid_payload(evidence=[], tests=[], rollback={}))
    result = service.validate(candidate["id"])
    assert result["status"] == "rejected"
    assert {"evidence is required", "tests are required", "rollback plan is required"}.issubset(result["validation"]["errors"])
    with pytest.raises(CandidateNotApprovable):
        service.decide(candidate["id"], approved=True, actor="user")


def test_validation_records_validating_transition(service, monkeypatch):
    candidate = service.create(valid_payload())
    seen = []
    original = service._validation_errors

    def observe(candidate_row, db):
        seen.append(candidate_row.status)
        return original(candidate_row, db)

    monkeypatch.setattr(service, "_validation_errors", observe)
    assert service.validate(candidate["id"])["status"] == "approvable"
    assert seen == ["validating"]


def test_sdk_paths_public_contract_and_model_claim_are_denied(service):
    candidate = service.create(valid_payload(scope={"kind": "application", "targets": ["notemeld-agent-sdk/crates/agent-core"]}))
    result = service.validate(candidate["id"])
    assert result["status"] == "rejected"
    assert any("SDK/public contract boundary denied" in error for error in result["validation"]["errors"])
    assert result["validation"]["model_safety_claim_used"] is False


@pytest.mark.parametrize("patch", [{"sdk_path": "packaged"}, {"public_contract": "agent_events.v1"}, {"artifact": "notemeld_agent.h"}])
def test_sdk_artifact_and_public_contract_metadata_are_denied(service, patch):
    candidate = service.create(valid_payload(patch=patch))
    result = service.validate(candidate["id"])
    assert result["status"] == "rejected"
    assert any("SDK/public contract boundary denied" in error for error in result["validation"]["errors"])


def test_unknown_permission_is_denied(service):
    candidate = service.create(valid_payload(permissions=["application.root_write"]))
    result = service.validate(candidate["id"])
    assert "requested permissions exceed candidate authority" in result["validation"]["errors"]


def test_approval_only_records_decision_and_plugin_requires_n03_flow(service):
    with service.session_factory.begin() as db:
        db.add(PluginInstallation(plugin_id="fixture.plugin"))
    candidate = service.create(valid_payload(kind="plugin", scope={"kind": "plugin", "targets": ["plugin:fixture.plugin"]}, permissions=["plugin.package"]))
    assert service.validate(candidate["id"])["status"] == "approvable"
    approved = service.decide(candidate["id"], approved=True, actor="reviewer")
    assert approved["status"] == "approved"
    assert "N03 standard package" in approved["next_step"]
    assert inspect(service.session_factory.kw["bind"]).has_table("candidate_app_migrations")
    with service.session_factory() as db:
        row = db.get(Candidate, candidate["id"])
        assert row.status == "approved"
        assert db.query(CandidateDecision).filter_by(candidate_id=candidate["id"]).count() == 1
        assert db.query(CandidateEvidence).filter_by(candidate_id=candidate["id"]).count() == 2
        assert db.query(CandidateArtifact).filter_by(candidate_id=candidate["id"]).count() == 2
        assert db.query(CandidateEvaluation).filter_by(candidate_id=candidate["id"]).count() == 1


def test_candidate_registry_isolated_and_idempotent(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'registry.db'}")
    Base.metadata.create_all(engine, tables=[CandidateMigration.__table__, Candidate.__table__])
    assert ensure_candidate_migration_registry(engine) == ("candidate-boundary-v1",)
    assert ensure_candidate_migration_registry(engine) == ("candidate-boundary-v1",)
    assert inspect(engine).has_table("candidate_app_migrations")
    assert inspect(engine).has_table("application_candidates")
