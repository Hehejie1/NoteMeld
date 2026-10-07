"""Deployment terminal（固定部署目录 + 可选 bubblewrap 内核强制）。

终端不再以“会话”为根，而是固定指向**部署项目目录**（如
``/srv/notemeld/projects``）：

- 每个对话终端默认进入该目录，目录下任意读写、装包（pip/npm）、部署都支持；
- 终端引用的路径若超出该目录，应用层直接拒绝；
- 当 ``terminal_use_bwrap`` 打开且系统存在 bwrap 时，命令在 bubblewrap 容器内
  执行，由内核强制：
  - 部署目录 bind 到容器内 ``/work``，是**唯一可写**位置；
  - 系统运行所需目录（/usr、/lib、/bin、/etc 等）只读 bind；
  - 宿主机其它路径（/root、/home、/srv/notemeld 的代码与数据）一律不挂载，
    内核层面不可见——因此 ``sh -c``、``python3``、``awk system()`` 等嵌套
    解释器也无法访问宿主机或 NoteMeld 代码。

注意：/etc 整体只读 bind 以满足 libc/CA/域名解析需要，但其中的宿主机敏感
文件（/etc/shadow、/etc/ssh、/etc/letsencrypt、/etc/wireguard 等）会在挂载后
用 tmpfs 遮蔽，容器内读到的是空内容。/etc/passwd 仅含账号名（各系统通用、
非机密），保留以支持用户名解析。
未启用 bwrap 时（如本地开发且未安装），退化为 cwd + 路径检查的应用层约束。
"""
from __future__ import annotations

import os
import re
import shlex
import shutil
import threading
from pathlib import Path

from .workspace import WorkspaceError

_MAX_OUTPUT_BYTES = 256 * 1024
# 容器内部署目录的挂载点。
_CONTAINER_WORK = "/work"
# /etc 下需要遮蔽的宿主机敏感文件与目录（挂载 /etc 后用 tmpfs 覆盖）。
_ETC_SECRETS = (
    "shadow", "shadow-", "shadow+",
    "gshadow", "gshadow-", "gshadow+",
    "passwd-", "passwd+",
    "sudoers", "sudoers.d",
    "ssh",
    "krb5.keytab",
    "letsencrypt",
    "ssl/private",
    "pki/tls/private", "pki/CA/private",
    "wireguard",
    "nginx",
    "cloud",
    ".pwd.lock",
    "machine-id",
)


class TerminalError(ValueError):
    pass


