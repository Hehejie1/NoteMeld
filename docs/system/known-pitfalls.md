# Known Pitfalls

更新时间：2026-08-13

本文记录历史踩坑和回归防线。修 Bug、新需求或重构前必须确认不会重新引入这些问题。

## Wiki 同步 materialize 卡死 UI

- 发生过的问题：Wiki 总结阶段出现长时间卡顿，任务卡在 `materialize`。
- 根因：笔记保存路径同步执行完整 Wiki materialize，且 `WikiPageMerger` 调用 LLM 合并页面时持有全局写锁；模型接口慢或超时会拖慢所有后续任务保存。
- 不允许重新引入的错误做法：在笔记任务保存路径中同步重建完整 Wiki；把慢 LLM 请求放进 `_WIKI_WRITE_LOCK`。
- 检查方式：`backend/tests/test_wiki_rebuild_service_contracts.py` 应覆盖 contribution 保存不 materialize；代码审查搜索 `WikiStore.persist(`、`rebuild_from_contributions(`、`WikiPageMerger().merge`。
- 修复经验：笔记任务只做单篇知识抽取和 contribution 保存；完整 Wiki rebuild 交给独立 `WikiRebuildService`；LLM merge 设置超时。

## Wiki rebuild 必须 latest-wins

- 发生过的问题：多个 Wiki 更新请求可能堆积，旧任务覆盖新任务或长时间占用资源。
- 根因：全局 Wiki 重建是跨任务共享资源，缺少 generation/cancel 语义会导致过期结果落盘。
- 不允许重新引入的错误做法：排队执行所有 rebuild；取消请求只改状态不停止当前重建；旧 generation 继续写 live Wiki。
- 检查方式：检查 `backend/app/services/wiki_rebuild_service.py` 中 `_generation`、`_current_cancel`、`cancel_check`；运行 `backend/tests/test_wiki_rebuild_service_contracts.py`。
- 修复经验：新 rebuild 请求递增 generation 并 set 当前 cancel event；materialize 中定期检查 cancel。

## 取消 rebuild 后清空 live Wiki

- 发生过的问题：rebuild 刚开始先清空 `sources/entities/concepts`，随后被新请求取消，前端短暂读到空 Wiki 或 404。
- 根因：删除 live 目录发生在 cancel check 或 staging 原子替换之前。
- 不允许重新引入的错误做法：在可取消流程中先删除 live 数据，再慢慢重建。
- 检查方式：审查 `WikiStore._materialize_from_packets()` 是否 reset 前检查 cancel；必要时补充 staging 目录原子替换测试。
- 修复经验：至少 reset 前检查 cancel；更稳妥是写 staging，确认未取消后再原子替换 live。

## Wiki 文件并发写 tmp 冲突

- 发生过的问题：并发写同一路径时固定 `.tmp` 文件互相覆盖，可能触发 `FileNotFoundError` 或写入旧内容。
- 根因：`_atomic_write_text()` 使用 `path.with_suffix(path.suffix + ".tmp")` 固定临时文件名；新增无锁 `persist_contribution()` 与 rebuild 可并发写。
- 不允许重新引入的错误做法：多个线程/worker 对同一路径使用同一个 tmp 文件；去掉写锁后不改 atomic write。
- 检查方式：搜索 `_atomic_write_text`；审查 `persist_contribution()`、`_write_status()`、task status 写入是否存在同路径并发。
- 修复经验：短写入可加互斥；更通用是唯一 tmp 文件名加 `replace()`，并避免旧 generation 覆盖新结果。

## 历史 running/materialize 状态误导 UI

- 发生过的问题：大量 Wiki 页面长期显示“正在提取中”。
- 根因：旧状态文件残留 `status=running, stage=materialize`；前端把非 success/failed/canceled/partial 状态映射为 pending 类展示。
- 不允许重新引入的错误做法：把历史残留状态当成真实后台任务；只改前端文案不清理状态语义。
- 检查方式：核对 `wiki_rebuild_job.json`、单篇 Wiki job 文件、`note_documents.wiki_status` 和前端状态映射。
- 修复经验：区分单篇 analysis 状态和全局 rebuild 状态；必要时提供脏状态清理或更准确文案。

## 桌面 sidecar 未 ready 时前端抢跑

