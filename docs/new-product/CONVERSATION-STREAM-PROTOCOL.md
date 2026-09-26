# 跨端会话发送与流式响应协议

状态：产品目标协议 v1（本文件是产品契约；不是当前所有端都已实现的 API 保证）。

本协议定义用户消息如何携带文本、附件、引用、模型、授权模式和 Workspace，以及 Agent 如何通过有序事件返回状态、可展示的思考摘要、工具活动和最终回答。各端可以使用不同网络传输，但映射到同一逻辑请求、消息、Turn 和事件语义。

## 1. 核心对象与边界

- **Session**：一段持久对话。用户消息、Agent 消息、系统提示和工具活动都归属 Session。
- **Command**：一次用户提交。由稳定的 `request_id` 幂等标识；进入队列后分配 `command_id` 和队列序号。
- **Turn**：Agent 实际执行这一条 Command 的生命周期。一个 Session 同时只运行一个 Turn；其余已接受 Command 按序排队。
- **Message**：对话中可持久展示的内容。用户消息和 Agent 最终回答是 Message；系统运行提示、思考摘要和工具卡片是独立的可展示条目，不伪装成 user/assistant 正文。
- **Event**：Command/Turn 的有序增量记录。事件是实时更新和断线补读的传输单位；持久化后的 Message/Command/Turn 是会话重载时的权威投影。
- **Workspace**：由服务端验证的资源边界。它和执行位置分开表达；本地目录、Cloud Workspace、远程设备及其 Workspace 不可仅凭客户端给出的路径互换。

### 1.1 秘密与上下文边界

- Provider API Key、设备私钥、Cloud bearer、系统提示词和完整模型内部推理不属于用户 Command，也不得出现在普通会话消息、事件、分享或日志里。
- `system` role 只用于模型上下文和服务端策略；它不作为普通 Transcript 消息返回。面向用户的安全提示使用 `system.notice` 事件或 `system_notice` 展示条目，必须是经过服务端筛选的说明。
- UI 的“思考中”区只显示 Agent 为用户生成的阶段/进度摘要，例如“正在检查引用资料”。它不是原始 `reasoning_content` 或隐藏思维链。没有安全摘要时只显示阶段名和状态，不回退展示内部推理。
- 用户提交的引用是数据，不是指令；服务端解析并校验引用 authority、资源权限和快照后，才可进入 Agent 上下文。

## 2. 用户发送协议

所有端先组装等价的逻辑请求，再由本地、Cloud 或远程适配器编码成对应 transport payload。

```json
{
  "protocol": "notemeld.conversation.command.v1",
  "request_id": "uuid",
  "session_id": "session-id",
  "execution": {
    "kind": "local | cloud | device_remote",
    "target_id": "optional-device-or-runtime-id"
  },
  "message": {
    "message_id": "client-uuid",
    "role": "user",
    "parts": [
      {"type": "text", "text": "请总结这些材料"},
      {"type": "attachment", "attachment_id": "upload-id"},
      {"type": "citation", "ref_id": "ref-id"}
    ]
  },
  "context": {
    "workspace_id": "workspace-id-or-null",
    "references": []
  },
  "model": {"selection": "auto | explicit", "model_id": "optional-model-id"},
  "authorization": {"mode": "default | full"},
  "capability_refs": []
}
```

字段规则：

