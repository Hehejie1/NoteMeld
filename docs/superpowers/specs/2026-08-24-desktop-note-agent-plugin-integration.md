# NoteMeld 桌面 Note Agent 与插件集成规格

Canonical requirement：`../../requirements/2026-08-24-desktop-note-agent-plugin-integration.md`
Plan：`../plans/2026-08-24-desktop-note-agent-plugin-integration.md`

## N01：SDK intake 与 baseline

- 验证 SDK handoff 的 version/schema/ABI/commit/hash、native exports、binding signatures、artifact manifest 和 supported matrix；复用现有 fail-closed loader，不添加源码 fallback。
- 生成机器可读 current URL capability inventory，来源至少包括 router/service/downloader/collector 注册和现有 tests；记录平台、输入 URL pattern、字幕/下载/转写/截图、网页 fallback、task state 和错误分类。
- 冻结现有 Note authority：`note_documents.task_id` 作为一期 SDK `NoteId`；`note_results`/Conversation/Wiki/Chroma 的权威与投影角色写入 adapter ADR。
- 冻结 SDK Note/plugin schema 到 Application DTO，不在 Python 中复制另一个领域模型。
- 验收：artifact mismatch 失败；baseline 文件可重复生成且代码新增/删除平台会让测试失败。

## N02：NoteMeld Note adapter

建议范围：`backend/app/agent_host/`、`backend/app/services/note_document_store.py`、`backend/app/db/` 和 `backend/tests/agent_host/`。

- 实现 SDK NoteStore/OperationStore/Authority adapter，读取/搜索/创建/更新/关联现有 Note。
- `task_id` 直接映射 opaque NoteId；历史 Note 不批量改 ID。
- 新增独立 registry，例如 `note_agent_app_migrations`，以及来源/关系/operation/provenance 表；不得使用共享 `PRAGMA user_version`，不得创建第二份正文权威。
- Note commit 的最小原子边界包含正文、版本和必要 operation/provenance；文件/Wiki/index/message projection 可独立重试/重建。
- 短 SQLite 写事务处理版本和幂等；模型、插件和网络调用不得持锁。
- 覆盖历史 Note、same/different payload replay、并发版本冲突、needs-attention、projection failure 和多 registry isolation。

## N03：插件控制面

建议范围：新增 `backend/app/services/plugins/`、router/models/schema，前端设置页/service，统一 storage path 下的 `plugins/` 和 `plugin-staging/`。

- Release URL resolver 只接受 HTTPS GitHub/Gitee Release artifact，限制 redirect host、文件大小、超时和 content type；测试使用本地 fixture/fake server，不依赖不稳定线上 Release。
- 下载到唯一 staging 目录，调用 SDK verifier 后再原子移动到 `plugins/<plugin_id>/<version>/`；active pointer 单独原子更新。
- DB 使用 `plugin_app_migrations` 和独立 plugin 表域，保存 source URL、digest、manifest、权限、状态、诊断、active/previous version 和审计。
- 安装不运行仓库脚本；路径穿越、symlink、hash、license、version、SDK compatibility、权限失败均 fail closed。
- capability L0/L1 不启动插件；L2/L3 才按需建立 MCP stdio/HTTP 或支持 transport，调用结束/取消/超时后清理。
- UI 覆盖列表、安装、升级、权限、回滚、禁用、错误/空状态，并遵守 backend ready gate。

## N04：官方链接转 Note 插件

建议创建可独立打包的 `plugins/official-link-note/`，代码边界不得 import React/router 或直接写 Agent Event/SQLite 内表。

- 把 N01 inventory 中所有 URL 路径迁入插件或插件可调用的稳定 host adapter；最终 Application 入口只调用 capability，不保留平台分支双实现。
- 保留官方字幕优先、视频/音频下载、转写、截图、多源汇总、网页抓取和失败降级。
- 插件写入使用 SDK Note operation；task progress/cancel/error 通过稳定 host callback 投影。
- 提供标准 package manifest/index/hash 和本地 Release fixture；源码可在后续不改变 contract 的情况下迁到独立 GitHub/Gitee repo。
- 建立 before/after baseline matrix；每类支持 URL 至少有 contract fixture，关键平台保留现有专门回归。

## I03：产品基础集成

- 按 N02→N03→N04 合入固定集成分支。
- 统一 DB bootstrap/registry 顺序、router、storage paths、frontend route/nav、plugin package resource 和 packaging。
- 运行三组 focused tests、compile、frontend contracts/build 和 Agent Host regression。
- 只有 Application 从已安装 official plugin 执行且无双实现时才通过。

## N05：Desktop/MCP/CLI/外部 Agent

- 通过现有 `/api/agent/v1` 和 Agent Host 调用 SDK Note Agent/capability；Router/UI/CLI 不直接写 Event/Note operation。
- MCP 提供 discover/describe/invoke 以及允许的 Note read/search/create/link 工具，保持 response/auth/path traversal/redaction 规则。
- CLI 复用同一 HTTP Host；同一个 Note/operation 在 UI、CLI、MCP 返回稳定 ID 和来源关系。
- Desktop UI 增加插件管理和任务诊断，保留 ready gate、进度、取消、approval 和 SSE replay。
- 真实纵向场景：桌面安装 fixture 插件→链接生成 Note→外部 MCP Client 读取→CLI 创建关联 Note→桌面恢复查看关系。

## N06：Application/plugin candidate

- 新增 `candidate_app_migrations` 与 candidate/evidence/artifact/eval/decision 表域或等价不可变记录。
- scope allowlist 只有 Application 与 plugin；路径解析、diff target 和 artifact manifest 任一触碰 SDK 标识/路径/制品/contract 即拒绝。
- candidate 状态至少区分 staged、validating、rejected、approvable、approved/declined；一期不存在自动 `activated` Application 路径。
- 测试结果、evidence、risk、rollback 缺一不可 approvable；模型自报“安全”无效。
- UI 只展示、审批/拒绝和诊断；不自动 patch 当前 worktree、安装包或运行应用。
- plugin candidate 如需激活，必须转换为 N03 标准 package 并重新走校验/权限/active pointer。

## I04：交互集成

- 合入 N05/N06，统一 router/nav/migration bootstrap 和权限 UI。
- 验证 candidate 不可绕过 plugin installer，外部入口不绕过 Host。

## N07：E2E 与发布

- 运行全量自动化和真实 desktop/MCP/CLI/plugin/candidate 场景，记录环境、artifact hash、命令和结果。
- 验证源码启动、桌面 sidecar、打包资源和旧历史数据。
- 更新 current-architecture、product-rules、data-model、api-inventory、known-pitfalls、requirements index、Change Spec 和测试证据。
- 未完成的手机/Web/同步/复杂多 Agent 明确保持非目标。
- 仅在 SDK child requirement 与本 Application requirement 都 Implemented 时，将上游 P7 标记 Implemented。

## 不变量

1. Rust SDK 是唯一 Agent/Note Agent 行为事实源；NoteMeld 只适配。
2. `task_id` 是一期稳定 NoteId；不建立第二正文权威。
3. 同 SQLite 文件、独立表域和 migration registry。
4. 插件包不可变、先校验后激活、失败保留旧版本、不执行安装脚本。
5. Note 成功不被投影失败回滚。
6. SDK 永远不在 candidate 可修改范围。
