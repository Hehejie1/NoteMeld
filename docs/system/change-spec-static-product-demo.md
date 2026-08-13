# Change Spec：高保真静态产品演示与功能讲解

日期：2026-08-13
状态：Design Review
关联需求：`docs/requirements/2026-08-13-static-product-demo-and-feature-guide.md`
关联设计：`docs/superpowers/specs/2026-08-13-static-product-demo-design.md`

## 0. 预检查

- [x] 已阅读 `docs/system/current-architecture.md`
- [x] 已阅读 `docs/system/product-rules.md`
- [x] 已阅读 `docs/system/data-model.md`
- [x] 已阅读 `docs/system/api-inventory.md`
- [x] 已阅读 `docs/system/known-pitfalls.md`
- [x] 已搜索相关前端页面、service、store、路由和测试
- [x] 已只读检查 SQLite 表、数量和状态分布
- [x] 已检查 `docs/product/` 10 张基准截图
- [x] 已确认当前没有 demo/mock transport
- [x] 已确认目标不影响本地数据或线上服务

## 1. 当前系统现状

- 相关模块：`frontend/src/App.tsx`、layouts、pages、services、Zustand task store、BackendInit、Vite。
- 相关入口：`frontend/src/main.tsx`；正式路由 `/`、`/new`、`/notes/:taskId`、`/styles`、`/wiki`、`/settings/*`、`/about`。
- 相关数据表/文件：正式数据来自 `notemeld.db`、`note_results/`、Wiki 和 workspace 文件；演示只用新 fixture。
- 相关 API：conversation、note/task、chat、Wiki、styles、models、transcriber、downloader、migration、usage、deploy、MCP server、research search。
- 相关前端页面/组件：LandingPage、HomePage、WikiPage、StylesPage、SettingPage、AboutPage、AppLayout 和各内容组件。
- 相关测试：frontend contract tests、runtime/backend ready gate tests、路由与打包契约。
- 当前行为：前端依赖 BackendInit ready，页面通过 Axios、fetch 和 Tauri API 获得数据或执行动作。
- 当前限制：后端未启动时不能形成完整自包含演示；截图不可交互；无现成 mock transport。

## 2. 本次目标

- 用户问题：无需后端直接预览与讲解正式产品主要功能。
- 成功后的用户可见行为：页面可跳转、主要交互可操作、关键状态可复现、模拟生成可运行、右侧可查看需求与代码双重说明。
- 成功后的系统内部行为：demo 构建通过适配层读取 fixture 和 scenario engine，禁止真实业务请求。
- 必须保留的旧行为：正式源码、CLI、桌面、后端 ready gate、API、任务/Wiki 状态和现有 UI 行为。

## 3. 明确不做

- 不新增后端 demo API。
- 不修改 SQLite schema、业务文件结构或正式数据。
- 不真实执行生成、下载、迁移、删除、更新和凭证保存。
- 不复制平行页面，不用截图热点图。
- 暂不支持无 history fallback 的任意静态托管环境。
- 后续可选：CI 像素 diff、公开 demo 部署、双击离线包。

## 4. 冲突分析

- `product-rules.md`：无冲突；保持正式产品范式与入口，演示只读且可追溯。
- `data-model.md`：无字段语义变更；fixture 仅复用类型与状态含义。
- `api-inventory.md`：无真实接口增删改；demo adapter 模拟调用方期望的现有契约。
- `known-pitfalls.md`：重点防止 ready gate 被正式模式绕过、API wrapper 漂移、状态混用和凭证泄漏。
- 桌面/源码/CLI/MCP：正式路径不变；demo 不启动或连接 MCP。
- 打包/迁移/导入/回滚：无正式产物和数据迁移；demo build 不进入默认桌面 bundle，除非后续明确要求。

## 5. 影响范围

- 后端文件：无。
- 前端文件：App/BackendInit、request/stream/desktop action 边界、demo runtime、fixtures、guide UI、少量页面标注。
- 桌面/Tauri 文件：无 native 改动。
- 数据库模型/迁移：无。
- 文件系统结构：新增源码 fixture、文档、测试和预览脚本；不改业务数据目录。
- API 调用方：demo 模式由适配器满足；正式调用不变。
- MCP 工具：无。
- 测试：demo contract、状态机、guide、build、network 与 shell smoke。
- 文档：requirement/design/change spec/plan/test evidence；实现完成后按实际入口同步架构文档。

