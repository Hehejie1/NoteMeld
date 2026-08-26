# NoteMeld Agent Knowledge Runtime 总体架构决策

日期：2026-08-23
状态：Direction Confirmed；一期范围以 ../requirements/2026-08-24-note-agent-plugin-foundation.md 为准

## 1. 执行摘要

NoteMeld 的长期目标不是再做一个带 AI 的笔记软件，而是建立一个以 Note 为最小知识原子、由 Agent 驱动、可被插件扩展、可跨端使用、也可被其他 Agent 复用的个人知识库运行时。

推荐采用“本地优先 + 可选同步服务”的分层架构：

```text
外部 Agent / MCP / SDK Client
            │
      Agent Access Protocol
            │
NoteMeld Application: Desktop UI / Host / Adapters / Plugin Control
            │ public contracts
notemeld-agent-sdk L2: Stateless Note Agent / Generic Note Model
            │
notemeld-agent-sdk L1: Stateless Agent Loop
            │
Shared SQLite file with isolated table and migration domains
            │
FTS / Vector / Wiki / Graph are derived projections
```

第一阶段只完成一个基础闭环：

> 一个 Agent 或外部 Agent 能发现能力，读取个人知识库，通过插件完成任务，把结果写成新的 Note，并保留来源、关系、操作记录和可恢复状态；用户可以在同一台电脑上的另一个 Agent、CLI 或 MCP Client 中继续使用这些内容。

关键取舍：

1. notemeld-agent-sdk 分为两层：L1 是完全无业务状态的通用 Agent loop；L2 定义通用 Note 模型和无业务状态 Note Agent。视频、网页、IM、白板等业务仍不得进入 L1/L2。
2. SQLite 是第一阶段权威事实源；全文、向量、图谱和 Wiki 都是可重建的派生投影。
3. 所有有副作用的 Agent 行动都经过 capability、authority、幂等 ledger 和审计事件。
4. 插件优先采用公开标准协议，从 GitHub/Gitee Release 安装标准包并校验 manifest、版本和 hash；不自动执行仓库安装脚本。
5. Agent 可以为 NoteMeld Application 和插件生成升级 candidate，但一期不自动激活；notemeld-agent-sdk 永远不在 Agent 自升级范围内。
6. 一期只交付桌面端和同机外部 Client；手机、Web 和跨设备同步后置。

## 2. 当前仓库事实与差距

核对当前代码和文档后，现状是：

- NoteMeld backend 已有 FastAPI、SQLite、本地文件存储、笔记导入、Wiki 抽取、知识检索、MCP 和迁移。
- frontend 是 React 19 + Vite + TypeScript + Zustand；desktop 使用 Tauri v2 启动 Python backend sidecar。
- backend/app/agent_host 已通过 notemeld-agent-sdk Python binding 进入统一 Agent runtime；Web、Tauri 和 CLI 使用 /api/agent/v1。
- SDK 已有 Rust canonical loop、事件 envelope、审批、取消、tool policy、trace、capability registry、plugin manifest、模型路由、同步 operation、multi-agent DAG 和 evidence-gated promotion 等基础 crate。
- 但 NoteMeld 的笔记事实仍分布在 SQLite note_documents、note_results 文件、Wiki 文件和 Chroma 中；SDK L2 尚未形成已确认的通用 Note 模型和无业务状态 Note Agent。
- SDK 的 plugin loader 主要负责 manifest 校验和 capability 注册；安装、沙箱、签名、生命周期和真实 transport 仍是宿主职责。
- sync operation 尚无账户、密钥、服务端 transport、冲突 UI；promotion 尚未完全映射到产品层的 Agent profile 和插件版本。

结论：当前基础设施相当充足，但第一阶段的关键不是继续堆 capability，而是收敛领域权威、宿主边界和跨端协议。

## 3. 多 Agent 研讨结果

### 产品架构师

支持 Note 原子、Agent 主体、插件扩展。反对第一阶段同时承诺面向所有人、所有端、任意 Agent、自主开发插件和自升级。最大风险是用户无法理解产品到底是笔记库、Agent 工作空间还是开发平台。建议推迟插件市场、复杂图谱 UI、开放式自修改和多人实时协作。

### Agent Runtime 架构师

