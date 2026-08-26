from app.db.models.models import Model
from app.db.models.model_usage_records import ModelUsageRecord
from app.db.models.providers import Provider
from app.db.models.provider_templates import ProviderTemplate
from app.db.models.video_tasks import VideoTask
from app.db.models.note_style import NoteStyle
from app.db.models.template_extraction_task import TemplateExtractionTask
from app.db.models.conversation import Conversation, ConversationMessage, NoteDocument
from app.db.models.agent import AgentEvent, AgentPreference, AgentTurn  # noqa: F401
from app.db.models.whiteboard import Whiteboard, WhiteboardCard, WhiteboardNoteLink, WhiteboardRelation
from app.db.models.knowledge import KnowledgeArticle, KnowledgeChunk, KnowledgeIndexState, KnowledgeProfile, KnowledgeRelation, KnowledgeTerm, KnowledgeTermOccurrence  # noqa: F401
from app.db.models.plugin import PluginAuditEvent, PluginInstallation, PluginMigration, PluginVersion  # noqa: F401
from app.db.models.candidate import Candidate, CandidateDecision, CandidateMigration  # noqa: F401
from app.db.engine import get_engine, Base, DATABASE_URL, SessionLocal, migrate_legacy_sqlite_if_needed
from app.db.conversation_schema import ensure_conversation_columns
from app.db.note_style_dao import ensure_note_style_columns
from app.db.model_schema import ensure_model_runtime_schema
from app.db.provider_schema import ensure_provider_schema
from app.db.database import ensure_agent_schema
from app.db.knowledge_schema import ensure_knowledge_schema
from app.db.plugin_migrations import ensure_plugin_migration_registry
from app.db.candidate_migrations import ensure_candidate_migration_registry
from app.services.conversation_store import bootstrap_conversations_from_storage
from app.utils.logger import get_logger
from app.services.official_link_note_host import ensure_official_link_note_installed


logger = get_logger(__name__)


def init_db():
    engine = get_engine()

    Base.metadata.create_all(bind=engine)
    ensure_plugin_migration_registry(engine)
    ensure_candidate_migration_registry(engine)
    ensure_knowledge_schema(engine)
    model_runtime_schema = ensure_model_runtime_schema(engine)
    if model_runtime_schema["upgraded"]:
        logger.info(
            "Model runtime schema upgraded: cleared_models=%s cleared_capabilities=%s",
            model_runtime_schema["cleared_models"],
            model_runtime_schema["cleared_capabilities"],
        )
    ensure_provider_schema(engine)
    ensure_agent_schema(engine)
    ensure_note_style_columns()
    ensure_conversation_columns(engine)
    migrated = migrate_legacy_sqlite_if_needed(DATABASE_URL)
    if migrated:
        logger.info(f"Legacy SQLite migration summary: {migrated}")
    bootstrapped = bootstrap_conversations_from_storage()
    if bootstrapped:
        logger.info(f"Conversation bootstrap summary: {bootstrapped}")
    ensure_official_link_note_installed(session_factory=lambda: SessionLocal(bind=engine))
