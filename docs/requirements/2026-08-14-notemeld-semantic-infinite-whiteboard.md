# NoteMeld 语义无限白板

日期：2026-08-14
作者 / Agent：Codex
状态：Planned
关联对话 / 任务：学习研究右侧白板从只读图谱升级为人可编辑的语义白板
关联旧需求：`docs/requirements/2026-08-13-notemeld-research-note-whiteboard.md`
关联系统文档：`docs/system/current-architecture.md` 、`product-rules.md` 、`data-model.md` 、`api-inventory.md` 、`known-pitfalls.md`

> 本文档同时是本功能的 canonical requirement 和增量 Change Spec。旧需求中“研究编译、歧义澄清、本地/Internet 调研、标准 Note 生成”仍然有效；其“Sigma 只读白板投影”的交互、存储和权威性规则由本需求替代。

## 1. 原始需求

用户确认要一个最终形态的白板，不再按 V1/V2/V3 拆分产品形态：

- 白板由“白板、卡片、关系”三种核心对象组成。
- 人可在无限画布中创建、编辑、拖拽、缩放、框选卡片，并把观点、证据、文件和新话题串联起来。
- 卡片有 `markdown | web | file | whiteboard` 四种类型，并统一具有标题、描述、来源和内容。
- 一张卡片可与多张卡片建立关系；关系是可选中、可编辑的连线，双击连线可填写关系名称和备注。
- 卡片与关系可被框选并“添加到对话”，对话必须得到完整的卡片内容和卡片间关系，不是一组孤立标题。
- 白板可转为标准 Note；只有用户确认发布的 Note 才进入现有 Wiki 编译管线。
- 画布框架必须开源、无生产 license key、无封闭运行时依赖，可由 NoteMeld 团队长期内部维护和二次开发。

## 2. 背景和问题

- 当前用户：使用 NoteMeld 进行本地知识研究、证据组织和主动判断的个人用户。
- 当前场景：用户在中间对话中发起研究，右侧在笔记和白板之间切换。
- 当前痛点：现有 Sigma 实现只展示点、短标签和连边，用户不能创建或排列卡片、表达关系语义、编辑内容或进行头脑风暴。
- 根本差距：当前 `LearningCanvas` 是 AI 编译结果的只读图谱投影，而用户需要的是一个人和 AI 共同编辑、可持久化、可发布的语义工作区。
- 为什么现在做：白板已成为学习/研究主交互，若继续在 Sigma 图谱上叠加浮层，会持续放大交互、数据和性能债务。

## 3. 目标结果

1. 用户可在右侧无限画布中自由组织卡片与关系，并清楚知道每块内容是什么、来自哪里、与其他内容有什么关系。
2. 白板卡片可承载 Markdown、网页/媒体、文件和嵌套白板，并统一支持选中、拖拽、缩放、连线、编辑、删除、撤销和恢复。
3. 用户可将选中卡片及其内部关系作为可追溯上下文加入中间对话，继续调研、反驳、对比或改写。
4. 白板是未发布研究草稿的权威结构；笔记是用户确认发布后的线性快照。白板改动不静默污染 Wiki。
5. 采用单一开源画布框架 React Flow，业务数据与框架对象解耦，保证上游停止维护时仍能由 NoteMeld 内部接管。

## 4. 非目标

- 不做自由手绘、画笔、橡皮、图形库或 Figma 级矢量编辑。
- 不做多人实时协作、跨设备 CRDT、光标同步或冲突自动合并。
- 不把白板建设成 BPMN/工作流执行引擎，连线只表达知识关系。
- 不依赖 React Flow Pro 代码、模板或运行时；撤销、复制、辅助线等业务能力由 NoteMeld 实现。
- 不保证无限数量 DOM 卡片仍无性能上限；通过可见区渲染、摘要态和可验证基准管理实际上限。
- 不自动把每次拖拽或草稿编辑发布到 Note/Wiki。
- 不删除旧 `LearningCanvas` JSON、学习证据、掌握状态或 Sigma Wiki 图谱能力。

## 5. 当前系统事实

### 5.1 已有能力

