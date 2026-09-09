# Change Spec: NoteMeld new-product Design System

## 现状

`docs/new-product` 是多端静态原型目录，页面分别维护自己的 CSS 和交互脚本。`design.md` 已定义部分视觉原则，但颜色、控件状态和基础交互还没有一个可运行的共同参考实现。

## 目标

新增独立的 `design-system/`，提供跨平台设计 Tokens、基础 HTML/CSS/JavaScript 交互原语、状态语义和可查看的展示页。现有页面通过公共样式/脚本入口使用这些原语；业务组件和页面布局仍由各页面维护。

组件库设计文档由 A04 承载，并分为两个一级目录：

- `设计价值观`：设计北极星、亲密性/对齐/对比/重复、跨端适配、状态透明、可访问性。
- `组件库`：Color/Spacing/Radius、Typography/Iconography、Layout/Density/Motion，以及 Buttons、Fields、Selection、Navigation、Data Display、Feedback、Overlay 等基础原语。

## 不做

- 不建立可被生产端直接依赖的前端 npm 组件包。
- 不把 Android、iOS、鸿蒙、桌面端和 Web 强行统一为一套源码。
- 不抽取 Session、Agent、Workspace、设备管理等业务组件。
- 不改变 NoteMeld 生产 API、数据库、应用协议或运行时。

## 验收

- `design-system/index.html` 可独立打开并展示 Tokens、按钮、字段、状态和反馈原语。
- A04 可在“设计价值观”和“组件库”两个一级目录之间切换，并为每个基础原语提供文字定义、适用边界和可操作 HTML 展示。
- 桌面、Cloud、移动端和设计文档页面的公共样式入口加载 Design System tokens/primitives。
- 公共脚本可在静态页面中初始化基础行为，不覆盖页面已有业务行为。
- 设计系统中的控件具备 focus-visible、disabled、active 和 reduced-motion 规则。
- 原有 `validate_product_docs.py` 继续通过，静态预览首页和 `start.sh` 继续可用。
