# Change Spec：对话驱动的研究笔记白板

日期：2026-08-13  
Canonical requirement：`docs/requirements/2026-08-13-notemeld-research-note-whiteboard.md`

## 0. 预检查

- [x] 已阅读五份必读 system 文档。
- [x] 已搜索 HomePage、ChatComposer、MarkdownViewer、LearningCanvas、Sigma、conversation/chat router、NoteImportService、Wiki 调度和相关测试。
- [x] 已确认类似能力与本地数据影响。

## 1. 当前系统现状

- 后端已有 LearningCanvas model/store/service/router、ResearchSearch、NoteImportService、note_documents 与 Wiki extraction queue。
- 前端已有学习提交、compact learning message、对话/右侧分栏、MarkdownViewer 和 Sigma 图。
- 现有 `/learning-canvases` 同步把本地检索和外部来源都变成节点，未创建 Note；右侧 LearningCanvasCard 一次展示全部内容。
- free-chat 只支持 `asset_content` 字符串，用户消息 meta 虽可扩展但没有 context reference 契约。

## 2. 本次目标

- 明确目标后把检索证据编译为研究 Note，同时生成绑定该 Note 的白板投影。
- 重大歧义时只返回一个澄清问题；用户回答后可重新发起精确研究。
- 右侧复用现有分栏，以“笔记 / 白板”展示同一研究产物。
- 笔记选文、白板节点可右键加入对话；结构化引用同时持久化和传给模型。
- 助手消息可展示有类型的下一步建议。
- 保留 chat/note、旧 canvas、Wiki、MCP、桌面和打包兼容。

## 3. 明确不做

- 不做多人协作、自由绘图、任意布局编辑和白板正文编辑。
- 不删除 mastery/session/evidence，也不迁移旧 canvas。
- 不同步执行完整 Wiki rebuild；只复用单篇 contribution 异步调度。
- 不改 SQLite schema。

## 4. 冲突分析

- 产品规则：新方案把 AI 输出作为可验证研究草稿，Note 入库后由用户消费，符合知识编译器范式。
- 数据模型：NoteDocument 继续为正文权威；canvas 追加 `document_task_id/overview/suggested_actions` 作为可重建投影缓存。
- API：现有 create/get/patch path 保留；create payload 追加可选模型字段，响应字段全为可选兼容扩展；free-chat 追加可选 `context_refs`。
- known pitfalls：搜索候选必须经过相关性过滤；Note 成功是事务边界；白板失败不可回滚 Note；消息只存轻量索引和引用快照。
- 运行模式：纯前后端改动，不改 Tauri/CLI/MCP；桌面继续等待 backendReady。
- 打包/迁移：无新依赖和 DB 迁移；新 JSON 字段被旧 Pydantic 默认兼容忽略/缺省读取。

## 5. 影响范围

- 后端：learning model/service/router、研究编译与白板投影、chat request context、note import 复用。
- 前端：learning service、task store、ChatComposer、message renderer、Home、MarkdownViewer、LearningCanvasCard/Graph、Sigma 右键事件。
- 数据库：无 schema 变更；新增 NoteDocument 行。
- 文件：继续写旧 canvas 路径；标准 Note 写 `note_results/{task_id}.json`；不新增第二份正文。
- API 调用方：首页学习模式、free-chat stream。
- 测试：learning service/API、context refs、前端 source contracts、build 与核心回归。

## 6. 实施方案

### 后端

- 新增独立 `ResearchNoteCompiler`：先过滤搜索候选，再用所选 LLM 将证据编译为严格结构；LLM 不可用或输出非法时用可追溯的确定性框架降级。
- 编译结果可为 `clarifying` 或 `ready`。clarifying canvas 只写一个问题和选项，不创建 Note。
- ready 时通过 `NoteImportService.import_note(..., conversation_id)` 进入标准 Note、向量索引和 Wiki contribution 队列；canvas 绑定 `document_task_id`。
- 外部 source 不直接创建 node。node 只来自编译后的概念/主张/证据/问题结构，并且 source_ids 必须指向已过滤来源。
- free-chat router 把有界 context_refs 格式化后并入 asset context，保留原函数签名和 Agent/legacy 分流。
- 错误处理：无结果可生成证据不足框架；Note 写入失败则创建失败；Note 成功后的消息/白板/Wiki失败独立降级。
- 并发：沿用 LearningCanvasStore 的路径锁和原子 replace；前端共享学习锁不变。

### 前端

