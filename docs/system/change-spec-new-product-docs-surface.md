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
- feature registry 成为页面说明、元素绑定和已确认范围规则的唯一配置源；规则嵌入 A01/A02/A03 的对应架构、数据与功能条目，不另设决策展示模块。
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

## 7. 已确认范围规则（嵌入总览）

- 本地开发验证码由 `.env` 配置，默认 `888888`；生产禁用开发默认值并通过 SMTP 邮件发送，响应不回传验证码。
- 一个 Cloud 服务端对应一个团队。模型目录与默认策略按组织共享，默认使用 `Auto` 按场景选择，用户可为当前会话显式选择；连接 Cloud 的本地端只选该目录。端侧 API Key 自行保管，不参与目录同步、扫码或共享；当前按 `user_id` 隔离的 schema/API 标记为迁移缺口。
- 生产 Workspace 备份使用 S3 兼容对象存储，Cloud SQLite 只保存对象键、大小和时间索引。
- 用户偏好按用户保存；组织级设置按组织保存，并在读取时覆盖对应默认值。
- 桌面端、Cloud、移动端使用统一 Workspace ID 和字段语义：名称、多个本地文件夹引用、长期记忆引用、授权策略引用；文件正文仍由各端文件系统负责。
- 桌面端和移动端对 Cloud 都是第三端设备；持续心跳同步在线状态，任一设备离线均进入 `offline_readonly`，恢复在线并完成同步后才恢复控制。
- C07 不进入当前页面目录、功能地图或独立生命周期决策；管理员能力由 C04/C06 承载。
- 成员角色暂时只读；未来开放升降级必须使用独立接口、二次确认、最小管理员保护和完整审计。