- 前端是 React 19 + TypeScript + Zustand，右侧已有“白板 / 笔记”切换容器。
- `LearningCanvasCard` 和 `LearningCanvasGraph` 把 `LearningCanvas.nodes/edges` 投影到 Sigma/Graphology。Sigma 支持缩放、平移、点选和右键，但是图可视化器，不是卡片白板编辑器。
- `LearningCanvas` v2 持久化到 `workspaces/{conversation_id}/canvases/{canvas_id}.json`；存储已有路径校验、单路径锁和唯一临时文件原子替换。
- 当前 `LearningNode` 没有 `x/y/width/height/zIndex/card_type/content` ，`LearningEdge` 没有标题、描述、线型和可编辑标注。
- 当前研究流程先通过 `NoteImportService` 创建标准 Note，再保存 Canvas 投影；Note 成功是不可回滚的事务边界。
- 当前对话引用支持 `note_selection | whiteboard_node`，上限 8 条、单条快照 2000 字符。它能保存快照，但不能表达多卡片与关系的一次选择。
- SQLite 由 SQLAlchemy `Base.metadata.create_all()` 建表；迁移导出会整体复制 `notemeld.db`，导入合并共享表。

### 5.2 当前限制和回归风险

- 继续扩展 Sigma 会把图展示、卡片编辑、空间布局和内容嵌入混在同一组图谱组件中。
- 若直接把 React Flow `Node[]/Edge[]` JSON 作为后端事实源，数据会被第三方框架字段绑定，不利于内部长期维护。
- 若白板和 Note 双向自动同步，会重新引入“两份正文同时演进”的双事实源问题。
- 若对话直接相信前端传入的卡片 snapshot/source_ids，客户端可伪造内容和来源。新白板引用必须从后端权威数据重建。
- 若拖拽过程每帧请求后端，会导致界面卡顿、写放大和 revision 冲突。

## 6. 用户故事

- 作为研究者，我希望把 AI 编译出的观点和证据拖到合适位置并重新连线，以便形成自己的判断，而不是被动接受 AI 的排列。
- 作为调研用户，我希望一张卡片能显示标题、描述和来源，并按需查看 Markdown、网页、媒体或文件，以便知道节点真正表达什么。
- 作为对话用户，我希望框选多张卡片和连线后一键加入对话，以便让 AI 理解内容及其支持、反驳、依赖等关系。
- 作为知识库用户，我希望先在白板上自由尝试，只在确认后发布或更新 Note，以便 Wiki 只编译已确认内容。
- 作为开源项目维护者，我希望画布运行时是宽松开源协议并且业务 schema 不受 SDK 绑定，以便未来能内部 fork 或替换渲染层。

## 7. 领域定义和产品规则

### 7.1 白板 Board

- 白板属于一个 conversation，包含标题、描述、viewport、revision、卡片和关系。
- 学习研究编译可生成初始白板；用户也可在对话中创建空白板。
- 白板是未发布草稿和空间结构的权威数据。React Flow 只是前端交互投影。
- 一个会话可有多个白板，当前右侧默认打开最近更新的白板。

### 7.2 卡片 Card

所有卡片都有：`id/type/title/description/content/source_refs/x/y/width/height/z_index/collapsed`。

- `markdown`：`content.markdown` 是 Markdown 正文，默认卡片只渲染摘要，选中或进入编辑态后显示正文。
- `web`：`content.url` 必须为 `http/https`；默认显示安全预览卡，用户主动打开后才激活网页或媒体，避免批量 iframe 占用资源。
- `file`：`content.upload_id` 引用现有安全上传资产，不保存任意本地绝对路径。
- `whiteboard`：`content.child_whiteboard_id` 指向同一 conversation 内的子白板；不允许指向自己或构成循环嵌套。

### 7.3 关系 Relation

- 关系必须连接同一白板内两张存在的不同卡片。
- 关系类型为 `related | supports | challenges | depends_on | contains | custom`。
- 线型为 `bezier | straight | smoothstep`，可设方向和箭头。
- 关系拥有 `label/description/source_refs`；双击连线打开编辑器，不把备注挺展为常驻大卡。

### 7.4 白板与 Note/Wiki