- 发生过的问题：桌面启动期间前端业务请求早于 backend sidecar 就绪，导致错误弹窗或空状态。
- 根因：前端没有等待 Tauri runtime 注入和 `/sys_health` 成功。
- 不允许重新引入的错误做法：组件 mount 后无条件请求 workspace、models、conversations、tasks。
- 检查方式：运行 `frontend/tests/backendReadyGatesWorkspaceRequests.test.mjs`、`frontend/tests/useCheckBackendNonBlockingContracts.test.mjs`、`frontend/tests/backendInitStartupWindowContracts.test.mjs`。
- 修复经验：通过 BackendInitContext 和 ready gate 控制业务请求；首次启动窗口必须足够长。

## 桌面首次启动等待窗口过短

- 发生过的问题：PyInstaller、模型、SQLite 或 ffmpeg 初始化较慢时，用户看到启动失败。
- 根因：前端或桌面壳等待时间不足。
- 不允许重新引入的错误做法：为了“更快失败”把首次启动静默等待降到 60 秒以下。
- 检查方式：`frontend/tests/backendInitStartupWindowContracts.test.mjs`。
- 修复经验：保留足够长的 silent check，后续再显示可操作错误。

## MCP 路径穿越和 API Key 泄露

- 发生过的问题/风险：MCP `get_note` 如果直接拼路径会读取数据目录外文件；`list_models` 如果返回 Provider 原始对象会泄露 API Key。
- 根因：MCP 是 AI IDE 可调用入口，安全边界比普通 UI 更敏感。
- 不允许重新引入的错误做法：把文件路径作为可信输入；把 provider rows 原样返回；日志打印完整 headers/payload。
- 检查方式：`backend/tests/test_core_mcp_generation_tools.py`；搜索 `api_key`、`read_text`、`Path(` 在 MCP service 中的使用。
- 修复经验：按 taskId/title 映射读取，拒绝 `..` 和绝对路径；MCP 模型列表只返回必要字段。

## MCP 设置脱敏后编辑覆盖真实凭证

- 发生过的问题/风险：列表接口只移除 `auth`，却回显任意 header/env 原值；前端再把 `***` 或空 auth 通过整体 PUT 写回，导致凭证泄露或启用切换后认证失效。
- 根因：不同 MCP 配置接口各自实现脱敏，且后端没有区分“用户输入新值”和“脱敏占位符/字段省略”。
- 不允许重新引入的错误做法：只脱敏 Authorization 而信任其他 header/env；把 `***` 写入配置；省略 auth 时清空旧 token；把保存异常原文返回前端。
- 检查方式：`backend/tests/agent/test_mcp_config_api.py`、`test_mcp_client.py::SaveLoadRoundTripTest`；确认 list/enabled/upsert 三条响应都不含 secret，编辑和 enabled 切换后旧凭证仍在。
- 修复经验：所有响应复用单一 sanitizer；auth 完全移除，headers/env 的所有值统一占位；PUT 按 `model_fields_set` 和占位符合并旧值；配置文件用唯一 tmp + 原子替换，错误只暴露安全文案和类型。

## Agent 首轮无条件 Wiki 搜索和全工具 schema 膨胀

- 发生过的问题/风险：free-chat 默认 `mixed` 且前端固定 `use_wiki=true`，导致首次 LLM 调用前几乎每轮遍历 Wiki；同时 Agent 每轮平铺 workspace、memory 和全部 Skill schema。继续直接接入第三方 MCP 会叠加网络发现、提示词噪声和连接泄漏。
- 根因：把“允许使用 Wiki/工具”实现成“请求前立即检索/一次性注册全部 schema”，缺少能力目录和渐进披露层。
- 不允许重新引入的错误做法：Agent hooks 调 `_prepare_free_chat_context()` 时省略 `prefetch_wiki=False`；在 `run_free_chat*` 直接把真实 Skill/MCP 工具放入 `AgentState.tools`；L0/L1 输出 MCP URL/header/env/token；请求结束不关闭 MCP adapter。
- 检查方式：`backend/tests/agent/test_capability_catalog.py`、`backend/tests/agent/test_agent_service_p3_integration.py`；首轮工具名必须恰为 `capability_discover/capability_describe/capability_invoke`，L0 不超过 1200 字符，MCP L0/L1 discovery 次数为 0。
- 修复经验：用请求级 `CapabilityRegistry` 统一 Wiki、builtin、memory、workspace、Skill、MCP；L0 只读 graph/config 元数据，L1 发现、L2 描述、L3 执行；`use_wiki=false` 双重门禁；non-stream/stream 都在 `finally` 关闭 registry。

