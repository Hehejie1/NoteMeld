from faster_whisper import WhisperModel

from app.decorators.timeit import timeit
from app.models.transcriber_model import TranscriptSegment, TranscriptResult
from app.transcriber.base import Transcriber
from app.utils.env_checker import is_cuda_available, is_torch_installed
from app.utils.logger import get_logger
from app.utils.path_helper import get_model_dir

from events import transcription_finished
from pathlib import Path
import os
import shutil
from tqdm import tqdm
from modelscope import snapshot_download

from app.transcriber.model_prep import FAST_WHISPER_MODEL_MAP


'''
 Size of the model to use (tiny, tiny.en, base, base.en, small, small.en, distil-small.en, medium, medium.en, distil-medium.en, large-v1, large-v2, large-v3, large, distil-large-v2, distil-large-v3, large-v3-turbo, or turbo
'''
logger=get_logger(__name__)

MODEL_MAP = FAST_WHISPER_MODEL_MAP

INCOMPLETE_MODEL_ERROR_MARKERS = (
    "model.bin is incomplete",
    "failed to read a buffer",
    "unexpected eof",
    "incomplete",
)


def _is_incomplete_model_error(exc: BaseException) -> bool:
    message = str(exc).lower()
    return any(marker in message for marker in INCOMPLETE_MODEL_ERROR_MARKERS)


def _download_model(model_size: str, model_path: str) -> str:
    repo_id = MODEL_MAP.get(model_size)
    if not repo_id:
        raise RuntimeError(f"不支持的 Whisper 模型: {model_size}")

    logger.info(f"开始下载 whisper-{model_size} 模型...")
    snapshot_download(repo_id, local_dir=model_path)
    logger.info(f"whisper-{model_size} 模型下载完成")
    return model_path

class WhisperTranscriber(Transcriber):
    # TODO:修改为可配置
    def __init__(
            self,
            model_size: str = "base",
            device: str = 'cpu',
            compute_type: str = None,
            cpu_threads: int = 1,
    ):
        if device == 'cpu' or device is None:
            self.device = 'cpu'
        else:
            self.device = "cuda" if self.is_cuda() else "cpu"
            if device == 'cuda' and self.device == 'cpu':
                print('没有 cuda 使用 cpu进行计算')

        self.compute_type = compute_type or ("float16" if self.device == "cuda" else "int8")

        self.model_size = model_size
        model_dir = get_model_dir("whisper")
        model_path = os.path.join(model_dir, f"whisper-{model_size}")
        model_bin_path = os.path.join(model_path, "model.bin")
        if not Path(model_bin_path).exists():
            model_path = _download_model(model_size, model_path)
        if not Path(model_path, "model.bin").exists():
            raise RuntimeError(
                f"Whisper 模型 whisper-{model_size} 尚未准备完成，请等待 model.bin 下载完成后重试"
            )

        try:
            self.model = self._load_model(model_path, model_dir)
        except Exception as exc:
            if not _is_incomplete_model_error(exc):
                raise

            logger.warning(
                f"检测到 whisper-{model_size} 模型缓存损坏，准备删除并重新下载: {model_path}; 原始错误: {exc}"
            )
            shutil.rmtree(model_path, ignore_errors=True)
            model_path = _download_model(model_size, model_path)
            try:
                self.model = self._load_model(model_path, model_dir)
            except Exception as retry_exc:
                raise RuntimeError(
                    f"Whisper 模型 whisper-{model_size} 缓存损坏，已自动清理并重新下载一次但仍无法加载。"
                    f"请检查网络后在「音频转写配置」重新下载该模型，或手动删除目录后重试: {model_path}。"
                    f"原始错误: {retry_exc}"
                ) from retry_exc

    def _load_model(self, model_path: str, model_dir: str):
        return WhisperModel(
            model_size_or_path=model_path,
            device=self.device,
            compute_type=self.compute_type,
            download_root=model_dir
        )
    @staticmethod
    def is_torch_installed() -> bool:
        try:
            import torch
            return True
        except ImportError:
            return False

    @staticmethod
    def is_cuda() -> bool:
        try:
            if is_cuda_available():
                print(" CUDA 可用，使用 GPU")
                return True
            elif is_torch_installed():
                print(" 只装了 torch，但没有 CUDA，用 CPU")
                return False
            else:
                print(" 还没有安装 torch，请先安装")
                return False

        except ImportError:
            return False

    @timeit
    def transcript(self, file_path: str) -> TranscriptResult:
        try:

            segments_raw, info = self.model.transcribe(file_path)

            segments = []
            full_text = ""

            for seg in segments_raw:
                text = seg.text.strip()
                full_text += text + " "
                segments.append(TranscriptSegment(
                    start=seg.start,
                    end=seg.end,
                    text=text
                ))

            result= TranscriptResult(
                language=info.language,
                full_text=full_text.strip(),
                segments=segments,
                raw=info
            )
            # self.on_finish(file_path, result)
            return result
        except Exception as e:
            print(f"转写失败：{e}")


    def on_finish(self,video_path:str,result: TranscriptResult)->None:
        print("转写完成")
        transcription_finished.send({
            "file_path": video_path,
        })
