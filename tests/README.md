# NoteMeld 评测体系 — 两阶段分层测试

> 版本：2.0 · 2026-07-29
> 对应产品阶段：**Workflow-First, Agent-Second**

NoteMeld 的评测严格对齐产品的两个阶段，分别放在独立的子目录中，互不干扰：

```
tests/
├── README.md                      ← 你在这里
├── reports/                       ← 共享：所有评测报告自动输出到这里
│
├── workflow/                      ← 阶段一：视频 → 笔记（Workflow 流水线评测）
│   ├── evaluate_model.py          #   Workflow 评测入口（需要 Ollama）
│   ├── test_metrics_offline.py    #   指标单元测试（无需模型）
│   ├── spec/                      #   9 种笔记模板 + 用例字段规范
│   ├── public_benchmarks/         #   L1 公开基准（LCSTS / HalluQA / 基准信息）
│   ├── business/                  #   L2 业务场景（来自 vector_db 真实素材）
│   ├── hallucination/             #   L2 幻觉专项（总结类事实一致性）
│   └── regression/                #   L3 线上问题回归（永久保留）
│
├── agent/                         ← 阶段二：Wiki 召回 → 对话回答（Agent 评测）
│   ├── evaluate_retrieval.py      #   检索评测入口（需要 backend wiki 数据）
│   └── retrieval/                 #   检索评测集（60 条人工标注 query）
│
└── shared/                        ← 共享工具
    └── test_ollama_connection.py  #   Ollama 连接诊断
```

---

## 1. 阶段一：Workflow 流水线评测（视频 → 笔记）

对应模块：下载 → 转码 → 抽帧 → 转写 → LLM 总结成结构化笔记。

### 核心指标（按权重）

| 排序 | 指标 | 权重 | 测什么 |
|---|---|---|---|
| 1 | **幻觉率** | 35% | 不出现原文没有的内容 |
| 2 | **模板遵循度** | 25% | 该 3 段不能只出 2 段、该有截图不能丢 |
| 3 | **引用精确度** | 15% | `*Content-[mm:ss]` 必须真指向该段 |
| 4 | **字幕召回** | 10% | 原视频关键信息有没有被保留 |
| 5 | **通用质量** (ROUGE-1/BERTScore) | 15% | 和公开榜单对齐，方便对外背书 |

### 数据集分层（金字塔）

| 层级 | 目录 | 用途 | 特点 |
|---|---|---|---|
| L1 公开基准 | `workflow/public_benchmarks/` | 和业界横向对比 | LCSTS 200万、HalluQA 2万中文样本 |
| L2 业务场景 | `workflow/business/` + `workflow/hallucination/` | 真实业务质量 | 每条带 evidence 指向原始素材 |
| L3 回归测试 | `workflow/regression/` | 防线上 Bug 复发 | 每条永久保留，修复后必须持续通过 |

### 快速使用

```bash
# 所有命令从项目根目录运行

# 指标逻辑单元测试（无需模型，秒跑完）
python3 tests/workflow/test_metrics_offline.py

# 日常迭代：跑业务场景 + 回归（需本地 Ollama）
python3 tests/workflow/evaluate_model.py --model qwen3:8b --skip-lcsts --skip-halluqa

# 全量评测（对外背书，包含公开基准）
python3 tests/workflow/evaluate_model.py --model qwen3:8b

# 验证 Bug 修复
python3 tests/workflow/evaluate_model.py --model qwen3:8b --only-regression

# 只测幻觉
python3 tests/workflow/evaluate_model.py --model qwen3:8b --only-factual
```

报告自动输出到 `tests/reports/eval_<model>_<timestamp>.{json,md}`。

---

## 2. 阶段二：Agent 对话评测（Wiki 召回 → 回答）

对应模块：用户提问 → 检索 Wiki → 召回相关笔记段落 → LLM 基于上下文回答。

### 核心指标

| 指标 | 含义 | 业界参考（Hybrid Search） |
|---|---|---|
| **Recall@3** | 前 3 条结果命中期望文档的查询占比 | ~70–80% |
| **Recall@5** | 前 5 条命中占比 | ~80–85% |
| **Recall@10** | 前 10 条命中占比 | ~85–90% |
| **MRR** | 第一个命中结果排名倒数的均值 | ~0.60–0.70 |
| **引用准确率 Top-1** | 返回的第一条是否就是期望文档 | ~50–60% |

### 评测集

- **位置**：`tests/agent/retrieval/retrieval_queries.json`
- **规模**：60 条人工标注的真实用户 query
- **语料库**：561 个真实 Wiki concepts（来自实际生产笔记）
- **覆盖问题类型**：概念定义(23)、方法类(18)、细节类(17)、对比类(1)、实体查询(1)
- **每条标注**：`expected_pages`（期望命中的 Wiki 页面）+ `hard_negatives`（易混淆的干扰项）

