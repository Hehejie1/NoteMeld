# NoteMeld 应用运行时与 Wiki 应用化执行规格

状态：Ready for Implementation
Canonical requirement：[`docs/requirements/2026-08-27-notemeld-application-runtime-and-wiki-app.md`](../../requirements/2026-08-27-notemeld-application-runtime-and-wiki-app.md)
Plan：[`docs/superpowers/plans/2026-08-27-notemeld-application-runtime-and-wiki-app.md`](../plans/2026-08-27-notemeld-application-runtime-and-wiki-app.md)

## 1. 协议范围

第一版协议名称为 `notemeld.application.v1`，由 NoteMeld Host 负责解析和执行。应用包是静态 UI、可选后端入口和声明文件的版本化单元。

应用包必须声明以下语义：

```json
{
  "protocol": "notemeld.application.v1",
  "id": "example.app",
  "version": "1.0.0",
  "name": "Example",
  "ui": {"entry": "ui/index.html"},
  "runtime": {"kind": "process-jsonl", "entry": "backend/entrypoint"},
  "platforms": {"desktop": "supported", "web": "supported", "mobile": "unsupported"},
  "capabilities": ["wiki.read", "workspace.file.read", "artifact.create"],
  "permissions": ["workspace.read"],
  "storage": {"scope": "application-instance", "workspace": "default"}
}
```

Host 必须拒绝：路径穿越、绝对路径、重复 capability、缺失 UI entry、未支持 runtime、非法平台值、空 id/version、未知权限、超过包大小限制的包和声明访问宿主内部 API/数据库的包。

## 2. 后端运行时

### Desktop adapter

- Host 按活动的 `app_id + version` 监督独立进程；默认按需启动，空闲可回收。
- Host 与进程使用私有 process-JSONL/RPC transport；应用不监听公开 TCP 端口。
- 每个 RPC frame 至少包含 `request_id`、`app_id`、`instance_id`、`run_id`、`method`、`input` 和 `sdk_version`。
- Host 注入短生命周期、仅用于 SDK bridge 的上下文，不把宿主 session token 放进应用环境变量或 UI。
- 进程的 cwd、可读写路径、环境变量、网络和资源额度由 Host 固定；应用只能访问自己的 workspace 和声明的 capability。
- EOF、非法 frame、超时、退出码非零和重复 request 必须形成明确的运行错误；未知非幂等请求不得自动重放。

### Web adapter

- Web UI 通过 Host gateway 调用 `managed-worker` invocation，不直连应用后端公网地址。
- 每个应用版本使用不可变部署单元；每次 invocation 由 Host 注入 app/instance/user/run context。
- Host 负责超时、内存、CPU、并发、请求体、响应体、存储和网络出口限制，并记录 invocation 日志和审计摘要。
- 长任务必须转换为 Host Application Run/Job，由 Host 负责取消、恢复和最终状态；worker 不得自行保持不可控后台进程。
- 本仓库第一版实现本地可测试的 managed-worker seam 和策略拒绝；不宣称完成外部云平台部署。

## 3. Host SDK 与 capability

应用 SDK 只提供深接口，不暴露内部 router、ORM、SQLite connection 或宿主文件路径。第一版 capability 包含：

- `wiki.read`：读取 graph、节点详情、文章详情和展示所需的分页/摘要数据；
- `workspace.file.list/read/write`：访问当前应用 workspace 的逻辑 file reference；
- `app.data.get/put/list`：访问当前应用实例的命名空间数据；
- `artifact.create/read`：写入和读取应用 Artifact；
- `agent.run`：通过现有 Agent Host 发起受 app/instance/run 约束的 Agent Turn；
- `plugin.invoke`：调用已安装、启用且获授权的插件 capability。

每次调用都由 Host 重新检查 manifest、当前平台、用户授权、应用实例和 capability authority。manifest 的 `safe` 或低风险声明不能替代 Host 授权。

## 4. 数据和状态

应用域需要独立的 forward-only migration registry。建议模型语义如下，具体 ORM 字段由实现按现有项目模式落地：

- Application：已安装包的 id、版本、manifest 摘要、平台和运行状态；
- ApplicationInstance：用户创建的应用实例、标题、状态和 workspace 绑定；
- ApplicationRun：一次启动/工作流/worker invocation 的状态、错误、取消和时间信息；
- ApplicationArtifact：应用产物引用、类型、摘要、来源 run 和数据权限；
- ApplicationSetting：应用默认 workspace 根目录等用户设置。

