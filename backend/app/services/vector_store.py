import json
import os
import re
from typing import Optional

import chromadb
from chromadb.config import Settings

from app.utils.logger import get_logger
from app.utils.storage_paths import note_output_dir, vector_store_dir

logger = get_logger(__name__)

NOTE_OUTPUT_DIR = str(note_output_dir())
VECTOR_DB_DIR = str(vector_store_dir())
WIKI_TERM_COLLECTION = "wiki_terms"


def _chunk_markdown(markdown: str) -> list[dict]:
    """按 H2/H3 标题拆分 markdown 为语义块。"""
    sections = re.split(r'(?=^#{2,3}\s)', markdown, flags=re.MULTILINE)
    chunks = []
    for section in sections:
        section = section.strip()
        if not section or len(section) < 30:
            continue
        heading_match = re.match(r'^(#{2,3})\s+(.+)', section)
        title = heading_match.group(2).strip() if heading_match else "intro"
        chunks.append({
            "text": section,
            "metadata": {"source_type": "markdown", "section_title": title},
        })
    return chunks


def _chunk_transcript(segments: list[dict], window_size: int = 15, overlap: int = 3) -> list[dict]:
    """将转录 segments 按滑动窗口分组。"""
    if not segments:
        return []
    chunks = []
    step = max(window_size - overlap, 1)
    for i in range(0, len(segments), step):
        window = segments[i:i + window_size]
        if not window:
            break
        text = "\n".join(
            f"[{seg.get('start', 0):.0f}s] {seg.get('text', '')}" for seg in window
        )
        chunks.append({
            "text": text,
            "metadata": {
                "source_type": "transcript",
                "start_time": window[0].get("start", 0),
                "end_time": window[-1].get("end", 0),
            },
        })
    return chunks


def _build_meta_chunk(audio_meta: dict) -> list[dict]:
    """将视频元信息（标题、作者、描述、标签等）构建为可检索的 chunk。"""
    if not audio_meta:
        return []

    raw = audio_meta.get("raw_info", {}) or {}
    parts = []

    title = audio_meta.get("title") or raw.get("title", "")
    if title:
        parts.append(f"视频标题：{title}")

    uploader = raw.get("uploader", "")
    if uploader:
        parts.append(f"视频作者/UP主：{uploader}")

    desc = raw.get("description", "")
    if desc:
        parts.append(f"视频简介：{desc[:500]}")

    tags = raw.get("tags", [])
    if tags and isinstance(tags, list):
        parts.append(f"标签：{', '.join(str(t) for t in tags[:20])}")

    duration = audio_meta.get("duration", 0)
    if duration:
        m, s = divmod(int(duration), 60)
        parts.append(f"视频时长：{m}分{s}秒")

    platform = audio_meta.get("platform", "")
    if platform:
        parts.append(f"平台：{platform}")

    url = raw.get("webpage_url", "")
    if url:
        parts.append(f"链接：{url}")

    if not parts:
        return []

    return [{
        "text": "\n".join(parts),
        "metadata": {"source_type": "meta"},
    }]


def _normalize_vector_metadata(metadata: dict) -> dict:
    normalized = {}
    for key, value in (metadata or {}).items():
        if isinstance(value, list):
            normalized[key] = ",".join(str(item) for item in value)
        elif value is None:
            normalized[key] = ""
        else:
            normalized[key] = value
    return normalized


def _restore_vector_metadata(metadata: dict) -> dict:
    restored = dict(metadata or {})
    for key in ("aliases", "matched_aliases", "related", "semantic_related"):
        value = restored.get(key)
        if isinstance(value, str):
            restored[key] = [item.strip() for item in value.split(",") if item.strip()]
    return restored


def _build_wiki_term_document(
    *,
    term_type: str,
    name: str,
    aliases: list[str],
    description: str,
) -> str:
    parts = [
        f"type: {term_type}",
        f"name: {name}",
    ]
    if aliases:
        parts.append(f"aliases: {', '.join(aliases)}")
    if description:
        parts.append(f"description: {description}")
    return "\n".join(parts)


