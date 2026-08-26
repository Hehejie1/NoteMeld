# Change Spec：桌面 Note Agent 与插件化个人知识库一期

日期：2026-08-24
状态：Planned
Canonical requirement：`../requirements/2026-08-24-desktop-note-agent-plugin-integration.md`

## 0. 预检查

- [x] 已阅读 current-architecture、product-rules、data-model、api-inventory、known-pitfalls。
- [x] 已搜索 Agent Host、Note、MCP、下载器/采集器、SQLite、桌面和测试。
- [x] 已确认已有 SDK artifact、Agent v1、Note generation、MCP、CLI、ready gate 和链接处理能力。
- [x] 当前只写变更文档，不修改运行数据或发布服务。

## 1. 当前系统现状

- 相关模块：`backend/app/agent_host/`、`routers/note.py`、`routers/agent.py`、`routers/mcp.py`、`services/note*.py`、`services/web_note.py`、`downloaders/`、`transcriber/`、`frontend/src/pages/`、`desktop/src-tauri/`。
- 数据：`note_documents`、Agent Turn/Event/Conversation 表、`note_results/`、Wiki、Chroma；当前不是单一 Note operation/provenance 模型。
- API：`/api/agent/v1`、Note/task API、`/mcp`、CLI 已存在。
- 当前行为：链接处理和 Note 生成是 Application 内建链路；plugin manifest 基础位于独立 SDK，但产品暂无完整 Release 安装控制面。
- 当前限制：通用 Note Agent 未发布；插件不能从 Release 安全安装；链接能力不能独立升级；candidate 流程缺失。

## 2. 本次目标

- 消费固定 SDK Note Agent artifact，建立现有 Note 的薄 adapter。
- 用标准插件控制面承载全部现有链接转 Note 能力。
- 打通桌面、CLI、MCP 和同机外部 Agent 的能力发现/读写/继续使用闭环。
- 建立 Application/plugin candidate 安全边界，不自动激活 Application 修改。
- 必须保留旧 Note、task_id、链接覆盖、字幕/转写/截图/fallback、Agent v1、CLI/MCP 和桌面启动行为。

## 3. 明确不做

- 手机/Web/跨设备同步、多人协作、中心市场、复杂 Multi-agent DAG。
- Agent 修改 SDK；Application candidate 自动激活。
- 任意 Git clone + install script；一次性插件化全部白板/IM/文档业务。

## 4. 冲突分析

- 产品规则：目标保持本地优先、唯一 Agent loop、来源可追溯和 Host 权威；实现后需把通用 Note 移入 SDK L2 的新边界写回系统规则。
- 数据语义：保留 `task_id`，不复制正文权威；新增 provenance/relation/operation/plugin/candidate 独立表域。
- API：保留 response wrapper、Agent v1 和 `/mcp`；新增接口须写回 inventory。
- 已知坑：重点防止第二 loop、SDK/version 漂移、SQLite migration 冲突、replay 重复副作用、Note 成功被投影失败回滚、MCP 凭证/路径泄漏和 capability 全量预加载。
- 运行模式：影响源码、桌面、CLI、MCP 和打包；不影响线上服务或跨设备同步。

## 5. 影响范围

- 后端：Agent Host、Note store、plugin/candidate services、routers、DB migrations、storage paths、MCP。
- 前端：插件设置、candidate 展示、任务诊断和 service/types。
- 桌面/打包：SDK artifact pin、official plugin resource/首次安装、sidecar ready 和发布校验。
- 测试：Agent Host、Note、collector/downloader、MCP、migration、packaging、frontend contracts、真实纵向。
- 文档：五份 system docs、requirements index、Change Spec 和验收证据。

## 6. 实施方案

### 后端

- SDK artifact intake 后新增薄 Note adapter；复用现有 Agent Host 生命周期。
- plugin control plane 采用 staging→verify→immutable install→atomic active pointer。
- 链接生成移动到 official plugin package，进度/取消通过 host callback，Note 通过 operation port 提交。
- candidate 只保存和验证，SDK scope deny，Application 不自动激活。
- 所有外部调用有 timeout/cancel/redaction；业务失败转稳定错误，不泄漏原始 payload。

### 前端

- 设置中提供 plugin/candidate 控制面；工作台链接入口保持用户心智不变。
- 所有页面等待 BackendInit ready；展示 loading/empty/error/rollback/permission 状态。

