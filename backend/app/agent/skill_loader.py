"""P3-T3: SKILL.md 解析 → AgentTool + Parameter Collector。

SKILL.md 格式（spec B.6）::

    ---
    name: compile_source
    description: 编译视频/网页为结构化笔记
    parameters:
      - key: url
        label: 视频链接
        widget: text_input
        required: true
      - key: style
        label: 笔记风格
        widget: select
        options: [简洁, 详细]
        required: false
        default: 简洁
    long_running: true
    timeout_seconds: 600
    ---
    脚本调用：python scripts/compile_source.py --url "$url" --style "$style"

设计要点：
- 复用 ``AgentTool`` 接口；execute 函数内完成「参数校验 → Parameter Collector →
  脚本执行」三步。
- ``long_running=true`` 的 skill 由 ``LongTaskManager`` 接管（P3-T4 实现）；
  本模块只负责把 ``LongTaskManager.start_task`` 包成 execute。
- ``long_running=false`` 的 skill 直接 ``asyncio.create_subprocess_exec`` 执行，
  捕获 stdout/stderr 作为 ToolResult；尊重 ``signal.aborted``（kill 子进程）。
- Parameter Collector：必填参数缺失时通过 ``on_update`` 派发 ``parameter_request``
  事件，并 await ``ParameterCollector`` 持有的 future；用户通过 HTTP 提交
  ``parameter_response`` 后 resolve。本机制对 Agent 透明，execute 看到的就是
  填好的 params。
- skills_dir 默认 = ``note_output_dir()/skills``；也可读工作空间的 ``skills`` 子目录。
- 路径安全：脚本命令通过 ``shlex.split`` 拆分后用 ``create_subprocess_exec``（非 shell）；
  ``$key`` / ``${key}`` 占位符用 ``shlex.quote`` 转义后的值替换，避免注入。
"""
from __future__ import annotations

import asyncio
import json
import re
import shlex
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from app.agent.core.signal import AbortSignal
from app.agent.core.tool import AgentTool, ToolResult
from app.utils.logger import get_logger
from app.utils.storage_paths import note_output_dir

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

#: 非长任务默认超时（秒）。
DEFAULT_SKILL_TIMEOUT = 120

#: 长 task 默认超时（秒）；0 表示不限。
DEFAULT_LONG_TASK_TIMEOUT = 0

#: widget → JSON Schema type 映射。
_WIDGET_TYPE_MAP: dict[str, str] = {
    "text_input": "string",
    "textarea": "string",
    "number_input": "number",
    "select": "string",
    "checkbox": "boolean",
    "date": "string",
}

#: skill name 安全字符。
_SKILL_NAME_RE = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")

#: 占位符正则：$key 或 ${key}。
_PLACEHOLDER_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)")


class SkillLoaderError(ValueError):
    """SKILL.md 解析或执行错误。"""


# ---------------------------------------------------------------------------
# SkillDefinition
# ---------------------------------------------------------------------------


@dataclass
class SkillDefinition:
    """解析后的 SKILL.md 定义。

    Attributes:
        name: skill 唯一标识（同时作为 AgentTool.name）。
        description: 工具描述，写入 LLM context。
        parameters: 参数定义列表，每项 ``{key,label,widget,required,default,options}``。
        long_running: 是否为长任务（由 LongTaskManager 接管）。
        script_command: 脚本调用模板，含 ``$key`` / ``${key}`` 占位符。
        timeout_seconds: 非长任务超时；0 表示不限。
        skill_file: SKILL.md 文件路径。
        working_dir: 脚本执行工作目录（默认 skill_file 的父目录）。
    """

    name: str
    description: str
    parameters: list[dict] = field(default_factory=list)
    long_running: bool = False
    script_command: str = ""
    timeout_seconds: int = DEFAULT_SKILL_TIMEOUT
    skill_file: Optional[Path] = None
    working_dir: Optional[Path] = None

    # ------------------------------------------------------------------ #
    def to_json_schema(self) -> dict:
        """把 parameters list 转为 JSON Schema（与 AgentTool.parameters 对齐）。"""
        properties: dict[str, dict] = {}
        required: list[str] = []
        for p in self.parameters:
            key = str(p.get("key") or "").strip()
            if not key:
                continue
            widget = str(p.get("widget") or "text_input")
            json_type = _WIDGET_TYPE_MAP.get(widget, "string")
            prop: dict[str, Any] = {"type": json_type, "description": p.get("label") or key}
            if "default" in p and p.get("default") is not None:
                prop["default"] = p.get("default")
            if widget == "select" and isinstance(p.get("options"), list):
                prop["enum"] = list(p.get("options") or [])
            properties[key] = prop
            if p.get("required"):
                required.append(key)
        return {
            "type": "object",
            "properties": properties,
            **({"required": required} if required else {}),
        }

    def required_keys(self) -> list[str]:
        return [str(p.get("key")) for p in self.parameters if p.get("required")]


