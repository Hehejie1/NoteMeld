# Workspace 与远程设备执行 Change Spec

更新时间：2026-09-15

## 当前现状

桌面 Agent Host 目前只有按 conversation id 隔离的只读 workspace adapter；D01 的工作区选择器写死为 `notemeld-project`，因此 Agent 没有用户选择的真实执行根目录。Cloud 侧已有设备、Grant、device_remote session 以及 LAN-first/Relay fallback，但能力只在 Cloud 页面可见，尚未成为 D01/D03 的执行目标模型。

## 目标

- 工作区成为本地 SQLite 中的全局实体，支持选择本地文件夹、列出、读取、创建/编辑/删除文件，并能作为 Agent turn 的 workspace context。
- 会话、turn、event、approval 继续由桌面数据库全局保存；工作区只保存文件和产物。
- 远程设备作为独立 execution target，复用现有设备身份、Grant、device_remote session、LAN-first 与 Relay；不把远程设备伪装成本地文件夹。
- `new-product` 明确 D01/D03/D09/APP04/C03/C05 的入口和状态。

## 明确不做

- 本次不在 macOS 上伪造 WSL；WSL 仅在 Windows host 可用。
- 本次不把 SSH 私钥、密码或 Cloud token 写入 SQLite；SSH transport/远端 helper 作为后续 adapter，当前 UI 只允许标记为待连接。
- 不修改已有 Cloud relay 协议，不复制 Agent loop。

## 最小实现

新增 `workspaces` 表及 `/api/workspaces`、`/api/workspaces/{id}/files` API。local_folder 通过 Tauri 原生目录选择器注册，路径仅存本机。文件 API 将所有路径解析限制在已注册 root 下，写入采用临时文件替换，删除只允许工作区内目标。D01 从 API 加载工作区并把真实 `workspace_id` 放进 context_refs；远程设备入口继续复用 CloudRemoteAgentPanel，并在产品文档中定义为独立 execution target。

## 验收

- [ ] 桌面端可以注册一个本地文件夹并在 D01 选择。
- [ ] 工作区列表、读取、创建、编辑、删除接口拒绝越界路径。
- [ ] Agent turn 携带所选 workspace context，而不是固定 `notemeld-project`。
- [ ] Cloud 多设备/远程控制的 authority、Grant、审批和断线状态在 new-product 中有明确页面映射。
- [ ] 后端目标测试、前端类型检查和 Vite build 通过。

## 风险与回滚

已有 conversation workspace API 保留不动；新表可独立删除/回滚，历史会话不受影响。真正的 SSH/WSL 执行必须在对应 transport adapter 和安全审批完成后开启，避免把本地路径或凭据泄露到 Cloud。
