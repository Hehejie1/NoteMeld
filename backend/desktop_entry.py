import uvicorn

from app.core.runtime_mode import resolve_runtime_settings
from main import app


def main() -> None:
    runtime_settings = resolve_runtime_settings()
    uvicorn.run(
        app,
        host=runtime_settings["backend_host"],
        port=int(runtime_settings["backend_port"]),
        reload=False,
    )


if __name__ == "__main__":
    main()
