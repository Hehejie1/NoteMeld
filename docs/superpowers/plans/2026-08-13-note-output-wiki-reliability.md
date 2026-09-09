# 笔记输出格式与 Wiki 抽取可靠性实施计划

日期：2026-08-13
Requirement：`docs/requirements/2026-08-13-note-output-wiki-reliability.md`
Spec：`docs/superpowers/specs/2026-08-13-note-output-wiki-reliability-design.md`

## 任务 1：笔记格式 RED

- 在 `backend/tests/` 增加全文围栏、真实 HTML、内部 fence、Markdown-only prompt 测试。
- 运行聚焦测试，确认因缺少 normalizer/错误 prompt 失败。

## 任务 2：笔记格式 GREEN

- 新增共享 normalizer。
- 修改 `note_style_prompt_builder.py`、`note.py`、`web_note.py` 复用它。
- 跑 Note/Web/style 聚焦回归。

## 任务 3：Wiki 兼容链 RED

- 增加 Provider reasoning/finish_reason 透传测试。
- 增加 NotemeldGPT adapter 与 KnowledgeExtractor 合法恢复、截断、无最终 JSON 测试。
- 确认测试在当前实现上按预期失败。

## 任务 4：Wiki 兼容链 GREEN

- 扩展 `CompleteResult`、Provider 与 adapter。
- 实现受控 reasoning JSON 提取和错误分类。
- 提高默认预算、收紧 prompt 输出边界。
- 跑 AI/Wiki 聚焦回归。

## 任务 5：系统回归与文档

- 更新 architecture、API inventory、known pitfalls。
- 运行 `compileall`、后端相关测试、前端 contract/build、`git diff --check`。
- 将真实命令与结果写入 `docs/superpowers/tests/2026-08-13-note-output-wiki-reliability.md`。

## 任务 6：本地验收

- 重启 NoteMeld 源码服务。
- 健康检查前后端；必要时对已确认的单条历史笔记做可逆、确定性归一化。
- 汇报通过项、未通过项和剩余风险。

## 风险与回滚

- 每项先测试再实现；变更不涉及 schema。
- 回滚只需撤销新 helper 和字段透传；历史数据不自动批量迁移。

