# Requirements Index

更新时间：2026-08-27

本文是需求层入口。它不是详细需求正文，而是帮助 Agent 快速定位已有需求、状态、关联计划和实现进度。

## 使用方式

- 新需求写入 `docs/requirements/YYYY-MM-DD-<topic>.md`。
- 已有需求修改时更新对应文件和本索引。
- 需求状态达到 `Ready for Plan` 后，可交给 Superpowers 生成 `docs/superpowers/plans/` 或 `docs/superpowers/specs/`。
- 用户说"执行 / 开始做 / 实现"时，优先从本文定位目标需求。

## 状态定义

- `Draft`：已记录，但还没有完成澄清。
- `Clarifying`：存在阻塞 plan/spec 的开放问题。
- `Ready for Plan`：需求已清楚，可以进入 Superpowers plan/spec。
- `Planned`：已经存在对应 plan/spec。
- `Implemented`：已经实现并完成验证。
- `Superseded`：被新需求替代。

## 需求列表

| P8 | Implemented | NoteMeld 应用运行时与 Wiki 应用化 | [`2026-08-27-notemeld-application-runtime-and-wiki-app.md`](2026-08-27-notemeld-application-runtime-and-wiki-app.md) | [`plan`](../superpowers/plans/2026-08-27-notemeld-application-runtime-and-wiki-app.md) + [`spec`](../superpowers/specs/2026-08-27-notemeld-application-runtime-and-wiki-app.md) + [`验证`](../superpowers/tests/2026-08-27-notemeld-application-runtime-and-wiki-app.md) | v1 协议、Host 生命周期/策略、应用 workspace 设置和 Wiki 内建应用已接入；真实外部 worker、应用包安装、移动端 UI、Agent 生成应用后置 |
| P8.1 | Ready for Plan | NoteMeld 插件管理与内置目录页面 | [`2026-08-27-plugin-management-page.md`](2026-08-27-plugin-management-page.md) | [`plan`](../superpowers/plans/2026-08-27-plugin-management-page.md) + [`spec`](../superpowers/specs/2026-08-27-plugin-management-page.md) | 在既有 `/settings/plugins` 安装/运行控制台上增加内置 catalog、搜索/筛选、详情、添加插件/内容和安装前确认；不修改插件协议与 SDK |

