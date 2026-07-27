from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class QueryIntent:
    scope: str
    intent: str
    needs: list[str]
    target_terms: list[str]


CURRENT_SCOPE_TERMS = ("这个视频", "这篇", "当前", "刚才", "这个内容", "这条")
GLOBAL_SCOPE_TERMS = ("知识库", "所有", "之前", "全局", "全部笔记", "历史笔记")
EVIDENCE_TERMS = ("原话", "证据", "依据", "哪一秒", "时间点", "出处", "引用")
CONCEPT_TERMS = ("是什么", "定义", "核心", "关键", "概念", "什么意思")
METADATA_TERMS = ("作者", "up主", "标题", "平台", "时长", "链接")
SUMMARY_TERMS = ("总结", "概括", "主要内容", "讲了什么", "说了什么")
COMPARE_TERMS = ("对比", "区别", "相同", "不同", "比较")


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    normalized = text.lower()
    return any(term.lower() in normalized for term in terms)


def _extract_target_terms(question: str) -> list[str]:
    terms: list[str] = []
    for match in re.finditer(r"[A-Za-z][A-Za-z0-9_\- ]{1,40}", question):
        term = match.group(0).strip()
        if term and term.lower() not in {"up"}:
            terms.append(term)
    quoted = re.findall(r"[「“\"]([^」”\"]+)[」”\"]", question)
    terms.extend(item.strip() for item in quoted if item.strip())
    return list(dict.fromkeys(terms))[:8]


def classify_query_intent(question: str) -> QueryIntent:
    text = (question or "").strip()
    if _contains_any(text, CURRENT_SCOPE_TERMS):
        scope = "current_note"
    elif _contains_any(text, GLOBAL_SCOPE_TERMS):
        scope = "global_wiki"
    else:
        scope = "mixed"

    if _contains_any(text, EVIDENCE_TERMS):
        intent = "evidence"
        needs = ["markdown", "transcript", "wiki_claim", "wiki_evidence"]
    elif _contains_any(text, METADATA_TERMS):
        intent = "metadata"
        needs = ["meta"]
    elif _contains_any(text, CONCEPT_TERMS):
        intent = "concept"
        needs = ["markdown", "wiki_concept", "wiki_claim", "wiki_evidence"]
    elif _contains_any(text, SUMMARY_TERMS):
        intent = "summary"
        needs = ["markdown", "wiki_claim"]
    elif _contains_any(text, COMPARE_TERMS):
        intent = "compare"
        needs = ["markdown", "wiki_concept", "wiki_claim", "wiki_relation"]
    else:
        intent = "general"
        needs = ["meta", "markdown", "transcript", "wiki_concept", "wiki_claim"]

    return QueryIntent(
        scope=scope,
        intent=intent,
        needs=needs,
        target_terms=_extract_target_terms(text),
    )


def build_vector_quotas(intent: QueryIntent) -> dict[str, int]:
    if intent.intent == "metadata":
        return {"meta": 3, "markdown": 1, "transcript": 1}
    if intent.intent == "evidence":
        return {"meta": 0, "markdown": 2, "transcript": 5}
    if intent.intent == "concept":
        return {"meta": 1, "markdown": 4, "transcript": 2}
    if intent.intent == "summary":
        return {"meta": 1, "markdown": 4, "transcript": 1}
    return {"meta": 1, "markdown": 3, "transcript": 2}