## 把“读过”误判成“学会”或丢失学习状态

- 发生过的问题/风险：AI 展示一段解释后直接把节点标为 mastered；即时问答通过后不安排延迟复测；画布只存在前端内存，刷新或重启后作答、当前节点和复习队列消失。
- 根因：把内容消费事件和掌握证据混为一个布尔字段，或只持久化静态图而没有 session/evidence/review 状态机。
- 不允许重新引入的错误做法：前端直接写 `mastered`；`start_unit` 推进到 provisional/mastered；接受空答案、缺 rubric 字段、越界分数或低分 `passed=true`；复用固定 canvas `.tmp`；只锁 `save()` 而在锁外 `load→mutate`；只写消息 meta 不写完整 canvas artifact。
- 检查方式：运行 `backend/tests/learning/test_learning_session_service.py`、`test_learning_canvas_store.py`、`test_learning_api.py::test_parallel_evidence_submissions_do_not_overwrite_each_other`、`frontend/tests/learningCanvasContracts.test.mjs`；确认 48 小时 review 门禁、并发证据不丢失和刷新恢复。
- 修复经验：展示只记 `exposed`；后端验证 learner answer + rubric，recall/apply 后只到 `provisional`，到期 review 才可 `mastered`；所有 canvas 读改写必须经 store 事务锁并原子写入会话 workspace，消息只存索引。

## pytest 收集期 stub 污染全局模块表

- 发生过的问题：测试文件用 `sys.modules.setdefault("app.services.web_note", stub)` 隔离重量依赖后不恢复，导致同一进程后续真实契约测试从 stub 导入符号并在收集阶段失败；单文件运行却全部通过。
- 根因：模块级 stub 生命周期跨越了测试文件边界，测试结果依赖 pytest 收集顺序。
- 不允许重新引入的错误做法：在模块顶层永久写 `sys.modules`；以“两个测试单独都绿”替代全量单进程验证。
- 检查方式：`PYTHONPATH=backend python3 -m pytest backend/tests -q` 必须作为最终门禁；检查 stub 导入后是否立即恢复原模块表。
- 修复经验：优先使用作用域内 patch；确需收集期 stub 时，在目标 router 导入完成后只删除自己注册的同一 stub 对象。

## Markdown 上传 MIME 兼容被删

- 发生过的问题：浏览器会把 `.md` 上传识别为 `application/octet-stream` 或 `binary/octet-stream`，严格 MIME 会误拒。
- 根因：只按 MIME 白名单判断，不结合扩展名和内容解析。
- 不允许重新引入的错误做法：删除 Markdown octet-stream 兼容；只看 MIME 或只看扩展名。
- 检查方式：`backend/tests/test_core_upload_contracts.py`。
- 修复经验：扩展名、MIME、大小和内容签名/解析共同判断。

## DMG 发布只做本地 hdiutil verify

- 发生过的问题/风险：本地可挂载不代表用户机器可安装、可通过 Gatekeeper、可更新。
- 根因：发布校验不完整，缺少 Developer ID、公证、staple、codesign、双架构和公网回验。
- 不允许重新引入的错误做法：正式发布只跑 `hdiutil verify`；只构建 Apple Silicon；使用 Homebrew 动态库 ffmpeg。
- 检查方式：`frontend/tests/dmgPackagingContracts.test.mjs`，`.trae/skills/notemeld-dmg-packaging/`，`packaging/scripts/build-backend-macos.sh`。
- 修复经验：正式发布使用 `--release --upload --public-verify`，并强制双架构、公证、Gatekeeper、SHA256 公网校验。

## 桌面更新入口残留坏版本