- 首次研究编译仍可同时产生初始 Note 和白板，此时 `published_revision == revision`。
- 用户编辑白板后 `revision > published_revision`，笔记视图显示“白板有未发布变更”，但仍展示上一次已发布 Note。
- 用户点击“发布为笔记”或“更新笔记”后，后端才把白板结构编译为 Markdown，更新同一 `note_task_id`，重建向量索引并调度 Wiki contribution。
- 发布失败不修改 `published_revision`，不删除白板，不覆盖上一次已成功 Note。
- 草稿卡片的创建、编辑、拖拽和删除不触发 Wiki。

## 8. 验收标准

### 8.1 布局与基础画布

1. GIVEN 用户打开含白板的学习对话，WHEN 切换到“白板”，THEN 左侧保留会话列表、中间保留对话，右侧切换栏以下全部为可平移和缩放的无限画布。
2. WHEN 用户使用鼠标滚轮/触控板或工具栏，THEN 画布支持缩放、平移、适配全部内容，不出现固定底部详情区挤压画布。
3. WHEN 用户双击画布空白处，THEN 在该画布坐标打开 `Markdown / 网页 / 文件 / 白板` 卡片创建菜单。

### 8.2 卡片与关系

4. GIVEN 任意卡片，WHEN 用户拖拽或调整尺寸并释放鼠标，THEN 位置和尺寸被持久化，刷新后恢复；拖拽进行中不逐帧请求后端。
5. WHEN 卡片未被选中或画布缩放较小，THEN 卡片只显示类型、标题、描述摘要和来源徽标，不同时展开所有正文、网页或媒体。
6. WHEN 用户选中卡片并选择编辑，THEN 可修改标题、描述、来源和对应类型内容；保存失败时本地输入保留并显示可恢复错误。
7. WHEN 用户从一张卡片的连接点拖向另一张卡片，THEN 创建一条可选中关系；自连接、不存在端点或跨白板连接被后端拒绝。
8. WHEN 用户双击关系线，THEN 可编辑关系类型、名称、描述、线型和方向；编辑后标签在连线中点附近显示。
9. WHEN 用户框选、`Shift` 多选、删除、复制/粘贴、`Cmd/Ctrl+Z` 或 `Cmd/Ctrl+Shift+Z`，THEN 仅对当前白板选区生效，并以一次用户操作为一个撤销单元。

### 8.3 卡片类型

10. GIVEN `markdown` 卡片，WHEN 用户退出编辑，THEN 卡片以安全 Markdown 预览显示，代码块、链接和图片不突破卡片边界。
11. GIVEN `web` 卡片，WHEN 用户未主动打开，THEN 不挂载 iframe/视频播放器；WHEN 用户打开，THEN 仅激活当前卡片的安全预览或现有外链流程。
12. GIVEN `file` 卡片，WHEN 持久化，THEN 只保存经验证的 upload/asset id 和公开元数据，不保存客户端任意绝对路径。
13. GIVEN `whiteboard` 卡片，WHEN 用户打开，THEN 进入同一对话内子白板并提供返回父白板入口；循环嵌套请求返回可理解错误。

### 8.4 添加到对话

14. GIVEN 用户选中卡片和关系，WHEN 点击“添加到对话”，THEN 输入区增加一个 `whiteboard_selection` chip，不自动发送消息。
15. WHEN 连线被显式选中但端点卡片未被选中，THEN 系统自动把该关系的两个端点加入选区；未选中的外部关系不进入对话。
16. WHEN 用户发送带 `whiteboard_selection` 的消息，THEN 后端根据 `conversation_id/whiteboard_id/card_ids/relation_ids/revision` 验证归属并重建有界快照，输出卡片标题、描述、内容摘要、来源以及 `A --[关系名称：描述]--> B`；前端自带 snapshot 不得覆盖后端权威内容。
17. WHEN 引用被写入 user message meta，THEN 持久化的 snapshot 是发送时后端生成的有界快照，之后白板修改不改写历史消息。

### 8.5 笔记与 Wiki

