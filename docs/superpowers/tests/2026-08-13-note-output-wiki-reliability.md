# 验证证据：笔记输出格式与 Wiki 抽取可靠性

Canonical requirement：`docs/requirements/2026-08-13-note-output-wiki-reliability.md`

## 自动测试

- `PYTHONPATH=backend python3 -m pytest -q backend/tests/test_note_output_normalizer.py backend/tests/test_note_style_packaging_contracts.py backend/tests/test_web_note_contracts.py`
  - 结果：覆盖来源前缀、错误文档围栏、内部 HTML fence、混合 Markdown/HTML 与真实 HTML 根元素。
- `PYTHONPATH=backend python3 -m pytest -q backend/tests/ai backend/tests/test_note_output_normalizer.py backend/tests/test_note_style_packaging_contracts.py backend/tests/test_web_note_contracts.py backend/tests/test_wiki_rebuild_service_contracts.py backend/tests/test_wiki_semantic_incremental_merge.py backend/tests/test_wiki_article_view_contracts.py backend/tests/test_knowledge_extractor_response_contracts.py`
  - 结果：最终结果见本文件末尾“完成前新鲜验证”。
- `python3 -m compileall -q backend/app`
  - 结果：通过，无输出。
- `node frontend/tests/learningCanvasContracts.test.mjs`
  - 结果：通过，无输出。
- `PATH=<bundled-node-and-pnpm> pnpm build`
  - 结果：Vite build 成功，13078 modules transformed，built in 1m 12s。
  - 非阻塞警告：第三方 `lottie-web` 使用 eval；若干既有 bundle 超过 500 kB。
- `git diff --check`
  - 结果：通过，无 whitespace error。

## TDD 证据

- Note RED：测试收集失败，`app.services.note_output_normalizer` 不存在。
- Wiki RED：6 failures，分别证明 reasoning/finish_reason 丢失、统一 empty 错误与 1600 token 默认预算。
- GREEN：新增实现后对应聚焦测试 12/12、47/47 通过；扩大集合最终 169/169 通过。

## 独立审查闭环

- Important：Markdown 内部 HTML fence/局部 HTML 触发整篇转换。已增加 Markdown marker 与 fence 防线，并扩展真实 HTML 根标签识别。
- 复审补充：不再维护有限 HTML 标签白名单，改为识别文档起始的通用 HTML start tag（支持可选 doctype/comment），并增加 aside/figure 回归测试。
- Important：输出数量/文本长度只由 prompt 约束。已在 `_normalize_analysis_payload` 后端硬裁剪实体/概念各 6、claims/evidence/relations 各 8，summary 240、description/evidence text 120。
- Minor：未知 `finish_reason` 被写成 `stop`。已保留 `None` 并增加兼容测试。

## 完成前新鲜验证

- `python3 -m compileall -q backend/app && PYTHONPATH=backend python3 -m pytest -q <AI + Note + Wiki 聚焦集合> && node frontend/tests/learningCanvasContracts.test.mjs && git diff --check && curl backend/frontend`
  - 结果：175 passed in 6.98s；compileall、前端 contract、diff check、后端 health 与前端 HTTP 均通过。
- 独立复审：本轮限定范围无剩余 Critical/Important，可交付。

## 本地数据验证

- 目标 task：`3ef54805-3dcd-4152-a1a9-753512580038`。
- 修复前：`note_documents.content` 与结果 Markdown 在来源引用后包含整篇 ` ```html ` fence。
- 修复后：数据库 content 长度 3739，来源引用保留，正文从 `# AI 产品经理...` 开始，不再包含文档 fence；结果 JSON/Markdown 与 Wiki source 已同步。
- Wiki 状态仍为 `partial`，没有伪造结构化抽取成功；用户可在新服务上点击“重试增强”。
- 可恢复备份：`vector_db/note_results/manual_fix_backups/3ef54805-3dcd-4152-a1a9-753512580038_20260813_note_format/`。