def _merge_where_clauses(clauses: list[dict]) -> Optional[dict]:
    active_clauses = [clause for clause in clauses if clause]
    if not active_clauses:
        return None
    if len(active_clauses) == 1:
        return active_clauses[0]
    return {"$and": active_clauses}


class VectorStoreManager:
    """基于 ChromaDB 的笔记向量存储管理器。"""

    def __init__(self):
        os.makedirs(VECTOR_DB_DIR, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=VECTOR_DB_DIR,
            settings=Settings(anonymized_telemetry=False),
        )

    def _collection_name(self, task_id: str) -> str:
        """ChromaDB collection 名称：直接使用 task_id（UUID 格式合法）。"""
        return task_id

    def _wiki_term_collection(self):
        return self._client.get_or_create_collection(
            name=WIKI_TERM_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )

    def index_task(self, task_id: str) -> None:
        """读取笔记结果并建立向量索引。"""
        result_path = os.path.join(NOTE_OUTPUT_DIR, f"{task_id}.json")
        if not os.path.exists(result_path):
            logger.warning(f"笔记文件不存在，跳过索引: {result_path}")
            return

        with open(result_path, "r", encoding="utf-8") as f:
            note_data = json.load(f)

        markdown = note_data.get("markdown", "")
        transcript = note_data.get("transcript", {})
        segments = transcript.get("segments", [])

        audio_meta = note_data.get("audio_meta", {})

        meta_chunks = _build_meta_chunk(audio_meta)
        md_chunks = _chunk_markdown(markdown)
        tr_chunks = _chunk_transcript(segments)
        all_chunks = meta_chunks + md_chunks + tr_chunks

        if not all_chunks:
            logger.warning(f"笔记内容为空，跳过索引: {task_id}")
            return

        col_name = self._collection_name(task_id)

        # 删除旧 collection（幂等）
        try:
            self._client.delete_collection(col_name)
        except Exception:
            pass

        collection = self._client.create_collection(
            name=col_name,
            metadata={"hnsw:space": "cosine"},
        )

        documents = [c["text"] for c in all_chunks]
        metadatas = [c["metadata"] for c in all_chunks]
        ids = [f"{task_id}_{i}" for i in range(len(all_chunks))]

        collection.add(documents=documents, metadatas=metadatas, ids=ids)
        logger.info(f"向量索引完成: task_id={task_id}, chunks={len(all_chunks)}")

    def index_chunks(self, task_id: str, chunks: list) -> None:
        """直接索引 ingestion 生成的 KnowledgeChunk。"""
        all_chunks = [chunk for chunk in chunks if getattr(chunk, "content", "").strip()]
        if not all_chunks:
            logger.warning(f"ingestion chunks 为空，跳过索引: {task_id}")
            return

        col_name = self._collection_name(task_id)
        try:
            self._client.delete_collection(col_name)
        except Exception:
            pass

        collection = self._client.create_collection(
            name=col_name,
            metadata={"hnsw:space": "cosine"},
        )

        documents = [chunk.content for chunk in all_chunks]
        metadatas = []
        ids = []
        for chunk in all_chunks:
            metadata = dict(chunk.metadata or {})
            metadata.update({
                "source_type": metadata.get("source_type", "document"),
                "chunk_index": chunk.chunk_index,
                "anchor_ids": chunk.anchor_ids,
                "confidence": chunk.confidence,
                "embedding_status": chunk.embedding_status,
            })
            metadatas.append(_normalize_vector_metadata(metadata))
            ids.append(chunk.id)

        collection.add(documents=documents, metadatas=metadatas, ids=ids)
        logger.info(f"ingestion 向量索引完成: task_id={task_id}, chunks={len(all_chunks)}")

    def _parse_results(self, results: dict) -> list[dict]:
        """将 ChromaDB query 结果转换为 chunk 列表。"""
        chunks = []
        if not results or not results.get("documents") or not results["documents"][0]:
            return chunks
        for i in range(len(results["documents"][0])):
            chunks.append({
                "id": results["ids"][0][i] if results.get("ids") else None,
                "text": results["documents"][0][i],
                "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                "distance": results["distances"][0][i] if results["distances"] else None,
            })
        return chunks

    def upsert_wiki_term(
        self,
        *,
        term_id: str,
        term_type: str,
        name: str,
        aliases: Optional[list[str]] = None,
        description: str = "",
        metadata: Optional[dict] = None,
    ) -> dict:
        normalized_aliases = [alias.strip() for alias in (aliases or []) if str(alias).strip()]
        payload = dict(metadata or {})
        payload.update(
            {
                "record_type": "wiki_term",
                "term_id": term_id,
                "term_type": term_type,
                "name": name,
                "aliases": normalized_aliases,
                "description": description or "",
            }
        )
        document = _build_wiki_term_document(
            term_type=term_type,
            name=name,
            aliases=normalized_aliases,
            description=description or "",
        )
        self._wiki_term_collection().upsert(
            documents=[document],
            metadatas=[_normalize_vector_metadata(payload)],
            ids=[term_id],
        )
        return {
            "term_id": term_id,
            "term_type": term_type,
            "name": name,
            "aliases": normalized_aliases,
            "description": description or "",
            "metadata": _restore_vector_metadata(payload),
        }

    def query_wiki_terms(
        self,
        *,
        term_type: Optional[str],
        query_text: str,
        n_results: int = 5,
        where: Optional[dict] = None,
    ) -> list[dict]:
        try:
            collection = self._client.get_collection(WIKI_TERM_COLLECTION)
        except Exception:
            logger.warning("Wiki term collection 不存在")
            return []

        filters = [{"record_type": "wiki_term"}]
        if term_type:
            filters.append({"term_type": term_type})
        if where:
            filters.append(where)

        results = collection.query(
            query_texts=[query_text],
            n_results=n_results,
            where=_merge_where_clauses(filters),
        )
        items = []
        for item in self._parse_results(results):
            metadata = _restore_vector_metadata(item.get("metadata") or {})
            items.append(
                {
                    "term_id": metadata.get("term_id") or item.get("id"),
                    "term_type": metadata.get("term_type"),
                    "name": metadata.get("name"),
                    "aliases": metadata.get("aliases", []),
                    "description": metadata.get("description", ""),
                    "text": item.get("text", ""),
                    "distance": item.get("distance"),
                    "metadata": metadata,
                }
            )
        return items

    def delete_wiki_term(self, term_id: str) -> None:
        try:
            collection = self._client.get_collection(WIKI_TERM_COLLECTION)
        except Exception:
            return
        collection.delete(ids=[term_id])

    def query(
        self,
        task_id: str,
        query_text: str,
        n_results: int = 6,
        quotas: Optional[dict[str, int]] = None,
    ) -> list[dict]:
        """
        按来源配额检索。默认兼容笔记索引与 ingestion document chunks。
        """
        col_name = self._collection_name(task_id)
        try:
            collection = self._client.get_collection(col_name)
        except Exception:
            logger.warning(f"Collection 不存在: {col_name}")
            return []

        all_chunks = []

        source_quotas = quotas or {"document": 3, "meta": 1, "markdown": 2, "transcript": 3}

        for source_type, quota in source_quotas.items():
            if quota <= 0:
                continue
            try:
                results = collection.query(
                    query_texts=[query_text],
                    n_results=quota,
                    where={"source_type": source_type},
                )
                all_chunks.extend(self._parse_results(results))
            except Exception:
                pass

        return all_chunks

    def delete_index(self, task_id: str) -> None:
        """删除指定任务的向量索引。"""
        col_name = self._collection_name(task_id)
        try:
            self._client.delete_collection(col_name)
            logger.info(f"已删除向量索引: {task_id}")
        except Exception:
            pass

    def is_indexed(self, task_id: str) -> bool:
        """检查指定任务是否已建立索引。兼容 legacy note chunks 与 ingestion document chunks。"""
        col_name = self._collection_name(task_id)
        try:
            col = self._client.get_collection(col_name)
            if col.count() == 0:
                return False
            for source_type in ("meta", "document", "markdown", "transcript"):
                found = col.get(where={"source_type": source_type}, limit=1)
                if len(found.get("ids", [])) > 0:
                    return True
            return False
        except Exception:
            return False