支持以 Rust canonical loop 为中心，宿主通过 driver/port 接入 Note、模型和插件。反对前端、FastAPI 和 SDK 各自维护状态机，也反对插件直接写 SQLite。必须先定义 request idempotency、tool ledger、checkpoint、authority 和 terminal outcome。

### 数据库架构师

支持 SQLite 作为本地权威源，索引和 Wiki 作为投影。反对把 Markdown 文件、向量库或 graph.json 当作同步事实源。必须先定义 Note ID、版本、来源、relation 类型和冲突规则。

### 插件平台架构师

支持 manifest、capability、permission 的组合。反对允许任意代码、网络和文件访问的插件市场。manifest 只声明请求，不授予权限；不兼容、缺依赖、缺 license 或权限被拒绝时必须 fail closed。

### 分布式系统架构师

支持本地优先加同步服务；权威变更使用 append-only operation，derived index 只发 rebuild signal。反对云端唯一事实源和无条件 last-write-wins。必须定义 replica identity、cursor、幂等、冲突表现和恢复协议。

### 安全与隐私专家

支持本地优先、最小权限和默认脱敏 trace。反对把自升级解释为任意代码自修改或自动发布。必须区分用户、设备、Agent 和插件身份，权限不能由模型输出或 manifest 自报决定。

### 开发者生态架构师

支持稳定 capability schema 和 Agent Access Protocol，不暴露内部表结构。反对过早冻结所有 ABI，也反对 HTTP、MCP、SDK 和插件分别定义不同语义。“面向所有人”应是长期愿景；第一阶段应是一个用户、一个 workspace、一个 durable Agent runtime、一个官方插件、一个外部 Agent client。

### 反对者 / 风险审查 Agent

“自主开发插件”若无沙箱和审批只是任意代码执行。“跨端”若无权威和冲突模型会放大现有数据分裂。“使用其他 Agent 的基础构建内容”必须区分可复用知识、工具和 skill。建议第一阶段只承诺一个可验证的单用户多端闭环。

## 4. 产品与系统边界

NoteMeld 是个人知识库运行时，提供知识权威存储、Agent 对知识的受控操作、能力扩展和跨端访问。它不是模型平台、通用数据库、向量数据库或插件市场本身。

SDK L1 必须拥有通用 loop、任务事件、恢复取消、工具策略、审批和可靠执行；SDK L2 必须拥有通用 Note 生命周期、版本、来源、关系、Note capability 和无业务状态 Note Agent。

Application 必须拥有桌面 UI、宿主生命周期、适配器、插件安装运行和用户权限交互。视频/音频/网页/文件采集、转写/OCR/翻译/摘要、Wiki/实体/图谱、白板/研究/学习、外部搜索/浏览器/代码执行、具体模型 provider 和第三方 Agent skill 必须插件化或适配器化。

插件不能改变 Note、Task、Event、Authority 等核心语义。

## 5. 核心领域模型

建议对象关系为：

```text
Workspace
 ├── Note ── NoteVersion / SourceRef[] / NoteRelation[]
 ├── AgentIdentity
 ├── PluginInstallation
 ├── Task / Turn / Event
 ├── Operation
 ├── ExperienceCandidate / PromotionDecision
 └── Device / Replica
```

| 对象 | 作用 |
|---|---|
| Workspace | 知识边界和权限根 |
| Note | 稳定身份，不因编辑改变 |
| NoteVersion | 不可变内容版本和父版本 |
| SourceRef | 来源 locator、authority、版本和采集时间 |
| NoteRelation | 引用、派生、冲突、相关、父子关系 |
| Task / Turn | 产品任务和 Agent 执行单元 |
| Event | append-only 生命周期和审计事件 |
| Operation | 跨端权威变更记录 |
| PluginInstallation | 已安装版本和权限声明 |
| ExperienceCandidate | 来自 trace 的改进候选 |
| PromotionDecision | 评测、审批、active pointer 和回滚记录 |

Note 正文可以是 Markdown 或未来的结构化 block，但存储层必须有 schema_version、note_id、workspace_id、current_version、title、content_format、content、source_refs、status 和时间字段。标签、实体、embedding、Wiki、摘要和图谱节点应是对 NoteVersion 的可重建 projection。模型推断的 relation 必须带 evidence 和 provisional 状态。

SQLite 权威保存 Note、NoteVersion、SourceRef、Relation、Task、Turn、Event 和 ledger。FTS、embedding、Wiki、graph、缓存摘要是派生数据，损坏后重建，不能反过来成为事实源。

