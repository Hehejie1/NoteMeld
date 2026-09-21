# Change Spec：new-product AI 实施路由

日期：2026-09-19
状态：Accepted

## 当前现状

`docs/new-product` 已将产品信息架构、数据边界和功能状态集中展示，但静态原型页面编号与实际 React、Cloud FastAPI、Android 原生实现之间没有一份面向实施者的入口索引。AI 容易只修改原型，或在未确认控制面与端侧权威的情况下改错层。

## 目标

- 在 `docs/new-product/AI-IMPLEMENTATION-ROUTING.md` 提供按页面编号与任务主题检索的实施入口。
- 每个入口明确原型文件、真实页面/组件、服务或后端路由、数据边界和最小验证命令。
- 固化“源码与契约优先于原型说明”的读取顺序，以及模型凭据、设备配对、Workspace、Agent 的跨端边界。

## 不做

- 不修改产品运行时、数据库 schema、API 或原型交互。
- 不把路由文档当作第二份接口或数据模型事实源。

## 验收

- AI 可从任一 D/C/M/APP 页面编号定位到原型、产品源码和验证入口。
- 文档指向现有系统规范、feature registry 与实际文件，不复制凭据或敏感样例。
- 文档通过 Markdown 链接检查和现有 product-docs 校验。