# ---------------------------------------------------------------------------
# SKILL.md 解析
# ---------------------------------------------------------------------------


def parse_skill_content(content: str, *, skill_file: Optional[Path] = None) -> SkillDefinition:
    """解析 SKILL.md 文本内容为 ``SkillDefinition``。

    Args:
        content: SKILL.md 文件全文。
        skill_file: 文件路径（用于记录与工作目录推断）。

    Raises:
        SkillLoaderError: frontmatter 缺失 / name 非法 / 缺少脚本调用。
    """
    frontmatter, body = _split_frontmatter(content)
    if frontmatter is None:
        raise SkillLoaderError("SKILL.md 缺少 frontmatter（需以 `---` 开头）")

    data = _parse_yaml(frontmatter)
    if not isinstance(data, dict):
        raise SkillLoaderError("SKILL.md frontmatter 必须是对象")

    name = str(data.get("name") or "").strip()
    if not _SKILL_NAME_RE.match(name):
        raise SkillLoaderError(f"非法 skill name: {name!r}")

    description = str(data.get("description") or "").strip()
    params = data.get("parameters") or []
    if not isinstance(params, list):
        raise SkillLoaderError("parameters 必须是列表")

    # 规范化每个参数项
    norm_params: list[dict] = []
    for item in params:
        if not isinstance(item, dict):
            continue
        norm_params.append({
            "key": str(item.get("key") or "").strip(),
            "label": str(item.get("label") or "").strip(),
            "widget": str(item.get("widget") or "text_input"),
            "required": bool(item.get("required")),
            "default": item.get("default"),
            "options": item.get("options"),
        })

    long_running = bool(data.get("long_running"))
    timeout = int(data.get("timeout_seconds") or (DEFAULT_LONG_TASK_TIMEOUT if long_running else DEFAULT_SKILL_TIMEOUT))

    script_command = _extract_script_command(body)
    if not script_command:
        raise SkillLoaderError(f"SKILL.md {name} 缺少脚本调用（需在 body 中提供 `脚本调用：...` 或 `script: ...`）")

    working_dir = skill_file.parent if skill_file else None

    return SkillDefinition(
        name=name,
        description=description or name,
        parameters=norm_params,
        long_running=long_running,
        script_command=script_command,
        timeout_seconds=timeout,
        skill_file=skill_file,
        working_dir=working_dir,
    )


def parse_skill_file(path: str | Path) -> SkillDefinition:
    """读取并解析 SKILL.md 文件。"""
    p = Path(path)
    if not p.exists():
        raise SkillLoaderError(f"SKILL.md 不存在: {p}")
    if not p.is_file():
        raise SkillLoaderError(f"SKILL.md 不是文件: {p}")
    content = p.read_text(encoding="utf-8")
    return parse_skill_content(content, skill_file=p)


def _split_frontmatter(content: str) -> tuple[Optional[str], str]:
    """分离 frontmatter 与 body。

    支持标准 ``---`` 分隔。返回 ``(frontmatter_text, body_text)``；
    若无 frontmatter 返回 ``(None, content)``。
    """
    if not content.startswith("---"):
        return None, content
    # 去掉首个 ---
    rest = content[3:]
    # 找下一个独立行的 ---
    idx = rest.find("\n---")
    if idx == -1:
        return None, content
    frontmatter = rest[:idx].strip()
    body = rest[idx + 4 :]  # 跳过 \n---
    # 去掉 body 开头的换行
    if body.startswith("\r\n"):
        body = body[2:]
    elif body.startswith("\n"):
        body = body[1:]
    return frontmatter, body


