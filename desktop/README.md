# NoteMeld desktop

桌面端的所有实现位于本目录：

- `frontend/`：React/Vite 桌面工作台前端。
- `backend/`：本地 FastAPI 业务 sidecar；由 `src-tauri/` 中的 Rust/Tauri 宿主启动、监控和打包。
- `src-tauri/`：桌面框架与原生 Rust 宿主。

当前 Rust 层是桌面原生后端/编排层，Python 层仍承载既有业务 API、采集、转写、知识库和 MCP。将全部业务 API 迁移到 Rust 属于独立的兼容性迁移，不在目录整理中隐式改变。