- `learning_canvas` 消息根据 status 渲染澄清问题或研究摘要；suggested action 放在回复下。
- Home 的学习右侧主视图改为同一研究产物的“笔记 / 白板”切换；ready 后默认笔记，旧 canvas 无 Note 时降级白板。
- LearningCanvasCard 收敛为白板画布 + 当前选中节点，不展示完整路径、掌握度、复习和全部来源。
- Zustand 保存 pending context refs；MarkdownViewer 和 Sigma 右键加入引用；ChatComposer 显示、移除并发送引用。
- 导航建议触发白板 focus event；研究建议填入 composer，由用户确认发送。

### 桌面/打包

- 无新增依赖或 native 入口；继续使用现有 API base 和 session header。

## 7. 数据变更

- SQLite：不新增表/字段。
- LearningCanvas version 提升为 2，并追加可选 `document_task_id`、`overview`、`clarification`、`suggested_actions`；version=1 可直接加载。
- conversation message meta 追加 canvas/document/status/clarification/actions 轻量索引。
- user message meta 追加 `context_refs`，单条快照限 2000 字符、总数限 8。
- 回滚后：研究 Note 仍是普通 Note；旧代码忽略新增 meta 和 canvas 字段，不需清理。

## 8. 接口变更

- 修改 `POST /api/conversations/{conversation_id}/learning-canvases`：新增可选 `provider_id/model_name/context`；响应仍为 canvas。
- 修改 `POST /api/chat/free` 与 `/stream`：新增可选 `context_refs[]`。
- GET/PATCH learning path 保持。
- 不删除接口，不改变 ResponseWrapper 与错误码基本语义。
- 更新 `docs/system/api-inventory.md`。

## 9. UI/交互变更

- 操作路径：学习输入 →（必要时一个澄清问题）→ 研究摘要消息 → 右侧笔记 → 切白板 → 选文/节点加入对话 → 继续研究。
- 加载态：保留持久构建进度消息和共享锁。
- 空态：证据不足时展示框架与开放问题。
- 失败态：创建失败可重试；Note 已成功时不得显示“研究生成失败”。
- 可访问性：右键菜单同时提供可点击按钮；引用 chip 可键盘移除；图控制有 aria-label。

## 10. 测试方案

- 后端：候选过滤、外部 source 不成为 node、clarifying 不创建 Note、ready 创建 Note 并绑定、message meta 紧凑、context refs 限长与格式化、旧 canvas 读取。
- 前端：双视图、右键引用、composer chip/payload、suggested action、legacy fallback 契约。
- 构建：`pnpm test:contracts`、`pnpm build`、`python3 -m compileall backend/app`。
- 回归：聚焦 learning/agent/note tests，条件允许再跑 `scripts/run_core_regression.sh`。
- 手工：输入明确 Agent 主题、输入“韩信”、从笔记选文、从节点引用、刷新恢复。

## 11. 验收标准

- [x] 明确目标创建标准 Note，右侧可切笔记/白板。
- [x] 歧义目标只问一个问题且不生成错误 Note。
- [x] 无关 GitHub/论文不成为节点或推荐起点。
- [x] 笔记与节点引用可进入对话并持久化。
- [x] 首屏不再倾倒完整路径、复习和来源列表。
- [x] 旧 canvas、chat、note、Wiki 与桌面入口回归通过。

## 12. 风险和回滚

- 风险：LLM JSON 不稳定、搜索全失败、Note 与 canvas 后处理部分失败、引用导致 prompt 膨胀。
- 信号：编译 fallback 比例、external_errors、wiki_status、sidecar load error、payload size。
- 降级：严格 schema 失败使用确定性研究框架；白板从 Note/节点缓存重建；引用截断；旧 canvas 用 legacy view。
- 回滚：恢复旧 LearningCanvasCard 和 create 编译路径即可；不删除已生成 Note/canvas。
- 数据一致性：Note 永远是正文权威；canvas 可丢弃重建。

## 13. Agent 必答问题

- 影响模块：learning、note/Wiki、chat context、Home/Markdown/Sigma/task store。
- 已有类似能力：有，复用而非重建。
- 产品冲突：旧课程式 UI 与新目标冲突，保留数据但替换主投影。
- 字段冲突：无，全部可选扩展且无 DB migration。
- known pitfalls：通过候选过滤、单事实源、异步 Wiki、原子写和紧凑消息规避。
- 本地/线上：新增本地 Note/JSON；只调用现有外部 provider。
- 最小改动：在现有 canvas 上绑定标准 Note并替换投影，扩展 free-chat 引用。
- 回归测试：候选过滤、Note 事务边界、上下文限长、双视图、legacy 和全链路构建。
