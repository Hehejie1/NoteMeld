import os
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[4]


def data_root() -> Path:
    return Path(os.getenv("NOTEMELD_DATA_DIR", project_root() / "desktop" / "data")).resolve()


def log_dir() -> Path:
    return Path(os.getenv("NOTEMELD_LOG_DIR", project_root() / "desktop" / "logs")).resolve()


def note_output_dir() -> Path:
    return data_root() / "note_results"


def workspaces_root() -> Path:
    """Shared workspace root without importing the legacy Agent package."""
    return (note_output_dir() / "workspaces").resolve()


def migration_root_dir() -> Path:
    return data_root() / "migrations"


def migration_jobs_dir() -> Path:
    return migration_root_dir() / "jobs"


def migration_packages_dir() -> Path:
    return migration_root_dir() / "packages"


def migration_upload_dir() -> Path:
    return migration_root_dir() / "uploads"


def vector_store_dir() -> Path:
    return data_root() / "chroma"


def downloader_config_path() -> Path:
    return data_root() / "config" / "downloader.json"


def transcriber_config_path() -> Path:
    return data_root() / "config" / "transcriber.json"


def research_search_config_path() -> Path:
    return data_root() / "config" / "research_search.json"


def database_path() -> Path:
    return data_root() / "notemeld.db"


def model_root_dir() -> Path:
    return data_root() / "models"


def app_data_dir() -> Path:
    return data_root() / "data"


def application_workspaces_root() -> Path:
    """Default physical root for isolated application instance workspaces."""
    return app_data_dir() / "applications"


def frame_output_dir() -> Path:
    return app_data_dir() / "output_frames"


def upload_dir() -> Path:
    return data_root() / "uploads"


def static_dir() -> Path:
    return data_root() / "static"


def screenshot_dir() -> Path:
    return static_dir() / "screenshots"


def temp_dir() -> Path:
    """Application-owned temporary files must remain inside the data root."""
    return data_root() / "tmp"


def plugins_root_dir() -> Path:
    return data_root() / "plugins"


def plugin_staging_dir() -> Path:
    return plugins_root_dir() / "staging"


def plugin_versions_dir(plugin_id: str) -> Path:
    return plugins_root_dir() / "versions" / plugin_id


def plugin_active_pointer(plugin_id: str) -> Path:
    return plugins_root_dir() / "active" / f"{plugin_id}.pointer"