18. GIVEN 白板尚未发布，WHEN 用户切换到“笔记”，THEN 显示“尚未发布”和发布入口，不伪造空 Note/Wiki 成功状态。
19. GIVEN 白板已有发布 Note 且发生新编辑，WHEN 查看笔记，THEN 显示上次已发布内容和“白板有未发布变更”提示。
20. WHEN 用户确认发布/更新笔记，THEN 后端将卡片和关系编译为可追溯 Markdown，使用同一 note task id 写入标准 Note，成功后更新 `published_revision` 并异步调度 Wiki。
21. GIVEN Note 已存在，WHEN 白板编译或 Note 持久化失败，THEN 保留白板和上次 Note、不更新 `published_revision`，并返回可重试阶段；WHEN Note 已持久化但向量索引或 Wiki 调度失败，THEN 更新 `published_revision`、保留已发布 Note，返回 `partial` 诊断与对应后处理重试入口，不回滚 Note。

### 8.6 兼容、冲突和性能

22. GIVEN 历史 `LearningCanvas` v1/v2，WHEN 首次打开，THEN 后端可幂等地生成一个新白板，保留节点、关系、来源和绑定 Note；原 JSON 不被修改或删除。
23. GIVEN 两个窗口同时编辑，WHEN 提交的 `base_revision` 落后，THEN API 返回 `409` 和当前 revision，前端保留未保存操作并提供重新加载，不静默覆盖。
24. GIVEN 合成白板包含 500 张紧凑卡片和 1000 条关系，WHEN 在项目基准机 Chromium 执行缩放、平移和单卡拖拽，THEN 需记录首次可交互时间、帧率和持久化请求数；验收门槛为首次可交互不高于 2.5s、连续操作中位帧率不低于 45 FPS、一次拖拽最多一次 mutation 请求。验证证据必须记录机型、系统和 Chromium 版本。
25. WHEN 白板卡片移出可见区、处于折叠态或缩放低于详情阈值，THEN 不挂载重型 Markdown、iframe、视频、PDF 或子白板组件。

## 9. 输入 / 输出样例

### 9.1 卡片

```json
{
  "id": "card_agent_loop",
  "type": "markdown",
  "title": "Agent 循环",
  "description": "规划、工具调用、观察与修订形成的闭环",
  "content": { "markdown": "## 核心\nAgent 不是单次问答……" },
  "source_refs": [
    { "source_id": "note_123", "source_type": "local_note", "title": "Agent 底层逻辑" }
  ],
  "position": { "x": 320, "y": 180 },
  "size": { "width": 300, "height": 180 },
  "z_index": 2,
  "collapsed": true
}
```

### 9.2 关系

```json
{
  "id": "rel_reflection_quality",
  "source_card_id": "card_reflection",
  "target_card_id": "card_quality",
  "relation_type": "supports",
  "label": "改善复杂任务质量",
  "description": "通过显式检查中间结果减少错误累积",
  "line_type": "bezier",
  "direction": "forward",
  "source_refs": ["note_123"]
}
```

### 9.3 加入对话

```json
{
  "type": "whiteboard_selection",
  "whiteboard_id": "wb_agent_design",
  "revision": 18,
  "card_ids": ["card_reflection", "card_quality"],
  "relation_ids": ["rel_reflection_quality"],
  "label": "Reflection 如何影响质量"
}
```

后端编译快照：

```text
[卡片] Reflection
描述：检查中间结果并修订后续策略。
内容：……
来源：note_123

Reflection --[支持：改善复杂任务质量]--> 结果质量
```

### 9.4 反例或失败样例

- 只显示八个灰点和“AI Agent”短标签，无法看到卡片描述、内容和来源。
- 将 React Flow 整个 node object 原样存入 SQLite。
- 拖拽一秒产生几十次 PATCH。
- 客户端传入伪造 snapshot，后端直接放进 LLM prompt。
- 白板一修改就静默覆盖 Note 并触发 Wiki。

## 10. 约束

