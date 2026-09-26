# Change Spec：跨端会话发送与流式响应协议

状态：产品协议已拟定；运行时改造未在本次文档变更中实施。

## 1. 当前系统现状

- 桌面 Agent v1 已有统一 `/api/agent/v1` Session/Turn API。Turn 请求支持 `input`（文本或对象）、附件、context refs、模型、幂等键、linked task 和 asset content；同一 Session 同时只能创建一个活动 Turn，忙时返回 `409 session_busy`。
- 桌面 SSE 事件含 schema version、event ID、sequence、type 和 payload，可从序号重放。已有 `message.delta/completed`、`reasoning.delta`/`thinking.delta`、工具、审批和 Turn 终态事件。桌面 UI 当前将 reasoning/thinking delta 写入 assistant streaming message，工具卡只显示部分字段。
- Cloud Session Command 已持久排队并顺序执行，支持幂等 request ID 和 event cursor；请求字段主要是 text、附件、model ID 和 authorization mode，Workspace 从 Session 绑定。Cloud Agent Provider 请求当前为 `stream=false`；Cloud event API 是有序分页读取，不等价于逐 token SSE。
- Android Cloud adapter 轮询 event API 并抽取 output/status；不同移动端与远程 Host adapter 的事件完整度不一致。LAN/Relay 只传递到 Host 的加密远程帧，不是消息 authority。
- 真实入口、能力和差异详见 [`docs/new-product/CONVERSATION-STREAM-PROTOCOL.md`](../new-product/CONVERSATION-STREAM-PROTOCOL.md) 第 7 节、`docs/system/api-inventory.md` Agent v1/Cloud 部分和对应实现测试。

## 2. 本次目标

- 建立各端同构的逻辑 Command 输入，覆盖文本、附件引用、消息引用、Workspace、执行位置、模型选择、授权模式和已选能力。
- 用户消息立即进入 Transcript；只有服务端持久接受的 Command 才显示为已发送/queued。排队 Command 同时进入等待列表，且列表与 Transcript 通过稳定 ID 共用一条消息。
- 定义 Agent 过程事件、system notice、用户可见思考摘要、工具调用/结果、审批、最终回答 delta、sources/artifacts 和唯一 Turn 终态。
- 所有终端使用单一事件 reducer 和可恢复序号。各 transport 适配到同一逻辑协议，不能各端猜测 payload。
- 思考 UI 只展示面向用户的安全阶段摘要；不展示原始内部 reasoning、system prompt、凭据或未脱敏工具参数。
- 文档明确区分目前实现和目标状态；本次不把目标协议标记为所有端已经支持。

## 3. 明确不做

- 本次文档任务不修改数据库、API、Agent SDK schema、Cloud worker、移动端 UI 或 Provider streaming。
- 不在新产品原型中伪造生产端点已经支持的功能，不新增第二套 Agent loop/状态机。
- 不改变当前审批、设备 Grant、Cloud Workspace 权限或本地 API Key authority。
- 不把隐藏的模型思维链作为产品数据契约；可展示的是安全摘要和真实的工具/状态事件。

## 4. 冲突分析

- `product-rules.md`：需保留统一 Agent Host/SDK、单活动 Turn、授权门禁、Cloud 组织模型目录、离线只读和端侧密钥边界。目标协议兼容这些规则。
- `data-model.md`：当前 Conversation/Turn/Event/Command authority 不统一存于一张表；新逻辑协议必须是适配层 DTO，实际数据仍由 Local Host、Cloud 或远程 Host authority 持有。
- `api-inventory.md`：当前各端请求字段与流式能力有差异。该 Change Spec 仅记录目标，不将目标字段写进当前 API 清单。
- `known-pitfalls.md`：需避免 duplicate command、丢失事件、重复副作用、伪造 ACK、跨端把缓存当真、错误/secret 泄露及第二状态机。
- 运行影响：本次只新增设计文档与 Change Spec，不改运行 API、数据、打包或线上服务。

## 5. 目标实施范围

- 逻辑协议与共享 DTO/schema、Local Agent v1 adapter、Cloud command/event adapter、移动端事件 reducer、远程 Host relay adapter。
- 需要独立评估 Local Host 是否新增持久 Command queue；Cloud queue 是当前已有 queue，不能直接假设同 schema。
- 影响 D01/D03、C03、M01/M02 和对应 `feature-registry.json`；实现时同步系统 API/data/current architecture/pitfalls 文档。
- 测试目标包括 payload canonicalization/idempotency、附件/引用权限校验、队列顺序/恢复、SSE/event replay、事件 reducer、重连 gap、单终态和 secret/redaction。

