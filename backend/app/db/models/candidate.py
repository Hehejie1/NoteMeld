from sqlalchemy import Column, DateTime, Integer, String, Text, func

from app.db.engine import Base


class Candidate(Base):
    __tablename__ = "application_candidates"

    id = Column(String, primary_key=True)
    kind = Column(String, nullable=False)
    title = Column(String, nullable=False)
    status = Column(String, nullable=False, default="staged")
    scope_json = Column(Text, nullable=False, default="{}")
    evidence_json = Column(Text, nullable=False, default="[]")
    trace_json = Column(Text, nullable=False, default="[]")
    artifact_json = Column(Text, nullable=False, default="{}")
    patch_json = Column(Text, nullable=False, default="{}")
    tests_json = Column(Text, nullable=False, default="[]")
    risks_json = Column(Text, nullable=False, default="[]")
    permissions_json = Column(Text, nullable=False, default="[]")
    rollback_json = Column(Text, nullable=False, default="{}")
    model_safety_claim = Column(Text, nullable=True)
    validation_json = Column(Text, nullable=False, default="{}")
    decision_actor = Column(String, nullable=True)
    decision_reason = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class CandidateMigration(Base):
    __tablename__ = "candidate_app_migrations"

    migration_id = Column(String, primary_key=True)
    applied_at = Column(DateTime, server_default=func.now())


class CandidateDecision(Base):
    __tablename__ = "candidate_decisions"

    id = Column(String, primary_key=True)
    candidate_id = Column(String, nullable=False, index=True)
    decision = Column(String, nullable=False)
    actor = Column(String, nullable=False)
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class CandidateEvidence(Base):
    __tablename__ = "candidate_evidence"

    id = Column(String, primary_key=True)
    candidate_id = Column(String, nullable=False, index=True)
    kind = Column(String, nullable=False)
    payload_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, server_default=func.now())


class CandidateArtifact(Base):
    __tablename__ = "candidate_artifacts"

    id = Column(String, primary_key=True)
    candidate_id = Column(String, nullable=False, index=True)
    kind = Column(String, nullable=False)
    payload_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, server_default=func.now())


class CandidateEvaluation(Base):
    __tablename__ = "candidate_evaluations"

    id = Column(String, primary_key=True)
    candidate_id = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False)
    payload_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, server_default=func.now())
