# NoteMeld new-product 真实系统接口矩阵（v1）

日期：2026-09-08  
状态：Implementation baseline  
关联需求：[`2026-09-06-notemeld-new-product-desktop-system-v2.md`](./2026-09-06-notemeld-new-product-desktop-system-v2.md)

本文把 `new-product` 的页面和应用原型映射到当前 NoteMeld 产品仓库已经存在的前端 service、后端 router、数据权威、权限边界和测试入口。它是进入生产 UI 迁移前的事实盘点，不把“已有原型”或“已有文件”当作功能已经完成。

## 判定规则

| 状态 | 含义 |
|---|---|
| `reuse` | 现有真实 service/API/数据链路可以直接复用，主要工作是新 UI 迁移和状态补齐 |
| `partial` | 有真实链路，但缺少新应用需要的聚合、列表、状态或权限闭环 |
| `missing` | 当前没有可确认的真实接口或数据权威，必须先补系统设计和契约 |
| `verify` | 代码或文档已有线索，但还没有完成逐接口/逐数据核对 |

## 1. 桌面宿主页面

| 页面 | 前端入口 | 后端/运行时 | 主要数据 | 当前判定 | 迁移要求 |
|---|---|---|---|---|---|
| D01 新对话 | `desktop/frontend/src/services/agent.ts`、`conversation.ts` | `routers/agent.py`；Agent Host；Workspace capability | conversation、agent_turn、conversation_context_refs、agent_events | `reuse` | 新 UI 接入真实 session/turn；保留幂等、取消、审批、事件序号和恢复语义 |
| D03 会话详情 | `agent.ts`、`conversation.ts` | Agent v1 session/turn/event/approval；文件/产物服务 | conversation、conversation_messages、agent_turns、agent_events、note_documents | `reuse` | 迁移消息、工具、审批、队列、文件面板和日志面板；禁止用前端状态冒充终态 |
| D06 插件应用 | `applications.ts`、`plugins.ts`、`mcpServers.ts` | `app/applications/router.py`、`routers/plugins.py`、`routers/config.py`、`routers/candidates.py` | applications、application_instances/runs/jobs/permissions、plugins、candidates | `implemented` | Capability Center/应用 Host/系统运行安全审批已统一接入真实列表、安装、启用、禁用、回滚、候选验证和激活；审批说明写入审计 |
| D09 设置 | `system.ts`、`usage.ts`、`transcriber.ts`、`downloader.ts`、`mcpServers.ts`、`migration.ts` | `routers/config.py`、`usage.py`、`migration.py`、`model.py`、`provider.py` | user preferences、models、providers、usage、device/config state | `implemented` | 通用配置保留在设置；笔记/学习/监控/系统运行已迁移到 APP01–APP04；自动启动、MCP、模型、转写、下载和迁移均消费真实 API |

## 2. 应用层映射

### APP01 笔记应用

| 能力 | 可复用链路 | 数据/状态 | 判定 | 缺口 |
|---|---|---|---|---|
| 笔记列表与详情 | `note.ts` `/notes/library`、`conversation.ts`；`routers/imported_notes.py`、`conversation.py` | conversations、note_documents、task status | `implemented` | APP01 已接入真实分页、搜索、筛选、详情弹层和空/加载/失败状态；笔记正文仍以 Agent Host note authority 为唯一来源 |
| 笔记样式与模板 | `noteStyle.ts`；`routers/note_style.py` | note styles、extraction tasks | `reuse` | 新 UI 迁移 CRUD、抽取、重试、取消和内置样式保护 |
| Wiki 图谱/文章/关系 | `wiki.ts`；`routers/wiki.py` | graph、communities、pages、articles、file pages | `reuse` | 增加应用级加载/空/重建/失败状态；图谱大数据量需要分页、分层或增量加载 |
| Wiki 重建 | `note.ts`、`wiki.ts`；`routers/note.py`、Wiki job/service | wiki task、note document wiki status | `implemented` | APP01 轮询真实任务状态，支持取消、失败/取消重建，完成状态由后端 Wiki job 写回 |
| 旧笔记/Markdown 导入 | `conversation.ts`、`note.ts`；`imported_notes.py` | imported notes、note documents、ingestion jobs | `implemented` | APP01 通过真实 Markdown import service 导入并刷新 canonical note library；文件名/格式校验和失败提示由服务端返回 |