- 平台 / 设备：源码 Web 和 Tauri 桌面共用同一 React 实现；桌面 backend ready gate 不变。移动端保留内容 tab，不强制三栏并排。
- 性能：重型内容按选中/缩放等级延迟加载；React Flow 启用 `onlyRenderVisibleElements`；自定义 node/edge 及回调必须 memoize。
- 隐私 / 安全：文件只保存经验证资产 id；网页限 `http/https`；白板和上下文 API 验证 conversation 归属；来源内容不作为系统指令。
- 兼容性：旧 `learning_canvas` message、v1/v2 JSON、Note、Wiki、会话模式和 API wrapper 保持可读。
- 成本：日常卡片操作不调用 LLM；只有用户显式发布/更新 Note 时才可调用已选模型。
- 第三方依赖 / License：唯一画布运行时为 `@xyflow/react@12.11.3`，MIT；不使用 Pro 示例代码或模板；保留上游归属说明和第三方 NOTICE。
- 数据：业务实体存 SQLite 表，不保存 React Flow 私有数据结构；多实体操作必须在同一 SQLite 事务中完成并递增 revision。
- 并发：每个 mutation 带 `base_revision`；过期写入返回 409；不使用固定 `.tmp` 或无版本的最后写入胜出。

## 11. 边界场景

- 空数据：空白板显示双击/工具栏创建卡片的引导，不显示“加载失败”。
- 权限/归属：跨 conversation 访问 whiteboard/card/relation 返回 403/404，不暴露对象是否存在。
- 网络失败：保留本地未保存操作，显示重试/重新加载；不清空整个画布。
- 任务中断：发布 Note 中断时不更新链接 revision，不破坏上次 Note。
- 旧数据兼容：旧 Canvas 原文件保留；转换使用 `legacy_canvas_id` 唯一约束保证幂等。
- 大数据量：默认卡片保持紧凑；可见区外不渲染重型内容；超出基准的画布显示性能提示而非崩溃。
- 嵌套循环：子白板链路不能回到任一祖先。
- 卡片删除：同一事务删除其相关关系；当前会话的历史 context snapshot 不被删除。
- 文件缺失：显示资产已缺失占位，保留卡片标题、描述和来源。
- 多窗口冲突：不自动合并删除与编辑冲突，保留本地操作并由用户确认重新应用。

## 12. 与系统事实的冲突检查

- 与 `product-rules.md` 冲突：**有显式增量变更**。当前规则是“Note 是唯一正文，白板是可重建投影”。本需求改为“白板是未发布草稿/空间结构的权威，Note 是用户确认的线性发布快照”。实现完成时必须同步更新产品规则。
- 与 `data-model.md` 冲突：需新增四张 SQLite 表和 `whiteboard_selection` 引用语义；不改写现有 LearningCanvas schema。
- 与 `api-inventory.md` 冲突：需新增 whiteboard CRUD/mutation/publish API，并向 chat/conversation meta 扩展新引用类型；保持 `{code,msg,data}` wrapper。
- 是否会重新引入 `known-pitfalls.md` 问题：已设置防线；不把搜索结果直接当卡片、不双向静默同步 Note、不信任客户端快照、不固定 tmp、不逐帧写后端。
- 是否影响本地数据或线上服务：影响本地 SQLite、迁移包和 Note/Wiki 发布链路；日常编辑不新增远端调用。
- 是否影响用户已确认交互：保留左/中/右布局、“白板 / 笔记”切换、中间对话和添加上下文；用真正卡片画布替代 Sigma 点图。

## 13. 增量 Change Spec

### 13.1 影响范围

- 后端：新增 whiteboard ORM/domain/repository/service/router；扩展 research seed、NoteImportService 更新语义、conversation context resolver 和 migration counts/tests。
- 前端：新增 whiteboard service/controller/React Flow 画布/卡片/关系/工具栏/编辑器；Home 优先渲染新白板，Sigma 仅作为旧数据 fallback。
- 数据库：新增 `whiteboards`、`whiteboard_cards`、`whiteboard_relations`、`whiteboard_note_links`；`Base.metadata.create_all` 幂等建表。
- 文件系统：保留旧 Canvas JSON；不新增一份白板 JSON 双写。
- 依赖：新增定版 `@xyflow/react@12.11.3` 和第三方归属文档。
- 测试：后端 schema/repository/API/publish/context/migration；前端类型/交互契约/build/性能基准；旧学习画布回归。
- 桌面/Tauri/MCP：不新增 native API；需验证 sidecar 初始化、前端静态打包和迁移包仍正常。MCP 本次不新增白板工具。