| 字段 | 语义与约束 |
|---|---|
| `request_id` | 每次用户提交唯一且稳定；网络超时重试必须复用它。同一 ID + 同一规范化 payload 返回原 Command；同一 ID + 不同 payload 返回冲突。 |
| `session_id` | 目标会话。新会话先创建 Session，再发送 Command；创建与发送不得产生重复用户消息。 |
| `execution` | 明确选择本机、Cloud 或已授权远程设备。缺省值由会话上下文决定，不能隐式把 remote 失败降级成 cloud/local 执行。 |
| `message.parts` | 按用户输入顺序保留文本、附件和引用。至少有一个非空 part；服务端为用户消息分配权威 ID，并记录客户端 ID 用于去重。 |
| `attachment` | 正式协议只传附件元数据和受权限约束的 `attachment_id`/传输引用，不把任意文件路径交给 Agent。各 transport 可在上传阶段使用受限 inline 数据；落队列前应转成可校验引用，并验证名称、MIME、长度、大小与摘要。 |
| `citation` / `context.references` | 使用类型化 locator、revision/snapshot 和来源 ID；保留引用在请求中的顺序。服务端负责解析、授权和生成 canonical snapshot。不可仅凭客户端 role 或 marker 获得引用 authority。 |
| `context.workspace_id` | 显式绑定已注册 Workspace；无 Workspace 时为 `null`。附件、引用不能反向修改 Workspace 选择。执行目标和 Workspace 必须分别校验兼容性。 |
| `model.selection` | `auto` 不要求 `model_id`；`explicit` 必须提供当前 authority 下有效的模型 ID。Cloud 和已连接 Cloud 的端只提交组织目录 `model_id`，不传 Provider 地址或密钥。 |
| `authorization.mode` | 仅为 `default` / `full` 请求意图。服务端仍根据工具风险、设备 Grant、Workspace 策略和审批规则作最终裁决；full 不代表绕过审批。 |
| `capability_refs` | 只列用户明确加入的 Skill/插件/Application/Agent 引用及版本/来源标识；适配器再校验宿主能力、权限和可用性。不得传可执行代码作为能力声明。 |

上传元数据规范：`attachment_id`、显示名、MIME、字节数、SHA-256、来源端与可用性。内容字节通过对应端受控上传流程发送；若当前端仍使用 Base64 command 载荷，adapter 必须校验后再持久化，且不能把 Base64 本身作为事件或消息显示内容。

用户引用采用稳定的类型化对象；例如 `note_selection`、`whiteboard_node`、`whiteboard_selection`、`workspace_file`。协议字段应包括 `ref_id`、`type`、不透明资源 ID、revision/locator 和有界显示快照。快照仅用于展示和模型上下文，不能取代服务端 provenance。

### 2.1 接受、排队和用户消息显示

1. 点击发送后，客户端可立即插入一条本地 `submitting` 乐观用户气泡，显示所发文本、附件和引用摘要；它尚未被服务端接受。
2. 服务端校验并持久接受 Command 后返回 `command_id`、稳定队列序号及 `queued|running` 状态。客户端将气泡确认为已发送，并用同一条消息 ID 关联 Command，避免重复插入。
3. 若状态为 `queued`，该用户消息同时出现在会话 Transcript 与“等待中”队列列表；显示队列序号/前方任务数量和可执行操作。队列项是该条用户消息的状态投影，不是另一份消息副本。
4. 收到 `command.started` / `turn.started` 后，队列项转为运行中并从等待列表移走；Transcript 中的用户消息保留。发生审批等待、失败或恢复需求时，在原 Command 上更新状态，不复制消息。
5. 若提交尚未被服务端确认便失败，气泡标为发送失败并保留编辑/同 `request_id` 重试入口。若服务端已接受后断线，不能重发新 Command；先用 `request_id` 查询/重放原 Command 和事件。

目标 Command 状态：

```text
submitting -> queued -> running -> completed
                    \-> failed
running -> waiting_approval -> running
running -> cancelling -> cancelled
running -> needs_attention | interrupted
```

`queued` 是唯一进入等待列表的已接受状态。`submitting` 是本地未确认态；`waiting_approval` 是当前 Turn 暂停，不属于队列中等待执行的后续消息。`failed` 可重试，但新尝试生成新的 `request_id`；只有明确是提交 ACK 丢失时才用原 ID 幂等查询/重试。`needs_attention` 不自动重放有副作用的执行。

## 3. 流式事件信封与顺序

```json
{
  "schema_version": "1",
  "event_id": "event-uuid",
  "sequence": 12,
  "session_id": "session-id",
  "request_id": "uuid",
  "command_id": "command-id",
  "turn_id": "turn-id-or-null",
  "type": "message.delta",
  "created_at": "RFC3339",
  "payload": {}
}
```

