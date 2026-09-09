from __future__ import annotations

import hashlib
import json
import re
from typing import Callable, Literal

from pydantic import BaseModel, Field, model_validator

from app.models.learning_canvas import LearningEdge, LearningNode, LearningSource


class ClarificationOption(BaseModel):
    id: str
    label: str
    description: str = ""


class ResearchClarification(BaseModel):
    question: str = Field(min_length=1)
    options: list[ClarificationOption] = Field(default_factory=list, min_length=2, max_length=4)
    allow_supplement: bool = True

    @model_validator(mode="after")
    def validate_unique_options(self):
        if not self.question.strip():
            raise ValueError("澄清问题不得为空")
        ids = [option.id.strip() for option in self.options]
        labels = [option.label.strip() for option in self.options]
        if any(not value for value in ids + labels):
            raise ValueError("澄清选项 id/label 不得为空")
        if len(set(ids)) != len(ids) or len(set(labels)) != len(labels):
            raise ValueError("澄清选项必须唯一")
        return self


class SuggestedResearchAction(BaseModel):
    id: str
    kind: Literal["focus", "research"]
    label: str
    node_id: str | None = None
    prompt: str | None = None


class ResearchCompilation(BaseModel):
    status: Literal["clarifying", "ready"]
    title: str = ""
    overview: str = ""
    markdown: str = ""
    nodes: list[LearningNode] = Field(default_factory=list)
    edges: list[LearningEdge] = Field(default_factory=list)
    sources: list[LearningSource] = Field(default_factory=list)
    clarification: ResearchClarification | None = None
    suggested_actions: list[SuggestedResearchAction] = Field(default_factory=list)


def _tokens(value: str) -> set[str]:
    normalized = str(value or "").lower()
    latin = set(re.findall(r"[a-z0-9][a-z0-9._+-]{1,}", normalized))
    cjk_runs = re.findall(r"[\u4e00-\u9fff]+", normalized)
    cjk = {run for run in cjk_runs if len(run) >= 2}
    for run in cjk_runs:
        cjk.update(run[index : index + 2] for index in range(max(0, len(run) - 1)))
    return latin | cjk


def _stable_id(prefix: str, value: str) -> str:
    return f"{prefix}_{hashlib.sha1(value.encode('utf-8')).hexdigest()[:16]}"


