from __future__ import annotations

import argparse
import shutil
import sys
import types
from pathlib import Path
from typing import Optional

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

APP_ROOT = BACKEND_ROOT / "app"
if "app" not in sys.modules:
    app_mod = types.ModuleType("app")
    app_mod.__path__ = [str(APP_ROOT)]
    sys.modules["app"] = app_mod

from app.services.transcriber_config_manager import (
    TranscriberConfigManager,
)
from app.transcriber.model_prep import (
    FAST_WHISPER_MODEL_MAP,
    MLX_WHISPER_MODEL_MAP,
    ModelPrepSpec,
    build_model_prep_spec,
)
from app.utils.storage_paths import model_root_dir


MLX_REQUIRED_FILES = ("config.json", "tokenizer.json")
MLX_WEIGHT_FILES = ("weights.npz", "weights.safetensors", "model.safetensors")


def build_bootstrap_model_prep_spec(
    config_manager: Optional[TranscriberConfigManager] = None,
    model_root: Optional[Path] = None,
) -> ModelPrepSpec:
    manager = config_manager or TranscriberConfigManager()
    config = manager.get_config()
    resolved_model_root = model_root or model_root_dir()
    return build_model_prep_spec(
        transcriber_type=config["transcriber_type"],
        model_size=config["whisper_model_size"],
        model_root=resolved_model_root,
    )


def _is_model_cache_ready(spec: ModelPrepSpec) -> bool:
    if spec.transcriber_type == "fast-whisper":
        return spec.required_path.exists()

    if spec.transcriber_type == "mlx-whisper":
        if not spec.local_dir.exists():
            return False
        if any(not (spec.local_dir / file_name).exists() for file_name in MLX_REQUIRED_FILES):
            return False
        return any((spec.local_dir / file_name).exists() for file_name in MLX_WEIGHT_FILES)

    raise ValueError(f"不支持的转写器类型: {spec.transcriber_type}")


def _find_existing_prepared_model(
    model_root: Path,
    preferred_transcriber_type: str,
) -> Optional[ModelPrepSpec]:
    candidate_types = [preferred_transcriber_type]
    for transcriber_type in ("mlx-whisper", "fast-whisper"):
        if transcriber_type not in candidate_types:
            candidate_types.append(transcriber_type)

    model_maps = {
        "fast-whisper": FAST_WHISPER_MODEL_MAP,
        "mlx-whisper": MLX_WHISPER_MODEL_MAP,
    }

    for transcriber_type in candidate_types:
        for model_size in model_maps[transcriber_type]:
            spec = build_model_prep_spec(
                transcriber_type=transcriber_type,
                model_size=model_size,
                model_root=model_root,
            )
            if _is_model_cache_ready(spec):
                return spec

    return None


def prepare_model_for_spec(spec: ModelPrepSpec) -> ModelPrepSpec:
    if _is_model_cache_ready(spec):
        return spec

    spec.local_dir.parent.mkdir(parents=True, exist_ok=True)
    if spec.local_dir.exists():
        shutil.rmtree(spec.local_dir, ignore_errors=True)

    if spec.transcriber_type == "fast-whisper":
        from modelscope import snapshot_download

        snapshot_download(spec.repo_id, local_dir=str(spec.local_dir))
    elif spec.transcriber_type == "mlx-whisper":
        from huggingface_hub import snapshot_download

        snapshot_download(
            spec.repo_id,
            local_dir=str(spec.local_dir),
            local_dir_use_symlinks=False,
        )
    else:
        raise ValueError(f"不支持的转写器类型: {spec.transcriber_type}")

    if not _is_model_cache_ready(spec):
        raise RuntimeError(
            f"转写模型尚未准备完成: {spec.transcriber_type}/{spec.model_size}"
        )

    return spec


def bootstrap_default_transcriber(
    config_manager: Optional[TranscriberConfigManager] = None,
    model_root: Optional[Path] = None,
) -> ModelPrepSpec:
    manager = config_manager or TranscriberConfigManager()
    resolved_model_root = model_root or model_root_dir()
    effective_config = manager.get_config()

    primary_spec = build_model_prep_spec(
        transcriber_type=effective_config["transcriber_type"],
        model_size=effective_config["whisper_model_size"],
        model_root=resolved_model_root,
    )

    if _is_model_cache_ready(primary_spec):
        manager.update_config(primary_spec.transcriber_type, primary_spec.model_size)
        return primary_spec

    existing_spec = _find_existing_prepared_model(
        resolved_model_root,
        preferred_transcriber_type=primary_spec.transcriber_type,
    )
    if existing_spec is not None:
        manager.update_config(existing_spec.transcriber_type, existing_spec.model_size)
        return existing_spec

    try:
        prepare_model_for_spec(primary_spec)
        manager.update_config(primary_spec.transcriber_type, primary_spec.model_size)
        return primary_spec
    except Exception:
        fallback_spec = build_model_prep_spec(
            transcriber_type="fast-whisper",
            model_size="base",
            model_root=resolved_model_root,
        )
        if (
            fallback_spec.transcriber_type == primary_spec.transcriber_type
            and fallback_spec.model_size == primary_spec.model_size
        ):
            raise

        prepare_model_for_spec(fallback_spec)
        manager.update_config(fallback_spec.transcriber_type, fallback_spec.model_size)
        return fallback_spec


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare the default NoteMeld transcriber model."
    )
    parser.add_argument(
        "--config-path",
        help="Path to the transcriber config JSON file.",
    )
    parser.add_argument(
        "--model-root",
        type=Path,
        help="Root directory where transcriber models are stored.",
    )
    return parser.parse_args([] if argv is None else argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    if args.config_path:
        spec = bootstrap_default_transcriber(
            config_manager=TranscriberConfigManager(args.config_path),
            model_root=args.model_root,
        )
    elif args.model_root is not None:
        spec = bootstrap_default_transcriber(model_root=args.model_root)
    else:
        spec = bootstrap_default_transcriber()
    print(
        f"Prepared default transcriber: {spec.transcriber_type}/{spec.model_size}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
