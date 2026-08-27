# NoteMeld 应用运行时与 Wiki 应用化

日期：2026-08-27
作者 / Agent：Codex
状态：Planned
关联对话 / 任务：应用宿主、小程序式 HTML 应用、SDK 能力调用与 Wiki 抽离
关联系统文档：

- [`docs/system/current-architecture.md`](../system/current-architecture.md)
- [`docs/system/product-rules.md`](../system/product-rules.md)
- [`docs/system/data-model.md`](../system/data-model.md)
- [`docs/system/api-inventory.md`](../system/api-inventory.md)
- [`docs/system/known-pitfalls.md`](../system/known-pitfalls.md)
- [`2026-08-24-desktop-note-agent-plugin-integration.md`](2026-08-24-desktop-note-agent-plugin-integration.md)
- `notemeld-agent-sdk/docs/protocol/agent-protocol-v1.md`

## 1. 原始需求

用户希望 NoteMeld 支持类似“小程序”的应用形态：NoteMeld 提供基础 Agent、插件、知识库、Note 和文件能力；应用在 NoteMeld 内运行，拥有自己的 HTML/CSS/JavaScript 界面、后端逻辑、应用数据和复杂交互流程，并通过版本化 SDK 调用宿主能力。桌面端为应用提供默认本地文件夹映射；桌面端和 Web 端尽量复用同一应用包和实现；移动端允许独立交互和实现，不把移动端同构作为本期目标。当前内建 Wiki 需要抽离为第一个应用。

本需求中的“应用”是带界面、持久状态、用户交互和复杂流程的可安装工作空间；无界面的自动处理是 Workflow；确定性的单项能力是 Plugin；Agent 是应用调用的智能执行引擎。

## 2. 背景和问题

- 当前用户：使用 NoteMeld 进行知识整理、研究、学习，或希望构建招聘分析等垂直工作空间的个人用户。
- 当前系统已有 Agent Runtime、Capability Router、插件控制面、Note/Wiki/Whiteboard 等能力，但复杂工作台主要以内建页面实现。
- 插件能提供能力，不能承载完整用户工作空间；普通对话也不能自然表达持续的表单、状态、批处理、人工确认和可恢复流程。
- 当前 Wiki 是 `/wiki` 内建路由，后端有独立 Wiki router/store，但尚未作为可安装、可启用、可独立演进的应用运行。
- 应用若直接访问宿主 SQLite、文件系统或内部 API，会破坏安全边界、跨端能力和数据权威边界。

本需求参考小程序和托管 Web 应用的共同形态：前端资源由宿主加载，业务逻辑由受控的云函数/托管运行时执行，数据和文件通过宿主提供的受控服务访问。腾讯 CloudBase 官方文档将小程序常见架构概括为客户端、云函数、文档数据库和云存储，也将 Web 应用区分为静态托管和后端服务；这为 NoteMeld 的 Web 应用托管提供参考，但不要求引入 CloudBase 或其他第三方平台。

参考资料：

