from dataclasses import dataclass
from pathlib import Path
from typing import Union


FAST_WHISPER_MODEL_MAP = {
    "tiny": "pengzhendong/faster-whisper-tiny",
    "base": "pengzhendong/faster-whisper-base",
    "small": "pengzhendong/faster-whisper-small",
    "medium": "pengzhendong/faster-whisper-medium",
    "large-v1": "pengzhendong/faster-whisper-large-v1",
    "large-v2": "pengzhendong/faster-whisper-large-v2",
    "large-v3": "pengzhendong/faster-whisper-large-v3",
    "large-v3-turbo": "pengzhendong/faster-whisper-large-v3-turbo",
}

MLX_WHISPER_MODEL_MAP = {
    "tiny": "mlx-community/whisper-tiny-mlx",
    "base": "mlx-community/whisper-base-mlx",
    "small": "mlx-community/whisper-small-mlx",
    "medium": "mlx-community/whisper-medium-mlx",
    "large-v1": "mlx-community/whisper-large-v1-mlx",
    "large-v2": "mlx-community/whisper-large-v2-mlx",
    "large-v3": "mlx-community/whisper-large-v3-mlx",
    "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
}


@dataclass(frozen=True)
class ModelPrepSpec:
    transcriber_type: str
    model_size: str
    download_key: str
    repo_id: str
    local_dir: Path
    required_path: Path


def build_model_prep_spec(
    transcriber_type: str,
    model_size: str,
    model_root: Union[str, Path],
) -> ModelPrepSpec:
    root = Path(model_root)

    if transcriber_type == "fast-whisper":
        repo_id = FAST_WHISPER_MODEL_MAP.get(model_size)
        if not repo_id:
            raise ValueError(f"不支持的 fast-whisper 模型大小: {model_size}")
        local_dir = root / "whisper" / f"whisper-{model_size}"
        return ModelPrepSpec(
            transcriber_type=transcriber_type,
            model_size=model_size,
            download_key=model_size,
            repo_id=repo_id,
            local_dir=local_dir,
            required_path=local_dir / "model.bin",
        )

    if transcriber_type == "mlx-whisper":
        repo_id = MLX_WHISPER_MODEL_MAP.get(model_size)
        if not repo_id:
            raise ValueError(f"不支持的 mlx-whisper 模型大小: {model_size}")
        local_dir = root / "mlx-whisper" / repo_id
        return ModelPrepSpec(
            transcriber_type=transcriber_type,
            model_size=model_size,
            download_key=f"mlx-{model_size}",
            repo_id=repo_id,
            local_dir=local_dir,
            required_path=local_dir,
        )

    raise ValueError(f"不支持的转写器类型: {transcriber_type}")
