# Application Runtime v2 增量 Change Spec

状态：Implemented in this branch

## 当前事实

当前 Application Protocol v1 已完成内置应用发现、实例/Run 生命周期、桌面 JSONL transport、iframe Bridge、`wiki.read.graph/article`、实例隔离的 `app.data.*`、workspace 文件 CRUD、外部授权目录读取、artifact、Agent 和 `plugin.invoke` adapter。声明的 permissions 在调用前通过 Host effective grant 校验，sync/async Job 及有序事件也已落地。依据：`backend/app/applications/{manifest,service,runtime}.py`、`frontend/src/app-host/ApplicationHost.tsx`、`backend/tests/test_applications.py`。

## 本次目标

- 保留 `notemeld.application.v1` 和现有内置应用兼容性。
- 增加实例隔离的 `app.data` 键值存储和 workspace 文件 CRUD。
- 外部文件只允许读取预先由用户在 Host 设置中授权的绝对目录。
- 增加 Host 默认权限与用户可修改的 per-application grants。
- 增加 sync/async 调用模式、持久化 Job 和有序事件查询。
- 暴露 `invokeRun` 的 SDK service 通道。
- 稳定区分 `capability_denied`、`permission_denied` 和 `capability_unavailable`。

## 明确不做

- 不开放第三方应用上传、安装、升级、回滚或签名控制面。
- Cloud worker、移动端 UI 和 `plugin.invoke` 已有独立实现；本变更不把它们改造成第二套 Application runtime。
- Artifact 已能在应用实例内创建和读取，但尚未接入 Note/导出链路；跨域消费仍是后续扩展边界。
- 不允许应用访问任意外部绝对路径；外部读取必须落在 Host 授权根目录内。

## 权限策略

`workspace.read` 和 `workspace.write` 是内置应用的默认权限，可在应用设置中关闭；manifest 申请的 `network.egress`、`agent.run`、`plugin.invoke` 默认关闭，只有用户显式授予后才有效。权限声明是申请，数据库中的 `ApplicationPermission` 是用户覆盖，调用前由 Host 计算 effective grant。

## 数据与配额

- `ApplicationData` 按 `app_id + instance_id + key` 唯一隔离。
- 单值上限 1 MiB，实例总量上限 10 MiB。
- workspace 文件路径只能是相对路径，禁止绝对路径、`..` 和符号链接逃逸；单文件读取上限 16 MiB。
- 外部读取根目录由 Host 设置保存，读取结果只返回文件名、逻辑结果和内容，不把未授权路径交给应用。

## 接口

- `GET/PUT /api/applications/{app_id}/permissions`
- `PUT /api/applications/settings/external-read-roots`
- `POST /api/applications/runs/{run_id}/invoke` 增加 `mode=sync|async`
- `POST /api/applications/runs/{run_id}/capability` 增加 `mode=sync|async`
- `GET /api/applications/jobs/{job_id}`
- `GET /api/applications/jobs/{job_id}/events?after_sequence=N`

Async 调用立即返回 `{mode, job_id, status}`；Job 事件使用单调 `sequence`，不得自动重放未知副作用。

## 验收

- [x] 未声明 capability 返回 403 `capability_denied`。
- [x] 已声明但未授权 permission 返回 403 `permission_denied`。
- [x] 已声明且授权但 adapter 未实现返回 501 `capability_unavailable`。
- [x] 两个实例无法读取对方 app data 或 workspace 文件。
- [x] 外部文件不在授权根目录时返回 403。
- [x] async 调用可查询 Job 终态和 accepted/started/completed 或 failed 事件。
- [x] 现有 Wiki 应用和 v1 contract tests 保持通过。

## 风险与回滚

新增表和字段只追加，不改变既有应用表语义；回滚代码后新增表可保留但不再被旧 Host 使用。默认内置应用保持 Wiki 只读，不自动授予网络、Agent 或插件权限。