- 同一 Session 的已持久事件使用单调递增 `sequence`；同一事件重放保留 `event_id/sequence`。客户端只应用大于本地游标的事件，并按序号去重。
- 事件订阅支持从 `after_sequence`/`Last-Event-ID` 补读；发现缺口时先拉取 Session/Command/Turn snapshot，再继续事件流。断线不能抹掉已显示文本或重复执行 Command。
- 每个 Turn 最多一个终态：`turn.succeeded`、`turn.failed`、`turn.cancelled`、`turn.interrupted` 或 `turn.needs_attention`。终态与完成的 assistant message、引用、产物绑定同一 `turn_id`。
- Assistant final 的增量按 `message_id` 和 `channel=final` 聚合；`message.completed` 给出规范完整文本/内容块以校验增量结果。只有终态成功后 final message 才标记 `completed`。
- 支持流式模型时按 Provider delta 转发。配置 `supports_stream=false` 的模型由 adapter 发出兼容的消息事件（通常为一条完整 delta + completed），客户端使用相同 reducer；协议层不保证每个模型都能逐 token 输出。

## 4. 事件类别与 payload

事件名以下列规范类型为目标；本地 Agent v1 的现有事件名映射见第 7 节。

| 类型 | 必要 payload | Transcript/界面行为 |
|---|---|---|
| `command.queued` | `command_id`, `queue_sequence`, `status` | 确认用户消息；在等待列表显示队列项。 |
| `command.started` / `turn.started` | `command_id`, `turn_id`, `status`, 可选 `execution_label` | 状态转运行中；关联 assistant 占位消息。 |
| `system.notice` | `code`, 安全文案 `message`, `severity`, 可选 `action` | 作为 system notice 展示，例如连接中断/恢复；不可包含 system prompt、原始异常、密钥或 Provider payload。 |
| `assistant.thinking.started` | `message_id`, `phase`, 可选安全 `summary` | 展示思考区标题“思考中”和当前阶段；可以折叠，运行期间更新。 |
| `assistant.thinking.delta` | `message_id`, `delta` 或替换用 `summary`, `phase` | 仅追加/替换面向用户的简短进度摘要。不得传输/显示 raw chain-of-thought 或未经筛选的 reasoning token。 |
| `assistant.thinking.completed` | `message_id`, `phase` | 将对应阶段折叠为已完成的思考摘要，不将摘要并入最终回答正文。 |
| `tool.started` | `call_id`, `tool_name`, 用户可读 `summary`, 可选脱敏 `arguments_summary` | 新建工具活动卡片；不渲染原始参数、秘密或完整内部 schema。 |
| `tool.progress` | `call_id`, `summary`, 可选 `progress` (0..1) | 更新同一工具卡片。未知/不可估算时不伪造百分比。 |
| `tool.completed` / `tool.failed` | `call_id`, `status`, 安全 `result_summary` 或安全 `error{code,message}` | 显示可读结果摘要与状态；可折叠查看允许展示的结构化结果。原始异常、凭据和受保护 payload 不出现在 transcript。 |
| `approval.required` | `approval_id`, `call_id`, `risk`, `summary`, `deadline?`, 用户可见 `requested_scope` | 进入 `waiting_approval`，展示请求操作/目标/后果及批准、拒绝入口。 |
| `approval.resolved` | `approval_id`, `decision`, `status` | 显示已批准/已拒绝；Turn 是否恢复以 Agent runtime 后续状态事件为准。 |
| `message.started` | `message_id`, `role=assistant`, `channel=final`, `format=markdown` | 建立唯一最终答复气泡，显示流式占位状态。 |
| `message.delta` | `message_id`, `channel=final`, `delta` | 按原顺序追加到同一最终答复气泡；保留 Markdown 未完成片段，渲染器不得按 token 破坏格式。 |
| `message.completed` | `message_id`, `channel=final`, `content`, `format`, `sources[]`, `artifacts[]` | 以规范完整内容替换增量缓冲，提交引用/产物元数据；Message 进入完成态。 |
| `turn.succeeded` | `turn_id`, `assistant_message_id`, `status=completed` | 关闭思考/工具活动态并确认 final message；不能仅凭 HTTP 200 判断完成。 |
| `turn.failed` | `turn_id`, `error{code,message,retryable}` | 关闭流式态，保留用户消息、已完成工具和可读部分结果；错误说明重试是否安全。 |
| `turn.cancelled` / `turn.interrupted` / `turn.needs_attention` | `turn_id`, `status`, 可选安全原因 | 显示对应终态和恢复动作；不伪装成成功回答。 |