### 桌面/打包

- 固定并校验 SDK artifact；official plugin 作为标准包发布/首次可安装资源。
- 不从 SDK 源码 fallback；不执行插件安装脚本。

## 7. 数据变更

- 新增独立 `note_agent_app_migrations`、`plugin_app_migrations`、`candidate_app_migrations` 或经 Spec 冻结的等价 registry。
- 新增来源/关系/operation/provenance、plugin version/permission/audit、candidate/evidence/eval/decision 表域。
- 不修改共享 `PRAGMA user_version`；不复制 `note_documents` 正文。
- 历史数据懒适配，以 `task_id` 为 NoteId；投影可重建。
- 回滚保留新增表和不可变历史，只切回旧 plugin active pointer/旧应用版本。

## 8. 接口变更

- 新增 plugin list/install/upgrade/rollback/permission/diagnostic API。
- 新增 candidate list/get/validate/approve/decline API；无 Application activate API。
- 扩展 MCP Note/capability 工具，但保持标准 JSON-RPC/auth/path/redaction。
- 所有普通 `/api` 返回 `ResponseWrapper`；文件/流/MCP 例外明确记录。
- 实现时更新 `docs/system/api-inventory.md`。

## 9. UI/交互变更

- 设置页增加插件和升级候选入口。
- 插件安装展示 source、version、hash、permissions、active/previous、诊断和回滚。
- 链接输入入口不改变；失败显示可分类错误和恢复动作。
- candidate 只允许查看、审批/拒绝；明确“一期不会自动应用”。
- 桌面 ready gate、键盘/焦点和错误可访问性必须回归。

## 10. 测试方案

- 后端：Note adapter/幂等/事务、plugin supply-chain、candidate deny、Agent Host/MCP、链接 baseline。
- 前端：services/types/routes/ready/loading/error/permission/rollback/candidate no-activate contract。
- 构建：compileall、pytest、frontend contracts/build、core regression、packaging contracts。
- 手动/纵向：桌面安装→链接 Note→MCP 读取→CLI 关联→桌面恢复；GitHub/Gitee fixtures；candidate SDK deny。
- 回归：旧历史 Note/task/Conversation/Wiki/导出可读，所有当前链接类型无减少。

## 11. 验收标准

- [ ] SDK S08 固定 artifact 是唯一 Note Agent 运行输入。
- [ ] Note adapter 不建立第二正文权威，独立 migrations 共存。
- [ ] Release 插件安装/升级/回滚和供应链失败安全。
- [ ] 全 URL baseline 插件化后无回退且无双实现。
- [ ] Desktop/MCP/CLI/外部 Agent 使用同一 Note 和 capability。
- [ ] candidate 不能修改 SDK，Application 不自动激活。
- [ ] 全量自动化与真实纵向证据通过。

## 12. 风险和回滚

- SDK contract 漂移：loader fail closed；回到上一固定 artifact。
- 链接能力回退：保留上一应用 release/official plugin active version，baseline gate 阻止发布。
- 插件损坏：staging 隔离，原子 pointer 不切换。
- 数据迁移异常：独立 registry + forward-only migration；旧表不删除，应用回滚仍可读旧 Note。
- Note 双写：强制单一 commit adapter；projection 失败独立诊断。
- candidate 越权：scope/path/artifact 三重 deny；不存在自动 Application activate 路径。

## 13. Agent 必答问题

- 影响模块：Agent Host、Note、DB、MCP/CLI、桌面、插件、链接采集、candidate、打包。
- 类似能力：SDK artifact integration、Agent v1、Capability Registry、Note generation、MCP、自动更新均已有部分基础。
- 产品规则冲突：仅通用 Note 归属从旧 Application-only 演进为 SDK L2；其余保持。
- 数据冲突：通过 task_id 映射、单一正文权威、独立 registry 规避。
- known pitfalls：已纳入第二 loop、replay、migration、projection、credential/path、artifact drift 门禁。
- 本地/线上影响：只影响本地 SQLite、插件目录、SDK/plugin artifact 和桌面包；无云同步。
- 最小改动：复用现有 Host/Note/CLI/MCP/ready gate，以 adapter 和 plugin control plane 替换业务直连。
- 防回归测试：见第 10 节和 Test evidence 文档。