### APP02 学习应用

| 能力 | 可复用链路 | 数据/状态 | 判定 | 缺口 |
|---|---|---|---|---|
| 学习空间/画布 | `learning.ts`；`routers/learning.py` | learning canvas、learning units、evidence | `implemented` | APP02 已接入持久化空间列表、画布节点、白板生成、编辑冲突恢复和发布笔记 |
| 掌握验证 | `startLearningUnit`、`submitLearningEvidence` | unit mastery、evidence、rubric result | `reuse` | 明确 exposed/reviewing/mastered 状态和错误/证据不足状态，不能前端直接写 mastered |
| 复习 | `learning.ts`；`GET /learning-reviews/due` | review schedule、mastery state | `implemented` | 后端按所有持久化学习空间聚合到期项目，APP02 可进入来源画布和掌握验证 |
| 语义白板 | `whiteboard.ts`；`routers/whiteboard.py` | whiteboard snapshot、revision、cards、relations、context refs | `reuse` | 迁移编辑、冲突 409、保存失败、撤销/重试和权限错误 |
| 发布为笔记 | `publishWhiteboard` | note document、published revision、index/Wiki job | `reuse` | 发布动作必须显示异步任务和最终结果，不能同步假设 Note 已完成 |

### APP03 监控应用

| 能力 | 可复用链路 | 数据/状态 | 判定 | 缺口 |
|---|---|---|---|---|
| Token 用量明细 | `usage.ts`；`routers/usage.py` | model_usage_records | `reuse` | UI 接入分页、日期/provider/model 筛选和任务聚合；保留空统计和查询失败 |
| 供应商/任务聚合 | `system.ts` `GET /monitoring/snapshot` | provider、model、task usage | `implemented` | 统一快照固定时间窗口、provider 筛选、任务/供应商聚合和权限边界；APP03 所有卡片消费同一快照 |
| 部署状态 | `system.ts`；`routers/config.py` `/deploy_status` | backend/cuda/whisper/ffmpeg/mcp checks | `reuse` | 统一健康快照和最后检查时间；区分 unavailable、degraded、healthy |
| GPU/CUDA/MCP/自动启动 | `system.ts`、`mcpServers.ts` | local runtime/config state | `implemented` | 监控/设置读取真实检测结果；自动启动通过专用读写 API 保存并返回实际状态，不以启动脚本推断成功 |
| 插件/转写健康 | `plugins.ts`、`transcriber.ts` | plugin runtime status、model download status、transcriber config | `reuse` | 统一健康时间线、错误详情和重试入口 |
| 监控首页快照 | `GET /api/monitoring/snapshot`；`system.ts` | model usage、task summary、deploy status、plugin runtime | `implemented` | APP03 已接入统一快照、30 秒刷新、provider 筛选、健康状态、GPU/CUDA、Whisper、MCP 和插件状态 |

### APP04 系统运行

