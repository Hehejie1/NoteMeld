from app.applications.models import ApplicationMigration
from app.db.engine import Base

APPLICATION_MIGRATIONS = ("application-host-v1", "application-runtime-v2")


def ensure_application_migration_registry(engine):
    Base.metadata.create_all(bind=engine, tables=[ApplicationMigration.__table__])
    with engine.begin() as connection:
        for migration_id in APPLICATION_MIGRATIONS:
            connection.execute(ApplicationMigration.__table__.insert().prefix_with("OR IGNORE").values(migration_id=migration_id))
    return APPLICATION_MIGRATIONS
