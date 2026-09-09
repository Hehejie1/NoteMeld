import os

RUNTIME_MODE_SOURCE_SCRIPT = "source-script"
RUNTIME_MODE_SOURCE_CLI = "source-cli"
RUNTIME_MODE_DESKTOP = "desktop"

VALID_RUNTIME_MODES = {
    RUNTIME_MODE_SOURCE_SCRIPT,
    RUNTIME_MODE_SOURCE_CLI,
    RUNTIME_MODE_DESKTOP,
}

def get_runtime_mode(default: str = RUNTIME_MODE_SOURCE_SCRIPT) -> str:
    raw_mode = os.getenv("NOTEMELD_RUNTIME_MODE", default).strip()
    if raw_mode in VALID_RUNTIME_MODES:
        return raw_mode
    return default

def resolve_runtime_settings() -> dict[str, str]:
    backend_port = os.getenv("BACKEND_PORT", "8483").strip() or "8483"
    return {
        "runtime_mode": get_runtime_mode(),
        "backend_host": os.getenv("BACKEND_HOST", "127.0.0.1").strip() or "127.0.0.1",
        "backend_port": backend_port,
        "data_dir": os.getenv("NOTEMELD_DATA_DIR", "").strip(),
        "log_dir": os.getenv("NOTEMELD_LOG_DIR", "").strip(),
        "api_base_url": os.getenv("NOTEMELD_API_BASE_URL", f"http://127.0.0.1:{backend_port}/api").strip()
        or f"http://127.0.0.1:{backend_port}/api",
    }