### 13.2 最小可行改动

1. 以 React Flow 替代研究右侧的 Sigma 白板渲染，保留 Sigma Wiki 页和 legacy fallback。
2. 建立与 React Flow 解耦的白板四表和 revision mutation API。
3. 实现四种卡片、关系编辑、框选上下文、发布 Note 和历史 Canvas 幂等转换。
4. 通过选区摘要态、可见区渲染、拖拽结束后持久化和基准测试控制性能。

### 13.3 成功与失败边界

- mutation 以 SQLite 事务成功且 revision 递增为成功边界。
- Note 发布以 Note 结果文件与 `note_documents` 成功写入为成功边界；向量/Wiki 失败以 partial diagnostic 独立返回。
- 前端 optimistic 交互不代表持久化成功；错误时保留待重试操作。

### 13.4 回滚

- 前端可通过单一 feature flag 回退到 `LearningCanvasCard`/Sigma legacy 视图。
- 回滚代码时不删除新表，旧版会忽略未知表，防止用户白板数据丢失。
- 旧 LearningCanvas JSON 始终保留，可继续显示原研究结果。
- 已成功发布的 Note/Wiki 不因白板 UI 回滚被删除。

## 14. Agent 必答问题

1. 影响哪些已有模块：LearningCanvas model/store/service/router、Home 右侧面板、Chat context refs、NoteImport/Wiki 调度、SQLite 初始化和迁移包。
2. 当前是否已有类似能力：有 Sigma 只读图投影、单节点上下文和 Note/Canvas 双视图，无可编辑卡片白板。
3. 是否和产品规则冲突：有受控的权威性语义变更，实现后更新 product rules；仍然符合“AI 编译，人验证和消费”。
4. 是否和数据模型冲突：需增量新表，不改现有表字段和 LearningCanvas JSON。
5. 是否重新引入 known pitfalls：不；需测试双事实源、固定 tmp、上下文伪造、逐帧写入和发布失败回滚。
6. 是否影响本地数据或线上服务：新增本地 SQLite 数据与迁移语义；只有发布 Note 才影响远端 LLM 和本地 Wiki 后处理。
7. 最小可行改动：单一 React Flow 渲染层 + 四表 + revision mutation + Note 发布 + 旧 Canvas 幂等 seed，不动 Wiki 图谱和会话模式。
8. 需补哪些测试：ORM/schema、事务/冲突、API 归属、嵌套循环、legacy seed、Note 发布/失败边界、引用权威重建、React Flow 交互、前端 build、迁移包和性能基准。

## 15. 需求质量门禁

- [x] 保留用户原始意图和约束。
- [x] 写清用户、场景、痛点和价值。
- [x] 目标是产品结果，实施细节隔离在 Plan/Spec。
- [x] 明确非目标，含手绘、实时协作、工作流引擎和 Pro 依赖。
- [x] 当前事实来自已读系统文档、代码和测试。
- [x] 验收标准可观察，覆盖正常、失败、兼容、冲突和大数据量路径。
- [x] 平台、性能、安全、兼容、成本和 License 约束已明确。
- [x] 已检查 product rules、data model、API inventory 和 known pitfalls 冲突。
- [x] 无密钥、token、私有素材或 Provider payload。
- [x] 无阻塞 Plan/Spec 的开放问题。

## 16. Superpowers 交接

- 已达到 Ready for Plan：是。
- 已生成：
  - `docs/superpowers/plans/2026-08-14-notemeld-semantic-infinite-whiteboard.md`
  - `docs/superpowers/specs/2026-08-14-notemeld-semantic-infinite-whiteboard-design.md`
- 计划必须覆盖：开源依赖、四表数据模型、revision mutation、legacy seed、四种卡片、关系编辑、选区对话上下文、Note/Wiki 发布、迁移、性能和回滚。
- 必须补充验证：后端聚焦 pytest、前端契约/build、数据迁移导出导入、500/1000 性能基准、源码 Web 与 Tauri 手工纵向验收。