| 阶段 | 状态 | 需求 | 文件 | 关联 plan/spec | 备注 |
| --- | --- | --- | --- | --- | --- |
| P0 | Implemented | notemeld-ai：统一 LLM Provider 抽象与 Token 统计 | [`2026-08-01-notemeld-ai-llm-abstraction.md`](2026-08-01-notemeld-ai-llm-abstraction.md) | [`specs/2026-08-01-notemeld-ai-llm-abstraction.md`](../superpowers/specs/2026-08-01-notemeld-ai-llm-abstraction.md) + [验收](../superpowers/tests/2026-08-01-notemeld-ai-llm-abstraction.md) | 已验收通过：抹平 30+ Provider；替换 GPTFactory；用量口径兼容 |
| P1 | Implemented | notemeld-agent-core：Agent 运行时（工具循环、状态机、事件流） | [`2026-08-01-notemeld-agent-core-runtime.md`](2026-08-01-notemeld-agent-core-runtime.md) | [`specs/2026-08-01-notemeld-agent-core-runtime.md`](../superpowers/specs/2026-08-01-notemeld-agent-core-runtime.md) + [验收](../superpowers/tests/2026-08-01-notemeld-agent-core-runtime.md) | 已验收通过：10 类事件 + 并行工具 + abort/steer；19 单测 |
| P2-P3 | Implemented (P3 阶段一) | notemeld-agent：研究助手（技能强化、长任务、工作空间、三层记忆、接管现有 Chat） | [`2026-08-01-notemeld-agent-research-assistant.md`](2026-08-01-notemeld-agent-research-assistant.md) | [`specs/2026-08-01-notemeld-agent-research-assistant.md`](../superpowers/specs/2026-08-01-notemeld-agent-research-assistant.md) + [P3 验收](../superpowers/tests/2026-08-01-notemeld-agent-research-assistant.md) | P2 已验收（Agent 接管 Chat + 7 工具 + SSE 兼容）；P3 阶段一验收（workspace/memory/skill_loader/long_task/mcp_client 五模块 + 111 单测）；Agent 运行时全量集成（workspace/skill/mcp 工具注册 + research_space 注入 + long_task SSE）待阶段二 |
| P4-P5 | Planned | 主动学习空间（本地知识、互联网研究、学习画布与掌握验证） | [`2026-08-01-notemeld-agent-deep-learning-canvas.md`](2026-08-01-notemeld-agent-deep-learning-canvas.md) | [`plan`](../superpowers/plans/2026-08-11-notemeld-active-learning-space.md) + [`spec`](../superpowers/specs/2026-08-11-notemeld-active-learning-space.md) + [`阶段验证`](../superpowers/tests/2026-08-11-notemeld-active-learning-space.md) | 核心纵向闭环已实现；诊断、选择性编译、增量合并等完整验收仍待推进；多 Agent 后续演进 |
| P4.1 | Implemented | 语义无限白板（可编辑卡片、关系、对话引用与显式 Note 发布） | [`2026-08-14-notemeld-semantic-infinite-whiteboard.md`](2026-08-14-notemeld-semantic-infinite-whiteboard.md) | [`plan`](../superpowers/plans/2026-08-14-notemeld-semantic-infinite-whiteboard.md) + [`spec`](../superpowers/specs/2026-08-14-notemeld-semantic-infinite-whiteboard-design.md) + [`证据`](../superpowers/tests/2026-08-14-notemeld-semantic-infinite-whiteboard.md) | 主线能力与白板/Note 发布链路已接入；性能基准与浏览器/纵向验收待补充 |
| P3.1 | Implemented | L0–L3 渐进式能力路由与按需 Wiki 检索 | [`2026-08-11-progressive-capability-routing.md`](2026-08-11-progressive-capability-routing.md) | [`plan`](../superpowers/plans/2026-08-11-progressive-capability-routing.md) + [`spec`](../superpowers/specs/2026-08-11-progressive-capability-routing.md) + [`验收`](../superpowers/tests/2026-08-11-progressive-capability-routing.md) | 首轮固定 3 个元工具；Wiki/Skill/MCP 渐进披露；Agent free-chat 取消默认重型 Wiki 预搜；定向回归通过 |
| P6 | Implemented | Agent SDK 单一运行时与 NoteMeld 正式切换 | [`2026-08-17-agent-sdk-single-runtime-cutover.md`](2026-08-17-agent-sdk-single-runtime-cutover.md) | [`目标架构`](../superpowers/specs/2026-08-17-agent-sdk-single-runtime-architecture.md) + [`plan`](../superpowers/plans/2026-08-17-agent-sdk-single-runtime-cutover.md) + [`执行规格`](../superpowers/specs/2026-08-17-agent-sdk-single-runtime-execution.md) | Rust SDK 是唯一 Agent 行为事实源；NoteMeld 只消费 artifact，历史 Conversation/Note/Wiki 数据继续可读 |
| P6.4 | Implemented | SDK ToolScheduler 到 NoteMeld 产品能力的完整 ToolDriver 链路 | [`2026-08-19-agent-tool-driver-chain.md`](2026-08-19-agent-tool-driver-chain.md) | [`plan`](../superpowers/plans/2026-08-19-agent-tool-driver-chain.md) + [`spec`](../superpowers/specs/2026-08-19-agent-tool-driver-chain.md) | 产品成功/失败均形成 ToolResult；真实 SDK 验证第二轮模型与多 Session 隔离；不涉及 approval |
| P6.5 | Implemented | Agent approval 暂停、持久化与跨入口恢复 | [`2026-08-19-agent-approval-resume.md`](2026-08-19-agent-approval-resume.md) | [`plan`](../superpowers/plans/2026-08-19-agent-approval-resume.md) + [`spec`](../superpowers/specs/2026-08-19-agent-approval-resume.md) + [`验证`](../superpowers/tests/2026-08-19-agent-approval-resume.md) | 复用 Conversation/Turn/Event；resolve 真正唤醒 native Turn；UI/CLI 共享同一暂停链路 |
| P7 | Planned | Note Agent 与插件化个人知识库一期总需求 | [`2026-08-24-note-agent-plugin-foundation.md`](2026-08-24-note-agent-plugin-foundation.md) | [SDK child](../../../notemeld-agent-sdk/docs/requirements/2026-08-24-stateless-note-agent-foundation.md) → [Application child](2026-08-24-desktop-note-agent-plugin-integration.md) | 两个独立仓库任务；SDK S08 artifact gate 通过后才允许 NoteMeld N01 实现，最终由 N07 关闭总需求 |
| P7-App | Planned | NoteMeld 桌面 Note Agent 与插件集成 | [`2026-08-24-desktop-note-agent-plugin-integration.md`](2026-08-24-desktop-note-agent-plugin-integration.md) | [`plan`](../superpowers/plans/2026-08-24-desktop-note-agent-plugin-integration.md) + [`spec`](../superpowers/specs/2026-08-24-desktop-note-agent-plugin-integration.md) + [`tests`](../superpowers/tests/2026-08-24-desktop-note-agent-plugin-integration.md) + Goal 手册 | N04 已在独立 worktree 完成；N02/N03/N05/N06/N07 仍待集成；一期桌面、同机 CLI/MCP/外部 Agent、链接插件、candidate 安全边界 |
| P7.1 | Implemented（一期桌面 Host） | 内容转换工具插件与 Agent 总结链路 | [`2026-08-27-content-conversion-tool-plugins.md`](2026-08-27-content-conversion-tool-plugins.md) | [`change-spec-content-conversion-tool-plugins.md`](../system/change-spec-content-conversion-tool-plugins.md) + [`plan`](../superpowers/plans/2026-08-27-content-conversion-tool-plugins.md) + [`spec`](../superpowers/specs/2026-08-27-content-conversion-tool-plugins.md) + [`tests`](../superpowers/tests/2026-08-27-content-conversion-tool-plugins.md) | Rust/anydoc 文档插件、媒体/OCR 原子 capability、MCP 与统一 artifact 已接入；server 仅 contract-ready，mobile/WASM 未接入，本期不做 ASCII |
| P6.3 | Implemented | 独立 Agent SDK 唯一源码仓库收敛 | [`change-spec-agent-sdk-single-source.md`](../system/change-spec-agent-sdk-single-source.md) | 本 Change Spec | NoteMeld 已删除内嵌 `agent-sdk/`、SDK CI 和源码回退；独立仓库承担 Rust/binding/CLI/build/release |
| P6.2 | Implemented | NoteMeld 消费独立 Agent SDK 产物并统一 CLI | [`2026-08-17-notemeld-agent-sdk-artifact-integration.md`](2026-08-17-notemeld-agent-sdk-artifact-integration.md) | [`plan`](../superpowers/plans/2026-08-17-notemeld-agent-sdk-artifact-integration.md) + [`spec`](../superpowers/specs/2026-08-17-notemeld-agent-sdk-artifact-integration.md) | wheel/native artifact 作为生产输入；源码/安装启动统一校验；CLI 复用 Agent v1；生产 legacy Agent 已删除 |
| P6.1 | Planned | K0-K3 文章级分层知识检索与独立 Agent 工具 | [`2026-08-18-k0-k3-article-knowledge-retrieval.md`](2026-08-18-k0-k3-article-knowledge-retrieval.md) | [`plan`](../superpowers/plans/2026-08-18-k0-k3-article-knowledge-retrieval.md) + [`执行规格`](../superpowers/specs/2026-08-18-k0-k3-article-knowledge-retrieval-execution.md) | 全层 article_id=task_id；K1/K2/K3 可预过滤；四工具独立/并行；目标 10 万篇单机索引。服务层可并行实施，Agent 接入依赖 P6 正式 Capability/ToolDriver |
| P6-history | Superseded | 跨平台 NoteMeld Agent SDK 与统一 UI/CLI 会话（旧兼容方案） | [`2026-08-14-universal-agent-sdk-unified-cli.md`](2026-08-14-universal-agent-sdk-unified-cli.md) | [`旧设计规格`](../superpowers/specs/2026-08-14-universal-agent-sdk-unified-cli-design.md) | 被 2026-08-17 单一运行时需求替代；旧方案中的一发布周期兼容与 Python rollback 不再适用 |
| - | Planned | 模型上下文与能力感知分块 | [`2026-08-13-model-context-capability-aware-chunking.md`](2026-08-13-model-context-capability-aware-chunking.md) | [`plan`](../superpowers/plans/2026-08-13-model-context-capability-aware-chunking.md) + [`spec`](../superpowers/specs/2026-08-13-model-context-capability-aware-chunking-design.md) + [`验证`](../superpowers/tests/2026-08-13-model-context-capability-aware-chunking.md) | Tasks 1–8 自动化 gate 已通过；真实 UI/Ollama/7.5 分钟视频/历史笔记手动验收待完成，保持 Planned |
| - | Planned | 多源视频增强总结 | 待补充 | `docs/superpowers/plans/2026-06-11-multisource-video-summary-implementation.md` | 三路并行采集融合总结 |
| - | Superseded | Agent Reach 集成 | `docs/requirements/notemeld-agent-reach-integration-prd.md` | - | 多平台搜索与爬取 → 合并到 [P4 search_web](2026-08-01-notemeld-agent-deep-learning-canvas.md) |
| - | Draft | 架构与迁移方案 | `docs/requirements/notemeld-architecture-and-migration.md` | 待生成 | 架构演进与数据迁移（参考 P0-P4 分层架构方案） |

