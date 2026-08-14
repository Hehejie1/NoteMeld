# Local Model Evaluation

更新时间：2026-07-30

本文记录 NoteMeld 本地模型评测体系、当前测试结果和能力现状。新需求涉及模型选择、评测指标或测试数据集变更前必须先阅读本文。

## 评测体系概述

NoteMeld 有两个核心 AI 场景，分别使用不同类型的模型，评测指标也不同：

- **Workflow 视频总结**：多模态模型（multimodal），负责理解视频截图、OCR、场景描述，生成结构化笔记。
- **Agent 知识检索**：纯文本推理模型（text_only），负责 Wiki 知识图谱检索、问答生成、引用溯源。

### 测试目录结构

```
tests/
├── workflow/                    # Workflow 场景评测
│   ├── evaluate_model.py        # 评测入口
│   ├── test_metrics_offline.py  # 离线指标计算
│   ├── test_cases.json          # 基础测试用例
│   ├── spec/                    # 测试集规格定义
│   ├── public_benchmarks/       # 公开基准（LCSTS + HalluQA）
│   ├── hallucination/           # 事实幻觉基准
│   ├── business/                # NoteMeld 业务场景
│   └── regression/              # 真实 Bug 回归
├── agent/                       # Agent 场景评测
│   ├── evaluate_retrieval.py    # 检索评测入口
│   └── retrieval/               # 查询集
├── reports/                     # 评测报告输出
└── shared/                      # 共享工具
```

### 模型推荐 Skill

模型推荐逻辑位于 `.trae/skills/notemeld-model-recommender/`，包含：
- `SKILL.md`：Agent 声明文件，定义硬性限制规则（按设备架构限制参数上限）。
- `scripts/model_recommender.py`：内部执行脚本，采集设备信息、过滤超限模型、打分排名。

推荐时同时输出两类模型各 5 个：多模态（视频总结用）+ 纯文本（Agent 对话用）。

## 评测指标定义

### Workflow 视频总结指标

| 指标 | 含义 | 权重 | 计算方式 |
|------|------|------|---------|
| 幻觉率 | 生成内容中未基于原文的比例（越低越好） | 35% | HalluQA 数据集 + FactualBenchmark 人工标注 |
| 模板遵循度 | 笔记段落完整性、`*Screenshot-[mm:ss]` 格式、时间戳准确性 | 25% | 正则匹配 + 章节计数 |
| 章节召回率 | 模板要求的所有章节是否都出现 | 15% | expected_sections vs actual_sections |
| 引用正确率 | `*Content-[mm:ss]` 和 `*Screenshot-[mm:ss]` 时间点准确性 | 15% | 时间戳偏差 ≤ 5s 视为正确 |
| ROUGE-1 | 生成摘要与参考摘要的重叠度 | 10% | 标准 ROUGE-N 计算 |

数据集分层（金字塔结构）：
- L3 回归测试：`regression/regression_cases.json`，用户真实 Bug 反馈。
- L2 业务场景：`business/business_cases.json`，真实素材（会议、教程、产品等）。
- L2 事实幻觉：`hallucination/factual_benchmark.json`，总结类幻觉检测。
- L1 公开基准：`public_benchmarks/`，LCSTS（中文摘要）+ HalluQA（幻觉检测）。

### Agent 知识检索指标

| 指标 | 含义 | 权重 | 计算方式 |
|------|------|------|---------|
| Recall@10 | 前 10 条检索结果中包含正确答案的比例 | 30% | 60 条真实查询 |
| Recall@5 | 前 5 条中包含正确答案的比例 | 20% | 同上 |
| MRR | 正确答案排名倒数均值（越靠前越好） | 25% | 1/rank 求平均 |
| 引用准确率 (Top-1) | 第一条结果就是正确答案的比例 | 25% | top-1 命中率 |

查询集位于 `tests/agent/retrieval/retrieval_queries.json`，包含 60 条真实查询，覆盖概念定义、细节查询、操作指南、对比、实体查找 5 个类别。

## 当前测试结果

测试环境：Intel Mac (x86_64), 32GB RAM, Intel UHD Graphics 630 (无独立 GPU), Ollama 本地推理。

### Workflow 视频总结

#### qwen3:8b（纯文本推理模型）

测试日期：2026-07-29

| 数据集 | 测试数 | 关键指标 | 结果 |
|--------|--------|---------|------|
| LCSTS 中文摘要 | 30 | ROUGE-1 / 关键词覆盖率 / 平均响应时间 | 0.175 / 90% / 24.2s |
| HalluQA 幻觉检测 | 30 | 非幻觉率 / 幻觉率 / 平均响应时间 | 63.3% / 36.7% / 25.5s |
| 业务场景 | 3 | 成功率 / 平均响应时间 | 66.7% / 85.7s |

HalluQA 分类统计：
- Misleading 类：12 条，5 条幻觉（41.7%）
- Knowledge 类：18 条，6 条幻觉（33.3%）

#### qwen2.5vl:3b（多模态模型）

测试日期：2026-07-29

| 测试用例 | 类型 | ROUGE-1 | 关键词覆盖率 | 响应时间 |
|---------|------|---------|------------|---------|
| 技术文章摘要 | text_summarization | 0.077 | 50% | 21.6s |
| 产品介绍摘要 | text_summarization | 0.400 | 100% | 14.5s |

问题：qwen2.5vl:3b 在技术类摘要中 ROUGE-1 极低（0.077），关键词覆盖率仅 50%，存在事实幻觉（遗漏"计算机科学"、"图像识别"、"自然语言处理"等核心概念）。