- 发生过的问题/风险：云端 `latest.json` 继续指向有问题的 `0.1.0`，导致本地 `0.0.3` 客户端提示升级到坏版本；release 下载页或根站首页 `https://notemeld.wiki/` 也可能保留旧 DMG 链接。
- 根因：DMG 发布目录、Tauri updater manifest、release 下载页和根站首页是不同产物，清理或发布 DMG 时未同步清理 `latest.json`、`*.app.tar.gz`、签名文件和所有公开下载入口。
- 不允许重新引入的错误做法：只删除或上传 DMG，不检查 `latest.json`；只更新 `/srv/filebox/releases/notemeld/stable/index.html`，漏掉 `/var/www/notemeld.wiki/index.html`；让公开下载页继续引用已废弃版本；发布请求不确认版本策略。
- 检查方式：发布或下架后必须 `curl` 校验 `latest.json`、废弃版本 DMG URL、release 下载页 `/releases/notemeld/stable/index.html`、根站首页 `https://notemeld.wiki/` 中的版本号和链接。
- 修复经验：用户说“打包并部署到云端”时先确认版本策略，默认建议当前版本递增一个 patch 小版本；如果需要 major/minor/beta/非正式版，必须先确认。坏版本下架时删除 updater manifest、updater 压缩包、签名文件、坏版本 DMG，并同步 release 下载页和根站首页。

## 迁移和导入绕过索引重建

- 发生过的问题/风险：导入数据后笔记存在但检索/Wiki/索引不可用。
- 根因：迁移导入只复制文件，不触发 reindex/rebuild。
- 不允许重新引入的错误做法：导入 zip 后直接返回成功，不创建 job 或不重建索引。
- 检查方式：`backend/tests/test_core_migration_contracts.py`、`backend/tests/test_core_migration_api_contracts.py`、迁移路由 `/api/migration/reindex`。
- 修复经验：迁移使用 job store，导入后默认重建索引，并保留下载/查询 job 能力。

## 任务状态和会话消息不同步

- 发生过的问题/风险：状态文件成功但会话不显示结果，或会话进度残留旧状态。
- 根因：只写 `note_results` 文件，没有同步 `conversation_messages` 和 `note_documents`。
- 不允许重新引入的错误做法：绕过 `emit_note_progress()`、`emit_note_result()`、`register_task_conversation()` 创建任务。
- 检查方式：`backend/tests/test_core_task_status_contracts.py`、`backend/tests/test_core_note_task_status_api.py`。
- 修复经验：任务创建时绑定 conversation，状态更新走统一 writer，成功时同步 note document。

## 仅凭 role=user 信任历史 context refs

- 发生过的问题/风险：assistant row 可先保存伪造白板 `snapshot/source_ids` 再改成 user；第一轮角色门禁修复后，漏洞产生的历史 tainted user row 仍能在相同 locator/revision PATCH 时被当成可信发送时快照。
- 根因：`role` 和 `meta_json` 都是客户端可影响的业务数据，不能证明该 row 曾经过服务端 authority resolver；只检查 stored/resulting role 会把历史污染状态永久升级成可信。
- 不允许重新引入的错误做法：仅凭 `role=user` 复用；把可伪造 marker 放在 `meta_json`；迁移或 legacy merge 时把历史 row 默认标可信；把内部 provenance 暴露为 POST/PATCH 请求字段。
- 检查方式：`backend/tests/test_conversation_context_refs.py` 的 tainted-user/canonical-reuse/assistant-transition 回归，以及 `backend/tests/test_core_conversation_contracts.py` 的幂等补列、legacy 默认 0 和 store 持久化测试。
- 修复经验：使用 `conversation_messages.context_refs_authority_version` 作为服务端持久、客户端不可写的 provenance。只有当前 resolver 写入的版本可复用；历史/legacy 默认 0 并在下一次引用 PATCH 时重新解析。

## 学习入口依赖模型自行选工具

