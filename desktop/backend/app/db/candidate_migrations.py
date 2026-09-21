from app.db.engine import Base
from app.db.models.candidate import CandidateMigration


CANDIDATE_MIGRATIONS = ("candidate-boundary-v1",)


def ensure_candidate_migration_registry(engine):
    Base.metadata.create_all(bind=engine, tables=[CandidateMigration.__table__])
    return CANDIDATE_MIGRATIONS
