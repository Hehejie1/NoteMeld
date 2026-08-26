# NoteMeld 桌面 Note Agent 与插件集成

日期：2026-08-24
状态：Planned
上游总需求：`2026-08-24-note-agent-plugin-foundation.md`
SDK 前置需求：`../../../notemeld-agent-sdk/docs/requirements/2026-08-24-stateless-note-agent-foundation.md`
目标架构：`../architecture/2026-08-notemeld-agent-knowledge-runtime-architecture.md`
Change Spec：`../system/change-spec-note-agent-plugin-foundation.md`
执行计划：`../superpowers/plans/2026-08-24-desktop-note-agent-plugin-integration.md`
执行规格：`../superpowers/specs/2026-08-24-desktop-note-agent-plugin-integration.md`
验收证据：`../superpowers/tests/2026-08-24-desktop-note-agent-plugin-integration.md`
Goal 手册：`../superpowers/goals/2026-08-24-desktop-note-agent-plugin-integration-prompts.md`

## 1. 任务定位

本需求是跨仓库一期目标的第二个大任务。只有 `notemeld-agent-sdk` S08 发布门禁通过并提供固定 artifact handoff 后，才能开始本仓库代码实现。

NoteMeld Application 负责：

- 消费而不是重写 SDK 的 Stateless Loop / Note Agent；
- 把现有 Note 权威数据适配到 SDK Note ports；
- 下载、校验、安装、启停和回滚 GitHub/Gitee Release 标准插件包；
- 把现有全部外部链接转 Note 能力迁移为官方插件；
- 通过桌面 UI、CLI、MCP 和同机外部 Agent 暴露同一能力与数据；
- 保存 Application/插件升级 candidate，但一期不自动激活 Application 源码修改。

## 2. 用户结果

1. 用户在桌面端粘贴当前任一受支持链接，仍可获得同等或更稳定的 Note、进度、取消、错误和恢复体验；实际执行来自已安装的官方链接插件。
2. 用户可从 GitHub/Gitee Release URL 安装标准插件包；manifest/version/hash/license/权限或兼容性失败时 fail closed，旧 active version 继续可用。
3. 同一电脑上的 NoteMeld UI、CLI、MCP Client 和外部 Agent 能发现相同能力、读取同一 Note，并通过插件生成或关联新 Note。
4. 每个新 Note 可追溯到来源、父 Note/关系、Agent Turn、插件 ID/版本、operation 和审计记录。
5. Agent 产生的 Application 或插件改进先进入 candidate；触碰 SDK、缺证据/测试/回滚或越权时不能进入可批准状态，一期不自动替换运行应用。

## 3. 当前系统与增量边界

- 现有 `/api/agent/v1`、native Host、ToolDriver、approval、CLI、MCP endpoint 和桌面 ready gate继续复用。
- 现有 `note_documents.task_id` 作为一期 NoteMeld adapter 的稳定 Note ID，避免创建第二份 Note 内容权威；历史 task/result/Conversation 继续可读。
- `note_results/*.json|md`、Wiki、FTS/Chroma、Conversation message 是兼容输出或投影，不能因其失败回滚已提交 Note。
- 新增来源、关系、operation、plugin 和 candidate 表域时，使用独立 migration registry；不得改写共享 `PRAGMA user_version`。
- SDK reference SQLite adapter 是通用示例；NoteMeld 必须通过产品 adapter 复用现有 Note 权威，不得同时写第二套 SDK reference Note 表形成双权威。

## 4. 功能需求

### 4.1 SDK artifact 接入

- 锁定 SDK version/schema/ABI、artifact SHA-256、binding signature 和 native exports。
- 启动和打包继续 fail closed；不得从 SDK checkout 源码回退，也不得保留 Python/legacy 第二 loop。
- Application adapter 只转换 SDK Note contract 与 NoteMeld 存储/权限/transport，不制造 SDK event 或 terminal outcome。

### 4.2 NoteMeld Note adapter

- 读取、搜索、创建、更新和关联 SDK Note；保留 `task_id` 兼容。
- 统一提交边界：Note 内容与必要 provenance/operation 成功即 Note 成功；Wiki、索引、消息、UI 投影独立失败并可重建。
- 同 request/same payload 幂等；same request/different payload conflict；不自动重放 uncertain side effect。
- 迁移历史 Note 时不得丢失来源、Markdown、task 状态、Conversation、Wiki 或导出兼容。

### 4.3 插件控制面

- 支持 GitHub/Gitee Release artifact URL，限制允许的 host/redirect/size/timeout，下载到 staging。
- 在 staging 校验 SDK 标准 manifest、版本、license、文件清单、hash 和路径安全；不执行 install script。
- 安装为不可变版本目录，通过原子 active pointer 激活；失败保留旧版本，回滚不删除审计与历史版本。
- 权限由真实 Application authority 决定；敏感权限需要用户审批，manifest 不可自授权。
- 未被发现/描述/调用的插件不启动；调用有超时、取消、资源边界和安全错误。

### 4.4 官方链接转 Note 插件

