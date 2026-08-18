# Change Spec：统一运行数据与日志目录

## 0. 预检查

- [x] 已阅读 `docs/system/current-architecture.md`
- [x] 已阅读 `docs/system/product-rules.md`
- [x] 已阅读 `docs/system/data-model.md`
- [x] 已阅读 `docs/system/api-inventory.md`
- [x] 已阅读 `docs/system/known-pitfalls.md`
- [x] 已搜索相关代码
- [x] 已搜索相关测试
- [x] 已确认当前已有统一路径模块，但仍有旧入口绕过它
- [x] 影响本地源码、CLI、PowerShell、桌面和打包 smoke 运行模式；不涉及线上服务

## 1. 当前系统现状

- 相关模块：`backend/app/utils/storage_paths.py`、`backend/main.py`、日志工具、下载器、导出工具、各启动脚本、Tauri sidecar 启动器。
- 相关入口：`run_notemeld.sh`、`scripts/notemeld`、`scripts/notemeld.ps1`、`backend/main.py`、桌面 sidecar。
- 相关数据：`notemeld.db`、`note_results/`、`uploads/`、`static/`、`data/`、`models/`、`chroma/`、migration 文件和应用临时文件。
- 当前行为：默认路径大多落在 `vector_db`，但 `.env` 的 `NOTE_OUTPUT_DIR`/`OUT_DIR`、下载器 `DATA_DIR`、旧迁移脚本和桌面环境注入仍可能生成其他根目录。
- 当前限制：根目录 `note_results`、`static`、`downloaded_videos` 等历史目录容易与正式数据混淆；启动脚本仍主动扫描并复制旧目录。

## 2. 本次目标

- 用户问题：所有运行中间数据应位于 `vector_db`，所有日志应位于 `logs`，不再产生旧根目录数据。
- 成功后的用户可见行为：从项目根目录启动后，运行数据只出现在 `vector_db/`，日志只出现在 `logs/`。
- 成功后的系统内部行为：所有后端数据子目录、应用临时文件、下载/转写缓存和导出结果都从统一路径函数派生；桌面模式使用应用数据目录下的 `vector_db/` 和应用日志目录 `logs/`。
- 必须保留的旧行为：数据库、笔记/Wiki、上传、模型、向量索引、截图、迁移和 MCP 的业务语义不变；测试仍可通过唯一的根目录注入隔离运行。

## 3. 明确不做

- 不删除用户现有本地数据；本次只删除代码中的自动迁移/兼容逻辑。
- 不修改 API 路径、请求参数、返回结构或数据库字段。
- 不把操作系统自身的 `/tmp`、CI 临时目录或打包工具临时目录改成业务数据目录；只替换 NoteMeld 后端运行时产生的临时文件。

## 4. 冲突分析

- `product-rules.md`：不冲突；任务状态和笔记事实源仍在 `note_results` 下，只改变其唯一父目录。
- `data-model.md`：不改变字段语义；同步更新文件系统路径说明。
- `api-inventory.md`：无接口契约变化。
- `known-pitfalls.md`：避免重新引入多根目录、固定相对路径和旧迁移入口；保留原子写入方式。
- 运行模式：影响源码、CLI、PowerShell、桌面和打包 smoke；所有模式都通过统一根目录派生子路径。
- 打包/迁移：导入导出包内的逻辑目录名仍为 `note_results`、`static` 等；仅运行时落盘根目录统一，不改变包格式。

## 5. 影响范围

- 后端：路径定义、启动初始化、下载器、导出工具、运行时临时文件、日志工具。
- 前端：无代码改动，截图 URL 契约不变。
- 桌面/Tauri：只保留数据根和日志根注入，子目录由后端统一派生。
- 数据库/迁移：无 schema 变更；删除启动脚本对根目录旧数据的自动复制。
- 文件系统：正式结构为 `vector_db/{notemeld.db,note_results,uploads,static,models,chroma,data,config,migrations,tmp}` 和 `logs/`。
- 测试：更新运行时路径、桌面启动和打包 smoke 契约，新增旧变量不再生效及临时文件落盘断言。
- 文档：同步架构、数据模型和已知坑点。