- 发生过的问题：用户在普通聊天里说“我想学习某主题”，界面只返回一段泛化建议，没有学习画布；LearningCanvas 已存在却无法被稳定体验。
- 根因：产品显式操作被错误地依赖于 Agent 的能力发现与工具选择；同时完整学习卡内嵌在对话消息，没有形成稳定的右侧学习工作区。
- 不允许重新引入的错误做法：把“学习”按钮实现为换一条 prompt；让输入内容自动覆盖用户选择的学习模式；以 `AGENT_CHAT_ENABLED` 作为显式学习入口的开关；在会话消息中保存完整 canvas；用短于串行 provider 总预算的前端超时；用组件局部锁处理跨路由长请求；canvas 已落盘后因消息 patch/reload/navigation 失败而标记为构建失败。
- 检查方式：`frontend/tests/learningCanvasContracts.test.mjs`；手动验证“学习 → 提交主题 → 对话摘要 + 右侧面板 → 刷新恢复”。
- 修复经验：显式学习 intent 直接调用 canvas API，持久会话保持 `chat` 兼容；消息只存 compact meta，HomePage 用最新 `canvas_id` 投影右侧面板。同步研究不设前端固定超时，互斥放入共享 store；canvas 返回成功是不可回滚的成功边界，旧请求只能在发起路径仍活跃时自动导航。

## 把搜索结果列表当成研究白板

- 发生过的问题：GitHub 搜索返回的无关仓库（例如 profile、政治归档或只因词项偶合命中的项目）直接成为首个“学习路径”；右侧一次展示 20 多个节点、完整路径、掌握度、复习和来源，用户无法形成判断。
- 根因：`LearningCanvasService` 把每个外部 `LearningSource` 直接转换成 `type=source` 节点，没有相关性安全门、概念编译或信息分层；UI 把领域模型的所有字段当作首屏内容。
- 不允许重新引入的错误做法：按 provider 排名直接建节点；用论文/仓库/网页标题充当概念；把完整 canvas 所有分区同时展开；让白板正文与 Note 各自演进形成双事实源。
- 检查方式：`backend/tests/learning/test_research_note_compiler.py`、`frontend/tests/learningCanvasContracts.test.mjs`；手动输入宽泛 Agent 主题并确认无关仓库不进入节点，右侧只显示图和当前焦点。
- Sigma 相机坐标不能直接使用 Graphology 布局坐标：聚焦节点应读取 `renderer.getNodeDisplayData()`，适配视图应使用 Camera `animatedReset()`，并在分栏尺寸变化后调用 `resize/refresh`。写死 `(0, 0, ratio=1)` 会把已有节点移出可视区域，造成“白板为空”的假象。无关系边的图应使用确定性紧凑布局，不运行 ForceAtlas2 把孤立节点推散。
- 修复经验：候选先做本地/外部相关性过滤，再由严格 schema compiler 生成 topic/concept/claim/evidence/conflict/case/question；Note 是正文权威，白板只做投影；首屏先概览，用户主动选择深入方向。

## Note 成功后被白板或消息失败误判为研究失败

- 发生过的问题/风险：研究 Note 已写入 `note_documents`，后续 canvas 保存、摘要消息、reload 或 navigate 失败却向用户提示“研究生成失败”；用户重试后产生重复 Note。
- 根因：把 Note、投影、消息、Wiki 和导航当成一个可回滚事务，但它们跨 SQLite、文件、异步队列和前端路由，无法原子提交。
- 不允许重新引入的错误做法：NoteImportService 返回后仍用总 catch 标记创建失败；白板固定 tmp/消息异常向上抛导致重试；Wiki 失败删除 Note。
- 检查方式：`backend/tests/learning/test_learning_canvas_service.py::test_note_success_is_not_rolled_back_by_projection_or_message_failure`；前端仍以 create API 返回为成功边界。
- 修复经验：Note 保存成功即研究正文成功；投影/消息失败只返回 `projection_save_failed/guide_message_failed` 安全诊断，Wiki 状态独立，白板可由 Note 重建。

## API response wrapper 被破坏

- 发生过的问题/风险：前端 Axios 封装按 `{code,msg,data}` 解包，后端局部返回裸对象会造成调用方类型错乱。
- 根因：新接口未遵循 `ResponseWrapper.success()`。
- 不允许重新引入的错误做法：在 `/api` 路由直接返回业务 dict，除非调用方明确按裸响应处理。
- 检查方式：新增接口时查 `frontend/src/services/` 调用方；运行 `pnpm test:contracts`。
- 修复经验：普通 API 统一返回 wrapper，MCP/文件下载/流式接口例外要在 API 文档中说明。

## 视频采集状态写入和抖音跳转解析

