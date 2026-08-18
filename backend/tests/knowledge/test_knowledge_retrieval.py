from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.agent_host.drivers.tools import NoteMeldToolDriver
from app.db.engine import Base
from app.models.knowledge_retrieval import KnowledgeQueryError
from app.services.knowledge_article_service import KnowledgeArticleService
from app.services.knowledge_capabilities import KnowledgeCapabilityProvider
from app.services.knowledge_evidence_index import KnowledgeEvidenceIndex
from app.services.knowledge_query_service import KnowledgeQueryService
from app.services.knowledge_repository import KnowledgeRepository


def _services(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'knowledge.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    sessions = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    repository = KnowledgeRepository(engine=engine, session_factory=sessions)
    vector = KnowledgeEvidenceIndex(enabled=False)
    article = KnowledgeArticleService(repository=repository, vector_index=vector)
    query = KnowledgeQueryService(repository=repository, vector_index=vector)
    return article, query


def _seed(article, article_id: str, title: str, summary: str, page: int):
    article.index_article(
        article_id=article_id,
        title=title,
        content=f"# {title}\n\n{summary}",
        source_type="upload",
        profile={"title": title, "summary": summary, "topics": ["RAG"], "status": "complete"},
        chunks=[{"chunk_id": f"{article_id}:chunk:0", "content": summary, "page_number": page, "chunk_index": 0}],
        terms=[
            {"term_id": "concept:rag", "term_type": "concept", "name": "RAG", "description": "retrieval augmented generation", "context": summary, "occurrence_id": f"{article_id}:rag"},
            {"term_id": "concept:agent", "term_type": "concept", "name": "Agent", "description": "tool-using model", "context": summary, "occurrence_id": f"{article_id}:agent"},
        ],
        relations=[{"source": "RAG", "target": "Agent", "relation_type": "supports", "evidence_id": f"{article_id}:evidence:0"}],
    )


def test_article_filter_is_shared_by_k1_k2_and_k3(tmp_path):
    article, query = _services(tmp_path)
    _seed(article, "article-a", "Agentic RAG", "RAG uses a profile before evidence retrieval.", 3)
    _seed(article, "article-b", "Other note", "RAG is mentioned in an unrelated note.", 9)

    evidence = query.evidence_search(query="RAG", article_ids=["article-a"], location={"page_from": 3, "page_to": 3})
    profile = query.profile_search(query="RAG", article_ids=["article-a"])
    semantic = query.semantic_search(query="RAG", article_ids=["article-a"], relation_types=["supports"])

    assert all(item["article_id"] == "article-a" for item in evidence["results"])
    assert all(item["article_id"] == "article-a" for item in profile["results"])
    assert all(item["article_id"] == "article-a" for item in semantic["results"])
    assert any(item["source_ref"].get("evidence_id") == "article-a:evidence:0" for item in semantic["results"])


def test_explicit_empty_article_ids_is_not_global_search(tmp_path):
    _, query = _services(tmp_path)
    with pytest.raises(KnowledgeQueryError, match="must not be empty"):
        query.profile_search(query="RAG", article_ids=[])


def test_four_capabilities_are_independent_and_use_common_article_id(tmp_path):
    article, query = _services(tmp_path)
    _seed(article, "article-a", "Agentic RAG", "RAG uses a profile before evidence retrieval.", 3)
    provider = KnowledgeCapabilityProvider(query_service=query)

    async def invoke_all():
        return await asyncio.gather(
            provider.invoke("knowledge:profile_search", {"query": "RAG"}, call_id="profile"),
            provider.invoke("knowledge:semantic_search", {"query": "RAG"}, call_id="semantic"),
            provider.invoke("knowledge:evidence_search", {"query": "retrieval", "article_ids": ["article-a"]}, call_id="evidence"),
            provider.invoke("knowledge:article_lookup", {"article_ids": ["article-a"]}, call_id="lookup"),
        )

    profile, semantic, evidence, lookup = asyncio.run(invoke_all())

    assert profile["capability_id"] == "knowledge:profile_search"
    assert semantic["capability_id"] == "knowledge:semantic_search"
    assert evidence["results"][0]["article_id"] == "article-a"
    assert lookup["results"][0]["article_id"] == "article-a"
    assert [item["id"] for item in provider.manifest()] == [
        "knowledge:article_lookup",
        "knowledge:evidence_search",
        "knowledge:profile_search",
        "knowledge:semantic_search",
    ]


def test_tool_driver_can_invoke_knowledge_provider_without_prior_tool(tmp_path):
    article, query = _services(tmp_path)
    _seed(article, "article-a", "Agentic RAG", "RAG uses a profile before evidence retrieval.", 3)
    driver = NoteMeldToolDriver(provider=KnowledgeCapabilityProvider(query_service=query))
    result = asyncio.run(driver.invoke(
        {"call_id": "c1", "tool_name": "knowledge:evidence_search", "arguments": {"query": "retrieval", "article_ids": ["article-a"]}},
        {"session_id": "s1", "turn_id": "t1"},
    ))
    assert result["call_id"] == "c1"
    assert result["structured_content"]["capability_id"] == "knowledge:evidence_search"
