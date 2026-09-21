import importlib
import json
import os
import platform
from pathlib import Path
from typing import Optional, Dict, Any

from app.utils.storage_paths import transcriber_config_path


def can_import_mlx_whisper() -> bool:
    try:
        importlib.import_module("mlx_whisper")
        return True
    except ImportError:
        return False


def select_default_transcriber_config() -> Dict[str, Any]:
    is_apple_silicon = (
        platform.system() == "Darwin" and platform.machine() == "arm64"
    )
    if is_apple_silicon and can_import_mlx_whisper():
        return {
            "transcriber_type": "mlx-whisper",
            "whisper_model_size": "base",
        }
    return {
        "transcriber_type": "fast-whisper",
        "whisper_model_size": "base",
    }


def build_default_transcriber_config() -> Dict[str, Any]:
    config = select_default_transcriber_config()
    return {
        "transcriber_type": os.getenv("TRANSCRIBER_TYPE", config["transcriber_type"]),
        "whisper_model_size": os.getenv(
            "WHISPER_MODEL_SIZE",
            config["whisper_model_size"],
        ),
    }


class TranscriberConfigManager:
    """管理转写器配置，存储在 JSON 文件中，支持前端动态修改。"""

    def __init__(self, filepath: Optional[str] = None):
        self.path = Path(filepath).resolve() if filepath else transcriber_config_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _read(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            with self.path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _write(self, data: Dict[str, Any]):
        with self.path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def get_config(self) -> Dict[str, Any]:
        """获取当前转写器配置，fallback 到环境变量默认值。"""
        data = self._read()
        config = build_default_transcriber_config()
        config.update(data)
        return config

    def update_config(
        self,
        transcriber_type: str,
        whisper_model_size: Optional[str] = None,
    ) -> Dict[str, Any]:
        """更新转写器配置并持久化。"""
        data = self._read()
        data["transcriber_type"] = transcriber_type
        if whisper_model_size is not None:
            data["whisper_model_size"] = whisper_model_size
        self._write(data)
        return self.get_config()

    def get_transcriber_type(self) -> str:
        return self.get_config()["transcriber_type"]

    def get_whisper_model_size(self) -> str:
        return self.get_config()["whisper_model_size"]
