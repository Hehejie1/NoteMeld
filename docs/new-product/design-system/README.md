# NoteMeld Design System

这是 `docs/new-product` 的跨端设计语言参考实现，不是生产端可直接依赖的 npm 组件包。

## 参考基线

设计方法参考成熟系统的共同做法：Ant Design 的语义 token、控件尺寸和 Select 变体；Radix Primitives 的可组合结构、焦点管理、键盘交互和弹层定位；Material Design 3 与 Carbon 的响应式布局、状态和可访问性规范。这里吸收的是设计契约，不复制任何库的视觉或源码。

## 目录

- `tokens.css`：颜色、字体、间距、圆角、控件尺寸、焦点和动效 token。
- `primitives.css`：基础 HTML 原语，包括按钮、图标按钮、字段、Badge、状态反馈和可见性工具类。
- `primitives.js`：静态原型中的基础行为，包括 toast、表单 busy 状态和旧页面 class 的兼容标记。
- `index.html`：可直接打开的交互展示页。

## 使用边界

各平台不共享这里的源码，而是参考同一套语义契约并使用自己的原生实现。公共系统只负责：

- Design Tokens；
- 基础交互原语；
- 状态语义；
- focus、disabled、active 和 reduced-motion 等通用行为；
- 跨端可比对的参考样例。

Session、Agent、Workspace、Wiki、设备和管理后台等业务组件留在对应平台的业务代码中。

## A04 设计文档

门户中的“产品设计文档 → A04 组件库设计”是本设计系统的主查看入口。A04 分为两个一级菜单：

- **设计价值观**：NoteMeld 的设计北极星、判断标准、跨端一致性、状态透明、安全可逆和可访问性。
- **组件库**：Design Tokens、Typography、Spacing、Iconography、Motion，以及 Actions、Fields、Selection、Navigation、Data Display、Feedback、Overlay 等基础原语。

每个基础原语都应说明目的、结构、状态、适用/禁用场景、桌面与移动端适配和可访问性，并提供可操作的 HTML 参考实现。

Select 的参考实现单独展示 Desktop/Web 和 Mobile 两种形态：前者是 32px 触发器 + 对齐的 Popover/Listbox，后者是适合触摸的 Bottom Sheet/Listbox；两者共享当前值、选项、键盘/返回、取消和确认语义。

## 在原型页面中使用

桌面、Cloud、移动端和设计文档页面通过各自的公共脚本入口自动加载本目录。新页面也可以显式引用：

```html
<link rel="stylesheet" href="../../design-system/tokens.css">
<link rel="stylesheet" href="../../design-system/primitives.css">
<script src="../../design-system/primitives.js"></script>
```

基础组件优先使用语义属性，例如：

```html
<button class="nm-button" data-variant="primary">保存</button>
<span class="nm-badge" data-status="running">运行中</span>
<div class="nm-state" data-state="error">...</div>
```
