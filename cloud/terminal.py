"""Sandboxed workspace terminal.

每个会话的终端只能运行在“分配文件夹”（workspace root）内：

- 终端进程的 cwd 固定为 workspace root，命令里的相对路径都基于它；
- 命令执行前做路径解析，``..`` 越界、绝对路径指向 root 之外一律拒绝；
- 不提供对系统目录（/etc、/usr 等）的访问：cd 到 root 之外会被拦截；
- 使用持久 PTY（WebSocket），支持交互式命令（vim/top 之外的常规 shell）。

注意：这是应用层沙箱。macOS 上非特权进程无法 chroot，因此靠 cwd + 路径
策略约束；生产 Linux 部署应把该终端放进以 workspace 为根的容器/chroot，
内核级强制隔离（见 create_app 中的挂载说明）。
"""
from __future__ import annotations

import os
import re
import shlex
import threading
from pathlib import Path

from .workspace import Workspace, WorkspaceError

# 危险/越界命令片段的保守拦截（纵深防御，真正的边界仍是 cwd + 路径校验）。
_FORBIDDEN_TOKENS = {
    "sudo", "su", "mkfs", "dd", "shutdown", "reboot", "halt",
    "mount", "umount", "chroot", "launchctl", "systemctl",
}

_MAX_OUTPUT_BYTES = 256 * 1024


class TerminalError(ValueError):
    pass


class SandboxedShell:
    """以 workspace root 为根目录的受限 shell 命令执行器。"""

    def __init__(self, workspace: Workspace):
        self.workspace = workspace
        self.root = workspace.root
        self._lock = threading.Lock()

    def resolve_cwd(self, cwd: str | None) -> Path:
        """把 shell 的逻辑 cwd（相对 root）解析为真实路径并禁止越界。"""
        if not cwd or cwd in {".", "~", "/"}:
            return self.root if cwd != "/" else self.root
        # 逻辑 cwd 一律相对 root；任何前导 / 也被当成 root。
        relative = cwd.lstrip("/")
        candidate = (self.root / relative).resolve(strict=False)
        try:
            inside = os.path.commonpath((str(self.root), str(candidate))) == str(self.root)
        except ValueError:
            inside = False
        if not inside:
            raise TerminalError(f"访问被拒绝：{cwd} 不在分配文件夹内")
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
        for token in tokens:
            base = token.split("/")[-1]
            if base in _FORBIDDEN_TOKENS:
                raise TerminalError(f"命令被禁止：{base}")
        for token in tokens:
            # 绝对路径：仅允许重定向到 /dev/null；其它一律禁止。
            if token.startswith("/") and token != "/dev/null":
                raise TerminalError("访问被禁止：只能使用分配文件夹内的相对路径")
            # 任何会跳出根目录的相对遍历（../../x、../x）都拒绝。
            if self._escapes_root(token):
                raise TerminalError(f"访问被拒绝：{token} 超出分配文件夹")

    @staticmethod
    def _escapes_root(token: str) -> bool:
        # 去掉前导 ./，按路径段压栈；只要解析结果需要离开根（.. 多于已进入
        # 的层级）即判定越界。保守起见，命令层直接禁止出现可越界的 .. 段。
        segments = token.split("/")
        depth = 0
        for segment in segments:
            if segment in {"", "."}:
                continue
            if segment == "..":
                if depth == 0:
                    return True
                depth -= 1
            else:
                depth += 1
        return False

    def run(self, command: str, cwd: str | None = None) -> dict[str, object]:
        """执行单条命令并返回 stdout/stderr/exit_code（阻塞至结束）。"""
        import subprocess

        with self._lock:
            self._validate_command(command)
            working_dir = self.resolve_cwd(cwd)
            working_dir.mkdir(parents=True, exist_ok=True)
            # 用沙箱前缀覆盖 cd/pushd，任何离开根目录的切换都被拒绝；
            # 执行后打印标记行回传真实 cwd。
            wrapped = (
                f"{self._sandbox_preamble()}\n"
                f"{command}\n"
                f"__rc=$?\n"
                f"printf '\\n__CLOUD_CWD__%%s' \"$PWD\"\n"
                f"exit $__rc\n"
            )
            try:
                completed = subprocess.run(
                    ["/bin/bash", "--noprofile", "--norc", "-c", wrapped],
                    capture_output=True,
                    timeout=30,
                    cwd=str(working_dir),
                    env=self._minimal_env(),
                )
            except subprocess.TimeoutExpired:
                raise TerminalError("命令执行超时（30 秒）")
            raw_out = self._cap(completed.stdout).decode("utf-8", errors="replace")
            stdout, reported_cwd = self._split_cwd(raw_out)
            final_cwd = self._safe_relpath(reported_cwd or str(working_dir))
            return {
                "stdout": stdout,
                "stderr": self._cap(completed.stderr).decode("utf-8", errors="replace"),
                "exit_code": completed.returncode,
                "cwd": final_cwd,
            }

    def _sandbox_preamble(self) -> str:
        root = shlex.quote(str(self.root))
        # 覆盖 cd/pushd：切换后用字符串前缀判定 PWD 是否仍在根目录内，
        # 越界则回滚到原目录并报错。纯 bash 实现，不依赖外部解释器。
        return (
            f"__CLOUD_ROOT__={root}\n"
            "__cloud_inside__(){\n"
            "  case \"$PWD/\" in \"$__CLOUD_ROOT__\"/*) return 0;; esac\n"
            "  [ \"$PWD\" = \"$__CLOUD_ROOT__\" ]\n"
            "}\n"
            "cd(){ local d=\"$1\"; [ -z \"$d\" ] && d=\"$__CLOUD_ROOT__\";\n"
            "  local before=\"$PWD\"; command cd \"$d\" 2>/dev/null || return 1;\n"
            "  if __cloud_inside__; then return 0; fi;\n"
            "  command cd \"$before\"; echo \"cd: 访问被拒绝：超出分配文件夹\" >&2; return 1; }\n"
            "pushd(){ cd \"$1\"; }\n"
        )

    @staticmethod
    def _split_cwd(raw: str) -> tuple[str, str | None]:
        marker = "\n__CLOUD_CWD__"
        if marker in raw:
            head, tail = raw.rsplit(marker, 1)
            return head, tail
        return raw, None

    def _safe_relpath(self, path: str) -> str:
        candidate = Path(path).resolve()
        try:
            inside = os.path.commonpath((str(self.root), str(candidate))) == str(self.root)
        except ValueError:
            inside = False
        if not inside:
            return "."
        return os.path.relpath(candidate, self.root) or "."

    def _minimal_env(self) -> dict[str, str]:
        # 不继承宿主环境变量，最小化泄露；HOME 指向 workspace root。
        return {
            "PATH": "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
            "HOME": str(self.root),
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


def open_workspace_shell(workspaces_dir: Path, user_id: str, workspace_id: str) -> SandboxedShell:
    """根据用户与工作区构造受限 shell；workspace_id 必须是安全的单段名称。"""
    if not _SAFE_NAME.match(user_id) or not _SAFE_NAME.match(workspace_id):
        raise WorkspaceError("invalid workspace identifier")
    workspace = Workspace(workspaces_dir / user_id / workspace_id)
    return SandboxedShell(workspace)
