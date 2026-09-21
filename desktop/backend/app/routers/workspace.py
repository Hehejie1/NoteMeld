from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.engine import get_db
from app.db.models.workspace import Workspace
from app.utils.response import ResponseWrapper as R

router = APIRouter(prefix="/workspaces", tags=["workspace"])
MAX_WRITE_BYTES = 4 * 1024 * 1024


class WorkspaceCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    kind: str = Field(default="local_folder", pattern="^(local_folder|ssh_remote|wsl)$")
    root_ref: str = Field(min_length=1, max_length=4096)


class WorkspaceFileWrite(BaseModel):
    content: str


class WorkspaceCommand(BaseModel):
    command: str = Field(min_length=1, max_length=4000)
    timeout_seconds: int = Field(default=15, ge=1, le=60)


class WorkspaceSearch(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    path: str = Field(default="", max_length=2000)
    max_results: int = Field(default=100, ge=1, le=500)


def _local_root(item: Workspace) -> Path:
    if item.kind != "local_folder":
        raise HTTPException(409, "该工作区尚未连接 transport")
    root = Path(item.root_ref).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise HTTPException(409, "工作区目录不可用")
    return root


def _target(item: Workspace, relative: str, *, allow_empty: bool = False) -> Path:
    if not relative and not allow_empty:
        raise HTTPException(400, "path 不能为空")
    if relative.startswith(("/", "\\")) or ".." in Path(relative).parts:
        raise HTTPException(400, "禁止越界路径")
    root = _local_root(item)
    target = (root / relative).resolve()
    if target != root and not str(target).startswith(str(root) + os.sep):
        raise HTTPException(400, "禁止越界路径")
    return target


def _view(item: Workspace) -> dict:
    return {"id": item.id, "display_name": item.display_name, "kind": item.kind, "status": item.status,
            "root_ref": item.root_ref, "capabilities": json.loads(item.capabilities_json)}


def _relative_path(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix() or "."


def _run_git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=10, check=False,
    )


@router.get("")
def list_workspaces(db: Session = Depends(get_db)):
    return R.success([_view(item) for item in db.query(Workspace).order_by(Workspace.created_at).all()])


@router.post("")
def create_workspace(payload: WorkspaceCreate, db: Session = Depends(get_db)):
    if payload.kind == "local_folder":
        root = Path(payload.root_ref).expanduser().resolve()
        if not root.exists() or not root.is_dir():
            raise HTTPException(400, "请选择存在的本地文件夹")
        root_ref = str(root)
    else:
        root_ref = payload.root_ref.strip()
    item = Workspace(id=f"ws-{uuid.uuid4().hex}", display_name=payload.display_name.strip(), kind=payload.kind, root_ref=root_ref)
    db.add(item); db.commit(); db.refresh(item)
    return R.success(_view(item))


@router.delete("/{workspace_id}")
def delete_workspace(workspace_id: str, db: Session = Depends(get_db)):
    item = db.get(Workspace, workspace_id)
    if not item: raise HTTPException(404, "工作区不存在")
    db.delete(item); db.commit()
    return R.success({"id": workspace_id, "deleted": True})


@router.get("/{workspace_id}/files")
def list_files(workspace_id: str, path: str = "", db: Session = Depends(get_db)):
    item = db.get(Workspace, workspace_id)
    if not item: raise HTTPException(404, "工作区不存在")
    target = _target(item, path, allow_empty=True)
    if not target.exists(): return R.success({"path": path, "entries": []})
    if not target.is_dir(): raise HTTPException(400, "不是目录")
    entries = [{"name": child.name, "type": "directory" if child.is_dir() else "file", "size": child.stat().st_size if child.is_file() else 0} for child in sorted(target.iterdir())]
    return R.success({"path": path, "entries": entries})


@router.get("/{workspace_id}/file")
def read_file(workspace_id: str, path: str, db: Session = Depends(get_db)):
    item = db.get(Workspace, workspace_id); target = _target(item, path) if item else None
    if not item: raise HTTPException(404, "工作区不存在")
    if not target.is_file(): raise HTTPException(404, "文件不存在")
    raw = target.read_bytes()
    if len(raw) > MAX_WRITE_BYTES: raise HTTPException(413, "文件过大")
    return R.success({"path": path, "content": raw.decode("utf-8"), "encoding": "utf-8", "size": len(raw)})


@router.put("/{workspace_id}/file")
def write_file(workspace_id: str, path: str, payload: WorkspaceFileWrite, db: Session = Depends(get_db)):
    item = db.get(Workspace, workspace_id)
    if not item: raise HTTPException(404, "工作区不存在")
    if len(payload.content.encode()) > MAX_WRITE_BYTES: raise HTTPException(413, "文件过大")
    target = _target(item, path); target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".notemeld-", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle: handle.write(payload.content)
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)
    return R.success({"path": path, "size": target.stat().st_size, "written": True})