- 发生过的问题：抖音视频生成任务没有真实下载视频，先被 `*.status.status.tmp -> *.status.json` 并发写冲突打断，后续又把直链解析成 `/jingxuan`，导致 `aweme_id=''` 和 `aweme_detail:null`。
- 根因：collector 状态文件使用固定 tmp 文件名，多个采集线程并发读改写同一状态文件；抖音下载器先跟随跳转再解析 ID，抖音把请求导向精选页时覆盖了原始 `/video/{id}`。
- 不允许重新引入的错误做法：原子写使用固定 tmp 名；状态上报异常中断下载/转写/分帧主流程；对已有 `/video/{id}` 的直链先 follow redirect 再取 ID；`aweme_detail` 为空时继续下标访问。
- 检查方式：`backend/tests/test_core_collector_status_contracts.py`、`backend/tests/test_multisource_video_collector_contracts.py`、`backend/tests/test_douyin_downloader_contracts.py`。
- 修复经验：并发状态更新必须用锁保护读改写并使用唯一 tmp；状态上报失败只能记 warning；抖音直链先从原始 URL 提取 ID，只有短链才跟跳转；空 ID/空详情返回明确错误；视频下载器需要兼容 `TranscriptCollector` 协议参数，尤其是 `skip_download`；抖音详情可能缺少 `music`，应 fallback 到 `video.play_addr/download_addr`；抖音 `uri` 可能只是媒体标识不是可请求 URL，下载地址只能使用 `http/https` 或协议相对 URL，优先读取 `url_list/url`；所有媒体下载请求必须设置超时。

## notemeld-ai 迁移期误删 GPTFactory 或误迁移 list_models

- 发生过的问题/风险：迁移到 notemeld-ai 抽象层时，过早删除 `GPTFactory`/`UniversalGPT` 会丢失回滚路径；把 `services/model.py` 的 `list_models` 也迁到 `NotemeldGPT` 会破坏非 chat-completion 路径（notemeld-ai `Models` 没有 list models 能力）。
- 根因：迁移分两类路径——chat-completion 走 `NotemeldGPT.create_chat_completion`（override 后走 notemeld-ai），list_models 走 `gpt.client.models.list()`（同步 OpenAI client，notemeld-ai 无对应能力）。
- 不允许重新引入的错误做法：在过渡期删除 `GPTFactory`/`UniversalGPT`；把 `model.py` 的 `list_models` 改成 `NotemeldGPT`；移除 `GPTFactory.from_config` 的 `DeprecationWarning` 之前先删工厂；新 chat-completion 调用点继续用 `GPTFactory`。
- 检查方式：`backend/tests/ai/test_provider_compat.py`（usage 双写对齐）、`test_note_generator_migration.py`、`test_t11_migration.py`（迁移点 + GPTFactory 回滚 import 保留断言）；搜索 `GPTFactory().from_config` 确认仅剩 `model.py` 的 list_models 路径。
- 修复经验：`GPTFactory.from_config` 加 `DeprecationWarning`，至少保留 1 个 Beta 版本；`model.py` 的 `list_models` 刻意不迁移；新 chat-completion 调用点一律用 `NotemeldGPT.from_config`。

## Agent 变更流程缺失

- 发生过的问题：新需求容易直接写 PRD 或方案，忽略当前系统事实，重复踩 Wiki、桌面、MCP、数据路径等坑。
- 根因：缺少强制的系统文档入口和增量变更模板。
- 不允许重新引入的错误做法：不读代码和测试就写实现方案；孤立 PRD 不分析现状冲突。
- 检查方式：新需求必须先创建基于 `docs/system/change-spec-template.md` 的 Change Spec。
- 修复经验：把当前系统事实、产品规则、数据模型、API、坑点和 Agent 工作流固化在 `docs/system/` 与 `AGENTS.md`。

## 风格 prompt 与持久格式不一致导致整篇笔记成为代码块

- 发生过的问题：`knowledge_card` 声明 Markdown 输出，但 prompt 强制模型只返回 HTML；模型实际返回 Markdown 并套上 `html` fence，后端仅按真实 HTML 标签转换，最终 ReactMarkdown 正确地把整篇渲染为灰色代码块。
- 根因：生成策略、格式检测和持久化使用三套隐含判断；把 fence 的语言标签误当格式，又缺少保存前统一归一化。
- 不允许重新引入的错误做法：用前端 CSS 隐藏 code block；Markdown-only prompt 继续要求 HTML/CSS/DOM；无条件剥离所有代码围栏。
- 检查方式：`backend/tests/test_note_output_normalizer.py`、`test_web_note_contracts.py`；测试全文错误 fence、来源引用前缀、真实 HTML 转换和正文内部代码块。
- 修复经验：`output_formats` 必须同时约束 prompt 和保存；只在整个文档是一个 fence 时安全剥离，视频/网页入口共用同一 normalizer。