## 6. 总体分层

### L1 Agent Kernel

只负责 canonical loop、上下文、模型和工具调用、事件、取消、审批暂停与状态转换。不能依赖 NoteMeld backend、HTTP、SQLite 具体实现、Wiki 或白板。

### L2 Stateless Note Agent

在 L1 上定义通用 Note Model、Note Store port、Note capability 和 Note Agent 行为契约，同时复用 durable runtime、tool ledger、capability registry、trace/eval 和 promotion gate。L2 不依赖具体来源平台、UI 或 NoteMeld Application 代码。

### L3 NoteMeld Application

提供桌面 UI、用户身份、SQLite adapter、artifact adapter、FTS/vector/Wiki projection、MCP gateway、插件安装运行控制面和业务适配。

Note 写入先提交权威事务，再异步更新派生索引；索引失败不能撤销已成功的 Note 写入。

## 7. Agent Runtime 与插件模型

基础流程：

1. Client 以 workspace、agent identity 和 request id 提交任务。
2. Host 校验 session、预算和 capability scope。
3. Runtime 恢复 session、turn 和 checkpoint。
4. Registry 以 L0/L1/L2/L3 渐进披露能力。
5. Model 产生 tool call；调用经过 policy、authority 和 ledger。
6. 需要授权时写 approval.required 并暂停，由同一 native runtime 原子恢复。
7. Note 写入与 operation 使用同一事务边界。
8. 事件和 trace best-effort 写入，不改变 turn 终态。

安全恢复规则：

- request id 在 workspace/session 范围内幂等；payload hash 不一致返回 conflict。
- 有副作用的工具声明 side effect、timeout、retry、idempotency requirement 和 risk。
- effect_committed 但尚未 checkpoint 的 ledger 条目恢复为 needs_attention，不自动重放。
- cancel 先进入 cancelling，最终 cancelled 必须由 runtime terminal event 确认。
- 同一 session 默认只运行一个非终态 turn。

插件 manifest 至少包含 plugin id/version、schema version、SDK requirement、capability 输入输出 schema、side effect、requested permissions、依赖、平台、license、artifact hash 和签名状态。manifest 只声明，不授予权限；loader 只验证和注册，不执行安装脚本。

| 插件模式 | 取舍 | 建议 |
|---|---|---|
| 进程插件 | 本地能力完整，隔离和跨平台成本较高 | 第一阶段官方插件 |
| WASM | 沙箱和跨平台较好，系统接入复杂 | 第二阶段纯计算 |
| MCP/HTTP | 复用生态快，网络和凭证风险高 | 第一阶段受控 adapter |
| 任意脚本 | 开发简单，安全和复现最差 | 不作为默认公开模式 |

## 8. Agent 自我扩展与自升级

必须区分任务记忆、经验候选、策略 candidate、新插件代码、active plugin pointer 和 runtime 核心代码。第一阶段允许保存记忆、生成候选、离线评测和 staged promotion；不允许在线修改 runtime 核心代码或自动向外发布插件。

晋级流程为：

```text
脱敏 trace → ExperienceCandidate → evidence + deterministic eval
→ PromotionDecision(staged/rejected) → owner approval
→ ActiveVersionPointer → regression 时 rollback
```

每个 candidate 必须有 trace/evidence 引用、版本化 diff、固定 suite/seed/config hash、baseline 对照、失败屏蔽指标和回滚记录。质量提升不能抵消安全回归。

## 9. 多端与同步方案

### A：本地优先单机

每台设备独立 SQLite，靠导入导出或局域网交换。隐私和开发速度最好，但跨端弱、数据分叉明显。适合验证内核，不适合作为长期架构。

### B：本地优先 + 同步服务（推荐）

每端拥有本地副本和 replica identity；同步服务负责认证、operation 存储、cursor 分发和冲突保留，不替代本地 Agent runtime。兼顾离线、数据主权和跨端，代价是账户、密钥、冲突 UI 和服务运维。

### C：云端知识库 + 本地 Agent

云端保存主数据，端侧做缓存和 Agent host。跨端容易，但隐私、成本和网络依赖更高，违背本地优先定位。适合作为未来团队版。

推荐规则：