## 开放问题汇总

| 需求 | 问题 | 阻塞原因 | 需要谁确认 |
| --- | --- | --- | --- |
| Agent Reach 集成 | 集成范围和优先级待确认 | 需求边界不清；大部分能力被 P4 search_web + P2 内建工具覆盖，是否保留此需求或合并 | 用户 |
| 架构与迁移方案 | 当前架构现状与迁移目标待对齐 | 新分层方案 P0-P4 已确定架构方向，此文档需升级为 P0-P4 迁移/落地顺序说明或 Superseded | 用户 |
|（其余 4 份新需求） | 无开放问题 | 所有阻塞项已在对话逐条确认：记忆存储、follow-up 开关、自主编译先询问、画布编辑范围、搜索 Provider | - |

## 最近变更

- 2026-08-24：按用户要求将 P7 拆成 SDK-first 与 Application 两个大任务；各自生成 Requirement/Plan/Spec/Test/Goal 手册，SDK S08 artifact handoff 成为 NoteMeld N01 硬门禁
- 2026-08-24：用户确认 P7 canonical requirement，状态更新为 Ready for Plan
- 2026-08-27：P7.1 一期实现完成：文档转 Markdown、视频/音频原子能力、OCR、MCP 映射和桌面 Host 回归通过；移动端/服务端 runtime 不虚报通过
- 2026-08-24：新增 P7 Note Agent 与插件化个人知识库一期基础；用户确认 SDK 采用无状态 Loop + 无业务状态 Note Agent 两层，Application 一期只做桌面端，插件从 GitHub/Gitee Release 安装并优先公开标准协议，现有全部链接转 Note 能力整体插件化，Application 自升级一期只建立 candidate 安全边界
- 2026-08-19：新增 P6.5 Agent approval 暂停/恢复需求、计划与执行规格；不新增第二状态链，SDK 保持唯一 Agent loop
- 2026-08-19：完成 P6.4 ToolDriver 产品能力链路；SDK ToolScheduler 保持唯一调度者，NoteMeld Capability Registry 复用现有 Wiki/Note 服务，五类脱敏工具结果进入下一轮模型，并补真实 native SDK 与多 Session 并发回归
- 2026-08-18：新增 P6.1 K0-K3 文章级分层知识检索 Requirement/Plan/Execution Spec；统一 article_id=task_id，定义四个无顺序依赖的 Knowledge Capability、共享版本化索引、K3 occurrence BM25/vector + SQLite graph provenance 和 10 万篇 benchmark 门槛
- 2026-08-17：P6 改为 Agent SDK 单一运行时正式切换；用户明确取消旧 Python Agent/compat/rollback，新增清晰分层架构和 SDK/Framework 能力边界，历史 Conversation/Note/Wiki 数据继续保留
- 2026-08-17：完成 NoteMeld 消费独立 Agent SDK artifact 与统一 CLI；wheel/native artifact 作为生产输入，legacy Python Agent 删除
- 2026-08-16：完成语义无限白板需求状态收口：`requirements`、`index`、`data-model`、`api-inventory`、`product-rules` 同步更新，新增白板验收证据骨架，状态更新为 Implemented（性能/纵向证据待补）
- 2026-08-15：完成语义无限白板 Requirement、Change Spec 与可执行 Plan；明确 Board/Card/Relation 模型、四类卡片、后端权威引用、白板草稿到 Note 显式发布、React Flow MIT 合规与 500/1000 性能门槛
- 2026-08-14：新增 P6 跨平台 NoteMeld Agent SDK 与统一 UI/CLI 会话需求；确认 Rust 单一核心、版本化 Turn/Event、Python Host binding、`notemeld agent` 和移动端/OpenHarmony SDK 产物
- 2026-08-13：模型上下文与能力感知分块完成 Tasks 1–8 自动化 gate 与证据收口；手动纵向验收未执行，状态保持 Planned
- 2026-08-13：新增模型上下文与能力感知分块需求，覆盖本地模型目录、4096 fallback、用户覆盖、图像/流式能力和 token 预算分块
- 2026-08-11：完成主动学习空间核心纵向闭环与阶段验证；保留 Planned，未把尚缺的诊断/选择性编译/增量合并虚报为已交付
- 2026-08-12：完成显式“学习”提交入口、默认学术/GitHub 研究源、对话摘要与右侧学习面板增量；真实浏览器纵向验收通过，完整 P4-P5 仍保持 Planned
- 2026-08-11：将 P4-P5 升级为“主动学习空间”，补充诊断、学习单元、掌握证据、间隔复习、学术/GitHub 来源；生成 Plan/Spec 并进入执行
- 2026-08-11：新增 L0–L3 渐进式能力路由需求，覆盖按需 Wiki 检索、Skill/MCP 延迟发现和固定元工具入口
- 2026-08-11：完成 L0–L3 渐进式能力路由实现与验证；同步架构、产品规则、API、坑点和验收证据
- 2026-08-02：P3 notemeld-agent 阶段一验收通过（workspace/memory/skill_loader/long_task/mcp_client 五模块 + 111 单测 + memory hook/工具最小接入）；同步更新 P0/P1/P2-P3 状态为 Implemented
- 2026-08-01：基于 Pi 框架分析对话产出 4 份新需求（P0-P5），状态均 Ready for Plan；新增"阶段"列和依赖关系说明
- 2026-07-27：doc-driven 初始化，创建需求索引，录入现有 2 份需求文档
