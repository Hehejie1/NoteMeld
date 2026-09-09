# Change Spec：统一 Agent Host 入口与生命周期

日期：2026-08-19
状态：Implemented

## 0. 预检查

- [x] 已阅读 `AGENTS.md`、`CLAUDE.md` 和五份必读系统文档。
- [x] 已阅读 `docs/system/change-spec-template.md`。
- [x] 已搜索 Agent Host、Router、SQLite Store、CLI、ChatComposer、桌面启动与相关测试。
- [x] 已确认改动影响本地 Agent Turn/Event 数据和源码、Web、Tauri、CLI 入口，不新增线上服务。

## 1. 当前系统现状

- `backend/app/routers/agent.py` 已提供 `/api/agent/v1`，Web/Tauri 共用的前端服务和 `scripts/notemeld-agent.py` 已调用该路径。
- 源码入口 `backend/main.py` 与桌面入口 `backend/desktop_entry.py` 共用同一个 FastAPI app 和进程级 `AgentSdkHost`。
- Session 直接复用 `conversations.id`；消息在 `conversation_messages`，Turn/Event 在 `agent_turns` / `agent_events`，不存在独立 Agent Session/Message 表。
- 旧 `/api/chat/ask`、`/api/chat/free`、`/api/chat/free/stream` 和旧 Python Agent package 已从生产入口移除；legacy runtime mode 已 fail-closed。
- 当前 Router 仍直接调用 `agent_store`，入口与持久化边界未完全收口。
- 当前同 Session 门禁采用“查询活动 Turn 后插入”。SQLite 忽略 `SELECT FOR UPDATE`，且没有活动 Turn 唯一索引，真实并发可穿透门禁。
- `create_turn()` 在 SQLAlchemy 2.x 已 autobegin 后再次 `db.begin()`，现有 Store 测试会报 `InvalidRequestError`。
- 前端 `AgentContextRef` 的索引签名与已有 Conversation ref 类型不兼容，前端契约类型检查失败。

## 2. 本次目标

- Web、Tauri、CLI 只经 `/api/agent/v1` 提交 Agent Session/Turn 和消费 Event。
- FastAPI 入口通过无内存状态的 Host lifecycle facade 操作 Agent Store，不直接写 Agent 表。
- 新建 Session 与指定既有 Conversation 的续聊都复用 canonical Conversation/Message/Turn/Event 数据。
- 同一 Session 同时只允许一个非终态 Turn；不同 Session 允许各自存在活动 Turn。
- 保持源码启动、桌面 sidecar 启动和非 Agent CLI 命令不变。

## 3. 明确不做

- 不新增模型调用、ToolDriver、Capability 或 SDK ABI。
- 不改变 Conversation/Message/Turn/Event 的字段语义，不新增第二套状态表。
- 不实现新的审批、取消、steer 或远程 Host 能力。
- 不修改 Note、Wiki、MCP、迁移、上传、发布流程和非 Agent CLI 命令。

## 4. 冲突分析

- 产品规则：不冲突；保留本地优先、源码、桌面、CLI 和既有非 Agent 能力。
- 数据模型：不改变现有表、字段或索引；用 SQLite 写事务落实现有单活动 Turn 规则。
- API：不新增或删除公开 API；保持 `/api/agent/v1` 请求和返回结构。
- Known pitfalls：避免 UI/CLI 双写、第二套内存状态、SQLite 并发竞态、旧 runtime 隐式 fallback 和桌面 ready gate 回退。
- 发布/迁移：不改变 schema 或历史数据；既有 `ensure_agent_schema()` 和 restart recovery 语义保持。

## 5. 影响范围

- 后端：Agent Host lifecycle facade、Agent Router、Agent Store、Event broker 语法修复、源码 lifespan。
- 前端：Agent request type 和 Agent 路径契约测试；ChatComposer 行为不重写。
- CLI：不改命令行为，仅补路径契约覆盖。
- 桌面：不改 Tauri 代码；验证桌面入口复用 `main.app` 和同一前端 Agent service。
- 测试：Store 并发、schema、入口路径、existing Conversation 续聊、前端类型检查。
- 文档：本 Change Spec、current architecture、data model、API inventory、known pitfalls。

## 6. 实施方案

### 后端