- [腾讯云 CloudBase：应用场景与小程序/Web 技术架构](https://cloud.tencent.com/document/product/876/20232)
- [腾讯云 CloudBase：小程序端 SDK](https://cloud.tencent.com/document/product/876/19385)
- [Vercel Functions：托管函数生命周期与按请求运行](https://vercel.com/docs/functions)

## 3. 目标结果

- NoteMeld 提供应用宿主；应用可以加载自己的 HTML UI、运行自己的后端逻辑、维护应用实例和运行记录。
- 应用通过版本化 SDK 调用 Agent、插件、Note、Wiki、知识检索、Artifact 和工作区文件能力；不得直接访问宿主数据库、session secret 或任意系统路径。
- 桌面端为每个应用提供应用级默认 workspace；应用通过逻辑 file/workspace reference 访问文件，不依赖绝对路径。
- 桌面端和 Web 端使用一致的应用 ID、协议、数据 schema、Artifact、权限和运行状态语义；UI 和文件/进程实现可以因宿主不同而不同。
- 移动端可以采用同一应用的独立 UI/实现；本期允许声明不支持移动端。
- 当前 Wiki 成为第一个内建应用，保留现有图谱、页面、文章、社区、文件页、Note 权威和 Wiki rebuild 链路。
- 第一版本先冻结 Application Package、Application SDK、Capability、权限、workspace、运行和 Artifact 协议，并用内建 Wiki 验证协议；Agent 自动生成应用只保留为后续方向，不进入本期验收。
- 应用以独立目录作为交付边界，宿主启动时只发现并校验 manifest/目录元数据；用户点击应用后才加载 UI bundle、创建实例并启动 runtime，不因打开 NoteMeld 而加载所有应用代码。

## 4. 非目标

- 本期不要求移动端复用桌面/Web UI、交互代码或运行时。
- 本期不把应用限制为统一 UI Schema；应用可以使用自己的 HTML/CSS/JavaScript 和前端框架。
- 本期不允许应用前端读取宿主 DOM、Tauri API、session secret 或未授权文件。
- 本期不允许应用后端直接连接 NoteMeld SQLite、读取内部表、伪造 Agent Event 或绕过 Host capability/permission。
- 本期不自动修改 NoteMeld 主程序、Agent SDK、公共协议或正在运行的宿主代码。
- 本期不实现 Agent 自动生成、自动安装或自动升级应用；只要求协议对未来生成应用保持可校验。
- 本期不复制 Wiki 知识事实到应用专属数据库，不建立第二套 Wiki 权威数据源。
- 本期不要求一次性把所有内建页面应用化；先完成 Wiki 垂直切片。
- 本期不把无界面的定时任务、批处理或单次 Agent 调用强行包装成应用。

## 5. 当前系统事实

- Agent：共享 Agent Runtime、Agent Host、Capability Registry、ToolDriver、approval/cancel/steer 和事件持久化已经存在；应用内 Agent 应复用同一 Agent 行为事实源。
- Plugin：已有 Release 包校验、版本、权限、启用、active pointer、运行状态和审计；插件负责确定性 capability，不负责完整应用 UI。
- Wiki：前端入口为 `frontend/src/pages/WikiPage/`，路由为 `/wiki`；后端入口为 `backend/app/routers/wiki.py`，包含 `/api/wiki/graph`、页面、文章、社区、文件页和取消抽取等接口；数据由 `backend/app/services/wiki_store.py` 读取/写入，包含 `vector_db/note_results/wiki/graph.json` 及 Wiki 文件。
- 数据权威：Note 是知识正文和可引用事实的权威对象；Wiki contribution、graph 和页面由现有 Wiki pipeline/store 生成或物化；白板不能成为第二事实源。
- 现有限制：当前没有应用包、应用宿主、应用 SDK、应用实例/运行记录或应用级权限模型；Web、桌面和移动端的文件、进程、存储和交互能力不同。
- 当前没有 Web 应用后端托管运行时；本需求确定采用 NoteMeld 管理的 serverless/worker 风格 Application Backend，不开放应用自建公网服务。
- 相关坑点：不能绕过统一 Note/Task/Conversation writer；不能在共享 SQLite 中覆盖其他域的 migration version；不能自动重放未知非幂等副作用；不能把 manifest 的 safe 声明当作授权证明；不能泄露密钥、token、绝对私有路径或原始敏感 payload。

## 6. 用户故事

- 作为用户，我希望打开一个应用并持续处理一类工作，以便保留上下文、数据和进度。
- 作为应用作者，我希望使用自己的 HTML 界面和后端逻辑，以便构建招聘分析、Wiki 图谱或白板学习工作台。
- 作为应用作者，我希望通过 SDK 调用 Agent、插件、Note、知识和文件能力，以便复用 NoteMeld 基础设施。
- 作为桌面用户，我希望每个应用拥有默认本地工作目录，以便管理输入文件、应用数据、缓存和 Artifact。
- 作为未来的应用作者，我希望应用协议可被工具和 Agent 生成，以便后续自动创建应用；本期不要求自动生成流程。
- 作为知识库用户，我希望 Wiki 应用化后能打开图谱、切换展示方式、选择节点并查看对应文章，而不需要重新生成知识库。
- 作为应用用户，我希望应用在进入前可以展示自己的配置项，保存后再按配置启动，以便不同应用实例可以有不同的工作方式。

## 7. 验收标准

### 应用宿主

1. GIVEN 合法 Application Package，WHEN 用户安装，THEN 系统校验身份、版本、完整性、平台、运行入口、能力依赖和权限声明，失败时拒绝安装。
2. GIVEN 已安装应用，WHEN 用户启动，THEN 应用在受控 iframe、独立 WebView 或等价容器中加载自有 HTML UI，不能读取宿主 DOM、session secret 或未授权文件。
3. GIVEN 应用拥有后端逻辑，WHEN 后端调用 NoteMeld 能力，THEN 调用只能通过版本化 SDK/Host capability seam 完成，并绑定 app、instance 和 run 上下文。
4. GIVEN 应用声明不支持当前平台或宿主缺少必需能力，WHEN 用户启动，THEN 系统展示明确诊断，不显示空白页面或静默伪装成功。
5. GIVEN 桌面应用访问默认 workspace，WHEN 应用读写文件，THEN 宿主只提供应用自己的逻辑 file/workspace reference，不暴露任意绝对路径。
6. GIVEN 同一应用在桌面和 Web 运行，WHEN 两端满足依赖，THEN 应用 ID、版本、数据 schema、Artifact、权限和运行结果语义一致；文件和进程实现可以不同。
7. GIVEN 应用没有移动端实现，WHEN 用户在移动端查看，THEN 应用明确标记为不支持移动端，不影响其他平台。

### Agent、插件和数据

8. GIVEN 应用请求 Agent 任务，WHEN SDK 发起调用，THEN 请求进入现有 Agent Runtime，并保留 Turn、Event、approval、cancel、usage 和 terminal outcome 语义；应用不创建第二套 Agent 状态机。
9. GIVEN 应用调用未声明、未安装、未授权或当前平台不具备的能力，WHEN 宿主处理请求，THEN 调用被拒绝且不产生副作用。
10. GIVEN Agent 或插件产生结构化结果，WHEN 应用保存结果，THEN 结果成为可追踪的应用 Artifact 或既有 Note/Whiteboard/Knowledge 引用，并带有来源和运行上下文。
11. GIVEN 操作需要确认或审批，WHEN 用户拒绝、取消或超时，THEN 未授权副作用不执行，应用进入可观察、可恢复状态。
12. GIVEN 应用后端或 transport 崩溃、EOF、超时或返回非法消息，WHEN 宿主收敛运行，THEN 运行进入确定的 failed/interrupted/needs-attention 结果，不自动重放未知非幂等操作。

### Wiki 应用化

13. GIVEN 当前已有 Wiki 数据和历史 Note，WHEN Wiki 应用首次启动，THEN 用户可以查看现有图谱、节点关系、类型/社区等展示方式、节点详情和对应文章，不需要复制到第二套事实源。
14. GIVEN Wiki 应用请求知识数据，WHEN 宿主处理请求，THEN 通过 Wiki domain capability 使用既有 Wiki store、Wiki pipeline 和 Note authority；应用不直接读取内部数据库，底层数据可继续由现有数据库/文件存储承载。
15. GIVEN Wiki UI 从当前内建页面迁移，WHEN 用户执行图谱查看、展示方式切换、缩放、节点选择、文章查看和刷新，THEN 当前 Wiki 页面提供的可观察能力保持可用；容器和具体 UI 结构可以调整。
16. GIVEN Wiki graph/rebuild 失败，WHEN 用户打开 Wiki 应用，THEN 已有数据仍可读取并显示明确状态，不清空历史图谱、不删除 Note、不把投影失败误报为生成失败。
17. GIVEN Wiki 应用被禁用或宿主升级，WHEN 操作完成，THEN Note、Wiki contribution、graph 和文章数据保持可读；本期不提供 Wiki 应用卸载删除知识数据的用户流程。

### Application Protocol v1

18. GIVEN Application Package 声明 HTML UI、后端入口、数据 schema、能力依赖、权限和平台，WHEN 宿主解析包，THEN 宿主可以得到完整的安装、启动、能力协商和存储配置，不需要读取应用内部实现才能做权限判断。
19. GIVEN 桌面端启动应用后端，WHEN 应用处理 UI/SDK 请求，THEN 后端作为由宿主监督的独立进程运行，通过私有 process-JSONL/RPC transport 与宿主通信，不监听公开地址，并可被宿主停止、重启和回收。
20. GIVEN Web 端启动应用后端，WHEN 应用处理请求，THEN 请求进入 NoteMeld 管理的受控 serverless/worker runtime；应用版本不可变、无公开监听端口，并受超时、内存、CPU、并发、存储和网络出口限制。
21. GIVEN 应用需要长任务，WHEN Web 或桌面端发起任务，THEN 宿主将其登记为可观察、可取消、可恢复的 Application Run；运行时退出或 transport 中断不会自动重放未知非幂等操作。
22. GIVEN 应用访问自己的数据或默认 workspace，WHEN 用户在设置中改变应用根目录，THEN 新请求使用新的逻辑 workspace 映射，历史 file/artifact reference 保持可解释且不越权访问其他应用目录。
23. GIVEN 本期不启用 Agent 自动生成应用，WHEN 用户在普通对话中描述一个应用，THEN 系统不会未经确认创建、安装或启动应用；协议仍可被后续生成工具校验。
24. GIVEN 应用位于可信应用目录，WHEN NoteMeld 启动或刷新应用列表，THEN Host 只读取 `manifest.json` 和安全元数据，不执行 UI/backend，不创建实例，不启动进程。
25. GIVEN 用户点击已启用应用，WHEN Host 加载应用，THEN 按“校验 manifest → 读取配置 → 创建/恢复 instance → 启动 runtime → 建立 Host bridge → 加载 UI → handshake → ready”顺序执行；任一步失败都进入可观察失败状态且不显示空白页面。
26. GIVEN 应用声明配置 schema，WHEN 用户首次进入或配置版本变化，THEN Host 展示宿主配置界面或应用声明的配置 UI，按 schema 校验并按 app/instance 命名空间保存；未通过校验不得启动 runtime。
27. GIVEN 用户离开应用或关闭窗口，WHEN 应用没有活动长任务，THEN Host 可以停止 UI bridge、回收 worker/独立进程并保留 instance/run 状态；有活动任务时先进入可观察的 stopping 状态，不直接丢弃任务。

## 8. 输入 / 输出样例

### Application Package 目录

```text
applications/<application-id>/
├── manifest.json          # 唯一入口：协议、版本、平台、能力、权限、配置和 runtime
├── ui/                     # HTML/CSS/JS bundle，entry 由 manifest 指定
├── backend/                # 可选 backend；desktop 进程或 Web managed worker 的入口
├── assets/                 # UI 静态资源
├── migrations/             # 应用自己的 forward-only 数据迁移
└── README.md
```

应用目录是包边界，不等同于 NoteMeld 页面目录。内建目录和未来用户安装目录必须分开；用户安装包不能覆盖内建应用 ID/version。Host 发现阶段不执行 `ui/` 或 `backend/`，点击加载阶段才根据平台选择 UI/runtime adapter。

### 输入

- 用户描述：“创建一个招聘应用，上传多份简历，按照岗位要求分析候选人，展示列表和详情，确认后生成招聘报告。”
- 应用包包含 HTML UI、后端入口、候选人 schema、Agent 任务、文件/Note capability 依赖、权限申请和平台声明。
- Wiki 应用使用现有 Note、Wiki contribution、graph、页面和文章数据。

### 输出

- 可校验的应用草稿或已确认应用实例；
- 应用 workspace 中的输入文件、业务记录、运行记录和 Artifact；
- Agent/插件结构化结果、用户确认状态和可引用的报告 Note；
- 独立加载的 Wiki 应用，保留现有知识数据和入口能力。

### 反例或失败样例

- UI 读取宿主 token、后端连接 NoteMeld SQLite、访问其他应用目录：请求被拒绝并记录诊断。
- Web 没有桌面目录能力：使用 Web workspace 或报告能力缺失，不伪装拥有本地目录。
- Agent 生成修改 Agent SDK 的代码：草稿不能安装，既有 candidate 边界继续生效。
- Wiki rebuild 失败：保留已有页面和图谱，显示待重建状态。

## 9. 约束

- 平台：本期目标为桌面端和 Web 端；移动端允许独立实现或明确不支持。
- UI：应用自由使用 HTML/CSS/JavaScript 和前端框架；必须隔离运行，不能注入宿主页面。
- 后端：桌面端采用宿主监督的独立应用进程，通过私有 process-JSONL/RPC transport 通信，不监听公开地址；Web 端采用 NoteMeld 管理的 serverless/worker 风格托管运行时，不允许应用自建公网服务。
- Web 托管：应用版本以不可变包部署；宿主控制每次 invocation/long task 的超时、内存、CPU、并发、存储和网络出口，并负责启动、停止、日志、审计和回收。
- 文件：桌面端提供应用级默认 workspace，用户可在设置中修改应用根目录；跨端可以有不同存储实现，但 file/workspace reference 和权限语义必须稳定。
- Agent：应用内 Agent 复用现有 Agent Runtime，不复制 loop、状态机、事件或 approval 语义。
- 数据：应用实例、运行记录和 Artifact 与 Note/Wiki 权威数据分离；Wiki 应用不得复制事实源。
- 安全：权限声明是申请，不是授权；文件、网络、Note 写入、插件和 Agent 敏感操作由宿主 authority/用户授权决定。
- 可靠性：安装、启动、transport、长任务、取消、恢复、幂等和非幂等副作用必须有可观察状态。
- 分发：第一期冻结协议并支持内建应用包；用户本地包、Release 分发和 Agent 生成包不进入本期安装流程，但包格式必须可扩展。
- 加载：应用列表是 manifest catalog，应用代码只在用户明确点击后按需加载；应用配置属于 Host lifecycle 的前置阶段，不得由应用代码自行绕过 Host 写入。
- 隐私：禁止写入或返回 Provider key、Cookie、token、绝对私有路径和原始敏感内容。

## 10. 边界场景

- 空数据：Wiki 显示空知识库状态，不创建虚假节点；新应用实例显示初始化状态。
- 权限拒绝：应用保留当前状态并提供恢复提示。
- 多实例：同一应用实例之间的文件、状态、运行记录和权限上下文隔离。
- 后端崩溃：释放 transport 和权限上下文，保留可诊断运行结果。
- 长任务取消：产生唯一终态，不重复执行非幂等工具。
- 大数据量：Wiki 图谱、批量简历和 Artifact 使用分页/流式或受控上下文；具体门槛待验证。
- 版本升级：失败时旧版本和旧实例可读取，数据迁移不删除知识或改变 Artifact 事实。
- Wiki 迁移：本期移除旧 `/wiki` 路由和当前内建页面 wiring，不提供旧路由兼容；Wiki domain service/capability 和现有知识数据继续作为应用宿主的权威来源。
- 应用目录：用户修改默认根目录后，新实例使用新映射；历史实例不能静默改变指向，迁移必须显式完成。

## 11. 开放问题

无阻塞性开放问题。以下决策已由用户确认，并作为本需求的范围：

- 桌面后端：宿主监督的独立进程，使用私有 process-JSONL/RPC transport，不监听公开地址；宿主负责启停、回收、权限上下文和运行状态。
- Web 后端：NoteMeld 管理的 serverless/worker 风格托管；应用包通过宿主网关调用，不允许应用自建公网服务；长任务进入宿主统一 Run/Job 管理。
- 第一版本：先冻结应用协议并以内建 Wiki 验证；暂不实现 Agent 自动生成应用，也暂不承诺用户本地包或公开 Release 分发。
- Wiki 路由：有 Wiki 应用后移除旧 `/wiki` 页面和路由逻辑，不提供旧路由兼容；保留 Wiki domain service/capability 和既有知识数据。
- Wiki 范围：只抽离当前 Wiki 页面能力，包括读取现有图谱、不同展示方式、缩放、节点选择、节点详情和文章查看、刷新及对应空/错状态；不扩展到 Wiki 管理后台或完整研究工作流。
- 默认目录：应用默认 workspace 根目录可在 NoteMeld 设置中修改；应用使用逻辑引用，历史实例不会静默改指向。

执行计划仍需细化但不改变范围的事项：应用包具体字段、SDK wire schema、runtime 资源配额、内建 Wiki capability 适配方式、迁移顺序和测试 fixture。

## 12. 与系统事实的冲突检查

- `product-rules.md`：未发现直接冲突；应用仍须服务“AI 编译知识，人验证和消费”。
- `data-model.md`：需要新增应用定义/实例/运行/Artifact/权限等域，但本需求不冻结具体字段；必须与 Note、Wiki、Agent、Plugin 权威边界分离。
- `api-inventory.md`：当前没有应用 API；本期不提供旧 `/wiki` 路由兼容，但 Wiki domain capability 必须在 plan/spec 中替代当前页面对 `/api/wiki/*` 的直接依赖。
- `known-pitfalls.md`：存在任意代码、直接 SQLite、路径分裂、投影误报、非幂等重放、权限自授权和 Wiki/Note 双事实源风险；本需求的约束和验收标准明确禁止这些路径。
- 本地/线上影响：会影响应用包缓存、应用数据目录、应用运行记录和 Wiki 路由/加载方式；本需求不执行数据删除或迁移。

## 13. Superpowers 交接

- 是否已达到 Ready for Plan：是。用户已确认后端、Web 托管、第一版本范围、Wiki 路由、Wiki 抽离范围和默认目录策略。
- 推荐下一步：
  - [ ] 生成 Application Host/SDK、Wiki 应用化、桌面/Web 适配和安全回归的执行计划
  - [ ] 再生成执行规格和验证证据文档
- 计划必须覆盖验收标准 1–23，并补充应用包恶意 corpus、容器隔离、目录越权、SDK deny、崩溃/EOF/取消/恢复、旧 `/wiki` 移除、Wiki 数据读取前后对比和应用运行回收验证。