- 实施前从现有 router/service/downloader/collector/tests 自动生成 URL 能力 baseline，不只依赖手写平台列表。
- 把当前全部链接类型、字幕优先、下载、转写、截图、网页抓取、任务状态和降级路径迁移到独立可打包插件边界。
- 插件通过 SDK Note capability/host port 写 Note，不直接写 UI、Conversation、SDK Event 或产品内部表。
- 插件 artifact 可由本仓库构建和作为 Release 安装；源码结构保持可独立迁出公开 GitHub/Gitee 仓库。
- 插件化前后 baseline 对照必须全部通过；不允许以删除少数平台来完成迁移。

### 4.5 桌面、MCP、CLI 和外部 Agent

- 桌面 UI 提供插件列表、安装/升级/回滚/权限/诊断和链接任务入口；sidecar ready 前不请求业务 API。
- MCP 优先暴露公开 Note/capability 工具；外部 Client 不需要 NoteMeld 私有协议。
- CLI 与 UI 通过同一 Host/API，不直接写 SQLite/Event。
- 同 Session 并发、approval、取消和 SSE replay 继续服从现有 Agent v1 状态机。
- 一期只保证同机进程/客户端共享本地知识；多端协议可文档化，但不建设同步服务。

### 4.6 Application upgrade candidate

- candidate 包含 target scope、evidence/trace、patch/artifact、测试、风险、权限和回滚说明。
- 只允许 `NoteMeld Application` 和已安装插件 scope；任何 SDK 路径/制品/公共契约变更一律拒绝。
- candidate 经静态边界、测试和人工审批门禁后最多进入 `approvable`；一期不自动修改当前 Application 源码、安装包或 active app version。
- 插件 candidate 可形成新 staging version，但仍走普通插件安装/校验/审批/激活流程。

## 5. 非目标

- 不修改或自升级 `notemeld-agent-sdk`。
- 不交付手机/Web 客户端、云同步、跨设备冲突或多人协作。
- 不建设中心化插件市场。
- 不从任意 Git branch clone 并执行脚本。
- 不要求复杂内部 Multi-agent DAG。
- 不把白板、IM、文档连接器等全部立即插件化；一期业务插件只有现有链接转 Note 全量迁移。
- 不自动激活 Application 源码 candidate。

## 6. 验收标准

1. GIVEN SDK S08 handoff 缺失、hash/version/schema/ABI 不匹配或 supported binding 未通过，WHEN 启动实现/运行，THEN N01 fail closed，后续 Goal 不开始。
2. GIVEN历史 `note_documents.task_id`，WHEN通过 SDK Note read/search，THEN内容、来源和稳定 ID 可读且不复制第二份权威 Note。
3. GIVEN插件创建派生 Note，WHEN提交成功，THEN来源、关系、Turn、plugin id/version、request/operation 和 actor 可查询。
4. GIVEN同 request/same payload 或 different payload，WHEN重复提交，THEN分别返回原结果或稳定 conflict，不产生重复 Note。
5. GIVEN Note 已成功但 Wiki/索引/message/UI 投影失败，WHEN任务结束，THEN Note 保持成功，独立诊断可重建。
6. GIVEN合法 GitHub/Gitee Release 包，WHEN安装，THEN staging 校验后原子激活不可变版本并记录审计。
7. GIVENhash 篡改、路径穿越、版本/license 不兼容、redirect 越界、权限拒绝或插件崩溃，WHEN安装/执行，THEN fail closed 且旧插件和知识库可用。
8. GIVEN当前 URL baseline，WHEN官方链接插件替换内建链路，THEN每类链接、字幕优先、下载/转写/截图、网页降级、任务状态和失败分类回归等价。
9. GIVEN桌面创建的 Note，WHEN同机 CLI/MCP/外部 Agent读取，THEN看到同一 Note、来源和关系。
10. GIVEN MCP/function calling client，WHEN发现 capability，THEN使用公开 schema；平台专属不兼容能力明确诊断。
11. GIVEN桌面 sidecar 未 ready，WHEN用户触发插件或 Agent请求，THEN现有 ready gate 阻止抢跑。
12. GIVEN同 Session 两个客户端并发提交，WHEN创建 Turn，THEN一个执行、一个稳定 session-busy，不出现第二状态链。
13. GIVEN candidate 尝试改 SDK、缺 evidence/test/rollback 或越权，WHEN验证，THEN不能进入 approvable。
14. GIVEN合法 Application candidate，WHEN一期流程完成，THEN只保存和展示，不自动修改运行中源码/安装包。
15. GIVEN同一 SQLite 文件，WHEN Note、plugin 或 candidate schema 独立升级，THEN其他 registry/version 和历史数据不变。
16. GIVEN最终桌面 release candidate，WHEN运行 core regression、前端 contracts/build、真实桌面与外部 MCP 纵向测试，THEN完整一期场景通过。

## 7. 完成定义

N01–N07 全部完成、测试证据具有真实命令/结果、官方链接插件 baseline 无回退、桌面与同机外部 Agent纵向闭环通过后，本需求才可标记 Implemented。随后上游总需求才可整体关闭。