### 快速使用

```bash
# 所有命令从项目根目录运行

# 跑检索评测（无需 LLM，纯离线检索，约 10 秒）
python3 tests/agent/evaluate_retrieval.py

# 指定 wiki 目录
python3 tests/agent/evaluate_retrieval.py --wiki-dir vector_db/note_results/wiki

# 输出报告到 tests/reports/（JSON + Markdown）
ls tests/reports/retrieval_eval_latest.md
```

输出包含：整体指标表格、按问题类型细分统计、所有未命中 case 的详细分析（query → 返回结果 → 期望结果 → 失败原因）。

---

## 3. 线上问题 → 回归用例闭环

任何线上发现的问题，都按以下流程沉淀为永久回归用例：

```
用户反馈 / 测试发现 Bug
     ↓
在 tests/workflow/regression/regression_cases.json 追加一条 case
  - source_ticket: 工单号或对话链接
  - input: 真实 transcript + 时间戳
  - expected: 正确总结（含模板要求）
  - forbidden_claims: 模型不能说的话
  - detector: 自动检测脚本
     ↓
修复代码 / 换模型 / 调 Prompt
     ↓
python3 tests/workflow/evaluate_model.py --model <model> --only-regression
     ↓
全绿 → 合入主线，case 永久保留
```

### 如何新增一条回归用例

编辑 `tests/workflow/regression/regression_cases.json`，追加：

```json
{
  "id": "reg_YYYYMMDD_001",
  "source_ticket": "问题来源（工单/用户反馈/commit）",
  "bug_type": "hallucination | missing_section | screenshot_missing | wrong_citation | wrong_template | schema_violation | content_deletion",
  "category": "template_adherence",
  "input": {
    "text": "<真实 transcript 片段>",
    "source_type": "transcript",
    "evidence": "vector_db/note_results/<note_id>_transcript.json"
  },
  "expected": {
    "template_id": "video_analysis",
    "required_sections": ["视频主旨", "关键片段"],
    "forbidden_claims": ["不能出现的幻觉内容"],
    "required_citations": ["*Content-[00:15]"],
    "required_screenshot_slots": ["00:15"]
  },
  "evaluation": {
    "metrics": ["hallucination_rate", "section_recall", "citation_precision"]
  },
  "source": {
    "origin": "user_reported_bug",
    "collected_at": "2026-07-29T10:00:00Z",
    "annotator_count": 2,
    "annotation_agreement": 0.85
  }
}
```

---

## 4. 为什么 Workflow 和 Agent 分开评测？

这直接对应 NoteMeld 的产品架构哲学：**Workflow-First, Agent-Second**。

| 维度 | Workflow（阶段一） | Agent（阶段二） |
|---|---|---|
| **评测目标** | 总结是否忠实、模板是否合规 | 检索是否召回正确、回答是否引用正确来源 |
| **核心指标** | 幻觉率 / 模板遵循度 / 引用精确度 | Recall@k / MRR / 引用准确率 |
| **是否需要 LLM** | 需要（调用总结模型） | 检索评测不需要，端到端回答评测需要 |
| **数据集来源** | 公开基准 + 真实视频素材 | 真实用户 query + Wiki 语料库 |
| **失败含义** | 笔记不可用（根本性错误） | 回答找不到正确笔记（体验问题） |
| **运行频率** | 模型切换/Prompt 调整时跑全量 | 检索算法变更时跑 |

正因为两阶段的失败模式和评测目标完全不同，我们将数据集、脚本、报告目录完全分离：
- **改总结 Prompt** 不会影响检索评测，也不会意外污染检索数据集。
- **优化检索算法**（如加 Hybrid Search）时，不需要本地 Ollama 就能跑完检索评测，快速验证 Recall 提升。
- 报告输出到统一的 `tests/reports/`，方便对比两阶段各自的质量趋势。

---

## 5. Ollama 连接诊断

如果评测脚本报连接错误，先跑：

```bash
python3 tests/shared/test_ollama_connection.py
```

确认 Ollama 正在运行（`http://127.0.0.1:11434`），且已 pull 目标模型（如 `ollama pull qwen3:8b`）。

---

## 6. 推荐验证命令

```bash
# 快速烟雾测试（无需模型，10 秒内完成）
python3 tests/workflow/test_metrics_offline.py
python3 tests/agent/evaluate_retrieval.py

# 日常工作流（需 Ollama，约 5-15 分钟）
python3 tests/workflow/evaluate_model.py --model qwen3:8b --skip-lcsts --skip-halluqa

# 全量验证（对外背书）
python3 tests/workflow/evaluate_model.py --model qwen3:8b
```