@router.delete("/{workspace_id}/file")
def delete_file(workspace_id: str, path: str, db: Session = Depends(get_db)):
    item = db.get(Workspace, workspace_id)
    if not item: raise HTTPException(404, "工作区不存在")
    target = _target(item, path)
    if not target.is_file(): raise HTTPException(404, "文件不存在")
    target.unlink()
    return R.success({"path": path, "deleted": True})


@router.post("/{workspace_id}/terminal")
def execute_terminal(workspace_id: str, payload: WorkspaceCommand, db: Session = Depends(get_db)):
    item = db.get(Workspace, workspace_id)
    if not item:
        raise HTTPException(404, "工作区不存在")
    root = _local_root(item)
    started = time.monotonic()
    try:
        completed = subprocess.run(
            ["/bin/zsh", "-lc", payload.command], cwd=root, capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=payload.timeout_seconds,
            env={**os.environ, "PWD": str(root)}, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return R.success({"command": payload.command, "cwd": str(root), "stdout": exc.stdout or "",
                          "stderr": (exc.stderr or "") + "\n命令超时，已终止。", "exit_code": 124,
                          "duration_ms": round((time.monotonic() - started) * 1000)})
    return R.success({"command": payload.command, "cwd": str(root), "stdout": completed.stdout,
                      "stderr": completed.stderr, "exit_code": completed.returncode,
                      "duration_ms": round((time.monotonic() - started) * 1000)})


@router.post("/{workspace_id}/search")
def search_workspace(workspace_id: str, payload: WorkspaceSearch, db: Session = Depends(get_db)):
    item = db.get(Workspace, workspace_id)
    if not item:
        raise HTTPException(404, "工作区不存在")
    root = _local_root(item)
    base = _target(item, payload.path, allow_empty=True)
    if not base.is_dir():
        raise HTTPException(400, "搜索目录不存在")
    query = payload.query.casefold()
    ignored = {".git", ".venv", "node_modules", "dist", "build", "target", "__pycache__"}
    results: list[dict] = []
    for current, directories, files in os.walk(base):
        directories[:] = [name for name in directories if name not in ignored and not name.startswith(".")]
        for name in files:
            if len(results) >= payload.max_results:
                break
            candidate = Path(current) / name
            relative = _relative_path(root, candidate)
            if query in name.casefold():
                results.append({"path": relative, "line": 0, "preview": name})
                continue
            try:
                if candidate.stat().st_size > 1024 * 1024:
                    continue
                text = candidate.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for line_number, line in enumerate(text.splitlines(), 1):
                if query in line.casefold():
                    results.append({"path": relative, "line": line_number, "preview": line.strip()[:240]})
                    break
    return R.success({"query": payload.query, "results": results, "truncated": len(results) >= payload.max_results})


@router.get("/{workspace_id}/git")
def git_status(workspace_id: str, db: Session = Depends(get_db)):
    item = db.get(Workspace, workspace_id)
    if not item:
        raise HTTPException(404, "工作区不存在")
    root = _local_root(item)
    check = _run_git(root, "rev-parse", "--is-inside-work-tree")
    if check.returncode != 0:
        return R.success({"is_repository": False, "branch": "", "changes": [], "message": "当前工作区不是 Git 仓库。"})
    branch = _run_git(root, "branch", "--show-current").stdout.strip()
    status = _run_git(root, "status", "--short").stdout.splitlines()
    changes = [{"index": line[:1], "worktree": line[1:2], "path": line[3:]} for line in status if len(line) >= 4]
    return R.success({"is_repository": True, "branch": branch or "HEAD detached", "changes": changes,
                      "ahead_behind": _run_git(root, "rev-list", "--left-right", "--count", "HEAD...@{upstream}").stdout.strip()})