## 推理模型消耗 completion token 但 final content 为空

- 发生过的问题：DeepSeek 等推理模型的每个 Wiki chunk 都记录了接近上限的 completion tokens，但 `message.content` 为空，系统统一报 `Wiki fallback analysis returned empty content`，无法判断截断还是响应适配丢字段。
- 根因：OpenAI 兼容 Provider 丢弃 `reasoning_content` 和真实 `finish_reason`，兼容 adapter 又把结束原因写死为 `stop`；Wiki 解析只读取 final content。
- 不允许重新引入的错误做法：以 usage success 证明已有 final answer；把任意 reasoning prose 当作 JSON；把 chain-of-thought 写入日志/UI；所有空响应统一归为网络或 empty content。
- 检查方式：`backend/tests/ai/test_provider.py`、`test_note_generator_migration.py`、`test_knowledge_extractor_response_contracts.py`；覆盖合法 JSON 恢复、length 截断、仅 reasoning、真正空响应。
- 修复经验：适配层要保留字段语义；业务层优先 final content，只恢复完整可验证 JSON，并按 finish reason 分类。输出预算与 schema 数量上限必须共同约束。

## 只按请求字节分块或把完整聊天历史直接发给 4K 模型

- 发生过的问题/风险：请求 JSON 明显低于 45MB，却因估算输入达到 6492 tokens 而超过 4096 模型上下文；聊天和 Agent 历史也可能在 Provider 端才失败。
- 根因：`RequestChunker` 只检查 HTTP 字节上限，`Models.stream/complete` 未把保存的模型窗口作为 Provider 前硬边界。
- 不允许重新引入的错误做法：只改模型设置 UI 而不让聊天、Agent 和笔记运行时消费保存值；用官网/模型文件的理论窗口覆盖用户确认的端点实际值；只按字节分块；用字符数冒充 token；在 chat_service/Agent loop 原地删除持久消息；拆散 assistant tool calls 与对应 tool messages；静默截断最新 user；使用能力探测缓存覆盖保存窗口。
- 检查方式：运行 `backend/tests/test_token_budget.py`、`backend/tests/ai/test_models.py`、`backend/tests/ai/test_chat_service_migration.py`、`backend/tests/ai/test_note_generator_migration.py`；确认 4096 的 literal 预算为 output 1024、safety 410、input 2662，并验证 token/byte 任一超限都会分块。
- 修复经验：统一使用保守的 `ceil(UTF-8 bytes / 3)` 加每消息 overhead；图片按每张 1200 token reserve；Provider 前裁剪副本，system/最新 user 必留，工具调用与结果成组；笔记分块同时执行 token 和 byte 两道门槛。

## legacy 合并重新导入已清空的模型配置

- 发生过的问题/风险：初始化先升级 schema 并清空旧 `models` / `model_capabilities`，随后 legacy SQLite merge 又导入模型行，三列旧表依靠 server defaults 被伪装成 `4096 / false / true`。
- 根因：通用 legacy table 白名单把 `models` 当成可兼容数据，忽略了模型运行字段必须由用户针对当前端点重新确认的产品边界。
- 不允许重新引入的错误做法：为 legacy `models` 补默认值后导入；因 legacy 表已含完整三字段就例外保留；为了跳过模型而一并丢弃 Provider、Note、Conversation 或 Usage。
- 检查方式：`backend/tests/test_model_runtime_schema.py`的 merge 和真实 `init_db()` 回归；确认 Provider/Note 可导入，`migrated_counts["models"] == 0` 且当前 `models` 保持空。
- 修复经验：legacy merge 表白名单彻底排除 `models`，保留摘要 key 以维持观测契约；用户重新添加后才产生完整权威运行配置。

## 模型 defaults pending 期间快速保存 fallback

