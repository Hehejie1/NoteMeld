import os
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def data_root() -> Path:
    return Path(os.getenv("NOTEMELD_DATA_DIR", project_root() / "vector_db")).resolve()


def log_dir() -> Path:
    return Path(os.getenv("NOTEMELD_LOG_DIR", project_root() / "logs")).resolve()


def note_output_dir() -> Path:
    return Path(os.getenv("NOTE_OUTPUT_DIR", data_root() / "note_results")).resolve()


def migration_root_dir() -> Path:
    return Path(os.getenv("NOTEMELD_MIGRATION_DIR", data_root() / "migrations")).resolve()


def migration_jobs_dir() -> Path:
    return Path(os.getenv("NOTEMELD_MIGRATION_JOBS_DIR", migration_root_dir() / "jobs")).resolve()


def migration_packages_dir() -> Path:
    return Path(os.getenv("NOTEMELD_MIGRATION_PACKAGES_DIR", migration_root_dir() / "packages")).resolve()


def migration_upload_dir() -> Path:
    return Path(os.getenv("NOTEMELD_MIGRATION_UPLOAD_DIR", migration_root_dir() / "uploads")).resolve()


def vector_store_dir() -> Path:
    return Path(os.getenv("VECTOR_DB_DIR", data_root() / "chroma")).resolve()


def downloader_config_path() -> Path:
    configured = os.getenv("NOTEMELD_DOWNLOADER_CONFIG") or os.getenv("DOWNLOADER_CONFIG")
    return Path(configured).resolve() if configured else data_root() / "config" / "downloader.json"


def transcriber_config_path() -> Path:
    configured = os.getenv("NOTEMELD_TRANSCRIBER_CONFIG")
    return Path(configured).resolve() if configured else data_root() / "config" / "transcriber.json"


def research_search_config_path() -> Path:
    configured = os.getenv("NOTEMELD_RESEARCH_SEARCH_CONFIG")
    return Path(configured).resolve() if configured else data_root() / "config" / "research_search.json"


def database_path() -> Path:
    configured = os.getenv("NOTEMELD_DATABASE_PATH")
    return Path(configured).resolve() if configured else data_root() / "notemeld.db"


def model_root_dir() -> Path:
    return Path(os.getenv("NOTEMELD_MODEL_DIR", data_root() / "models")).resolve()


def app_data_dir() -> Path:
    return Path(os.getenv("NOTEMELD_APP_DATA_DIR", data_root() / "data")).resolve()


def frame_output_dir() -> Path:
    return Path(os.getenv("NOTEMELD_FRAME_DIR", app_data_dir() / "output_frames")).resolve()


def upload_dir() -> Path:
    return Path(os.getenv("UPLOAD_DIR", data_root() / "uploads")).resolve()


def static_dir() -> Path:
    return Path(os.getenv("STATIC_DIR", data_root() / "static")).resolve()


def screenshot_dir() -> Path:
    return Path(os.getenv("OUT_DIR", static_dir() / "screenshots")).resolve()
