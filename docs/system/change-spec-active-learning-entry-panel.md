# Change Spec：显式学习入口、默认研究源与右侧学习面板

日期：2026-08-12
状态：Implemented / Verified
Canonical requirement：`docs/requirements/2026-08-01-notemeld-agent-deep-learning-canvas.md`
Spec：`docs/superpowers/specs/2026-08-11-notemeld-active-learning-space.md`
Plan：`docs/superpowers/plans/2026-08-12-notemeld-learning-mode-entry.md`

## 0. 预检查

- [x] 已阅读 `docs/system/current-architecture.md`
- [x] 已阅读 `docs/system/product-rules.md`
- [x] 已阅读 `docs/system/data-model.md`
- [x] 已阅读 `docs/system/api-inventory.md`
- [x] 已阅读 `docs/system/known-pitfalls.md`
- [x] 已搜索相关前后端代码、数据契约和测试
- [x] 已确认现有 LearningCanvas、研究搜索和学习状态机可复用
- [x] 不修改线上服务；只影响本地 API、会话消息和工作空间 canvas 文件

## 1. 当前系统现状

- 相关模块：`LearningCanvasService`、`ResearchSearchConfigManager`、learning router/tools、`ChatComposer`、`HomePage`、`LearningCanvasCard`、消息 renderer。
- 相关入口：首页输入框目前只有聊天/笔记；Agent 可在自由聊天时自行发现 learning tools；learning REST API 已存在。
- 相关数据：会话仍为 SQLite `chat|note`；完整画布位于 `workspaces/{conversation_id}/canvases/{canvas_id}.json`；会话只保存轻量 `learning_canvas` 消息。
- 当前行为：Settings 可关闭 academic/GitHub；直接 canvas API 的默认 `external_scopes=[]`；完整学习卡内嵌在对话流；纯 chat 页面没有右侧面板。
- 当前限制：用户无法稳定、显式触发学习；文本/URL 自动模式选择会覆盖未来的学习选择；学习消息不承担摘要和引导职责。

## 2. 本次目标

- 用户问题：现有界面看不到“如何进入白板学习”，配置项也把默认能力暴露成用户负担。
- 用户可见行为：输入区出现“学习”；提交后自动研究本地内容、论文、GitHub 和已配置的普通网页；对话返回摘要引导，右侧展示完整学习面板。
- 系统内部行为：学习提交直接调用现有 canvas API，不依赖模型路由碰运气；baseline scopes 始终包含 academic/GitHub；最新 canvas 驱动右侧面板。
- 保留行为：聊天、笔记、上传、桌面 ready gate、旧学习消息和旧配置文件保持兼容。

## 3. 明确不做

- 不新增 `conversation.mode=learning`，不做数据库迁移。
- 不实现多 Agent、自动批量采集外部正文或新 provider。
- 不改变 mastery 证据规则，不把展示视为掌握。
- 暂不实现 LLM 生成的长篇课程报告；对话摘要使用可追溯 canvas 数据。

## 4. 冲突分析

- 产品规则：符合“AI 编译知识，人验证和消费”；必须同步把“用户启用的学术/GitHub”改为默认基线。
- 数据模型：无字段语义冲突；`learn` 仅是前端 intent，持久 mode 仍为 `chat`。
- API：POST canvas body 保持向后兼容；`external_scopes` 变为可选且不能关闭基线来源。
- known pitfalls：重用 store 的原子更新；完整 canvas 不塞进 SQLite 消息；外部失败保留本地结果；不破坏 ready gate。
- 运行/发布：浏览器和桌面共享同一 React/API 路径；无 Tauri、CLI、MCP、迁移和打包入口变更。

## 5. 影响范围

- 后端：research config、canvas service、learning router、Agent learning tool、对应 tests。
- 前端：learning service、ResearchSearch、ChatComposer、HomePage、message renderer、LearningCanvasCard、contract tests。
- 数据：继续读取旧 `enabled_scopes`，写配置时不再依赖该字段；不清理用户数据。
- 文档：requirement/spec/plan/system architecture/product rules/API inventory/test evidence。

## 6. 实施方案

### 后端

- `ResearchSearchConfigManager.get_learning_scopes()` 固定返回 `academic, github`，仅当普通网页 provider 配置完整时追加 `web`。
- `LearningCanvasService.create_canvas()` 将调用方 scopes 与默认 scopes 合并；provider 单点失败仍写入 `external_errors`。
- canvas 摘要消息增加来源类型、推荐起点等小型 meta，content 形成可读学习引导；完整 nodes 仍只在 JSON artifact。
- API 的 `external_scopes` 改为可选；旧请求仍被接受。

