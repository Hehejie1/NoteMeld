# Known Pitfalls

更新时间：2026-06-19

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

## Agent 变更流程缺失

- 发生过的问题：新需求容易直接写 PRD 或方案，忽略当前系统事实，重复踩 Wiki、桌面、MCP、数据路径等坑。
- 根因：缺少强制的系统文档入口和增量变更模板。
- 不允许重新引入的错误做法：不读代码和测试就写实现方案；孤立 PRD 不分析现状冲突。
- 检查方式：新需求必须先创建基于 `docs/system/change-spec-template.md` 的 Change Spec。
- 修复经验：把当前系统事实、产品规则、数据模型、API、坑点和 Agent 工作流固化在 `docs/system/` 与 `AGENTS.md`。