最终答复的 `sources[]` 使用结构化来源（如 `source_id/type/title/locator/url?`）；`artifacts[]` 使用不透明 artifact ID、显示名、媒体类型、大小摘要和授权读取句柄。消息正文中可放 citation marker，但实际 source/card 由结构化数据驱动。来源和产物不得以本机绝对路径作为跨端 ID。

事件 payload 示例（省略共同的 event envelope）：

```jsonl
{"type":"system.notice","payload":{"code":"attachment.ready","severity":"info","message":"附件已加入当前任务"}}
{"type":"assistant.thinking.started","payload":{"message_id":"process:turn-1","phase":"analysis","summary":"正在检查引用资料"}}
{"type":"assistant.thinking.delta","payload":{"message_id":"process:turn-1","phase":"analysis","delta":"已定位到 3 份与问题相关的材料。"}}
{"type":"tool.started","payload":{"call_id":"call-1","tool_name":"workspace.read","summary":"读取 Workspace 文件","arguments_summary":"架构资料目录"}}
{"type":"tool.completed","payload":{"call_id":"call-1","status":"completed","result_summary":"已读取 3 个文件"}}
{"type":"message.started","payload":{"message_id":"answer:turn-1","role":"assistant","channel":"final","format":"markdown"}}
{"type":"message.delta","payload":{"message_id":"answer:turn-1","channel":"final","delta":"## 结论\n当前架构有 2 个风险。"}}
{"type":"message.completed","payload":{"message_id":"answer:turn-1","channel":"final","content":"## 结论\n当前架构有 2 个风险。","format":"markdown","sources":[{"source_id":"src-1","type":"workspace_file","title":"架构说明","locator":"file-ref-1"}],"artifacts":[]}}
{"type":"turn.succeeded","payload":{"turn_id":"turn-1","assistant_message_id":"answer:turn-1","status":"completed"}}
```

示例中的思考文本是进度摘要，不表示模型内部 reasoning；`tool.started` 不承载完整模型参数，工具真实结果只通过授权后的安全摘要/结果投影提供。

## 5. “思考中”与内容分层

参考附件中的对话布局，Transcript 按用户可理解的执行顺序显示：

```text
用户消息
  系统状态提示（如需要）
  思考中 ▾ / 已完成的思考摘要
  工具活动卡片（开始 -> 进度 -> 结果）
  最终回答（Markdown 流式正文、引用和产物）
```

- “思考中”是一个可折叠的过程摘要区，展示当前阶段、Agent 提供的安全进度说明和工具活动。没有摘要时只展示“正在分析”等状态，不显示空白正文。
- system prompt、开发者指令、模型内部 reasoning、未执行的工具草稿不是可展示消息。客户端不能把 `reasoning.delta`、Provider 原始 `analysis` 或 system role 内容映射为思考区。
- 面向用户的系统事件不是 `role=system` 消息；它是独立、可筛选的状态提示，按严重程度决定常驻时间，关键审批/失败保留在时间线。
- 工具调用和工具结果分别有 `call_id` 关联；结果不替代最终回答。Agent 可在多个工具调用之间多次更新思考摘要，完成工具循环后再流式返回最终回答。
- 用户连续发送消息时，每个请求拥有独立 Command/Turn/assistant message ID；不能将不同 Turn 的 delta 合并进同一回答气泡。

## 6. 错误、恢复与队列一致性

- 提交 API 的成功表示 Command 已持久接受；非成功 HTTP 响应不产生已接受队列项。`429`、授权失败、Workspace/model 不可用需保留输入并给可操作错误。
- 已接受 Command 的 Provider 错误以 `turn.failed` 事件终结，不得只返回 HTTP 错误而丢失已持久用户消息。
- 队列和 transcript 使用相同 `request_id/command_id/message_id` 做 join。页面重载先读 snapshot，再从事件游标续读；同一 user message 不因响应 ACK 和 snapshot 各自到达而重复。
- Cloud、移动端缓存与远程 Host 的队列事实以其 authority 返回的 Command 状态为准。移动端离线只读；离线待发草稿如被产品支持，明确标 `not_submitted`，不能伪装为服务端 `queued`。
- 附件上传失败时 Command 不得引用不存在/校验失败的附件；用户消息草稿保留并标记失败。已接受任务发生恢复/重试须遵循 idempotency 和副作用恢复契约。

## 7. 现有入口与目标映射

