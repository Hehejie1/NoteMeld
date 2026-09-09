# 回归测试集（Regression Suite）

本目录用于沉淀**线上真实反馈的 Bug**，形成"问题 → 用例 → 修复 → 永不复发"的闭环。

## 设计原则

1. **一条 Bug 一条用例**：`regression_cases.json` 中每个 case 对应一个具体的线上问题。
2. **永久保留**：修复后不得删除，任何改动都必须保证它继续通过。
3. **可自动检测**：每条 case 含 `detector` 字段，描述如何自动判断"模型又犯了同样的错"。
4. **证据确凿**：必须带 `source_ticket`（工单或对话链接）和 `evidence`（真实数据路径）。

## 新增一条用例的流程

1. **用户反馈 Bug**：必须收集
   - 视频 ID / URL / 时间点
   - 错误截图或错误描述
   - 期望正确输出
2. **在 `regression_cases.json` 追加一条**：
   - `id`: `reg_YYYYMMDD_NNN`（日期+序号）
   - `source_ticket`: 工单编号或对话截图
   - `bug_type`: `hallucination` / `missing_section` / `wrong_citation` / `wrong_template` / `screenshot_missing` / `schema_violation`
   - `category`: 见 `workflow/spec/test_set_spec.json`
   - `input.text`: 从 `vector_db/note_results/*_transcript.json` 截取的**真实 transcript 片段**
   - `input.evidence`: 原始数据路径
   - `expected.forbidden_claims`: 模型**绝对不能说**的话（通常是用户反馈中实际出现的错误内容）
   - `expected.required_sections`: 必须出现的章节标题
   - `expected.required_citations`: 必须出现的时间戳引用
   - `expected.required_screenshot_slots`: 必须截图锚点的时间段
   - `source.annotation_agreement`: 至少 2 人独立标注后 Kappa 系数
3. **修复 / 换模型 / 调 Prompt**
4. **跑回归验证**：
   ```bash
   python3 tests/workflow/evaluate_model.py --model <model> --only-regression
   ```
   必须所有 case 通过。
5. **合入主线**。

## bug_type 枚举

| bug_type | 含义 | 自动检测方法 |
|---|---|---|
| `hallucination` | 模型编造原文没有的事实 | 用 forbidden_claims 子串匹配 summary |
| `missing_section` | 模板要求的章节没出现（3 段变 2 段） | 用 required_sections 匹配 |
| `screenshot_missing` | 该带截图的章节没带 | 用 required_screenshot_slots 匹配 |
| `wrong_citation` | 时间戳引用对不上 | 用 required_citations + 时间偏差 ≤ 5s 判定 |
| `wrong_template` | 用了错误的模板 | 用 template_id 校验 |
| `schema_violation` | 格式不符合模板规范 | 用 template_definitions.json 规则校验 |
| `content_deletion` | 原文关键信息被丢掉 | 用 keywords 召回率判定 |

## 示例

```json
{
  "id": "reg_20260729_001",
  "source_ticket": "用户反馈 2026-07-29：视频总结里出现了原视频没有的「Windows 图形界面配置步骤」",
  "bug_type": "hallucination",
  "category": "hallucination",
  "input": {
    "text": "...（真实 transcript 片段）...",
    "source_type": "transcript",
    "evidence": "vector_db/note_results/bc0977f7-c472-4511-917c-19c9cfdf8a79_transcript.json",
    "duration_seconds": 180
  },
  "expected": {
    "template_id": "video_analysis",
    "required_sections": ["视频主旨", "关键片段"],
    "forbidden_claims": [
      "视频讲解了 Windows 环境变量的图形界面配置步骤",
      "讲师同时演示了 macOS 和 Windows 的图形界面配置"
    ],
    "required_citations": ["*Content-[00:15]", "*Content-[00:38]"],
    "required_screenshot_slots": ["00:15", "00:38"]
  },
  "evaluation": {
    "metrics": ["hallucination_rate", "section_recall", "citation_precision"]
  },
  "source": {
    "origin": "user_reported_bug",
    "collected_by": "product",
    "collected_at": "2026-07-29T10:00:00Z",
    "annotator_count": 2,
    "annotation_agreement": 0.85
  }
}
```