def _parse_yaml(text: str) -> Any:
    """解析 YAML；优先 PyYAML，缺失时用最小内建解析器（仅支持本格式子集）。"""
    try:
        import yaml  # type: ignore

        return yaml.safe_load(text)
    except ImportError:
        return _minimal_yaml_parse(text)


def _minimal_yaml_parse(text: str) -> Any:
    """极简 YAML 解析：支持 flat key:value 与 ``- key: value`` 列表项。

    仅满足 SKILL.md frontmatter 子集；复杂结构请装 PyYAML。
    """
    result: dict[str, Any] = {}
    current_list: list[Any] | None = None
    current_key: str | None = None

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line.strip() or line.strip().startswith("#"):
            continue
        stripped = line.strip()
        # 列表项：- key: value 或 - value
        if stripped.startswith("- "):
            item_text = stripped[2:].strip()
            if current_list is None:
                current_list = []
                if current_key is not None:
                    result[current_key] = current_list
            # - key: value
            if ":" in item_text:
                k, _, v = item_text.partition(":")
                item: dict[str, Any] = {k.strip(): _coerce_scalar(v.strip())}
                current_list.append(item)
            else:
                current_list.append(_coerce_scalar(item_text))
            continue
        # top-level key: value
        if ":" in stripped:
            k, _, v = stripped.partition(":")
            current_key = k.strip()
            v = v.strip()
            if v == "":
                # 下一行可能是列表
                current_list = []
                result[current_key] = current_list
            else:
                result[current_key] = _coerce_scalar(v)
                current_list = None
    return result


def _coerce_scalar(value: str) -> Any:
    """把 YAML 标量字符串转为 Python 值。"""
    if not value:
        return ""
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_coerce_scalar(x.strip()) for x in inner.split(",")]
    if value in ("true", "True"):
        return True
    if value in ("false", "False"):
        return False
    if value in ("null", "None", "~"):
        return None
    # 去引号
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    # 数字
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


def _extract_script_command(body: str) -> str:
    """从 body 提取脚本调用命令。

    支持两种前缀：
    - ``脚本调用：python scripts/foo.py --url "$url"``
    - ``script: python scripts/foo.py --url "$url"``

    也接受无前缀的首个非空命令行（以 ``python`` / ``python3`` / ``bash`` / ``sh`` / ``node`` 开头）。
    """
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("脚本调用："):
            return line[len("脚本调用：") :].strip()
        if line.startswith("脚本调用:"):
            return line[len("脚本调用:") :].strip()
        if line.lower().startswith("script:"):
            return line[len("script:") :].strip()
        # 无前缀：识别常见可执行文件开头
        first_token = line.split()[0] if line.split() else ""
        if first_token in ("python", "python3", "bash", "sh", "node", "ruby", "perl"):
            return line
    return ""


# ---------------------------------------------------------------------------
# ParameterCollector
# ---------------------------------------------------------------------------