#### qwen3-vl:8b（多模态模型）

测试日期：2026-07-30

| 数据集 | 测试数 | 准确率 | 平均响应时间 | 问题 |
|--------|--------|--------|------------|------|
| FactualBenchmark | 10 | 10% (1/10) | 90.3s | 模型将所有摘要判定为"faithful"，无法识别幻觉内容 |

分析：qwen3-vl:8b 在幻觉检测任务上表现极差。10 条测试中，9 条包含幻觉的摘要被错误判定为"忠实"，模型缺乏对事实一致性的批判性分析能力。这意味着在 NoteMeld Workflow 中，qwen3-vl:8b 生成的总结需要强人工验证。

业务场景测试（64 条）进行中，结果待补充。

### Agent 知识检索

测试日期：2026-07-30

| 指标 | 结果 | 评价 |
|------|------|------|
| Recall@3 | 38.33% | 一般 |
| Recall@5 | 50.00% | 中等 |
| Recall@10 | 66.67% | 良好 |
| MRR | 0.3120 | 偏低 |
| 引用准确率 (Top-1) | 16.67% | 偏低 |
| 未命中 (top10) | 20/60 | 33% 查询未命中 |

按查询类别拆分：

| 类别 | 数量 | Recall@3 | Recall@5 | Recall@10 | MRR | Top-1 |
|------|------|---------|---------|----------|-----|-------|
| concept_definition | 23 | 39.1% | 47.8% | 65.2% | 0.362 | 26.1% |
| detail | 17 | 47.1% | 58.8% | 76.5% | 0.357 | 17.6% |
| how_to | 18 | 27.8% | 44.4% | 61.1% | 0.222 | 5.6% |
| comparison | 1 | 0% | 0% | 0% | 0.000 | 0% |
| entity_lookup | 1 | 100% | 100% | 100% | 0.333 | 0% |

分析：
- 概念定义类和细节查询类表现最好，Recall@10 在 65-77%。
- 操作指南类（how_to）表现最弱，Recall@3 仅 27.8%，MRR 0.222。
- 当前检索系统使用关键词匹配（WikiSearch），未接入 LLM 语义检索。

## 能力现状总结

### Workflow 视频总结能力

**当前水平：可用，但需人工验证。**

- ✅ 关键词覆盖率达 90%（qwen3:8b），能提取视频核心内容。
- ✅ 产品介绍类摘要质量较好（ROUGE-1: 0.40, 关键词覆盖率: 100%）。
- ⚠️ ROUGE-1 整体偏低（0.175），摘要精炼度和忠实度有提升空间。
- ⚠️ 幻觉率 36.7%（qwen3:8b HalluQA），生成内容可能包含原文未提及的信息。
- ⚠️ qwen3-vl:8b 幻觉检测准确率仅 10%（FactualBenchmark），模型无法识别幻觉内容，倾向将所有摘要判定为"忠实"。
- ⚠️ 技术类内容摘要质量不稳定（qwen2.5vl:3b ROUGE-1: 0.077）。
- ⚠️ Intel CPU 推理速度偏慢（24-86s/条），影响批量处理效率。

**改进方向：**
1. 接入更大参数模型（14B+）以降低幻觉率（需 GPU 设备）。
2. 优化 prompt 模板，强化"基于原文"约束。
3. 增加 FactualBenchmark 测试覆盖，建立幻觉率基线。
4. 考虑接入 LLM 语义重排序，提升摘要忠实度。

### Agent 知识检索能力

**当前水平：基础可用，检索精度待提升。**

- ✅ Recall@10 达 66.7%，大部分查询能在前 10 条找到相关结果。
- ✅ 概念定义类查询表现最好（Recall@10: 65.2%, Top-1: 26.1%）。
- ⚠️ MRR 0.312，正确结果排名偏后，用户需翻阅多条结果。
- ⚠️ Top-1 准确率仅 16.7%，首条结果命中率低。
- ⚠️ 操作指南类查询表现最弱（Recall@10: 61.1%, Top-1: 5.6%）。
- ⚠️ 33% 的查询在前 10 条完全未命中，存在检索盲区。

**改进方向：**
1. 接入 LLM 语义检索（如 embedding-based search），替代纯关键词匹配。
2. 增加查询重写（query rewriting），将口语化查询转为关键词。
3. 优化 Wiki 知识图谱的 entity/concept 索引覆盖率。
4. 增加召回结果的 LLM 重排序，提升 Top-1 准确率。

## 评测命令参考

```bash
# Workflow 评测（从项目根目录运行）
python3 tests/workflow/evaluate_model.py --model qwen3:8b
python3 tests/workflow/evaluate_model.py --model qwen3:8b --skip-lcsts --skip-halluqa
python3 tests/workflow/evaluate_model.py --model qwen3:8b --only-factual
python3 tests/workflow/evaluate_model.py --model qwen3:8b --only-regression

# Agent 检索评测
python3 tests/agent/evaluate_retrieval.py

# 模型推荐（Skill 内部脚本）
python3 .trae/skills/notemeld-model-recommender/scripts/model_recommender.py
```

评测报告输出到 `tests/reports/` 目录，JSON + Markdown 双格式。

## 数据来源

- 公开排行榜：Vectara HHEM 幻觉率排行榜、HuggingFace Open LLM Leaderboard、Ollama 模型库。
- 本地测试：`tests/reports/` 目录下的评测报告。
- 模型推荐 Skill：`.trae/skills/notemeld-model-recommender/SKILL.md`。
