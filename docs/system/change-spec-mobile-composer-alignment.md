# Change Spec: 移动端输入区布局微调

## 现状与问题

M01、M02 静态原型共用 `docs/new-product/assets/mobile.css` 的 `.mobile-composer[data-composer]` 和 `mobile.js` 的展开状态。收起态 `.composer-input-row` 没有占满父容器，导致发送按钮随内容停在中间；展开态权限和模型文字只有 10px，发送圆形为 42px。

## 目标、范围与页面简述

用户在移动端发消息：主操作始终是最右侧发送；输入聚焦后，上方输入、下方左侧添加与权限、右侧模型与发送的层级不变。收起态发送按钮靠右；展开态权限/模型文字更易读，发送图形略小但可点击区域仍不小于 44px。M01/M02 共享视觉契约，浅色、深色及窄屏一致。

不改变发送行为、权限/模型选择、数据结构、API、后端、原生移动端或桌面端；不添加新的组件或图标。

## 组件映射与最小实现

继续使用现有 `mobile-composer`、`composer-input-row`、`composer-tools`、按钮和 Lucide 图标。仅在 `mobile.css` 内给收起态输入行足够宽度，在展开态调整字体、网格末列和发送按钮视觉尺寸；保留原有 `data-composer`、`is-expanded`、事件及功能地图 selector。

## 冲突与风险

产品规则、数据模型和 API 不变；`known-pitfalls` 中的移动端 Agent 状态和远程链路不受影响。主要风险是窄屏模型长名称挤压发送按钮，须检查 390px 和 320px 宽度、长模型名、收起/展开状态和键盘焦点。回滚为撤销本次 CSS 增量。

## 验证

运行产品文档校验、JS 语法和 `git diff --check`；浏览器测量 M01/M02 收起及展开的按钮位置、字体和可点击区域，并检查深色截图。