## 6. 实施方案

### 后端

- 改动点：无。
- 错误处理/日志/并发：不适用。

### 前端

- 改动点：显式 demo mode；统一 demo adapter；fixture/scenario engine；guide catalog/provider/drawer/target。
- 状态流转：沿用现有 TaskStatus 和 message/Wiki 状态；模拟生成由集中 scheduler 驱动。
- 加载/错误/空状态：均通过预定义 scenario 覆盖；未知 endpoint 快速失败。
- 桌面 ready gate：只在编译期 demo 模式返回 ready；正式模式代码和时长不变。

### 桌面/打包

- 改动点：不进入默认 Tauri 构建；Tauri action 在 demo 中由浏览器适配器模拟。
- 发布影响：无，除非后续决定发布 demo 静态产物。

## 7. 数据变更

- SQLite 表/字段/文件结构/迁移：全部无。
- 历史数据：不读取、不修改。
- 演示数据：版本控制的合成 fixture；只参考只读状态分布。
- 回滚后数据：无一致性问题。

## 8. 接口变更

- 新增/修改/删除后端接口：无。
- 请求、返回、错误语义：正式接口无变化。
- 前端调用方：demo 模式在前端边界模拟相同业务数据；未知 demo endpoint fail closed。
- MCP 调用方：无。
- `api-inventory.md`：当前无需更新；若实现产生新的公共协议再同步。

## 9. UI/交互变更

- 页面/组件：主要正式页面全部可演示；新增全局讲解开关和右侧说明抽屉。
- 用户路径：左键保持正式行为；讲解模式点击看说明；任意模式右键看说明；抽屉可继续执行原动作。
- 加载/空/失败/成功：由 scenario 选择并走正式组件。
- 可访问性：键盘关闭、焦点恢复、移动端讲解开关、target 语义。
- 桌面与浏览器差异：demo 以浏览器为主，桌面专属操作明确模拟。

## 10. 测试方案

- 后端测试：无新增；不涉及后端。
- 前端契约：运行现有 `pnpm test:contracts` 并新增 demo 契约测试。
- 构建：正式 `pnpm build` 与 demo build。
- 手动：10 张截图基准、1440px、移动端、深层路由、主要交互和说明抽屉。
- 原问题复现：后端关闭时正式前端出现 ready 问题；demo 脚本应独立成功。
- 回归断言：正式模式仍检查 backend；demo 无真实网络；状态齐全；无秘密/绝对路径；shell 深层路由可访问。

## 11. 验收标准

- [ ] 无后端可通过 shell 启动并浏览主要路由。
- [ ] 10 个截图基准状态无明显大范围视觉偏差。
- [ ] 模拟状态覆盖空、pending、running、success、failed、canceled、Wiki partial。
- [ ] 功能说明包含产品依据、代码依据、数据和演示限制。
- [ ] demo 操作不写正式数据、不访问真实业务后端。
- [ ] 正式 build、ready gate 和现有入口无回归。

## 12. 风险和回滚

- 主要风险：模式泄漏、漏拦直接 fetch/Tauri、fixture 泄密、target 改布局、timer race。
- 触发信号：正式 build 出现 fixture、network 访问 8483、截图偏差、卸载后状态继续变化。
- 降级策略：关闭 demo flag；隐藏未完成说明 target；scenario 快速失败。
- 回滚步骤：删除 demo 分支、适配层、fixture、guide 与脚本；恢复少量页面标注。
- 回滚后数据一致性：无数据迁移，不需处理。
- 用户可见影响：仅静态演示不可用，正式产品不受影响。

## 13. Agent 必答问题

- 影响哪些模块：前端运行入口、数据访问边界、主要页面、task store、Vite、测试与文档。
- 是否已有类似能力：已有正式 UI/路由和 Vite preview，没有静态 demo transport。
- 是否和产品规则冲突：不冲突。
- 是否和数据模型冲突：不冲突；沿用状态语义。
- 是否重新引入坑点：可能涉及 ready gate、wrapper、状态和泄密，已有明确防线。
- 是否影响本地/线上：目标为零影响；demo 不访问真实业务系统。
- 最小可行改动：共享正式 UI，在编译期 demo 模式替换运行时/传输/桌面副作用。
- 补哪些测试：模式隔离、endpoint fail closed、fixture 安全、scenario、guide、双构建、network、shell 和截图核对。