- 权威变更是 append-only Operation：operation id、replica id、sequence、entity、base version、payload。
- operation id 和 replica/sequence 双重幂等。
- base version 不匹配时产生可审计 conflict，不用无条件 last-write-wins。
- Note 冲突保留双方 NoteVersion，并创建 conflict record/relation。
- derived index 只同步 rebuild signal 或 artifact manifest。
- cursor 出现 gap 时拒绝推进并重新拉取。
- 第一阶段只保证单用户多端；多人实时协作另行定义。

## 10. 外部 Agent 接入

HTTP、MCP 和 SDK 可以是不同传输，但共享同一套 capability 语义。第一阶段最小能力：

- note.discover、note.search、note.read；
- note.create、note.propose_update、note.relate；
- task.start/status/cancel；
- capability.list/describe/invoke。

外部 Agent 不能直接访问 SQLite、note_results、Chroma、Wiki 文件或内部 Python service。所有写入都带 initiator identity、request id、base version 和 source/evidence refs。身份至少分为用户、设备、Agent、插件和同步服务。

## 11. 推荐技术选型

- 核心 runtime：Rust，保留当前 agent-core、agent-runtime、agent-events、agent-tools 分层。
- 本地权威数据库：SQLite；最终收敛 NoteMeld 主库与 runtime schema，避免两套 durable store。
- 内容：Markdown/JSON envelope；NoteVersion 保存规范化内容和 hash。
- 全文：SQLite FTS5。
- 向量：当前 Chroma 作为 adapter/派生索引，不能成为事实源。
- 图谱：SQLite relation 表 + 可重建 projection，暂不引入图数据库。
- 插件：进程插件优先，WASM 作为后续 sandbox，MCP/HTTP 作为远程 adapter。
- 对外：保留 MCP，同时建立 transport-neutral capability schema。
- 跨端：Rust core + C ABI/语言 binding；UI 只做 protocol client。

不建议当前采用：向量数据库作为主库、立即引入图数据库、每端独立 Agent loop、插件直接写产品表、Agent 在线修改 runtime、同时冻结所有平台 ABI。

### 对当前 notemeld-agent-sdk 的判断

当前 Rust Core、durable SQLite runtime、事件/错误 schema、driver seam、Python/Swift/Kotlin binding 方向是合理的。应继续保留 agent-core 的 L1 无产品依赖边界，在 SDK L2 增加通用 Note Model、Note Store port 和无业务状态 Note Agent；插件安装宿主和具体业务 adapter 仍由 NoteMeld Application 组装。

需要避免的过早稳定化：

- 不要把 Note 放入 L1 agent-core；Note 只属于 SDK L2，Wiki、Canvas、VideoTask 仍不得成为 L1/L2 公共实体；
- 不要让每个 binding 复制 Agent loop 或存储状态机；
- 不要在 ABI 尚未被真实外部 client 使用前冻结所有产品细节；
- 不要把当前 plugin loader 等同于完整的安装、沙箱和供应链系统。

SDK 第一阶段最值得稳定的是 Agent event/error schema、通用 Note schema、Note Store、Note capability、AgentStore/ToolLedger port 和外部 Agent protocol；复杂 Task DAG 保持 feature-gated。

## 12. 第一阶段范围与验收

必须交付：

1. Note、NoteVersion、SourceRef、NoteRelation schema。
2. 可恢复 SQLite authority，支持迁移、备份和导出。
3. Agent Kernel + durable runtime，统一处理 task/turn/event/cancel/approval。
4. SDK L2 通用 Note Agent；Application 通过 Store/Driver adapter 接入。
5. Tool execution ledger、权限和审计。
6. Plugin manifest v1、Release package 安装、hash/版本校验、registry 和“当前全部外部链接转 Note”官方插件。
7. 一个外部 Agent 接入方式，至少完成 MCP 或 HTTP 之一。
8. 统一 discovery/describe/invoke schema。
9. 桌面端写入、同机 CLI/MCP Client/外部 Agent 读取并继续创建 Note 的验证。
10. 同一个 SQLite 文件中的独立表域、migration registry 和幂等 operation 记录。
11. trace/eval 以及 staged/promotion/rollback 骨架。
12. 端到端 Demo：外部 Agent → discover → search/read Note → 调用官方插件 → create/update Note → citation/relation/audit → 另一端读取。
13. 自动化测试覆盖 crash recovery、idempotency、permission denial、plugin fail closed、index rebuild、sync gap/conflict 和外部 Agent protocol。

