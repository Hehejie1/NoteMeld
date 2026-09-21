"""模型 Provider API Key 的本地加密支持。

- 主密钥为 Fernet key，首次启动生成，0600 保存在运行数据目录 config/model_secret.key。
- 数据库只存密文（providers.api_key_ciphertext），任何 HTTP 响应/日志都不得出现明文。
- 写文件遵循 known-pitfalls：os.open 限定权限 + fsync + 同目录原子替换。
"""

from __future__ import annotations

import logging
import os
import tempfile
from functools import lru_cache
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from app.utils.storage_paths import model_secret_key_path

logger = logging.getLogger(__name__)


def _atomic_write_key(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".model_secret.", dir=str(path.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(raw)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, path)
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    path = model_secret_key_path()
    if not path.exists():
        key = Fernet.generate_key()
        try:
            _atomic_write_key(path, key)
        except OSError as exc:
            # 生成/落盘失败时，若并发的另一进程已写入，则回退读取已有密钥
            if not path.exists():
                raise RuntimeError(f"无法写入模型密钥文件: {exc}") from exc
            key = path.read_bytes().strip()
    else:
        key = path.read_bytes().strip()
    try:
        return Fernet(key)
    except (ValueError, TypeError) as exc:
        raise RuntimeError("模型密钥文件内容无效") from exc


def encrypt(plaintext: str) -> str:
    """加密明文 Key，返回字符串密文；空串返回空串（免 Key 协议不产生密文）。"""
    if not plaintext:
        return ""
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt(ciphertext: str | None) -> str:
    """解密密文；空值/空串返回空串；解密失败返回空串并记录（绝不把密文抛给上层响应）。"""
    if not ciphertext:
        return ""
    try:
        return _fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, TypeError):
        logger.warning("模型密钥解密失败，已按空凭据处理（不输出密文）")
        return ""


def mask_key(plaintext: str | None) -> str:
    """对外展示用掩码；短于 8 位全掩码。"""
    if not plaintext:
        return ""
    if len(plaintext) < 8:
        return "*" * len(plaintext)
    return f"{plaintext[:4]}{'*' * (len(plaintext) - 8)}{plaintext[-4:]}"