## 6. 实施方案要点

### 请求

- 先定义 `notemeld.conversation.command.v1` 稳定 envelope；附件使用授权资源引用，引用需带受校验 locator/revision，执行位置和 Workspace 分列，模型使用 authority 内 model ID，权限使用 default/full 请求意图。
- 基于规范化 payload 计算幂等摘要；同 request ID 不同 payload 稳定冲突。
- ACK 返回稳定 user message/command/turn IDs 和权威状态；UI 的 `submitting` 乐观态与 server `queued/running` 严格区分。

### 事件/流

- 以 session 单调序号持久事件为断线重放事实；所有 endpoint adapter 使用一致 envelope 与终态语义。
- 规范化队列、运行、thinking summary、tool/approval、final message delta/completion、sources/artifacts、failure/cancel/recovery 事件。
- final 答复事件增量可回放；Cloud 当前 non-stream Provider 需后续设计是否启用 Provider streaming，或只在 adapter 完成时发送一段兼容 delta。
- UI 不消费 raw reasoning delta；安全 thinking summary 作为独立 channel。

### 队列与终端

- 统一明确持久队列 authority 与 per-session 顺序；仅已 ACK 的 queued 命令进入等待列表。
- `waiting_approval` 是当前 Turn pause，不进入 queued list；超时/崩溃恢复继续走既有 runtime recovery，不自动重放副作用。
- 一个 Turn 只产生一个终态事件，结果 Message 与其终态关联。

## 7. 数据/API 变更清单（实施阶段填写）

- 本次文档提交：无 schema/API/data mutation。
- 后续实现：根据最终 adapter/schema 选择兼容新增 API 字段或版本化 DTO；不得未经评估直接改 Agent Event schema 1 或 Cloud command 既有字段。
- 若持久化队列或事件补足涉及新的表/列、状态和错误语义，需另外更新 data-model、api-inventory 和 current-architecture，并提供迁移/兼容方案。
- 历史会话及 legacy messages 必须保持读取；客户端升级期间服务端兼容旧 payload。

## 8. 验收标准

- [x] `docs/new-product/CONVERSATION-STREAM-PROTOCOL.md` 明确用户提交 envelope、附件/引用/model/authorization/Workspace 字段。
- [x] 文档区分 optimistic submitting、持久 accepted queue、running、approval wait 和终态，并规定等待列表不产生重复消息。
- [x] 文档覆盖 system notice、思考摘要、工具调用/结果、审批、最终回复流式 delta、sources/artifacts、终态、断线恢复与安全边界。
- [x] 文档标明各端当前入口/差异和目标/已实现边界。
- [ ] 运行时实现和对应测试通过（不属于本次文档变更）。

## 9. 风险与回滚

- 风险：逻辑模型比当前 Cloud/Local 存储模型更统一；实现若跨 authority 共享底层表会越过职责边界。通过协议 adapter 保持逻辑一致、authority 分离。
- 风险：当前 `reasoning.delta` UI 映射不能直接复用为安全思考摘要。需在 adapter 侧生成/筛选用户可见摘要，并测试禁止原始推理泄露。
- 回滚：本次仅新增协议文档与 Change Spec，并调整导航链接；可单独移除新增文件和对应链接，不触碰运行数据。

## 10. 必答问题

- 影响模块：桌面 Agent Host/UI，Cloud command/agent/event，移动端 adapter/reducer，远程 Host relay adapter 和新产品功能地图。
- 类似能力：Agent v1 SSE 与 Cloud command/event 已分别存在，但输入/事件 payload、队列和流式正文能力尚未统一。
- 产品规则冲突：无；目标明确保留 Host/SDK authority、审批、Grant、组织模型目录和离线只读。
- 数据字段冲突：不直接合并现有表；逻辑协议需由各 authority 分别映射。
- known-pitfalls 风险：重复副作用、ACK 丢失、事件游标 gap、缓存误判和 raw reasoning/secret 泄露均需覆盖。
- 运行/线上影响：本次无。
- 最小改动：新增跨端协议文档、Change Spec 和导航链接；后续实现另开实施变更。
- 验证：本次检查了文档链接、Change Spec 内容与 `git diff --check`；未运行产品文档验证器或测试。实现阶段补充后端 API/queue contract、前端 reducer、Cloud/mobile adapter 与跨端 replay/security 测试。
