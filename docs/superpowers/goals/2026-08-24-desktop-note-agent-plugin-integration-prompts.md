# NoteMeld 桌面 Note Agent 与插件集成 Codex Goal 提示词

依据：`docs/requirements/2026-08-24-desktop-note-agent-plugin-integration.md`
顺序：SDK S08 → N01 →（N02 ∥ N03 ∥ N04）→ I03 →（N05 ∥ N06）→ I04 → N07。

所有 Goal 默认在 NoteMeld 独立 linked worktree 中执行；保护用户改动，不碰 `.agents/skills` 既有删除，不修改 SDK 仓库，不 push/发布；实际测试未通过不得完成。

## N01

```text
/goal 在 /Users/hehejie/ai/notemeld-project/NoteMeld 完成 N01“SDK artifact intake 与产品 baseline 冻结”。开始前验证 notemeld-agent-sdk 的 2026-08-24 child requirement 已 Implemented，S08 handoff 提供固定 version/schema/ABI/commit/artifact SHA-256 和 supported conformance；任何一项缺失就保持 Goal 未完成并准确报告，不绑定开发快照。完整阅读 NoteMeld AGENTS.md、CLAUDE.md、Change Spec、Requirement/Plan/Spec。创建独立 linked worktree。复用现有 loader 做 hash/version/native/binding fail-closed；自动生成并测试当前 URL 能力 baseline；冻结 note_documents.task_id 作为一期 NoteId 和各投影权威边界；冻结 SDK DTO/adapter seam。更新证据 N01 行并提交，汇报 artifact、baseline、测试和供 N02-N04 使用的固定 commit/contract。
```

## N02

```text
/goal 基于 N01 固定 commit，在 NoteMeld 完成 N02“NoteMeld Note Store adapter”。阅读 Requirement/Plan/Spec N02，创建独立 linked worktree；不修改 plugin installer、链接解析器、前端导航或 candidate。实现 SDK NoteStore/OperationStore/Authority 的薄 adapter，以现有 note_documents.task_id 为稳定 NoteId，不创建第二正文权威；新增独立 note migration registry 和来源/关系/operation/provenance 表域。实现 same request 幂等、different payload conflict、版本并发、needs-attention 和 Note 成功/投影失败分离。用真实临时 SQLite 重开和多 registry 共存测试验证。更新证据 N02 行并提交，汇报 schema、事务边界、测试和 I03 共享文件。
```

## N03

```text
/goal 基于 N01 固定 commit，在 NoteMeld 完成 N03“插件安装与运行控制面”。阅读 Requirement/Plan/Spec N03，创建独立 linked worktree；不修改链接业务实现、Note adapter 或 candidate。实现 HTTPS GitHub/Gitee Release resolver、受限 redirect/size/timeout、唯一 staging、SDK package verifier、不可变版本目录、原子 active pointer、权限 authority、按需 runtime、升级/回滚/禁用和审计；永不执行 install script。新增独立 plugin migration registry、API response wrapper、设置页及 ready gate。用本地/fake Release fixture 覆盖 hash、zip-slip、license/version、权限、崩溃和旧版本保留。更新证据 N03 行并提交，汇报测试和 I03 共享文件。
```

## N04

```text
/goal 基于 N01 固定 commit，在 NoteMeld 完成 N04“官方链接转 Note 插件”。阅读 Requirement/Plan/Spec N04，创建独立 linked worktree；不修改 plugin control-plane、Note DB adapter、全局 router/nav。以 N01 自动 inventory 为硬 baseline，把当前全部 URL 类型及字幕优先、下载、转写、截图、多源总结、网页抓取、任务状态和降级迁入可独立打包的 official-link-note 插件；Application 入口最终只调用 capability，禁止保留双实现。插件不直接写 SDK Event、Conversation 或内部 SQLite，而通过 host/Note operation port。生成标准 package/本地 Release fixture和 before/after matrix，运行全部平台专门回归。更新证据 N04 行并提交；任何 URL 能力回退都不得完成。
```

## I03

```text
/goal 在 NoteMeld 执行 I03“产品基础集成”。确认 N02/N03/N04 都基于同一 N01 commit 完成。使用专用集成分支按 N02→N03→N04 合入，不修改 SDK、不 push；统一 DB bootstrap/registry、router、storage paths、frontend routes/nav、plugin resource 和 packaging，解决共享冲突但不新增功能。删除/关闭内建链接双路径，证明生产入口来自已安装 official plugin。运行三组 focused tests、backend compile、Agent Host tests、frontend contracts/build 和核心链接回归。提交 I03 固定 commit，汇报供 N05/N06 使用的 API/schema、测试与风险。
```

## N05

```text
/goal 基于 I03 固定 commit，在 NoteMeld 完成 N05“桌面/MCP/CLI/外部 Agent 闭环”。阅读 Requirement/Plan/Spec N05，创建独立 linked worktree；不修改 candidate domain。让 UI、CLI、MCP 和外部 Agent 经现有 /api/agent/v1/Host 使用同一 SDK Note Agent、capability 和 Note authority，禁止直接写 SQLite/Event。补插件管理/任务诊断 UI、ready gate、approval/cancel/SSE/session-busy 回归。用固定 artifact 与真实本地 MCP Client 跑纵向：安装插件→链接生成 Note→MCP 读取→CLI 创建关联 Note→桌面恢复关系。更新证据 N05 行并提交；mock-only 不算完成。
```

## N06

```text
/goal 基于 I03 固定 commit，在 NoteMeld 完成 N06“Application/plugin candidate 安全边界”。阅读 Requirement/Plan/Spec N06，创建独立 linked worktree；不修改 MCP/CLI/链接业务。实现独立 candidate migration/table/domain/service/API/UI，保存 scope、evidence/trace、artifact/patch、测试、风险、权限和 rollback；SDK 路径/制品/公共契约为不可修改硬边界。缺 evidence/test/rollback、越权或模型自报安全均不能 approvable。Application candidate 一期只展示/审批/拒绝，绝不自动 patch/激活；plugin candidate 必须重新进入 N03 标准包流程。更新证据 N06 行并提交，汇报 deny tests 和 I04 共享文件。
```

## I04

```text
/goal 在 NoteMeld 执行 I04“外部入口与 candidate 集成”。确认 N05/N06 基于 I03 完成，使用专用集成分支按 N05→N06 合入，不 push。统一 router、nav、migration bootstrap 和权限 UI；证明 candidate 不能绕过 plugin installer，UI/CLI/MCP 不绕过 Agent Host。运行两组 focused tests、frontend contracts/build、backend compile 和 Agent Host/MCP 回归。提交 I04 固定 commit，输出 N07 使用的集成结果。
```

## N07

```text
/goal 在 NoteMeld 完成 N07“全链路验收与发布收口”。确认 SDK child requirement Implemented、N01-N06/I03/I04 完成。使用 release-candidate 集成分支，保护用户改动，不 push/upload。运行 backend compile、全部 backend tests、frontend contracts/build、core regression、固定 SDK loader、GitHub/Gitee Release fixture、全 URL baseline、plugin rollback、同 SQLite migration isolation、candidate SDK deny；真实运行桌面 sidecar/UI、CLI 和外部 MCP Client 纵向场景。更新 current-architecture、product-rules、data-model、api-inventory、known-pitfalls、Change Spec、requirements index 和测试证据。任何 required 失败保持 Planned；全部通过后标记 Application child requirement 与上游 P7 Implemented，汇报 commit、测试计数、artifact/hash、纵向证据和明确后置范围。
```