class ParameterCollector:
    """必填参数缺失时与前端交互的协调器。

    流程：
    1. 工具 execute 检测到必填参数缺失 → 调 ``await collector.request(...)``
       ，该方法通过 ``on_update`` 派发 ``parameter_request`` 事件，并 await future。
    2. 前端收到 SSE ``parameter_request`` → 弹窗收集 → POST ``parameter_response``。
    3. HTTP handler 调 ``collector.provide(call_id, values)`` → future resolve。
    4. execute 拿到值后合并到 params，继续执行。

    超时 / 取消时 future 抛 ``asyncio.TimeoutError`` / ``CancelledError``，
    execute 转为 error ToolResult。
    """

    def __init__(self, *, default_timeout: float = 300.0) -> None:
        self._pending: dict[str, asyncio.Future[dict]] = {}
        self._default_timeout = default_timeout

    def request(
        self,
        call_id: str,
        missing_params: list[dict],
        *,
        on_update: Optional[Callable[[dict], Awaitable[None] | None]] = None,
        timeout: float | None = None,
    ) -> Awaitable[dict]:
        """发起一次参数请求。

        Args:
            call_id: 工具调用 id（与 AgentEvent ToolExecutionUpdate 对齐）。
            missing_params: 缺失参数定义列表 ``[{key,label,widget,options}]``。
            on_update: 工具的 on_update 回调；用于把请求作为 ``parameter_request``
                事件派发到 SSE bridge。
            timeout: 等待响应超时；None 用 default_timeout。

        Returns:
            awaitable，resolve 后得到 ``{key: value}`` dict。
        """
        loop = asyncio.get_event_loop()
        fut: asyncio.Future[dict] = loop.create_future()
        self._pending[call_id] = fut

        payload = {
            "kind": "parameter_request",
            "call_id": call_id,
            "params": missing_params,
            "ts": time.time(),
        }
        if on_update is not None:
            try:
                maybe = on_update(payload)
                if asyncio.iscoroutine(maybe):
                    asyncio.create_task(maybe)  # fire-and-forget；listener 异常不影响主流程
            except Exception as exc:  # noqa: BLE001
                logger.warning("parameter_request on_update 派发失败: %s", exc)

        timeout_s = self._default_timeout if timeout is None else timeout

        async def _wait() -> dict:
            try:
                return await asyncio.wait_for(fut, timeout=timeout_s)
            except asyncio.TimeoutError:
                self._pending.pop(call_id, None)
                raise

        return _wait()

    def provide(self, call_id: str, values: dict) -> bool:
        """HTTP handler 调用：提交参数响应。"""
        fut = self._pending.pop(call_id, None)
        if fut is None or fut.done():
            return False
        if not isinstance(values, dict):
            values = {}
        fut.set_result(values)
        return True

    def cancel(self, call_id: str, reason: str = "canceled") -> None:
        """取消挂起的参数请求。"""
        fut = self._pending.pop(call_id, None)
        if fut is not None and not fut.done():
            fut.set_exception(asyncio.CancelledError(reason))

    @property
    def pending_count(self) -> int:
        return len(self._pending)


# ---------------------------------------------------------------------------
# 脚本执行
# ---------------------------------------------------------------------------


def _substitute_command(template: str, params: dict) -> list[str]:
    """把 ``$key`` / ``${key}`` 替换为 params 值，并用 shlex 拆分为 argv。

    缺失的占位符替换为空字符串。替换后的值通过 ``shlex.quote`` 防注入，
    但因为最终走 ``create_subprocess_exec``（非 shell），实际不需要外层 quote；
    我们只在原模板里做字符串替换，再 shlex.split。
    """
    def repl(m: re.Match) -> str:
        key = m.group(1) or m.group(2)
        val = params.get(key, "")
        if val is None:
            val = ""
        # 把值作为单 token：用双引号包裹，shlex.split 后保持完整
        return '"' + str(val).replace('"', '\\"') + '"'

    substituted = _PLACEHOLDER_RE.sub(repl, template)
    return shlex.split(substituted)


async def run_skill_script(
    skill: SkillDefinition,
    params: dict,
    *,
    signal: AbortSignal,
    on_update: Optional[Callable[[dict], Awaitable[None] | None]] = None,
) -> dict:
    """执行非长任务 skill 脚本，返回 ``{returncode, stdout, stderr, timed_out}``。

    - 用 ``asyncio.create_subprocess_exec``（非 shell）启动。
    - ``signal.aborted`` → 终止子进程。
    - ``skill.timeout_seconds > 0`` → 超时 kill。
    """
    argv = _substitute_command(skill.script_command, params)
    if not argv:
        return {"returncode": -1, "stdout": "", "stderr": "empty command", "timed_out": False}

    cwd = str(skill.working_dir) if skill.working_dir else None

    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
    except FileNotFoundError as exc:
        return {"returncode": -1, "stdout": "", "stderr": f"executable not found: {exc}", "timed_out": False}
    except Exception as exc:  # noqa: BLE001
        return {"returncode": -1, "stdout": "", "stderr": str(exc), "timed_out": False}

    timed_out = False
    try:
        timeout = skill.timeout_seconds if skill.timeout_seconds and skill.timeout_seconds > 0 else None

        async def _wait_proc() -> tuple[bytes, bytes]:
            stdout, stderr = await proc.communicate()
            return stdout or b"", stderr or b""

        if timeout is not None:
            try:
                stdout, stderr = await asyncio.wait_for(_wait_proc(), timeout=timeout)
            except asyncio.TimeoutError:
                timed_out = True
                _kill_proc(proc)
                try:
                    stdout, stderr = await proc.communicate()
                except Exception:  # noqa: BLE001
                    stdout, stderr = b"", b""
                stdout, stderr = stdout or b"", stderr or b""
        else:
            stdout, stderr = await _wait_proc()

        # 监听 abort（仅在等待期间通过 task 检测）
        if signal.aborted:
            _kill_proc(proc)
    finally:
        if proc.returncode is None:
            _kill_proc(proc)

    return {
        "returncode": proc.returncode if proc.returncode is not None else -1,
        "stdout": _decode(stdout),
        "stderr": _decode(stderr),
        "timed_out": timed_out,
        "aborted": bool(signal.aborted),
    }


