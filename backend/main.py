import os
import secrets
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from starlette.middleware.gzip import GZipMiddleware
from starlette.staticfiles import StaticFiles
from dotenv import load_dotenv

from app.db.init_db import init_db
from app.core.runtime_mode import resolve_runtime_settings
from app.core.agent_runtime_descriptor import AgentRuntimeDescriptor, remove_descriptor, write_descriptor
from app.agent_host.host import close_agent_sdk_host, get_agent_sdk_host
from app.utils.storage_paths import data_root
from app.exceptions.exception_handlers import register_exception_handlers
from app.utils.logger import get_logger
from app.utils.storage_paths import screenshot_dir, static_dir as runtime_static_dir, upload_dir
from app import create_app
from app.services.template_extraction_tasks import run_startup_template_task_cleanup
from app.services.transcriber_config_manager import TranscriberConfigManager
from events import register_handler
from ffmpeg_helper import ensure_ffmpeg_or_raise

logger = get_logger(__name__)
load_dotenv()

# 读取 .env 中的路径
static_path = os.getenv('STATIC', '/static')
out_dir = os.getenv('OUT_DIR', './static/screenshots')

# 自动创建本地目录（static 和 static/screenshots）
static_dir = str(runtime_static_dir())
uploads_dir = str(upload_dir())
out_dir = str(screenshot_dir())
if not os.path.exists(static_dir):
    os.makedirs(static_dir)
if not os.path.exists(uploads_dir):
    os.makedirs(uploads_dir)

if not os.path.exists(out_dir):
    os.makedirs(out_dir)

@asynccontextmanager
async def lifespan(app: FastAPI):
    register_handler()
    init_db()
    deleted = run_startup_template_task_cleanup()
    logger.info("模板提取任务启动清理完成，deleted=%s", deleted)
    # 转写器不再在启动时强制初始化，而是在首次生成笔记时按需创建
    # 如果配置了不可用的类型（如 mlx-whisper 未安装），会在使用时报错而非静默回退
    _cfg = TranscriberConfigManager().get_config()
    logger.info(f"当前转写器配置: type={_cfg['transcriber_type']}, model_size={_cfg['whisper_model_size']}")
    runtime_settings = resolve_runtime_settings()
    host = get_agent_sdk_host()
    descriptor_root = data_root()
    descriptor = None
    try:
        # One process-scoped native runtime is created before any UI/CLI turn
        # can arrive.  A missing/incompatible SDK is a startup error, never a
        # reason to re-enable the removed Python Agent runtime.
        host.start()
        descriptor = write_descriptor(
            descriptor_root,
            AgentRuntimeDescriptor(
                pid=os.getpid(),
                base_url=runtime_settings["api_base_url"],
                token=secrets.token_urlsafe(32),
                sdk_version=str(getattr(host._loaded, "sdk_version", "0.1.0")),
                abi_version=2,
                data_root=str(descriptor_root),
            ),
        )
        logger.info("Agent SDK Host started: descriptor=%s", descriptor)
        yield
    finally:
        close_agent_sdk_host()
        if descriptor is not None:
            remove_descriptor(descriptor_root)

app = create_app(lifespan=lifespan)

app.add_middleware(GZipMiddleware, minimum_size=1000)
register_exception_handlers(app)
app.mount(static_path, StaticFiles(directory=static_dir), name="static")

if __name__ == "__main__":
    runtime_settings = resolve_runtime_settings()
    port = int(runtime_settings["backend_port"])
    host = runtime_settings["backend_host"]
    logger.info(f"Runtime mode: {runtime_settings['runtime_mode']}")
    logger.info(f"Starting server on {host}:{port}")
    uvicorn.run(app, host=host, port=port, reload=False)
