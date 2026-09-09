from app.models.learning_canvas import LearningNode, LearningSource
import pytest
from pydantic import ValidationError

from app.services.research_note_compiler import ResearchNoteCompiler


def test_irrelevant_external_candidates_never_become_research_nodes():
    sources = [
        LearningSource(id="github:noise", source_type="github", provider="github", title="china-dictatorship", snippet="politics archive"),
        LearningSource(id="github:agent", source_type="github", provider="github", title="agent-runtime", snippet="AI agent planning tools runtime"),
    ]
    result = ResearchNoteCompiler().compile(
        goal="AI Agent 运行机制",
        local_nodes=[LearningNode(id="local", label="Agent 循环", summary="感知、规划、执行与反馈", source_ids=["wiki:agent"])],
        sources=sources,
    )

    assert result.status == "ready"
    assert [source.id for source in result.sources] == ["github:agent"]
    assert all(node.type != "source" for node in result.nodes)
    assert "china-dictatorship" not in result.markdown


def test_llm_can_return_one_clarification_without_note():
    result = ResearchNoteCompiler(
        llm_compiler=lambda **_kwargs: {
            "status": "clarifying",
            "clarification": {
                "question": "你指的是历史人物还是游戏角色？",
                "options": [
                    {"id": "history", "label": "历史人物"},
                    {"id": "game", "label": "游戏角色"},
                ],
            },
        }
    ).compile(goal="韩信", local_nodes=[], sources=[], provider_id="provider", model_name="model")

    assert result.status == "clarifying"
    assert result.clarification is not None
    assert result.clarification.question
    assert 2 <= len(result.clarification.options) <= 4
    assert result.markdown == ""


@pytest.mark.parametrize(
    "question,options",
    [
        ("   ", [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}]),
        ("选哪个？", [{"id": "a", "label": "A"}]),
        ("选哪个？", [{"id": "a", "label": "A"}, {"id": "a", "label": "B"}]),
    ],
)
def test_clarification_requires_one_question_and_two_to_four_unique_options(question, options):
    from app.services.research_note_compiler import ResearchClarification

    with pytest.raises(ValidationError):
        ResearchClarification(question=question, options=options)


def test_short_clear_concept_does_not_trigger_generic_clarification_without_model():
    result = ResearchNoteCompiler().compile(goal="熵增", local_nodes=[], sources=[])

    assert result.status == "ready"
    assert result.clarification is None


def test_ready_compilation_starts_with_overview_and_judgment_framework():
    result = ResearchNoteCompiler().compile(
        goal="AI Agent 运行机制",
        local_nodes=[LearningNode(id="local", label="Agent 循环", summary="感知、规划、执行与反馈", source_ids=["wiki:agent"])],
        sources=[],
    )

    assert result.status == "ready"
    assert "## 概览" in result.markdown
    assert "## 判断框架" in result.markdown
    assert result.overview
    assert any(action.kind == "focus" for action in result.suggested_actions)


def test_llm_compilation_cannot_reference_unseen_sources():
    source = LearningSource(id="arxiv:agent", source_type="academic", provider="arxiv", title="Agent runtime", snippet="AI agent runtime")

    def fake_llm(**_kwargs):
        markdown = "\n\n".join([
            "# Agent 研究", "## 研究范围\n\nAgent", "## 概览\n\n概览", "## 基础定义\n\n定义",
            "## 核心结构\n\n结构", "## 判断框架\n\n框架", "## 冲突与证据\n\n证据",
            "## 代表案例\n\n案例", "## 开放问题\n\n问题", "## 来源\n\n来源",
        ])
        return {
            "status": "ready",
            "title": "Agent 研究",
            "overview": "概览",
            "markdown": markdown,
            "nodes": [
                {"id": "concept-agent", "label": "Agent", "type": "concept", "summary": "运行循环", "source_ids": ["arxiv:agent", "made-up"]}
            ],
            "edges": [],
            "suggested_actions": [],
        }

    result = ResearchNoteCompiler(llm_compiler=fake_llm).compile(
        goal="AI Agent runtime",
        local_nodes=[],
        sources=[source],
        provider_id="provider",
        model_name="model",
    )

    assert result.nodes[0].source_ids == ["arxiv:agent"]


def test_llm_compilation_rejects_unseen_markdown_urls_and_source_titles_as_nodes():
    source = LearningSource(
        id="github:agent",
        source_type="github",
        provider="github",
        title="owner/agent-runtime",
        repository="owner/agent-runtime",
        snippet="AI agent runtime",
        url="https://github.com/owner/agent-runtime",
    )

    def fake_llm(**_kwargs):
        markdown = "\n\n".join([
            "# Agent 研究", "## 研究范围\n\nAgent", "## 概览\n\n概览", "## 基础定义\n\n定义",
            "## 核心结构\n\n结构", "## 判断框架\n\n框架", "## 冲突与证据\n\n证据",
            "## 代表案例\n\n案例", "## 开放问题\n\n问题", "## 来源\n\nhttps://evil.invalid/report",
        ])
        return {
            "status": "ready",
            "title": "Agent 研究",
            "overview": "概览",
            "markdown": markdown,
            "nodes": [
                {"id": "repo", "label": "owner/agent-runtime", "type": "concept", "summary": "runtime", "source_ids": ["github:agent"]}
            ],
            "edges": [],
        }

    result = ResearchNoteCompiler(llm_compiler=fake_llm).compile(
        goal="AI Agent runtime",
        local_nodes=[],
        sources=[source],
        provider_id="provider",
        model_name="model",
    )

    assert "evil.invalid" not in result.markdown
    assert all(node.label != source.title for node in result.nodes)


def test_fallback_normalizes_legacy_local_node_types():
    result = ResearchNoteCompiler().compile(
        goal="Agent 证据",
        local_nodes=[
            LearningNode(
                id="legacy",
                label="Agent 证据",
                type="entity",
                summary="本地知识",
                source_ids=["wiki:agent"],
            )
        ],
        sources=[],
    )

    assert result.nodes[0].type == "concept"


def test_llm_clarification_is_preserved_instead_of_falling_back_to_note():
    def fake_llm(**_kwargs):
        return {
            "status": "clarifying",
            "clarification": {
                "question": "你指的是历史人物还是游戏角色？",
                "options": [
                    {"id": "history", "label": "历史人物"},
                    {"id": "game", "label": "游戏角色"},
                ],
            },
        }

    result = ResearchNoteCompiler(llm_compiler=fake_llm).compile(
        goal="韩信",
        local_nodes=[LearningNode(id="local", label="韩信", summary="同名对象", source_ids=["wiki:hanxin"])],
        sources=[],
        provider_id="provider",
        model_name="model",
    )

    assert result.status == "clarifying"
    assert result.markdown == ""


def test_irrelevant_local_wiki_hits_do_not_become_nodes():
    result = ResearchNoteCompiler().compile(
        goal="AI Agent 运行机制",
        local_nodes=[
            LearningNode(id="noise", label="短剧产品经理", summary="招聘与面试", source_ids=["wiki:noise"]),
            LearningNode(id="agent", label="AI Agent", summary="规划、工具调用与反馈", source_ids=["wiki:agent"]),
        ],
        sources=[],
    )

    assert [node.id for node in result.nodes] == ["agent"]