class SandboxedShell:
    """以固定部署目录为根的命令执行器（可选 bwrap 内核隔离）。"""

    def __init__(self, root: Path, use_bwrap: bool = False):
        self.root = Path(root)
        self.use_bwrap = use_bwrap and shutil.which("bwrap") is not None
        self._lock = threading.Lock()

    def resolve_cwd(self, cwd: str | None) -> Path:
        """把终端逻辑 cwd（相对部署根）解析为宿主机真实路径并禁止越界。"""
        if not cwd or cwd in {".", "~", "/"}:
            return self.root
        relative = cwd.lstrip("/")
        candidate = (self.root / relative).resolve(strict=False)
        if not self._is_inside(candidate):
            raise TerminalError(f"访问被拒绝：{cwd} 不在部署目录内")
        return candidate

    def _validate_command(self, command: str) -> None:
        if not command.strip():
            raise TerminalError("空命令")
        if "\x00" in command:
            raise TerminalError("非法命令")
        try:
            tokens = shlex.split(command, posix=True)
        except ValueError as exc:
            raise TerminalError(f"命令解析失败：{exc}") from exc
        # 不限制命令本身，只校验它引用的每个路径是否仍在部署目录内。
        for token in tokens:
            if self._looks_like_path(token) and not self._token_inside(token):
                raise TerminalError(f"访问被拒绝：{token} 超出部署目录")

    def _token_inside(self, token: str) -> bool:
        # bwrap 模式下，容器内路径 /work/xxx 等价于部署根下的 xxx。
        if self.use_bwrap and token == _CONTAINER_WORK:
            candidate = self.root
        elif self.use_bwrap and token.startswith(_CONTAINER_WORK + "/"):
            candidate = self.root / token[len(_CONTAINER_WORK) + 1:]
        else:
            candidate = Path(token) if token.startswith("/") else self.root / token
        return self._is_inside(candidate.resolve(strict=False))

    def _is_inside(self, candidate: Path) -> bool:
        try:
            return os.path.commonpath((str(self.root), str(candidate))) == str(self.root)
        except ValueError:
            return False

    @staticmethod
    def _looks_like_path(token: str) -> bool:
        """仅把含路径分隔符/目录遍历的 token 判定为路径，避免误伤普通文本参数。"""
        return token in {".", ".."} or "/" in token

    def run(self, command: str, cwd: str | None = None) -> dict[str, object]:
        """执行单条命令并返回 stdout/stderr/exit_code/cwd（阻塞至结束）。"""
        import subprocess

        with self._lock:
            self._validate_command(command)
            working_dir = self.resolve_cwd(cwd)
            working_dir.mkdir(parents=True, exist_ok=True)
            logical_cwd = os.path.relpath(working_dir, self.root) or "."
            wrapped = (
                f"{self._sandbox_preamble()}\n"
                f"{command}\n"
                f"__rc=$?\n"
                f"printf '\\n__CLOUD_CWD__%%s' \"$PWD\"\n"
                f"exit $__rc\n"
            )
            if self.use_bwrap:
                argv = self._bwrap_argv(working_dir=working_dir, script=wrapped)
            else:
                argv = ["/bin/bash", "--noprofile", "--norc", "-c", wrapped]
            try:
                completed = subprocess.run(
                    argv,
                    capture_output=True,
                    timeout=30,
                    cwd=str(working_dir),
                    env=self._minimal_env(),
                )
            except subprocess.TimeoutExpired:
                raise TerminalError("命令执行超时（30 秒）")
            raw_out = self._cap(completed.stdout).decode("utf-8", errors="replace")
            stdout, reported_cwd = self._split_cwd(raw_out)
            final_cwd = self._safe_relpath(
                reported_cwd, host_cwd=working_dir, logical_cwd=logical_cwd
            )
            return {
                "stdout": stdout,
                "stderr": self._cap(completed.stderr).decode("utf-8", errors="replace"),
                "exit_code": completed.returncode,
                "cwd": final_cwd,
            }

    def _bwrap_argv(self, working_dir: Path, script: str) -> list[str]:
        """构造 bubblewrap 命令：/work 唯一可写，系统目录只读，宿主其余路径不可见。"""
        rel = os.path.relpath(working_dir, self.root)
        container_cwd = _CONTAINER_WORK if rel == "." else f"{_CONTAINER_WORK}/{rel}"
        argv = ["bwrap"]
        # 只读挂载运行所需的系统目录（不存在则跳过）。
        for system_dir in ("/usr", "/lib", "/lib64", "/bin", "/sbin", "/etc"):
            if Path(system_dir).exists():
                argv += ["--ro-bind", system_dir, system_dir]
        # 遮蔽 /etc 下的宿主机敏感文件/目录：目录用 tmpfs 覆盖，
        # 普通文件只读绑定 /dev/null（--tmpfs 仅支持目录目标）。
        for secret in _ETC_SECRETS:
            target = Path("/etc", secret)
            if target.is_dir():
                argv += ["--tmpfs", "/etc/" + secret]
            elif target.is_file():
                argv += ["--ro-bind", "/dev/null", "/etc/" + secret]
        argv += [
            "--proc", "/proc",
            "--dev", "/dev",
            "--tmpfs", "/tmp",
            # 部署目录 bind 为唯一可写位置。
            "--bind", str(self.root), _CONTAINER_WORK,
            "--setenv", "HOME", _CONTAINER_WORK,
            "--chdir", container_cwd,
            "--new-session",
            "/bin/bash", "--noprofile", "--norc", "-c", script,
        ]
        return argv

    def _sandbox_preamble(self) -> str:
        # bwrap 内根为 /work；非 bwrap（应用层模式）根为宿主机部署目录。
        root = _CONTAINER_WORK if self.use_bwrap else shlex.quote(str(self.root))
        # 覆盖 cd/pushd：切换后判定 PWD 是否仍在根目录内，越界则回滚并报错。
        return (
            f"__CLOUD_ROOT__={root}\n"
            "__cloud_inside__(){\n"
            "  case \"$PWD/\" in \"$__CLOUD_ROOT__\"/*) return 0;; esac\n"
            "  [ \"$PWD\" = \"$__CLOUD_ROOT__\" ]\n"
            "}\n"
            "cd(){ local d=\"$1\"; [ -z \"$d\" ] && d=\"$__CLOUD_ROOT__\";\n"
            "  local before=\"$PWD\"; command cd \"$d\" 2>/dev/null || return 1;\n"
            "  if __cloud_inside__; then return 0; fi;\n"
            "  command cd \"$before\"; echo \"cd: 访问被拒绝：超出部署目录\" >&2; return 1; }\n"
            "pushd(){ cd \"$1\"; }\n"
        )

    @staticmethod
    def _split_cwd(raw: str) -> tuple[str, str | None]:
        marker = "\n__CLOUD_CWD__"
        if marker in raw:
            head, tail = raw.rsplit(marker, 1)
            return head, tail
        return raw, None

    def _safe_relpath(self, reported: str | None, host_cwd: Path, logical_cwd: str) -> str:
        """把命令回传的 cwd 归一为相对部署根的逻辑路径。"""
        if not reported:
            return logical_cwd
        if self.use_bwrap:
            # 容器内路径 /work/xxx -> 相对路径 xxx。
            if reported == _CONTAINER_WORK:
                return "."
            prefix = _CONTAINER_WORK + "/"
            if reported.startswith(prefix):
                return reported[len(prefix):] or "."
            return logical_cwd
        candidate = Path(reported).resolve()
        return os.path.relpath(candidate, self.root) if self._is_inside(candidate) else logical_cwd

    def _minimal_env(self) -> dict[str, str]:
        # 不继承宿主环境变量，最小化泄露。
        return {
            "PATH": "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
            "HOME": _CONTAINER_WORK if self.use_bwrap else str(self.root),
            "LANG": os.getenv("LANG", "en_US.UTF-8"),
            "TERM": "xterm-256color",
            "PS1": r"\u@cloud:\w\$ ",
        }

    @staticmethod
    def _cap(data: bytes) -> bytes:
        if len(data) > _MAX_OUTPUT_BYTES:
            return data[:_MAX_OUTPUT_BYTES] + "\n[输出已截断]".encode()
        return data


_SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]+$")


def open_deployment_shell(root: Path, use_bwrap: bool = False) -> SandboxedShell:
    """构造以固定部署目录为根的终端执行器。"""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    return SandboxedShell(root, use_bwrap=use_bwrap)


def open_workspace_shell(workspaces_dir: Path, user_id: str, workspace_id: str) -> SandboxedShell:
    """已废弃：保留仅为兼容旧调用，按用户/工作区构造应用层 shell。"""
    if not _SAFE_NAME.match(user_id) or not _SAFE_NAME.match(workspace_id):
        raise WorkspaceError("invalid workspace identifier")
    return SandboxedShell(Path(workspaces_dir) / user_id / workspace_id)