### 前端

- `ComposerMode` 新增 `learn`，但 `ensureConversation` 映射为持久 `chat`。
- `submitLearning` 保存用户输入、创建 canvas、重载会话、导航；loading/error 复用 composer 状态和 toast。
- renderer 把 `learning_canvas` 变成摘要气泡；Home 读取最新 canvas，在右侧渲染完整卡片。
- ResearchSearch 删除范围 switches，只保留普通网页 provider 配置和说明文字；GitHub 无需用户配置。

## 7. 数据变更

- SQLite：无新增表/字段/迁移。
- 文件结构：无变化。
- 历史兼容：旧 canvas 和旧消息继续读取；缺少新增 meta 时摘要降级使用 content/goal/node_count。
- 回滚：代码回滚后 canvas JSON 和旧配置仍可读取，无数据清理。

## 8. 接口变更

- 修改 `POST /api/conversations/{cid}/learning-canvases`：`external_scopes` 可省略；服务端始终合并 academic/GitHub。
- `GET/PUT /api/research-search/config`：保留 wrapper 和密钥脱敏；前端不再发送范围开关。旧 `enabled_scopes` 输入保持兼容但不能关闭基线来源。
- 无删除接口；需同步 `docs/system/api-inventory.md`。

## 9. UI/交互变更

- 路径：选择学习 → 输入主题 → 提交 → 构建中 → 对话摘要 + 右侧学习面板。
- 加载：任何异步操作前建立跨 composer 的共享提交锁，并持久化构建中消息；创建请求不设前端固定超时。成功后仅在用户仍停留于发起页时导航，避免卸载后重复提交或旧请求劫持当前页面。
- 失败：toast 显示服务端安全错误，并把失败状态写入同一构建消息；不伪造 canvas，不删除旧面板。
- 成功：重载会话后自动展开学习面板；同时有笔记时可切换。
- 移动端：使用内容 tab；不强制双栏。

## 10. 测试方案

- 后端：默认 scopes、Web 配置判定、旧开关不能关闭基线、compact guide message、API 可省略 scopes。
- 前端契约：第三个学习标签、显式 create API、右侧 LearningCanvasCard、inline renderer 不再渲染完整卡、Settings 无 scope switch。
- 构建：`pnpm test:contracts`、`pnpm build`。
- 回归：learning focused pytest、backend full pytest、core regression。

## 11. 验收标准

- [x] 无需设置即可看到并使用学习模式。
- [x] academic/GitHub 默认检索；普通网页只在配置可用时加入。
- [x] 对话显示总结引导，右侧显示完整且可继续操作的学习面板。
- [x] 同会话笔记与学习空间可切换，历史数据不丢。
- [x] 刷新/重启可恢复最新学习面板。

## 12. 风险和回滚

- 风险：外部研究延迟使前端等待较久；provider 失败导致来源不完整；旧消息 meta 不全。同步创建请求不设前端固定超时，构建状态持久化并由共享提交锁防止重复创建；canvas 返回成功后，消息刷新或导航失败只能降级提示，不能把已存在的 canvas 标记为失败。
- 信号：创建 API 503、external_errors、前端 toast 或空 panel。
- 降级：外部失败时用本地 canvas；摘要按缺失字段降级；普通聊天/笔记不受影响。
- 回滚：移除 learn intent 和右侧选择逻辑，恢复 inline renderer；保留 canvas 文件。

## 13. Agent 必答问题

- 影响模块：输入提交、研究 scope 解析、canvas 摘要消息、Home 分栏、Settings 与契约测试。
- 类似能力：已有 canvas API/Card/Agent tools，可直接复用。
- 产品冲突：无；本次修正了把默认能力错误变成配置负担的问题。
- 数据语义：无冲突，不新增持久 mode。
- 历史坑：通过原子 store、compact message、ready gate 和 local-first 降级规避。
- 数据/服务：只新增本地 canvas 与会话消息；外部仅调用既有 arXiv/GitHub/可选 Web API。
- 最小改动：显式前端 intent + 后端默认 scope helper + right panel projection。
- 回归测试：scope/API/service tests、frontend source contracts、build、backend/core regression。