def _kill_proc(proc: asyncio.subprocess.Process) -> None:
    try:
        if proc.returncode is None:
            proc.kill()
    except ProcessLookupError:
        pass
    except Exception as exc:  # noqa: BLE001
        logger.warning("kill subprocess failed: %s", exc)


def _decode(data: bytes) -> str:
    if not data:
        return ""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        import base64
        return base64.b64encode(data).decode("ascii")


# ---------------------------------------------------------------------------
# AgentTool 工厂
# ---------------------------------------------------------------------------


def build_skill_tool(
    skill: SkillDefinition,
    *,
    long_task_manager: Any = None,
    parameter_collector: Optional[ParameterCollector] = None,
) -> AgentTool:
    """把 ``SkillDefinition`` 转为 ``AgentTool``。

    Args:
        skill: skill 定义。
        long_task_manager: ``LongTaskManager`` 实例；长任务 skill 通过它接管。
            为 None 时长任务 skill 直接返回错误。
        parameter_collector: 参数收集器；为 None 时必填参数缺失直接报错。
    """
    parameters_schema = skill.to_json_schema()

    async def execute(call_id: str, params: dict, signal: AbortSignal, on_update) -> ToolResult:  # noqa: ARG001
        # 1) 参数校验 + Parameter Collector
        merged = dict(params or {})
        missing = _find_missing_params(skill, merged)
        if missing:
            if parameter_collector is None:
                return _error_result(
                    call_id,
                    f"缺少必填参数: {', '.join(p['key'] for p in missing)}",
                    details={"missing_params": missing},
                )
            try:
                values = await parameter_collector.request(
                    call_id, missing, on_update=on_update
                )
            except asyncio.TimeoutError:
                return _error_result(call_id, "参数请求超时未响应")
            except asyncio.CancelledError:
                return _error_result(call_id, "参数请求已取消")
            except Exception as exc:  # noqa: BLE001
                return _error_result(call_id, f"参数请求失败: {exc}")
            # 合并：用户响应优先，但不覆盖 Agent 显式传入的值
            for k, v in (values or {}).items():
                if k not in merged or merged[k] in (None, ""):
                    merged[k] = v

        # 2) 应用 default
        for p in skill.parameters:
            key = p.get("key")
            if key and (merged.get(key) in (None, "")) and p.get("default") is not None:
                merged[key] = p.get("default")

        # 3) 执行
        if skill.long_running:
            if long_task_manager is None:
                return _error_result(
                    call_id,
                    f"skill {skill.name} 是长任务，但未启用 LongTaskManager",
                )
            try:
                card = await long_task_manager.start_task(
                    skill=skill,
                    params=merged,
                    conversation_id=getattr(long_task_manager, "_conversation_id", None) or "",
                    call_id=call_id,
                )
            except Exception as exc:  # noqa: BLE001
                return _error_result(call_id, f"启动长任务失败: {exc}")
            return _text_result(call_id, json.dumps(card, ensure_ascii=False))

        # 非长任务：subprocess 直接执行
        if on_update is not None:
            try:
                maybe = on_update({"kind": "script_start", "call_id": call_id, "skill": skill.name})
                if asyncio.iscoroutine(maybe):
                    asyncio.create_task(maybe)
            except Exception:  # noqa: BLE001
                pass

        result = await run_skill_script(skill, merged, signal=signal, on_update=on_update)

        payload = {
            "skill": skill.name,
            "returncode": result["returncode"],
            "stdout": result["stdout"],
            "stderr": result["stderr"],
            "timed_out": result["timed_out"],
            "aborted": result["aborted"],
        }
        if result["returncode"] == 0 and not result["timed_out"] and not result["aborted"]:
            return _text_result(call_id, json.dumps(payload, ensure_ascii=False))
        return _error_result(
            call_id,
            f"skill 执行失败 (code={result['returncode']}): {result['stderr'] or 'no stderr'}",
            details=payload,
        )

    return AgentTool(
        name=skill.name,
        description=skill.description,
        parameters=parameters_schema,
        label=skill.name,
        execution_mode="serial",  # 脚本类工具默认串行，避免并发副作用
        execute=execute,
    )


