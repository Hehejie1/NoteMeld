"""Document & file capability layer for NoteMeld Cloud.

设计原则（对应产品需求）：

1. 图片/附件都先落盘到服务器并在 ``files`` 表注册；
2. 传给 LLM 的图片链接是**短期签名链接**（HMAC，带过期时间），
   中转服务器无法在过期后再次获取，避免图片被长期反复拉取；
3. 非图片文件只把「名称 + 描述 + file_id」告诉模型，由模型通过专门的
   工具决定是否读取、解析或检索；
4. 工具职责互不重叠：

   - ``file.list``   : 只列文件（名称/类型/描述），不返回正文；
   - ``file.read``   : 只读取**纯文本/代码**文件原文（含分页）；
   - ``file.parse``  : 只把 **PDF/Word/Excel** 等富格式解析为文本/图片；
   - ``file.search`` : 只在**大文件/文档库**里做关键词 + 片段检索（RAG）。

   read 处理“本来就是文本”的文件；parse 处理“需要转换”的文件；
   search 处理“不知道内容在哪、需要先定位”的场景。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import math
import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .db import CloudDB
from .workspace import Workspace, WorkspaceError

# 临时图片链接有效期（秒）。LLM 中转只需要在生成当次请求时能取到。
DEFAULT_TTL_SECONDS = 600

# 文本读取 / 切片的默认参数。
READ_LIMIT_BYTES = 100_000
CHUNK_TOKENS = 800
CHUNK_OVERLAP = 100
MAX_SEARCH_RESULTS = 8

_TEXT_EXTS = {
    ".txt", ".md", ".markdown", ".csv", ".json", ".log", ".xml", ".yaml", ".yml",
    ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go", ".rs", ".c", ".h",
    ".cpp", ".hpp", ".cs", ".rb", ".php", ".sh", ".sql", ".ini", ".toml", ".env",
}
_DOC_EXTS = {".pdf", ".docx", ".xlsx", ".doc", ".xls", ".pptx", ".ppt"}
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]")


class DocumentError(ValueError):
    """File/parse failure surfaced as a 4xx at the API boundary."""


# --------------------------------------------------------------------------- #
# 分类 / 命名
# --------------------------------------------------------------------------- #
def classify(name: str, mime: str) -> str:
    ext = Path(name).suffix.lower()
    if mime.startswith("image/") or ext in _IMAGE_EXTS:
        return "image"
    if ext in _DOC_EXTS:
        return "document"
    if ext in _TEXT_EXTS:
        return "text"
    return "other"


def safe_segment(name: str) -> str:
    base = Path(name).name or "attachment"
    cleaned = _SAFE_NAME.sub("_", base)
    return cleaned or "attachment"


# --------------------------------------------------------------------------- #
# 临时签名链接（图片）
# --------------------------------------------------------------------------- #
def _sign(secret: str, expires: int, file_id: str) -> str:
    message = f"{file_id}.{expires}".encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def signed_url(*, base_url: str, secret: str, file_id: str, ttl: int = DEFAULT_TTL_SECONDS) -> str:
    expires = int(time.time()) + int(ttl)
    signature = _sign(secret, expires, file_id)
    return f"{base_url.rstrip('/')}/v1/cloud/files/{file_id}?expires={expires}&sig={signature}"


def verify_signed_url(*, secret: str, file_id: str, expires: str, sig: str) -> bool:
    now = int(time.time())
    try:
        exp = int(expires)
    except (TypeError, ValueError):
        return False
    if exp < now:
        return False
    expected = _sign(secret, exp, file_id)
    return hmac.compare_digest(expected, sig)


# --------------------------------------------------------------------------- #
# 文件注册
# --------------------------------------------------------------------------- #
@dataclass
class StoredFile:
    id: str
    name: str
    description: str
    mime: str
    kind: str
    path: str
    size: int
    sha256: str
    workspace_id: str

    def to_catalog(self) -> dict[str, Any]:
        return {
            "file_id": self.id,
            "name": self.name,
            "description": self.description,
            "mime": self.mime,
            "kind": self.kind,
            "size": self.size,
        }


def register_file(
    *,
    db: CloudDB,
    workspace: Workspace,
    user_id: str,
    workspace_id: str,
    name: str,
    content: bytes,
    mime: str,
    description: str = "",
    session_id: str | None = None,
) -> StoredFile:
    """把字节内容存入 workspace 并注册到 files 表，返回 StoredFile。"""
    file_id = str(uuid.uuid4())
    kind = classify(name, mime)
    safe_name = safe_segment(name)
    prefix = "images" if kind == "image" else "files"
    logical_path = f"{prefix}/{file_id[:8]}-{safe_name}"
    workspace.write_bytes(logical_path, content)
    digest = hashlib.sha256(content).hexdigest()
    now = int(time.time())
    with db.connect() as cx:
        cx.execute(
            "INSERT INTO files(id,user_id,session_id,workspace_id,name,description,mime,kind,path,sha256,size,created_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (file_id, user_id, session_id, workspace_id, safe_name, description[:500],
             mime[:128], kind, logical_path, digest, len(content), now),
        )
    return StoredFile(
        id=file_id, name=safe_name, description=description[:500], mime=mime[:128],
        kind=kind, path=logical_path, size=len(content), sha256=digest,
        workspace_id=workspace_id,
    )


def _get_file_row(db: CloudDB, user_id: str, file_id: str) -> dict[str, Any]:
    with db.connect() as cx:
        row = cx.execute(
            "SELECT * FROM files WHERE id=? AND user_id=?", (file_id, user_id)
        ).fetchone()
    if not row:
        raise DocumentError("file not found")
    return row


def list_registered(db: CloudDB, user_id: str) -> list[dict[str, Any]]:
    with db.connect() as cx:
        rows = cx.execute(
            "SELECT * FROM files WHERE user_id=? ORDER BY created_at DESC LIMIT 200",
            (user_id,),
        ).fetchall()
    return [
        {
            "file_id": r["id"],
            "name": r["name"],
            "description": r["description"],
            "mime": r["mime"],
            "kind": r["kind"],
            "size": r["size"],
        }
        for r in rows
    ]


# --------------------------------------------------------------------------- #
# 工具一：read —— 纯文本/代码原文（分页）
# --------------------------------------------------------------------------- #
def read_text_file(
    *, db: CloudDB, workspace: Workspace, user_id: str, file_id: str,
    offset: int = 0, limit: int = READ_LIMIT_BYTES,
) -> dict[str, Any]:
    row = _get_file_row(db, user_id, file_id)
    if row["kind"] not in {"text", "other"} and row["mime"].startswith("image"):
        raise DocumentError("use the signed image link for images; not a text file")
    if row["kind"] == "document" and Path(row["name"]).suffix.lower() in _DOC_EXTS:
        raise DocumentError("this is a formatted document; use file.parse instead of file.read")
    content, truncated = workspace.read_text_bounded(row["path"], max(1, int(limit)))
    if offset:
        content = content[max(0, int(offset)):]
    return {
        "ok": True,
        "file_id": file_id,
        "name": row["name"],
        "content": content,
        "truncated": truncated,
    }


# --------------------------------------------------------------------------- #
# 工具二：parse —— PDF / Word / Excel → 文本/图片
# --------------------------------------------------------------------------- #
def parse_document(
    *, db: CloudDB, workspace: Workspace, user_id: str, file_id: str,
) -> dict[str, Any]:
    row = _get_file_row(db, user_id, file_id)
    name = row["name"]
    ext = Path(name).suffix.lower()
    raw_path = workspace.path(row["path"])
    if not raw_path.is_file():
        raise DocumentError("file is unavailable")

    if ext == ".pdf":
        text, images = _parse_pdf(raw_path)
    elif ext == ".docx":
        text, images = _parse_docx(raw_path)
    elif ext == ".xlsx":
        text, images = _parse_xlsx(raw_path)
    elif ext in {".pptx", ".ppt"}:
        text, images = _parse_pptx(raw_path)
    else:
        label = ext or "unknown"
        raise DocumentError(
            f"unsupported document type '{label}'; file.parse supports pdf/docx/xlsx/pptx"
        )

    # 解析结果同时切片入库，供 file.search 使用。
    chunks = chunk_text(text)
    _replace_chunks(db, file_id, chunks)
    return {
        "ok": True,
        "file_id": file_id,
        "name": name,
        "text": text[:200_000],
        "truncated": len(text) > 200_000,
        "image_count": len(images),
        "chunk_count": len(chunks),
    }


def _parse_pdf(path: Path) -> tuple[str, int]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - dependency installed at deploy
        raise DocumentError("pypdf is not installed") from exc
    reader = PdfReader(str(path))
    parts: list[str] = []
    for index, page in enumerate(reader.pages, start=1):
        page_text = (page.extract_text() or "").strip()
        parts.append(f"[第 {index} 页]\n{page_text}")
    image_count = 0
    for page in reader.pages:
        try:
            image_count += len(getattr(page, "images", []) or [])
        except Exception:  # noqa: BLE001 - 某些 PDF 无图片资源
            continue
    return "\n\n".join(parts), image_count


def _parse_docx(path: Path) -> tuple[str, int]:
    try:
        from docx import Document as DocxDocument
    except ImportError as exc:  # pragma: no cover
        raise DocumentError("python-docx is not installed") from exc
    doc = DocxDocument(str(path))
    lines = [p.text for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        for row in table:
            cells = [cell.text.strip() for cell in row.cells]
            if any(cells):
                lines.append(" | ".join(cells))
    image_count = len(doc.inline_shapes)
    return "\n".join(lines), image_count


def _parse_xlsx(path: Path) -> tuple[str, int]:
    try:
        import openpyxl
    except ImportError as exc:  # pragma: no cover
        raise DocumentError("openpyxl is not installed") from exc
    workbook = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
    parts: list[str] = []
    for sheet in workbook.worksheets:
        rows = [
            " | ".join("" if value is None else str(value) for value in row)
            for row in sheet.iter_rows(values_only=True)
        ]
        rows = [row for row in rows if row.strip(" |")]
        if rows:
            parts.append(f"[工作表] {sheet.title}\n" + "\n".join(rows[:1000]))
    return "\n\n".join(parts), 0


def _parse_pptx(path: Path) -> tuple[str, int]:  # pragma: no cover - optional path
    try:
        from pptx import Presentation
    except ImportError as exc:
        raise DocumentError("python-pptx is not installed") from exc
    prs = Presentation(str(path))
    parts: list[str] = []
    image_count = 0
    for index, slide in enumerate(prs.slides, start=1):
        texts = []
        for shape in slide.shapes:
            if getattr(shape, "has_text_frame", False) and shape.text.strip():
                texts.append(shape.text.strip())
            if shape.shape_type == 13:  # MSO_SHAPE_TYPE.PICTURE
                image_count += 1
        parts.append(f"[幻灯片 {index}]\n" + "\n".join(texts))
    return "\n\n".join(parts), image_count


# --------------------------------------------------------------------------- #
# 工具三：chunk + search —— 大文件切片与检索（本地、无外部嵌入）
# --------------------------------------------------------------------------- #
def chunk_text(text: str, chunk_tokens: int = CHUNK_TOKENS, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """按近似 token（约等于字符/2 对中英文折中）长度切片，带重叠。"""
    if not text:
        return []
    size = max(200, int(chunk_tokens) * 2)
    step = max(50, size - max(0, int(overlap)) * 2)
    chunks: list[str] = []
    start = 0
    total = len(text)
    while start < total:
        piece = text[start:start + size]
        if piece.strip():
            chunks.append(piece)
        if start + size >= total:
            break
        start += step
    return chunks


def _replace_chunks(db: CloudDB, file_id: str, chunks: list[str]) -> None:
    with db.connect() as cx:
        cx.execute("DELETE FROM file_chunks WHERE file_id=?", (file_id,))
        for ordinal, piece in enumerate(chunks):
            cx.execute(
                "INSERT INTO file_chunks(id,file_id,ordinal,content,token_count) VALUES(?,?,?,?,?)",
                (str(uuid.uuid4()), file_id, ordinal, piece, math.ceil(len(piece) / 2)),
            )


def ensure_indexed(*, db: CloudDB, workspace: Workspace, user_id: str, file_id: str) -> int:
    """确保文件已解析并切片（惰性索引），返回 chunk 数。"""
    with db.connect() as cx:
        existing = cx.execute(
            "SELECT COUNT(*) AS n FROM file_chunks WHERE file_id=?", (file_id,)
        ).fetchone()["n"]
    if existing:
        return int(existing)
    # 富文档先解析；纯文本直接切片。
    row = _get_file_row(db, user_id, file_id)
    if row["kind"] == "document":
        result = parse_document(db=db, workspace=workspace, user_id=user_id, file_id=file_id)
        return int(result["chunk_count"])
    content, _ = workspace.read_text_bounded(row["path"], 20_000_000)
    chunks = chunk_text(content)
    _replace_chunks(db, file_id, chunks)
    return len(chunks)


def search_chunks(*, db: CloudDB, user_id: str, query: str, file_id: str | None = None,
                  top_k: int = MAX_SEARCH_RESULTS) -> dict[str, Any]:
    """关键词检索 + 评分（BM25 风格的轻量实现，纯 SQL/内存，无需嵌入模型）。"""
    terms = [t for t in re.findall(r"[\w\u4e00-\u9fff]+", (query or "").lower()) if t]
    if not terms:
        raise DocumentError("empty query")
    with db.connect() as cx:
        if file_id:
            rows = cx.execute(
                "SELECT fc.id, fc.file_id, fc.ordinal, fc.content, f.name AS file_name "
                "FROM file_chunks fc JOIN files f ON f.id=fc.file_id "
                "WHERE fc.file_id=? AND f.user_id=?",
                (file_id, user_id),
            ).fetchall()
        else:
            rows = cx.execute(
                "SELECT fc.id, fc.file_id, fc.ordinal, fc.content, f.name AS file_name "
                "FROM file_chunks fc JOIN files f ON f.id=fc.file_id WHERE f.user_id=?",
                (user_id,),
            ).fetchall()
    scored: list[tuple[float, dict[str, Any]]] = []
    for row in rows:
        haystack = (row["content"] or "").lower()
        score = 0.0
        for term in terms:
            # 子串计数（对中文友好），长内容做长度归一。
            frequency = haystack.count(term.lower())
            if frequency:
                score += frequency * (1.0 / math.sqrt(1 + len(haystack) / 500))
        if score > 0:
            scored.append((score, {
                "file_id": row["file_id"],
                "name": row["file_name"],
                "ordinal": row["ordinal"],
                "score": round(score, 4),
                "snippet": _snippet_around(row["content"], terms),
            }))
    scored.sort(key=lambda item: item[0], reverse=True)
    results = [item[1] for item in scored[: max(1, min(int(top_k), MAX_SEARCH_RESULTS))]]
    return {"ok": True, "query": query, "results": results, "result_count": len(results)}


def _snippet_around(content: str, terms: Iterable[str], width: int = 160) -> str:
    lower = content.lower()
    position = -1
    for term in terms:
        position = lower.find(term.lower())
        if position >= 0:
            break
    if position < 0:
        return content[:width]
    start = max(0, position - width // 2)
    snippet = content[start:start + width]
    return ("…" if start > 0 else "") + snippet + ("…" if start + width < len(content) else "")


# --------------------------------------------------------------------------- #
# 工具元数据（注入给 LLM 的 schema；职责互不重叠）
# --------------------------------------------------------------------------- #
def tool_schemas() -> list[dict[str, Any]]:
    return [
        {
            "name": "file.list",
            "description": (
                "List available files with their name, kind (image/document/text) and description. "
                "Returns no content. Use this first to discover file_id values."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            "risk": "safe",
            "safe": True,
        },
        {
            "name": "file.read",
            "description": (
                "Read the raw content of a PLAIN-TEXT or code file by file_id (supports offset/limit). "
                "Do NOT use for PDF/Word/Excel — use file.parse for those."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_id": {"type": "string"},
                    "offset": {"type": "integer", "minimum": 0},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 100000},
                },
                "required": ["file_id"],
                "additionalProperties": False,
            },
            "risk": "safe",
            "safe": True,
        },
        {
            "description": (
                "Parse a FORMATTED document (PDF / Word .docx / Excel .xlsx / PowerPoint) into text and "
                "image count, and index it. Use this — not file.read — for office/PDF files."
            ),
            "name": "file.parse",
            "parameters": {
                "type": "object",
                "properties": {"file_id": {"type": "string"}},
                "required": ["file_id"],
                "additionalProperties": False,
            },
            "risk": "safe",
            "safe": True,
        },
        {
            "name": "file.search",
            "description": (
                "Search within large files or the document library for passages matching a query and "
                "return ranked snippets with file_id and position. Use when you do not know where the "
                "answer is or the file is too large to read fully."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "file_id": {"type": "string"},
                    "top_k": {"type": "integer", "minimum": 1, "maximum": 8},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
            "risk": "safe",
            "safe": True,
        },
    ]


def decode_data_url(data_url: str) -> tuple[bytes, str]:
    """Decode a browser data URL into (bytes, mime)."""
    match = re.match(r"data:([^;,]*)(;base64)?,(.*)", data_url, re.DOTALL)
    if not match:
        raise DocumentError("invalid data url")
    mime, is_b64, payload = match.groups()
    if is_b64:
        raw = base64.b64decode(payload)
    else:
        raw = __import__("urllib.parse", fromlist=["unquote"]).unquote(payload).encode()
    return raw, (mime or "application/octet-stream")


# --------------------------------------------------------------------------- #
# 系统提示词
# --------------------------------------------------------------------------- #
def system_prompt() -> str:
    """Cloud Agent 系统提示词：约定角色与工具选择策略（工具职责不重叠）。"""
    return (
        "你是 NoteMeld Cloud 中运行的智能 Agent，能在云端持久工作，"
        "并可使用受控工具读写、解析和检索用户 workspace 中的文件。\n\n"
        "工作原则：\n"
        "1. 不要凭空猜测文件内容；需要文件信息时，按下列分工选择工具，不要重复调用功能相同的工具：\n"
        "   • file.list：列出可用文件（名称、类型、描述），用于先发现 file_id；它不返回正文。\n"
        "   • file.read：只用于【本来就是文本/代码】的文件（txt/md/json/代码等），可分页。\n"
        "   • file.parse：只用于【需要转换】的富格式文档（PDF、Word .docx、Excel .xlsx、PPT）。"
        "不要用 file.read 去读这些文件。\n"
        "   • file.search：当你【不知道答案在哪个片段】或【文件太大无法全读】时，"
        "用它按查询检索相关片段；不要对小文件先 search 再 read，直接 read 即可。\n"
        "2. 图片通过消息中附带的临时链接查看；该链接短期有效，需要时当次获取，不要假设之后仍可访问。\n"
        "3. 工具返回 truncated=true 表示内容被截断，需要时用 offset/limit 或 file.search 继续读取后续部分。\n"
        "4. 写入（workspace.write）或删除（workspace.delete）属于高风险操作，"
        "系统会要求用户显式批准；不要试图绕过审批。\n"
        "5. 回答使用与用户相同的语言，结论先行、简洁准确；引用文件内容时注明来源文件名。"
    )
