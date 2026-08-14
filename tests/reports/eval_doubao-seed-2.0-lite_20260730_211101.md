# NoteMeld 模型评测报告 v3.1

## 评测元信息

- **模型**: doubao-seed-2.0-lite
- **时间**: 2026-07-30T21:11:01.271194
- **硬件**: 云端推理 (Provider: https://ark.cn-beijing.volces.com/api/plan/v3)
- **评测套件**: LCSTS + HalluQA + FactualBenchmark + 业务场景 + 回归测试（线上真实 Bug 沉淀）

## 综合评分（加权）

**综合得分**: 35.00% 🔴 待改进

| 一级指标 | 得分 | 权重 | 评价 |
|---|---|---|---|
| ① 幻觉率（越低越好） | 0.00% | 0.35 | 🟢 优秀 |
| ② 模板遵循度 | 0.00% | 0.25 | 🔴 待改进 |
| ③ 章节召回率 | 0.00% | 0.15 | 🔴 待改进 |
| ④ 引用正确率 | 0.00% | 0.15 | 🔴 待改进 |
| ⑤ ROUGE-1（通用质量） | 0.00% | 0.10 | 🔴 待改进 |

> **门槛**：生产环境 ≤ 5% 幻觉率，Beta ≤ 10%。模板遵循度 ≥ 95%。章节召回率 ≥ 90%。

## 数据集总览

| 数据集 | 测试数 | 成功 | 核心指标 |
|---|---|---|---|
| NoteMeld Regression | 5 | 5 | 通过率=20.00% (通过 1/5) |

## 结论

- **综合评分**: 35.00% 🔴 待改进
- ✅ 幻觉率 ≤ 5%，达到生产标准
- ⚠️ 模板遵循度仅 0.00%，存在「3 段只出 2 段」类问题

报告文件:
- JSON: /Users/hehejie/ai/NoteMeld/tests/reports/eval_doubao-seed-2.0-lite_20260730_211101.json
- Markdown: /Users/hehejie/ai/NoteMeld/tests/reports/eval_doubao-seed-2.0-lite_20260730_211101.md

## 回归测试结果（线上真实 Bug 沉淀）

- **通过率**: 20.00% (1/5)
- **通过数**: 1
- **失败数**: 4

### ❌ 失败用例（需修复）

- **reg_20260729_001** (hallucination) — 工单：用户反馈 2026-07-29：Mac 系统 API Key 配置总结出现 Windows 图形界面幻觉
  - 失败原因：screenshot_missing(cov=0.0); citation_screenshot_recall=0.0; citation_content_recall=0.0
- **reg_20260729_002** (missing_section) — 工单：产品复盘 2026-07-29：video_analysis 模板下「关键片段」章节偶发缺失（3 段变 2 段）
  - 失败原因：missing_sections=['AI 总结']; screenshot_missing(cov=0.0); citation_screenshot_recall=0.0
- **reg_20260729_003** (screenshot_missing) — 工单：产品复盘 2026-07-29：章节要求必须带截图时，模型经常漏掉 screenshot
  - 失败原因：screenshot_missing(cov=0.0); citation_screenshot_recall=0.0
- **reg_20260729_005** (content_deletion) — 工单：产品复盘 2026-07-29：总结删除了原视频的关键步骤（content_deletion）
  - 失败原因：keywords_missing(cov=0.6)