- 发生过的问题/风险：用户选择模型后 defaults 请求尚未返回就点击“添加模型”，弹窗把初始 fallback 当作用户确认值持久化。
- 根因：只有 request version 与 dirty 保护迟到响应，没有把“当前 defaults 请求尚未 settle”纳入保存可用性和 handler 防御。
- 不允许重新引入的错误做法：只禁用按钮而不防御 handler；旧请求 `finally` 结束新请求的 loading；关闭后允许迟到响应改写状态；defaults 失败后永久禁止保存。
- 检查方式：`frontend/tests/modelRuntimeConfigContracts.test.mjs`；确认 loading 同步 ref + state、按钮/handler 双门禁、current-version-only finally 和关闭失效化。
- 修复经验：请求启动时同步锁定保存；仅当前 version 在 `finally` 解锁；失败后保留 fallback 可编辑并允许用户主动确认。

## 笔记 map 重复注入辅助上下文、非视觉模型仍先走视觉

- 发生过的问题/风险：多源 collector 先把 frame/search 拼入 `extras`，统一上下文又再次渲染，导致每个 map 块重复携带整份辅助内容；不支持视觉的模型仍可能调用 analyzer、生成 grid payload；空 OCR 占位也持续膨胀 prompt。
- 根因：用户原始要求和 collector 结果共用一个字符串通道，采集入口没有使用已保存的 `supports_vision` 做明确分支，OCR formatter 把空结果变成了有效文本。
- 不允许重新引入的错误做法：把 collector content 写回原始 `extras`；map 阶段注入 final-stage search/vision；`supports_vision=false` 时先试视觉再 OCR；对空 OCR 写“未识别到文本”；调用旧 extractor fallback 暗中生成 grid；即使 grid 为空仍调用 base64 encoder；把 vision→OCR 临时 fallback 当成稳定 vision cache。
- 检查方式：`backend/tests/test_multisource_summary_contracts.py`、`backend/tests/test_multisource_video_collector_contracts.py`；断言 map/final payload、vision analyzer/OCR 调用次数、真实 `VideoReaderFrameExtractor` 的 grid/group/concat/base64 调用次数、旧 extractor 未调用、空 OCR 不产生 vision extra，以及 analyzer 临时失败后下次仍会重试视觉。
- 修复经验：原始 `extras` 单独保留，collector 结果经 `SummaryInput.user_options` 进入 final weighted pack；`allow_vision=false` 通过显式 `include_grid_images=false` 契约直接逐帧 OCR 并使用独立 `_frames_ocr` 缓存，空文本跳过；vision fallback 不写稳定 vision cache。

## Provider 实际上下文小于保存值时无限重试或破坏缓存

- 发生过的问题/风险：本地模型报 `request (6492 tokens) exceeds ... (4096 tokens)`、`exceed_context_size_error` 或 `n_prompt_tokens/n_ctx` 后直接失败，或通用网络 retry 重发同一 payload；失败清理 checkpoint 会浪费已完成 map 和采集结果。
- 根因：只在请求前按保存窗口估算，没有统一识别 Provider 的上下文错误形态，也没有限制“缩小预算重分块”的次数和 checkpoint 命名边界。
- 不允许重新引入的错误做法：把上下文错误当网络抖动原样重发；因 payload 同时含 500/timeout/service unavailable 而先走通用重试；仅凭孤立或不可解析的 `n_ctx/n_prompt_tokens` 判超限；循环缩小预算；对用户或日志泄漏完整 Provider payload；重试前删除 transcript/frame/search cache 或原 checkpoint。
- 检查方式：`backend/tests/ai/test_note_generator_migration.py`、`backend/tests/ai/test_provider.py` 的 6492/4096、结构化 code、正负错误变体、混合 500/timeout 调用次数、70% 预算、二次安全错误、日志脱敏和 checkpoint 保留测试。
- 修复经验：统一 `is_context_limit_error()` 并优先解析结构化 code；成对数字必须满足 `n_prompt_tokens > n_ctx`。上下文错误在通用 retry 前排除，只用原输入预算的 70% 重分块一次，并给重试使用独立 checkpoint key；二次失败转换为专用安全 `ContextLimitExceededError`，日志也只记录安全归一化错误，已有缓存和 checkpoint 原样保留。
