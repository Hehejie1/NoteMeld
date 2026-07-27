import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from starlette.middleware.gzip import GZipMiddleware
from starlette.staticfiles import StaticFiles
from dotenv import load_dotenv

from app.db.init_db import init_db
from app.core.runtime_mode import resolve_runtime_settings
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
    yield

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
