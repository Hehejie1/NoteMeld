# NoteMeld Product Polish Contract

这是 `docs/new-product` 页面原型在交给 Codex 设计或优化时使用的简短约束。完整的多角色流程位于工作区 skill：`.agents/skills/notemeld-product-polish/`。

## 页面生成前

先写清楚：用户是谁、要完成什么、主操作是什么、用户必须先看懂什么、有哪些状态、窄屏如何收缩，以及本次明确不做什么。页面必须选择一个已有 archetype：工作台、列表-详情、Agent 会话、设置、管理列表或设计文档。

## 组件规则

- 优先使用 `design-system/tokens.css`、`primitives.css`、`primitives.js`。
- 图标使用 `assets/vendor/lucide.js`，禁止 emoji、Unicode 图标和 icon font。
- 禁止页面内重新定义已有按钮、字段、Badge、状态反馈、焦点环、圆角或颜色。
- 基础原语负责通用交互；Session、Agent、Workspace、Wiki、设备和 Cloud 管理流程属于页面业务层。
- 每个主要交互至少覆盖默认、hover、focus、active、disabled 或 busy，以及适用的 empty/error/success 状态。

## NoteMeld 的高级感

保持冷静、中性、可长时间阅读的工作台气质。用字体层级、对齐线、间距节奏、内容密度和表面关系形成高级感；蓝色只承担操作与状态强调。装饰性渐变、玻璃效果、持续循环动效和大面积卡片网格不是默认答案。

## 交付验收

页面完成前检查宽桌面、窄桌面、移动端、浅色、深色和真实长度文本；确认导航、feature selector、Explain 模式、键盘焦点、`prefers-reduced-motion` 和相关验证脚本没有回归。视觉审查不可执行时，必须把“结构验证”和“视觉验证”分开报告。