class ResearchNoteCompiler:
    def __init__(self, llm_compiler: Callable[..., ResearchCompilation | dict] | None = None):
        self.llm_compiler = llm_compiler

    def compile(
        self,
        *,
        goal: str,
        local_nodes: list[LearningNode],
        sources: list[LearningSource],
        provider_id: str | None = None,
        model_name: str | None = None,
    ) -> ResearchCompilation:
        normalized_goal = str(goal or "").strip()
        relevant_local_nodes = self._filter_local_nodes(normalized_goal, local_nodes)
        relevant_sources = self._filter_sources(normalized_goal, relevant_local_nodes, sources)
        if self.llm_compiler is not None and provider_id and model_name:
            try:
                compiled = self.llm_compiler(
                    goal=normalized_goal,
                    local_nodes=relevant_local_nodes,
                    sources=relevant_sources,
                    provider_id=provider_id,
                    model_name=model_name,
                )
                result = compiled if isinstance(compiled, ResearchCompilation) else ResearchCompilation.model_validate(compiled)
                if result.status == "clarifying" and result.clarification and result.clarification.options:
                    return result
                if result.status == "ready" and self._valid_ready_result(result, relevant_sources):
                    allowed_source_ids = {source.id for source in relevant_sources}
                    allowed_source_ids.update(source_id for node in relevant_local_nodes for source_id in node.source_ids)
                    for node in result.nodes:
                        node.source_ids = [source_id for source_id in node.source_ids if source_id in allowed_source_ids]
                    result.sources = relevant_sources
                    return result
            except Exception:
                pass
        return self._fallback(normalized_goal, relevant_local_nodes, relevant_sources)

    @staticmethod
    def _valid_ready_result(result: ResearchCompilation, sources: list[LearningSource]) -> bool:
        allowed_node_types = {"topic", "concept", "claim", "evidence", "conflict", "case", "question"}
        allowed_edge_types = {"contains", "supports", "challenges", "depends_on", "example_of", "related"}
        required_sections = (
            "## 研究范围",
            "## 概览",
            "## 基础定义",
            "## 核心结构",
            "## 判断框架",
            "## 冲突与证据",
            "## 代表案例",
            "## 开放问题",
            "## 来源",
        )
        node_ids = {node.id for node in result.nodes}
        allowed_urls = {source.url.rstrip("/") for source in sources if source.url}
        markdown_urls = {
            value.rstrip("/.,);]")
            for value in re.findall(r"https?://[^\s<>()\]]+", result.markdown)
        }
        source_titles = {
            value.strip().casefold()
            for source in sources
            for value in (source.title, source.repository or "")
            if value.strip()
        }
        return (
            bool(result.title and result.overview and result.nodes)
            and all(node.type in allowed_node_types for node in result.nodes)
            and all(section in result.markdown for section in required_sections)
            and all(edge.type in allowed_edge_types and edge.source in node_ids and edge.target in node_ids for edge in result.edges)
            and markdown_urls.issubset(allowed_urls)
            and all(node.label.strip().casefold() not in source_titles for node in result.nodes)
        )

    @staticmethod
    def _filter_local_nodes(goal: str, local_nodes: list[LearningNode]) -> list[LearningNode]:
        goal_tokens = _tokens(goal)
        relevant = [
            node for node in local_nodes
            if node.id.startswith("context_") or goal_tokens & _tokens(f"{node.label} {node.summary}")
        ]
        return relevant[:12]

    @staticmethod
    def _filter_sources(goal: str, local_nodes: list[LearningNode], sources: list[LearningSource]) -> list[LearningSource]:
        query_tokens = _tokens(goal)
        query_tokens.update(token for node in local_nodes for token in _tokens(f"{node.label} {node.summary}"))
        ranked: list[tuple[int, LearningSource]] = []
        for source in sources:
            overlap = query_tokens & _tokens(f"{source.title} {source.snippet} {source.repository or ''}")
            if not overlap:
                continue
            metadata_bonus = int(source.source_type == "academic") + int(bool(source.repository)) + int(bool(source.authors))
            ranked.append((len(overlap) * 10 + metadata_bonus, source))
        ranked.sort(key=lambda item: (-item[0], item[1].title.lower()))
        return [source for _, source in ranked[:12]]

    @staticmethod
    def _fallback(goal: str, local_nodes: list[LearningNode], sources: list[LearningSource]) -> ResearchCompilation:
        allowed_node_types = {"topic", "concept", "claim", "evidence", "conflict", "case", "question"}
        nodes = [node.model_copy(deep=True) for node in local_nodes[:8]]
        for node in nodes:
            if node.type not in allowed_node_types:
                node.type = "concept"
        if not nodes:
            nodes = [
                LearningNode(
                    id=_stable_id("topic", goal),
                    label=goal,
                    type="topic",
                    summary="当前证据不足，先建立研究范围与待验证问题。",
                    priority="high",
                )
            ]
        overview = nodes[0].summary or f"围绕“{goal}”建立可验证的研究范围、核心结构和判断标准。"
        source_lines = [f"- [{source.title}]({source.url})" if source.url else f"- {source.title}" for source in sources]
        markdown = "\n\n".join(
            [
                f"# {goal}研究笔记",
                f"## 研究范围\n\n本笔记围绕“{goal}”整理当前可验证的本地知识与外部证据。",
                f"## 概览\n\n{overview}",
                "## 基础定义\n\n" + "\n".join(f"- **{node.label}**：{node.summary or '待补充证据'}" for node in nodes[:4]),
                "## 核心结构\n\n从研究对象、运行机制、边界条件和结果反馈四个角度继续拆解。",
                "## 判断框架\n\n判断一个结论是否成立时，分别检查定义是否一致、证据是否直接、适用条件是否满足、是否存在反例。",
                "## 冲突与证据\n\n当前材料中的不同结论应按来源、时间、方法和适用范围逐项对照，未验证部分保持为开放问题。",
                "## 代表案例\n\n优先选择能够暴露边界条件的正例与反例，而不是只罗列热门项目。",
                "## 开放问题\n\n- 哪些结论有直接证据？\n- 哪些结论依赖特定场景？\n- 存在哪些反例或相互冲突的观点？",
                "## 来源\n\n" + ("\n".join(source_lines) if source_lines else "- 当前没有通过相关性门槛的外部来源。"),
            ]
        )
        return ResearchCompilation(
            status="ready",
            title=f"{goal}研究笔记",
            overview=overview,
            markdown=markdown,
            nodes=nodes,
            edges=[],
            sources=sources,
            suggested_actions=[
                SuggestedResearchAction(id="focus-overview", kind="focus", label="查看核心结构", node_id=nodes[0].id),
                SuggestedResearchAction(id="research-criteria", kind="research", label="补充判断标准", prompt=f"继续研究“{goal}”的判断标准、适用边界和反例"),
            ],
        )


def build_llm_research_compiler():
    def compile_with_model(*, goal, local_nodes, sources, provider_id, model_name):
        from app.gpt.notemeld_gpt import NotemeldGPT
        from app.services.model import ModelService
        from app.services.provider import ProviderService

        provider = ProviderService.get_provider_by_id(provider_id)
        if not provider:
            raise ValueError(f"未找到模型供应商: {provider_id}")
        gpt = NotemeldGPT.from_config(
            ModelService.build_saved_model_config(
                provider,
                model_name,
                usage_context={
                    "phase": "research_note_compile",
                    "provider_id": provider["id"],
                },
            )
        )
        evidence = {
            "goal": goal,
            "local_knowledge": [node.model_dump(mode="json") for node in local_nodes[:12]],
            "sources": [source.model_dump(mode="json") for source in sources[:12]],
        }
        response = gpt.create_chat_completion(
            phase_label="Research Note Compile",
            response_format={"type": "json_object"},
            timeout=45,
            max_tokens=5000,
            request_meta={"stage": "research_compile"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是 NoteMeld 研究编译器，只输出合法 JSON。不是老师，不制定课程或学习时长。"
                        "先判断研究目标是否存在会改变检索对象的重大歧义；有则 status=clarifying 且只问一个问题。"
                        "目标明确则 status=ready，把证据编译为研究笔记和白板。搜索结果只是证据，禁止把论文标题或仓库名直接作为节点。"
                        "节点 type 只能是 topic/concept/claim/evidence/conflict/case/question，source_ids 只能引用输入 id。"
                        "Markdown 必须包含研究范围、概览、基础定义、核心结构、判断框架、冲突与证据、代表案例、开放问题、来源。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "输出字段：status,title,overview,markdown,nodes,edges,clarification,suggested_actions。"
                        "clarification={question,options:[{id,label,description}],allow_supplement}。"
                        "suggested_actions 最多4个，kind 为 focus 或 research。\n\n证据：\n"
                        + json.dumps(evidence, ensure_ascii=False)
                    ),
                },
            ],
        )
        content = gpt._extract_message_content(response, "研究编译")
        return json.loads(content)

    return compile_with_model