明确不做：手机/Web/跨设备同步；白板、IM 等新增插件集合；中心化插件市场；任意 Git 仓库安装脚本；Application candidate 自动激活；任何 notemeld-agent-sdk 自修改；多人实时协作；复杂 Task DAG；所有平台最终稳定 ABI。

验收必须证明：

- 删除 FTS、vector、Wiki、graph 后可从权威数据重建。
- 相同 request id 和 payload 返回同一结果；不同 payload 返回 conflict。
- 进程中断后不自动重复副作用。
- 未授权工具、插件或越界 workspace 访问被拒绝并留下审计。
- 插件不兼容、缺依赖、缺 license 或权限拒绝时 fail closed。
- 第二个 client 可通过公开协议读取第一个 client 创建的 Note。
- 同机外部 Client 使用同一权威 Note 数据，重复请求不创建重复 Note。
- candidate 无固定 eval、baseline 或审批时不能成为 active，rollback 不删除历史。

## 13. 当前仓库建议调整

保留 Rust canonical loop、durable runtime、events、approval、tools、trace、capabilities、evidence、artifact、sync 基础，以及 NoteMeld 当前 /api/agent/v1、MCP 和 Host adapter。

需要收敛：

- 把 note_documents、结果文件和 Wiki source/contribution 的关系整理成迁移计划，最终由 Note/NoteVersion/SourceRef authority 统一管理。
- 在 SDK L2 建立 typed Note Model、NoteStore 和 Note capability，禁止 L1 或插件直接依赖产品表和文件路径。
- 让 /api/agent/v1、MCP 和未来移动端 API 投影同一套 Note、Task、Capability 语义。
- 明确 SDK AgentStore 与 NoteMeld product store 的组合方式，避免第二套 Agent history。
- 将插件安装、运行、授权、升级、回滚从 manifest loader 分离为宿主控制面。
- 为 Application 增加 GitHub/Gitee Release 插件安装控制面和 Application candidate 边界。

禁止新增：Note/Wiki/Canvas 直接进入 agent-core；视频任务、模型 provider 表和前端路由成为通用 SDK 实体；每种插件维护一套 Agent loop；graph.json 或 Chroma 成为同步事实源。

## 14. 已确认决策与后续 ADR

用户已确认：

1. SDK 是 L1 无状态 Loop + L2 无业务状态 Note Agent 两层。
2. 一期只做桌面端和同机外部 Agent/CLI/MCP Client。
3. 同一 SQLite 文件使用独立表域和 migration registry。
4. 插件优先公开标准协议，从 GitHub/Gitee Release 标准包安装。
5. 当前全部外部链接转 Note 能力整体插件化，不降低稳定性。
6. Application 自升级一期只建立 candidate 流程；SDK 禁止自修改。
7. 一期不要求复杂 Multi-agent Task DAG。

可以先默认：relation 用关系表而不是图数据库；用户、Agent、插件、设备使用不同 identity；派生索引用 rebuild job；自升级只覆盖 policy、procedural skill 和插件版本 pointer；多 Agent 先共享 workspace，不做远程 worker。

后续再确认：同步服务自建还是托管、端到端加密密钥恢复、WASM runtime、插件市场和签名、多人 workspace、第三方 Agent 自动发布。

建议形成的 ADR/协议：

1. note-authority-and-versioning
2. agent-runtime-host-boundary
3. capability-plugin-authority
4. local-first-sync-and-conflict
5. external-agent-access-protocol
6. experience-promotion-and-rollback
7. schemas/note.v1.json
8. schemas/note-operation.v1.json
9. schemas/capability-invocation.v1.json
10. schemas/agent-access-error.v1.json

## 15. 最终建议

NoteMeld 应继续建设为 Agent + Knowledge Runtime，而不是回到功能型笔记应用路线。第一阶段收敛为：

```text
一个用户、一个 workspace、一套 Note authority、
一个 durable Agent runtime、一个官方插件、
一个外部 Agent client、两个端可访问/同步、
一套可审计、可恢复、可回滚的边界。
```

只要 Note authority、Agent protocol、plugin authority 和 operation/sync model 稳定，白板、视频、研究、学习和其他 Agent 能力都可以作为上层插件加入，而无需重写核心系统。
