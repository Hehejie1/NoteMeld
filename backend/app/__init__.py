import logging
import os
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware


logger = logging.getLogger(__name__)


def _default_cors_origins() -> list[str]:
    frontend_port = os.getenv("VITE_FRONTEND_PORT") or os.getenv("FRONTEND_PORT") or "3015"
    configured = os.getenv("NOTEMELD_CORS_ORIGINS", "").strip()
    default_origins = [
        f"http://127.0.0.1:{frontend_port}",
        f"http://localhost:{frontend_port}",
        "http://tauri.localhost",
        "tauri://localhost",
    ]
    if not configured:
        return default_origins
    configured_origins = [origin.strip() for origin in configured.split(",") if origin.strip()]
    return list(dict.fromkeys([*default_origins, *configured_origins]))


def create_app(lifespan) -> FastAPI:
    from .routers import agent, candidates, chat, config, conversation, imported_notes, ingestion, learning, mcp, migration, model, note, note_style, plugins, provider, usage, whiteboard, wiki

    app = FastAPI(title="NoteMeld",lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_default_cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def api_timing_middleware(request: Request, call_next):
        started_at = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration_ms = (time.perf_counter() - started_at) * 1000
            logger.info(
                "API timing method=%s path=%s status=%s duration_ms=%.2f",
                request.method,
                request.url.path,
                status_code,
                duration_ms,
            )

    app.include_router(note.router, prefix="/api")
    app.include_router(provider.router, prefix="/api")
    app.include_router(model.router,prefix="/api")
    app.include_router(config.router,  prefix="/api")
    app.include_router(chat.router, prefix="/api")
    app.include_router(usage.router, prefix="/api")
    app.include_router(wiki.router, prefix="/api")
    app.include_router(ingestion.router, prefix="/api")
    app.include_router(note_style.router, prefix="/api")
    app.include_router(conversation.router, prefix="/api")
    app.include_router(learning.router, prefix="/api")
    app.include_router(whiteboard.router, prefix="/api")
    app.include_router(imported_notes.router, prefix="/api")
    app.include_router(migration.router, prefix="/api")
    app.include_router(mcp.router)
    app.include_router(agent.router, prefix="/api")
    app.include_router(plugins.router, prefix="/api")
    app.include_router(candidates.router, prefix="/api")

    return app
