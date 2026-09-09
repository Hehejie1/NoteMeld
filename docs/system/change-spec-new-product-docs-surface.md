# Change Spec：new-product 多端设计文档与讲解模式

日期：2026-09-02
状态：Accepted design decisions / Prototype docs updated

## 1. 当前系统现状

- `docs/new-product/` 是静态信息架构原型目录，入口页通过 iframe 加载桌面端、云端和移动端页面。
- `config/feature-registry.json` 已记录部分 Cloud 功能、接口、数据表、状态和 selector，但没有完整覆盖桌面端与移动端。
- A01/A02/A03 已有 Cloud 架构、Cloud 数据库和 Cloud 功能表页面；A01/A02 主要按 Cloud 功能配置渲染，不能表达桌面端和移动端的架构与本地数据边界。
- 讲解模式已有雏形，但 A01/A02 使用元素顺序与功能顺序的兜底匹配，可能把错误的功能说明展示给用户；原型页面的绑定覆盖也不完整。
- 本次只改静态产品原型与其校验脚本，不修改正式 React、FastAPI、SQLite 或 Agent runtime。

## 2. 本次目标

- A01 展示桌面端、云端、移动端和跨端链路的整体架构、边界、运行位置与关键状态流转。
- A02 展示桌面端本地存储、Cloud SQLite、移动端缓存/投影和跨端同步的职责边界，以及页面映射和未决字段。
- A03 展示 D/C/M 页面所有已登记功能的功能描述、接口/能力、数据、状态和完成度。
- feature registry 成为页面说明、元素绑定和设计决策的唯一配置源。
- 预览模式保持原型正常操作；讲解模式按明确的 `feature_id` 绑定点击，并显示功能描述、实现映射、数据和状态；未登记的可交互元素显示“尚未登记”，不再按数组下标猜测功能。

## 3. 明确不做

- 不把静态配置直接当作正式产品 API、数据库迁移或运行时契约。
- 不在本次需求中新增真实后端接口、SQLite 表或生产权限。
- 不删除现有桌面、Cloud、移动端原型页面；仅补充目录、说明和绑定。

## 4. 冲突分析

- 与 `product-rules.md`：保持“AI 编译知识，人验证和消费”以及云端/远程设备边界，不把设备和运行节点混为一类。
- 与 `data-model.md`：文档将明确区分产品事实表、Cloud 控制面元数据、Agent 事件和本地缓存，不虚构已实现字段。
- 与 `known-pitfalls.md`：讲解配置不参与业务执行；不会把说明页的示例状态当成真实任务状态。
- 对线上/本地服务无影响；静态预览服务只读取 `docs/new-product` 文件。

## 5. 影响范围

- `docs/new-product/config/feature-registry.json`
- `docs/new-product/pages/cloud/a01.html`、`a02.html`、`a03.html`
- `docs/new-product/assets/product-docs.js`、`product-docs.css`
- `docs/new-product/assets/portal.js`、`PAGE-MAP.md`、`README.md`
- `scripts/cloud/validate_product_docs.py`

## 6. 实施与验证

- 用 `architecture`、`database`、`features` 三类配置驱动 A01/A02/A03。
- 用 selector 显式绑定 D/C/M 页面交互；解释弹窗只读取配置，不改写业务状态。
- 扩展校验器，使其检查所有原型页面的 selector，并只对 Cloud 功能执行 Cloud API/表存在性校验。
- 运行 JSON/JavaScript 语法检查、校验脚本、静态服务 HTTP 200 检查，并在浏览器中验证预览/讲解模式。

## 7. 待讨论决策

- 桌面端的本地 SQLite 与 Cloud 的 Workspace 元数据是否最终统一为跨端同步协议，还是长期保持两套事实源？本版先按“本地事实源 + Cloud 控制面 + 明确投影”展示。
- 移动端是否允许离线创建完整会话，还是只缓存已授权的会话投影？本版按后者展示，避免把移动端缓存误认为 Agent 执行事实。
- 已确认：桌面端、Cloud、移动端均使用统一语义的 Workspace 实体，记录名称、多个本地文件夹引用、长期记忆引用和授权策略引用；三端按各自事实源/投影保存，不把文件正文塞进元数据表。
- 已确认：移动端离线进入 `offline_readonly`，只能读取已同步历史信息，禁止提交远程命令、审批、设备授权和其他远程写操作；恢复在线并同步后才恢复控制。
- 已确认：用户偏好按用户保存；组织长期记忆和 Workspace 长期记忆分别按组织、Workspace 作用域隔离，不与 `user_preferences` 混用。
- 已确认：C07 是旧管理员页，归档并保留历史文件/兼容说明；当前入口、功能地图和数据库映射使用 C01-C06。