## 6. 实施方案

### 后端

- `storage_paths.py` 保留唯一数据根注入口；所有子目录不再读取 `NOTE_OUTPUT_DIR`、`VECTOR_DB_DIR`、`STATIC_DIR`、`OUT_DIR`、`UPLOAD_DIR`、`DATA_DIR` 等旧变量。
- 增加 `temp_dir()`，后端生成的 Cookie、音频压缩、样式预览、PDF 页面、迁移解包临时文件统一放入 `vector_db/tmp`。
- `main.py` 只按统一路径函数创建目录。
- 日志工具只写统一日志根；启动器负责把 stdout/stderr 日志也写入 `logs`。

### 启动器与桌面

- `run_notemeld.sh` 删除根目录/`backend` 目录的迁移扫描和复制逻辑。
- `scripts/notemeld`、`scripts/notemeld.ps1`、`scripts/install.sh` 使用应用目录下的 `vector_db` 和 `logs`。
- Tauri 仅注入数据根和日志根；数据子目录全部由后端计算，桌面数据根为应用数据目录下的 `vector_db`。

## 7. 数据变更

- SQLite：无变化。
- 文件结构：新增运行时 `vector_db/tmp`；不再创建根目录 `note_results`、`static`、`downloaded_videos`。
- 迁移：不再自动迁移旧根目录；用户如需保留旧数据，应通过现有导入流程显式导入。
- 历史数据：本次不自动删除或移动。

## 8. 接口变更

- 无新增、修改或删除 API。
- 前端和 MCP 调用方无需变更。

## 9. UI/交互变更

- 无 UI 交互变化。

## 10. 测试方案

- 后端：路径契约、启动契约、临时文件路径契约、现有核心回归。
- 桌面/打包：检查 Tauri 只注入根路径，运行时子目录仍在统一根下。
- 手动验证：从项目根启动后检查 `find . -maxdepth 1`，确认不生成根目录 `note_results`、`static`、`downloaded_videos`；确认文件只在 `vector_db`/`logs` 下。

## 11. 验收标准

- [ ] 所有业务运行数据路径均为 `vector_db` 的子路径。
- [ ] 所有 NoteMeld 后端和启动器日志均写入 `logs` 的子路径。
- [ ] 旧子目录环境变量和根目录迁移兼容逻辑不再生效。
- [ ] 后端临时文件均位于 `vector_db/tmp` 或目标数据文件同目录的原子临时文件。
- [ ] 相关契约测试通过，且不破坏源码、CLI、桌面和打包启动入口。

## 12. 风险和回滚

- 主要风险：旧 `.env` 中的子目录变量不再生效；桌面首次启动会使用新的 `.../vector_db` 数据根。
- 风险触发信号：启动后出现数据写入旧路径、数据库无法打开或桌面截图不可访问。
- 降级策略：修复统一路径函数或回滚本分支；不恢复旧多根目录兼容逻辑。
- 回滚步骤：回滚代码后由用户显式处理新旧数据目录，不自动覆盖数据。

## 13. Agent 必答问题

- 影响模块：后端存储路径、日志、下载/导出/临时文件、源码/CLI/PowerShell/Tauri 启动器和契约测试。
- 类似能力：已有 `storage_paths.py`，但旧入口仍绕过它。
- 产品规则：不冲突，仍保持 AI 产物和任务状态落在 `note_results`。
- 数据模型：不改变字段，只统一文件根目录。
- known pitfalls：本改动直接消除相对路径和多根目录问题，并保留原子写入。
- 本地/线上影响：影响本地数据位置和启动流程，不影响线上服务。
- 最小改动：收紧统一路径模块，移除旧环境变量/迁移入口，修改启动器和运行时临时文件。
- 回归测试：路径、启动、打包 smoke、临时文件和核心后端契约测试。
