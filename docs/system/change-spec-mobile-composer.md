# Change Spec：移动端 Agent 输入框与能力入口

## 当前现状

`docs/new-product/pages/mobile/m01.html` 只有单行输入框；M02 已有模型、权限和文件按钮，但权限为即时切换，文件按钮仅改变 placeholder。两页共用 `docs/new-product/assets/mobile.css` 与 `mobile.js`，设计系统由 `docs/new-product/design-system/` 提供 HTML 原语。

## 本次目标

- 空闲时保留单行输入框：左侧添加、中央输入、右侧发送。
- 聚焦输入时展开第二行，提供模型和操作权限；M01/M02 行为一致。
- 添加入口提供拍照、图片/视频、手机文件，以及技能、插件、应用、智能体搜索选择。
- 完全访问必须先展示统一风险提示，再确认切换。
- M02 新建会话按钮使用设计系统中的语义图标样式。

## 范围与边界

本次只修改静态原型，不新增后端 API、数据库字段、原生权限实现或生产端组件；文件 input 仅模拟调用系统选择器的入口。桌面端与云端生产页面不受影响。

## 影响与实现

- 修改 M01/M02 HTML、移动端共享 CSS/JS、feature registry 和 design-system primitives。
- 交互状态为 collapsed/expanded、sheet open/closed、permission default/full、access confirmation。
- 保留菜单、模型选择、产物查看、删除会话和页面跳转。

## 验证

- `node --check docs/new-product/assets/mobile.js`
- `python3 scripts/cloud/validate_product_docs.py`
- `git diff --check -- docs/new-product`
- 手动检查 M01/M02 的聚焦展开、添加面板、模型面板、权限确认和新建会话按钮。