| 场景 | 当前入口/传输 | 当前事实与协议映射 |
|---|---|---|
| 桌面、本地 Web/Tauri/CLI | `POST /api/agent/v1/sessions/{id}/turns` + `GET /api/agent/v1/turns/{turn_id}/events` SSE | 请求已有 `input.text/attachments/context_refs`、`model`、`idempotency_key`、`linked_task_id`、`asset_content`。SSE 已带 `schema_version/event_id/sequence/type/payload`；Host 发 `message.delta/completed`、`reasoning.delta`/`thinking.delta`、工具/审批及 Turn 终态。该路由对同 Session 并发返回 `409 session_busy`，当前没有多个 Command 的持久等待队列。 |
| Cloud Web/Cloud Agent | 流式：`POST /v1/cloud/sessions/{id}/stream`（SSE）；兼容：`POST /v1/sessions/{id}/commands`；`GET /v1/sessions/{id}/commands`、`events?after=`、snapshot | Command 已持久队列、幂等并按 Session 顺序领取；请求为 `request_id/input/model_id/authorization_mode`，Workspace 从云端 Session 绑定。`/stream` 以 SSE 逐块转发 provider 的 `reasoning`（思考）与 `delta`（正文），结束写 `turn.completed`（payload 带 output 与 reasoning 数组）；provider I/O 阻塞，服务端在线程池迭代。另有 `/terminal` 在分配文件夹内执行受限 shell。完整字段、帧格式与约束见 [CLOUD-IMPLEMENTATION-SPEC](./CLOUD-IMPLEMENTATION-SPEC.md)。 |
| 移动端本地 Agent | Agent v1 native adapter + 本地事件读取 | 应复用 Agent v1 Session/Turn/Event 语义；按平台 adapter 序列化附件和引用，离线不可冒充 accepted queue。 |
| 移动端 Cloud Agent | Cloud commands/events adapter | 当前 Android adapter 提交命令后轮询 Cloud events，并只抽取部分 output/status；后续应还原完整公共事件和等待队列投影。 |
| 远程设备会话 | LAN-first / 加密 Relay 到目标设备 Host | transport 搬运加密命令/事件帧；Cloud Relay 不读写消息明文、不伪造队列 ACK 或 Agent 结果。目标 Host durable enqueue 才能确认 `received/queued`，之后消息/Turn/Event 仍由目标 Host authority 产生。 |

兼容期规则：为旧客户端保留现有 endpoint/字段，由 adapter 将旧请求和事件映射到此逻辑协议；不要让每个 UI 自己猜 event payload。将 `reasoning.delta`/`thinking.delta` 映射为公开思考摘要前，必须确认来源已经是安全、面向用户的摘要；否则只显示运行状态。

## 8. 页面与验收映射

- D01/D03、C03、M01/M02 的发送组件都呈现同一逻辑状态：submitting、queued、running、waiting_approval、completed、failed、cancelled、needs_attention。
- D03/C03/M02 的 Transcript 与等待列表必须以稳定 ID 连接同一用户消息；工具卡、系统提示、思考摘要、最终回答是有类型的不同投影。
- 逐事件验收：按顺序读取完整 Transcript 与增量事件时得到相同的用户消息、思考摘要、工具调用/结果、sources/artifacts 和最终答案；断线后从游标恢复无重复/无遗漏；终态最多一次。
- 跨端验收：桌面、Cloud Web、移动端和远程设备给同一逻辑输入后遵守相同 envelope、校验、授权/Workspace 语义和 UI 状态；只允许 transport 编码、上传分片和呈现布局不同。
- 安全验收：Provider Key、系统提示词、设备 secret、原始模型内部推理和未脱敏工具参数在 API 响应、事件日志、Transcript、分享视图均不可见。

## 9. 当前实现状态

这是要收敛的目标契约。已存在的 Agent v1 SSE 和 Cloud command/event 基础可以复用；**Cloud 已落地 `/stream` 真流式（reasoning + delta）与 `/terminal` 受限终端**（见 [CLOUD-IMPLEMENTATION-SPEC](./CLOUD-IMPLEMENTATION-SPEC.md)）。本地持久队列、统一请求 DTO、移动端完整事件 reducer、可恢复等待列表及事件类型的一致化仍需按实现 Change Spec 逐步落地。实现时以 `docs/system/`、代码和测试更新后的事实为准。