- 新增无进程内 Turn map 的 `AgentHostEntry`，只把 Router/startup 命令委托给现有事务 Store。
- Router 不再 import 或直接调用 `agent_store`；Native executor/Event broker 继续作为 Host 内部持久化边界。
- `create_turn()` 在 SQLite `BEGIN IMMEDIATE` 写事务内先校验 Conversation，再检查幂等和活动 Turn；其他数据库使用普通显式事务。这样兼容 SQLAlchemy 2.x autobegin，并让并发创建按数据库事实串行判定。
- 启动恢复通过同一 Host entry 调用，不在 `main.py` 直接写 Agent Store。

### 前端 / Tauri / CLI

- 保持 Web/Tauri 共用 `frontend/src/services/agent.ts`；修正 ref 类型为结构化最小契约。
- 保持 CLI 为 `/api/agent/v1` 薄 HTTP 客户端，不读取或写入 SQLite，不加载独立 Agent loop。
- 保持 Tauri 使用同一 `frontend/dist` 与 `backend/desktop_entry.py -> main.app`。

## 7. 数据变更

- 不新增或修改表、字段、索引和文件结构。
- 历史数据兼容；现有 restart recovery 继续把残留非终态 Turn 置为 `interrupted`，不静默删除数据。

## 8. 接口变更

- 新增/删除接口：无。
- 请求/返回变化：无。
- 错误语义：并发创建同 Session Turn 稳定返回既有 `409 session_busy`。
- UI、Tauri、CLI 调用方继续只使用 `/api/agent/v1`。

## 9. UI/交互变更

- 无新增 UI。
- Web/Tauri 的 ChatComposer 继续 optimistic 展示，但 canonical 消息只由 Host 投影。
- 后端 ready gate、加载态和错误态保持不变。

## 10. 测试方案

- 后端 Store：SQLAlchemy 2.x 创建、同 Session 顺序/并发拒绝、不同 Session 活动 Turn、幂等重放。
- Schema：现有 Agent schema ensure 保持幂等且没有第二套 Session/Message 表。
- 入口契约：前端、CLI 都固定 `/api/agent/v1`；ChatComposer/compat chat 不含旧执行路径；桌面入口复用 `main.app`。
- Conversation：既有 Conversation 创建 Turn 后不新增第二个 Conversation/Session 状态。
- 前端：`pnpm test:contracts`、`pnpm build`。
- 后端：Agent Host focused pytest、compileall；按结果补充 core regression。

## 11. 验收标准

- [x] UI 和 CLI 只调用 `/api/agent/v1`，源码和桌面共用同一 app/Host 生命周期。
- [x] 同 Session 并发 Turn 只有一个成功，另一个得到 `session_busy`。
- [x] 不同 Session 可同时保有活动 Turn。
- [x] 继续已有 Conversation 不创建第二套 Session/Message 状态。
- [x] 旧 Python Agent 入口和隐式 runtime fallback 保持禁用。
- [x] 非 Agent CLI 能力无改动。

## 12. 风险和回滚

- 主要风险：SQLite `BEGIN IMMEDIATE` 会短暂串行化 Turn 创建写事务。
- 触发信号：高频创建 Turn 时出现 SQLite busy；当前事务只包含会话校验、幂等/活动检查和单行插入，持锁时间有界。
- 降级策略：不降级到内存锁或旧 Agent；保留数据库事实源并返回安全错误。
- 回滚：回退 Host facade 和事务修改；无 schema/data 清理。
- 用户可见影响：仅并发重复提交更稳定地返回 409。

## 13. Agent 必答问题

- 影响模块：Agent Host/Router/Store/schema、main lifespan、前端 Agent service、CLI/桌面入口契约测试和系统文档。
- 已有类似能力：已有 `/api/agent/v1`、canonical Conversation 和 SDK Host；本次只补入口边界与并发完整性。
- 产品冲突：无，且强化所有入口共享同一事实源。
- 数据语义冲突：无字段或 schema 变更；数据库写事务落实既有单活动 Turn 规则。
- known pitfalls：重点防止双写、第二状态、SQLite 并发穿透、桌面入口分叉和 legacy fallback。
- 本地/线上影响：影响本地 SQLite Turn 创建事务和所有部署模式的 Agent 请求；不新增远端服务。
- 最小可行改动：Host facade + SQLAlchemy/SQLite 事务修正 + 类型修正 + 目标测试。
- 回归测试：Agent Host focused、前端 contracts/build、入口契约和 core regression。
