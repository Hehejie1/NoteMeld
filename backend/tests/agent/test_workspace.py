"""P3-T1: workspace 单测 — 路径穿越校验 + list/read/write + AgentTool。

验收映射：
- §验收 5 工作空间路径穿越 → 403（WorkspaceError）
- create_workspace_tools 三个工具仅作用于 cid 工作空间
"""
from __future__ import annotations

import asyncio
import json
import os
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.agent.core.signal import AbortSignal
from app.agent.workspace import (
    ALLOWED_TOP_DIRS,
    WorkspaceError,
    create_workspace_tools,
    ensure_workspace,
    list_directory,
    read_file,
    resolve_safe_path,
    workspaces_root,
    workspace_root,
    write_file,
)


class _BaseWithTmpDir(unittest.TestCase):
    """重定向 NOTE_OUTPUT_DIR 到临时目录。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["NOTE_OUTPUT_DIR"] = str(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()
        os.environ.pop("NOTE_OUTPUT_DIR", None)

    @staticmethod
    def _run(coro):
        return asyncio.run(coro)


class WorkspaceRootTest(_BaseWithTmpDir):
    def test_valid_cid_resolves_under_workspaces_root(self) -> None:
        root = workspace_root("conv_123")
        self.assertTrue(str(root).startswith(str(workspaces_root()) + os.sep))
        self.assertEqual(root.name, "conv_123")

    def test_empty_cid_raises(self) -> None:
        with self.assertRaises(WorkspaceError):
            workspace_root("")

    def test_non_safe_cid_raises(self) -> None:
        # 含路径分隔符 / .. → 视为非法 cid
        for bad in ("../etc", "a/b", "a b", "conv.x", "带空格的"):
            with self.assertRaises(WorkspaceError, msg=f"cid={bad!r} 应被拒"):
                workspace_root(bad)


class ResolveSafePathTest(_BaseWithTmpDir):
    def test_valid_relative_path_under_assets(self) -> None:
        ensure_workspace("c1")
        p = resolve_safe_path("c1", "assets/foo.txt")
        self.assertTrue(str(p).startswith(str(workspace_root("c1")) + os.sep))
        self.assertEqual(p.name, "foo.txt")

    def test_dotdot_segment_rejected(self) -> None:
        with self.assertRaises(WorkspaceError):
            resolve_safe_path("c1", "../etc/passwd")
        with self.assertRaises(WorkspaceError):
            resolve_safe_path("c1", "assets/../../etc")

    def test_absolute_path_rejected(self) -> None:
        with self.assertRaises(WorkspaceError):
            resolve_safe_path("c1", "/etc/passwd")

    def test_windows_drive_rejected(self) -> None:
        with self.assertRaises(WorkspaceError):
            resolve_safe_path("c1", "C:/evil")

    def test_empty_path_rejected(self) -> None:
        with self.assertRaises(WorkspaceError):
            resolve_safe_path("c1", "")
        with self.assertRaises(WorkspaceError):
            resolve_safe_path("c1", "   ")

    def test_create_parents_flag(self) -> None:
        p = resolve_safe_path("c2", "scratch/nested/deep.txt", create_parents=True)
        self.assertTrue(p.parent.exists())


class EnsureWorkspaceTest(_BaseWithTmpDir):
    def test_ensure_creates_all_allowed_subdirs(self) -> None:
        root = ensure_workspace("c3")
        self.assertTrue(root.exists())
        for sub in ALLOWED_TOP_DIRS:
            self.assertTrue((root / sub).is_dir(), f"缺少子目录 {sub}")


class ListReadWriteTest(_BaseWithTmpDir):
    def test_write_then_read_utf8_roundtrip(self) -> None:
        ensure_workspace("c4")
        write_file("c4", "assets/note.md", "# 标题\n中文内容")
        result = read_file("c4", "assets/note.md")
        self.assertEqual(result["encoding"], "utf-8")
        self.assertIn("# 标题", result["content"])
        self.assertFalse(result["truncated"])

    def test_list_directory_returns_entries(self) -> None:
        ensure_workspace("c5")
        write_file("c5", "assets/a.txt", "a")
        write_file("c5", "assets/b.txt", "bb")
        listing = list_directory("c5", "assets")
        names = [e["name"] for e in listing["entries"]]
        self.assertIn("a.txt", names)
        self.assertIn("b.txt", names)
        # 每条 entry 含 type/size
        for e in listing["entries"]:
            self.assertIn("type", e)
            self.assertIn("size", e)

    def test_list_nonexistent_returns_empty(self) -> None:
        result = list_directory("c6", "assets")
        self.assertEqual(result["entries"], [])

    def test_read_nonexistent_raises_filenotfound(self) -> None:
        ensure_workspace("c7")
        with self.assertRaises(FileNotFoundError):
            read_file("c7", "assets/nope.txt")

    def test_write_traversal_raises(self) -> None:
        with self.assertRaises(WorkspaceError):
            write_file("c8", "../escape.txt", "x")

    def test_write_base64_encoding(self) -> None:
        ensure_workspace("c9")
        import base64
        # 用真非 utf-8 字节，确保读取时回退 base64
        raw = b"\xff\xfe\x80\xbd binary"
        write_file("c9", "assets/bin.dat", base64.b64encode(raw).decode(), encoding="base64")
        # 读回来是 base64
        result = read_file("c9", "assets/bin.dat")
        self.assertEqual(result["encoding"], "base64")
        self.assertEqual(base64.b64decode(result["content"]), raw)

    def test_read_truncated_flag(self) -> None:
        ensure_workspace("ca")
        # 直接写文件绕过 write_file 的 MAX_WRITE_BYTES 限制，制造超过 MAX_READ_BYTES 的文件
        from app.agent.workspace import MAX_READ_BYTES, resolve_safe_path
        big = "x" * (MAX_READ_BYTES + 100)
        target = resolve_safe_path("ca", "assets/big.txt", create_parents=True)
        target.write_text(big, encoding="utf-8")
        result = read_file("ca", "assets/big.txt")
        self.assertTrue(result["truncated"])
        self.assertEqual(len(result["content"]), MAX_READ_BYTES)


class WorkspaceToolsTest(_BaseWithTmpDir):
    def test_create_workspace_tools_returns_three_named_tools(self) -> None:
        tools = create_workspace_tools("cb")
        names = [t.name for t in tools]
        self.assertEqual(names, ["workspace_list", "workspace_read", "workspace_write"])

    def test_workspace_write_then_list_via_tool(self) -> None:
        ensure_workspace("cc")
        tools = create_workspace_tools("cc")
        write_tool = next(t for t in tools if t.name == "workspace_write")
        list_tool = next(t for t in tools if t.name == "workspace_list")

        wres = self._run(write_tool.execute("c1", {"path": "assets/x.md", "content": "hi"}, AbortSignal(), None))
        self.assertFalse(wres.is_error)

        lres = self._run(list_tool.execute("c2", {"path": "assets"}, AbortSignal(), None))
        self.assertFalse(lres.is_error)
        payload = json.loads(lres.content[0]["text"])
        names = [e["name"] for e in payload["entries"]]
        self.assertIn("x.md", names)

    def test_workspace_tool_traversal_returns_error_result(self) -> None:
        """工具内遇路径穿越应返回 is_error=True（不抛异常，供 Agent 处理）。"""
        tools = create_workspace_tools("cd")
        write_tool = next(t for t in tools if t.name == "workspace_write")
        res = self._run(write_tool.execute(
            "c3", {"path": "../escape.txt", "content": "x"}, AbortSignal(), None
        ))
        self.assertTrue(res.is_error)
        payload = json.loads(res.content[0]["text"])
        self.assertIn("error", payload)

    def test_workspace_read_tool_nonexistent_returns_error_result(self) -> None:
        ensure_workspace("ce")
        tools = create_workspace_tools("ce")
        read_tool = next(t for t in tools if t.name == "workspace_read")
        res = self._run(read_tool.execute("c4", {"path": "assets/nope.txt"}, AbortSignal(), None))
        self.assertTrue(res.is_error)

    def test_tools_scoped_to_different_cids_isolated(self) -> None:
        """cid=A 的工具看不到 cid=B 工作空间的文件。"""
        ensure_workspace("cf_a")
        ensure_workspace("cf_b")
        write_file("cf_a", "assets/secret.txt", "A-only")

        tools_b = create_workspace_tools("cf_b")
        read_b = next(t for t in tools_b if t.name == "workspace_read")
        res = self._run(read_b.execute("c5", {"path": "assets/secret.txt"}, AbortSignal(), None))
        # cf_b 工作空间里没有这个文件 → error
        self.assertTrue(res.is_error)


if __name__ == "__main__":
    unittest.main()