状态必须至少支持 `installed`、`disabled`、`starting`、`running`、`stopped`、`failed` 和 `needs_attention`；Run 必须能表达 `queued`、`running`、`waiting_user`、`cancelled`、`failed`、`completed` 和 `interrupted`。

应用数据不得复制 Note/Wiki 事实；Wiki graph、Note、contribution 和文章继续由既有 domain service/store 维护。

## 5. Backend HTTP 接口

新增接口应挂在 `/api/applications`，复用 `{code,msg,data}` response wrapper，并要求现有 session token：

- `GET /api/applications`：列出可用内建应用及安装/运行状态；
- `GET /api/applications/{app_id}`：读取 manifest 摘要和平台/能力诊断；
- `POST /api/applications/{app_id}/enable`、`/disable`：启停应用；
- `POST /api/applications/{app_id}/instances`：创建应用实例；
- `GET /api/applications/{app_id}/instances`：列出实例；
- `POST /api/applications/{app_id}/instances/{instance_id}/runs`：启动应用运行；
- `POST /api/applications/runs/{run_id}/cancel`：请求取消运行；
- `GET /api/applications/runs/{run_id}`：读取运行状态和安全诊断；
- `GET /api/applications/settings/workspace`、`PUT /api/applications/settings/workspace`：读取/修改默认 workspace 配置；
- `GET /api/applications/{app_id}/wiki/graph`、`GET /api/applications/{app_id}/wiki/articles/{source_id}`：由 Wiki capability adapter 提供当前 Wiki 应用所需数据。

旧 `/api/wiki/*` 是否仍作为内部 domain router 保留由实现决定，但应用 UI 不得直接调用它；旧前端 `/wiki` route 和导航 wiring 必须删除。

## 6. Frontend Application Host

建议新增：

- `frontend/src/pages/Applications/`：应用列表、应用实例和运行容器；
- `frontend/src/services/applications.ts`：应用/实例/run/workspace API client；
- `frontend/src/app-host/`：HTML bundle 容器、Host bridge、生命周期和安全事件；
- `frontend/src/apps/wiki/`：Wiki 应用 UI 和图谱适配；
- `frontend/src/apps/registry.ts`：内建应用 registry。

应用 UI 不直接 import NoteMeld 的内部 service；Wiki 应用通过 app host bridge 或 applications service 获取 host-provided 数据。Bridge 必须只暴露声明过的 capability，并对消息来源、request id 和 payload 大小做校验。

## 7. Wiki 应用迁移

- 将当前 `frontend/src/pages/WikiPage/` 的可观察功能迁移到 `frontend/src/apps/wiki/` 或等价应用包目录；保留 Sigma 图谱、类型/社区视图、缩放、节点选择、详情和刷新。
- Wiki 应用启动时从既有 Wiki domain capability 获取 graph；节点详情根据现有 source/page/article 语义展示。
- 空 graph、请求失败、节点不存在、文章不存在和 refresh 失败必须有独立 UI 状态，不能清空已加载数据。
- 在应用入口可用后，删除 `App.tsx` 中 `/wiki` route、`AppLayout.tsx` 中旧 Wiki 导航 wiring 和直接内建 Wiki 页面引用；不加 redirect。
- Wiki data store、Wiki pipeline、Note authority 和现有 graph 文件不迁移、不复制、不删除。

## 8. 测试要求

### Backend

- manifest 合法/非法、路径穿越、版本、平台、capability、permission 和包大小；
- 应用域 migration registry 不修改 plugin/candidate/legacy registry；
- 应用实例和 run 状态、重复 request、取消、EOF、超时、非零退出和 needs-attention；
- workspace 根目录设置、应用间隔离、逻辑 file reference 和越权拒绝；
- Wiki capability 读取 graph/article，禁止直接 DB/router bypass；
- Agent/plugin capability 复用 Host authority，未授权时无副作用。

### Frontend

- 应用 registry、启动/禁用/能力缺失/运行失败状态；
- HTML host bridge 不暴露宿主 token/DOM，拒绝未声明 capability；
- Wiki 应用的图谱展示切换、缩放、节点选择、文章详情、刷新、空和错误状态；
- `/wiki` route 和旧导航 wiring 已移除，应用入口存在；
- contract API wrapper、类型和 build。

## 9. 不在本期实现的协议扩展

- Agent 自动生成应用包；
- 用户上传/Release 应用包的公开安装流程；
- 移动端 UI bundle；
- 外部云基础设施真实部署；
- 任意应用自定义数据库直连；
- 应用升级 candidate 的自动激活。
