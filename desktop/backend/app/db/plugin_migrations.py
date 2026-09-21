from app.db.engine import Base
from app.db.models.plugin import PluginMigration


PLUGIN_MIGRATIONS = ("plugin-control-plane-v1",)


def ensure_plugin_migration_registry(engine):
    Base.metadata.create_all(bind=engine, tables=[PluginMigration.__table__])
    return PLUGIN_MIGRATIONS
