# NoteMeld 应用运行时与 Wiki 应用化执行计划

状态：Planned
Canonical requirement：[`docs/requirements/2026-08-27-notemeld-application-runtime-and-wiki-app.md`](../../requirements/2026-08-27-notemeld-application-runtime-and-wiki-app.md)

## 1. 目标与交付边界

本计划把 P8 需求落成一个可运行的第一版 Application Host，并将当前 Wiki 页面作为第一个内建 Application Package 运行。

第一版必须交付：

- Application Package v1 的 manifest、静态 UI、后端入口声明、平台/能力/权限声明和版本校验；
- NoteMeld Application Host 的安装、启动、停止、状态、workspace 和应用实例入口；
- 桌面端宿主监督的独立应用进程协议，采用私有 process-JSONL/RPC，不开放应用公网监听；
- Web 端宿主管理的 worker/invocation 抽象，统一通过 Host gateway 调用并受资源/权限策略约束；
- Application SDK 的最小 capability seam，复用已有 Agent、Plugin、Note、Wiki、知识和文件宿主能力；
- 应用实例、运行记录、应用 Artifact 和独立 migration registry；
- Wiki 应用加载现有 graph，支持当前 Wiki 页面中的展示模式、缩放、节点选择、详情/文章查看、刷新、空状态和错误状态；
- 移除旧 `/wiki` 页面路由和导航 wiring，不保留旧路由兼容；
- 应用默认 workspace 根目录可在设置中配置，且应用只能通过逻辑引用访问；
- 后端、前端、协议安全和 Wiki 迁移回归测试。

本期不做：移动端实现、Agent 自动生成/安装应用、公开应用市场、用户自定义应用包分发、应用自升级、任意应用直接访问 SQLite/系统路径，以及 Wiki 研究工作流或管理后台的扩展。

## 2. 当前基线

- `frontend/src/App.tsx` 直接注册 `/wiki` 与 `WikiPage`；`AppLayout.tsx` 直接注册知识库导航。
- `frontend/src/services/wiki.ts` 调用 `/wiki/*` 产品接口；`backend/app/routers/wiki.py` 与 `backend/app/services/wiki_store.py` 提供当前 Wiki 数据访问。
- Agent Host、Capability Registry、Plugin Manager、插件权限/版本/active pointer 和 Note authority 已存在，应通过 Adapter 复用。
- 运行数据根由 `backend/app/utils/storage_paths.py` 管理；新的应用数据不得写入仓库根目录或系统临时目录。
- SQLite 的 plugin/candidate 域已有独立 migration registry；应用域必须使用自己的 registry，不修改共享 `PRAGMA user_version`。

## 3. 任务拆分与依赖

### A：Application Host、协议和后端存储（可与 B 并行）

写集：`backend/app/applications/`、应用域 DB model/schema/storage、应用 router/service、后端契约测试；不修改 WikiPage、App.tsx 或 AppLayout。

- 定义并校验 `ApplicationManifest v1`、package metadata、platform/capability/permission/storage/runtime 声明。
- 实现应用包注册/加载、内建包解析、应用实例和 Application Run 状态。
- 实现应用 workspace 路径配置和逻辑 file reference；默认根目录可被设置服务读写。
- 实现 desktop `process-jsonl` runtime adapter 的受控生命周期和 web `managed-worker` invocation adapter 的统一接口；桌面 adapter 实际监督 stdin/stdout 子进程，第一版不允许应用监听公开端口。
- 提供 Host gateway/capability adapter，至少覆盖 Wiki read、workspace file、Artifact，以及已有 Agent/Plugin 调用的边界描述。
- 将应用 API 统一使用现有 response wrapper，加入权限拒绝、缺能力、运行时异常、取消和 needs-attention 错误。
- 添加应用域独立迁移 registry，不改变既有表和 migration registry。

### B：Application UI Host 与 Wiki 应用（可与 A 并行）

写集：应用 UI 容器/前端服务、新 Wiki app package 和 Wiki app UI；只在最后需要修改 `App.tsx`、`AppLayout.tsx` 与旧 Wiki 入口 wiring。

- 建立应用路由/容器，加载受控的内建 HTML bundle；不把应用 UI 限制为 NoteMeld React 组件 schema。
- 把当前 Wiki 页面能力迁移为内建 Wiki Application UI，保留图谱类型/社区展示、缩放、节点选择、详情/文章查看、刷新和空/错状态。
- 让 Wiki UI 通过 Application Host capability 获取数据，不直接调用旧产品 router 或访问 SQLite。
- 将导航从“知识库内建页面”改为“应用中的 Wiki”，删除旧 `/wiki` route 和直接页面 wiring；不保留兼容跳转。
- 添加应用启动失败、能力缺失、应用禁用和运行中断的 UI 状态。

### C：集成回归与系统文档（A/B 合并后串行）

写集：集成测试、`docs/system/`、`docs/superpowers/tests/`、需求索引状态；不重写 A/B 内部实现。

- 验证真实 FastAPI app 中 Application Host、Wiki capability、应用路由和旧 `/wiki` 移除。
- 验证应用进程/worker 的权限、workspace 隔离、异常退出、EOF、取消和非幂等调用保护。
- 验证 Wiki 数据前后对比、Note/Wiki authority 不变、旧 UI 交互保持可用。
- 更新 current architecture、data model、api inventory、known pitfalls 和需求索引。
- 生成只包含命令与结果的验证证据文件。

## 4. 验收标准映射

| 需求标准 | 计划任务 |
| --- | --- |
| 1–7 应用包、宿主、workspace、桌面/Web/移动端声明 | A、B |
| 8–12 Agent、插件、权限、运行和错误语义 | A、C |
| 13–17 Wiki 应用与既有知识数据 | A、B、C |
| 18–23 Application Protocol v1、桌面进程、Web worker、目录配置、Agent 生成边界 | A、C |

## 5. 风险与回滚

- 任意 HTML 或后端代码越权：通过独立容器、CSP/bridge、manifest allowlist、Host authority 和无公开监听限制；安全测试失败则不合并。
- Wiki 迁移造成知识不可读：先保持 Wiki store/pipeline/Note authority 不变，用同一数据运行新 UI；数据对比失败则回滚应用入口 wiring。
- 应用运行状态与 Agent/Task 状态不一致：Application Run 只作为应用运行投影，Agent Turn 继续由现有 Agent Runtime 产生唯一终态。
- Web worker 在当前本地 FastAPI 中无法模拟真实云基础设施：第一版冻结受控 invocation/worker seam 和资源策略，不宣称已完成外部云部署；真实部署属于后续宿主 Adapter。
- 合并冲突：A/B 不共享写集；`App.tsx`、`AppLayout.tsx` 和 system docs 只由 C 或主流程收口。

回滚策略：保留已有 Wiki store、graph、Note 和 plugin 数据；移除 Application Host wiring 后恢复原业务入口仅作为代码回滚手段，但本需求本身不要求保留旧 `/wiki` 兼容运行。

## 6. 验证命令

- `python3 -m compileall backend/app`
- `PYTHONPATH=backend pytest -q backend/tests/test_application_* backend/tests/test_wiki_*`
- `(cd frontend && corepack pnpm test:contracts)`
- `(cd frontend && corepack pnpm build)`
- `git diff --check` 与每个 worktree 的 `git status --porcelain`
- 合并后按风险补充 `scripts/run_core_regression.sh` 或对应核心测试。
