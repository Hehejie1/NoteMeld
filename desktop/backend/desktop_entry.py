from multiprocessing import freeze_support

import uvicorn

from app.core.runtime_mode import resolve_runtime_settings
from main import app


def main() -> None:
    # PyInstaller one-file sidecars may be re-entered by multiprocessing
    # workers.  Register the frozen-process dispatcher before importing the
    # application so a worker cannot recursively boot another backend.
    freeze_support()
    runtime_settings = resolve_runtime_settings()
    uvicorn.run(
        app,
        host=runtime_settings["backend_host"],
        port=int(runtime_settings["backend_port"]),
        reload=False,
    )


if __name__ == "__main__":
    main()