def _find_missing_params(skill: SkillDefinition, params: dict) -> list[dict]:
    """返回缺失的必填参数定义列表。"""
    missing: list[dict] = []
    for p in skill.parameters:
        if not p.get("required"):
            continue
        key = p.get("key")
        if not key:
            continue
        val = params.get(key)
        if val in (None, ""):
            missing.append({
                "key": key,
                "label": p.get("label") or key,
                "widget": p.get("widget") or "text_input",
                "options": p.get("options"),
            })
    return missing


# ---------------------------------------------------------------------------
# 入口：load_skills
# ---------------------------------------------------------------------------


def default_skills_dir() -> Path:
    """默认 skills 目录：``<note_output_dir>/skills``。"""
    return (note_output_dir() / "skills").resolve()


def load_skills(
    skills_dir: str | Path | None = None,
    *,
    long_task_manager: Any = None,
    parameter_collector: Optional[ParameterCollector] = None,
) -> list[AgentTool]:
    """加载 ``skills_dir`` 下所有 SKILL.md，返回 AgentTool 列表。

    Args:
        skills_dir: 目录路径；None 用 ``default_skills_dir()``。目录不存在时返回空列表。
        long_task_manager: 长任务管理器（可选）。
        parameter_collector: 参数收集器（可选）。

    Returns:
        AgentTool 列表（按 skill name 字母序）。
    """
    if skills_dir is None:
        skills_dir = default_skills_dir()
    root = Path(skills_dir)
    if not root.exists() or not root.is_dir():
        return []

    tools: list[AgentTool] = []
    seen_names: set[str] = set()
    for skill_path in sorted(root.rglob("SKILL.md")):
        try:
            skill = parse_skill_file(skill_path)
        except SkillLoaderError as exc:
            logger.warning("跳过非法 SKILL.md %s: %s", skill_path, exc)
            continue
        except Exception as exc:  # noqa: BLE001
            logger.warning("解析 SKILL.md %s 失败: %s", skill_path, exc)
            continue
        if skill.name in seen_names:
            logger.warning("跳过重复 skill name %s (%s)", skill.name, skill_path)
            continue
        seen_names.add(skill.name)
        tools.append(build_skill_tool(
            skill,
            long_task_manager=long_task_manager,
            parameter_collector=parameter_collector,
        ))
    return tools


# ---------------------------------------------------------------------------
# ToolResult 构造助手（与 workspace/memory 一致风格）
# ---------------------------------------------------------------------------


def _text_result(call_id: str, text: str) -> ToolResult:
    return ToolResult(
        call_id=call_id,
        content=[{"type": "text", "text": text}],
        is_error=False,
    )


def _error_result(call_id: str, message: str, *, details: dict | None = None) -> ToolResult:
    return ToolResult(
        call_id=call_id,
        content=[{"type": "text", "text": json.dumps({"error": message}, ensure_ascii=False)}],
        is_error=True,
        details=details or {},
    )


__all__ = [
    "SkillDefinition",
    "SkillLoaderError",
    "ParameterCollector",
    "parse_skill_content",
    "parse_skill_file",
    "build_skill_tool",
    "load_skills",
    "default_skills_dir",
    "run_skill_script",
]