| 能力 | 可复用链路 | 数据/状态 | 判定 | 缺口 |
|---|---|---|---|---|
| Agent Turn 诊断 | `agent.ts`；`routers/agent.py` diagnostics/events | agent_turns、agent_events | `reuse` | 迁移事件序号、最后错误、恢复点、耗时和事件明细；必须按 turn 权限隔离 |
| Application 实例/项目目录 | `applications.ts`；`app/applications/router.py` | applications、instances、runs、jobs | `reuse` | 迁移 Host 状态、run 生命周期、日志 ring buffer、取消和 artifact 下载 |
| 外部文件读取权限 | `applications.ts` workspace/external roots | application permissions/settings | `reuse` | 使用绝对路径校验、越权拒绝和审计；界面不能回显不必要的本地路径 |
| Candidate 验证/人工审批 | `candidates.ts`；`candidates.py` | candidates、validation evidence、audit | `implemented` | APP04 展示安全声明、风险、权限、测试、rollback 和验证错误；审批说明写入审计，Application 仍需独立激活 |
| 桌面更新 | Tauri updater plugin、`AboutPage`、Release workflow、`latest.json` generator | updater state、signed artifact metadata | `partial` | 已接通检查/下载/重启、签名包生成和 manifest；仍需 CI secret、公网 Release 资产与回滚安装验收 |
| 设备身份/LAN/Relay/远程帧 | `deviceIdentity.ts`、Device Connectivity Panel、Cloud device/relay API、RemoteFrame adapters | device keys、grants、relay cursors、opaque frames | `partial` | 桌面 UI、Cloud Host bootstrap、移动端 E2EE/AAD 已接通；仍需真实设备矩阵核对 LAN proof、Relay fallback、断线和远程帧回执 |

## 3. 插件能力归属

以下能力不在 APP01–APP04 中重复实现，统一由 D06 的插件/Capability Host 管理；应用只消费结构化结果、任务状态和证据引用：

| 能力 | 当前事实入口 | 状态 |
|---|---|---|
| 视频/音频/网页采集与导入 | Agent capability registry、ingestion services、content conversion plugins | 已有能力线索，需补应用级任务投影 |
| Whisper 配置/模型下载/转写 | `transcriber.ts`、`routers/config.py` | `reuse` |
| 下载器/Cookie/平台视频 | `downloader.ts`、`routers/config.py`、downloaders | `reuse`，Cookie 不入日志 |
| OCR/视频帧/文档解析 | Agent Host atomic media capabilities、content conversion plugins | `reuse`，需统一 artifact/evidence schema |
| 证据锚点/知识切片审阅 | `ingestion.ts`、`IngestionReviewPanel.tsx`；ingestion report/evidence/chunks API | `implemented`，由真实 ingestion artifact manifest、证据锚点和知识切片驱动审阅 |

## 4. 跨端与安全门禁

| 领域 | 事实来源 | 本轮门禁 |
|---|---|---|
| Agent 唯一运行时 | Agent Host + SDK contract | UI 只能消费 session/turn/event/approval，不复制 Agent loop |
| Workspace/文件 | Workspace capability、application external roots、Cloud device scopes | 真实路径不进入日志或分享；每次读取经过 Host 权限校验 |
| 插件/Application | manifest、permission、candidate、plugin manager | 安装、启用、审批、回滚、禁用必须可审计且可恢复 |
| Cloud/设备/Relay | `docs/system/api-inventory.md` Cloud v1 + relay 契约 | Cloud 只做控制面；Relay 只转发加密帧，不保存消息明文 |
| 数据重建 | migration/reindex/Wiki rebuild | 允许丢失旧数据，但必须明确确认、写入审计、可观察进度和失败状态 |

## 5. 当前剩余验收门禁

1. 桌面、Cloud 和移动端的实现已经按本矩阵进入统一实现计划；新增能力必须继续同步 registry、API、数据权威和测试证据。
2. 桌面更新仍需在 GitHub Actions 配置签名密钥后完成 macOS ARM/Intel、Windows 的公开 Release、安装、更新和回滚验收。
3. 设备身份/LAN/Relay/远程帧仍需真实 Android、iOS、Harmony 设备或等价 device farm 验证 LAN proof、Relay fallback、断线恢复和远程回执；源码、模拟器和协议契约通过不替代该门禁。
4. 生产部署仍需由部署环境提供邮件、OpenAI-compatible Provider 和 S3-compatible backup 的具体凭据/地址；代码已提供适配接口、失败处理和安全边界，不在产品规格中锁定供应商。
