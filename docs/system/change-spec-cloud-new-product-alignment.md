# Cloud Web new-product 对齐增量变更说明

## 当前现状

Cloud Web 已有真实 CloudClient、登录、会话、设备、成员、模型、授权和设置能力，但页面未完整复用 `docs/new-product` 的 Cloud 壳层与设计系统。构建入口还遗漏了共享 `src/components` 的 Tailwind 扫描范围，导致人员和设备页面部分工具类没有进入产物，出现控件挤压、输入框不可见和布局断裂。

## 本次目标

- 对齐 new-product Cloud 的左侧导航、品牌层级、页面内容区和浅/深色语义 token。
- 将提供的 NoteMeld logo 复制到前端源码资产中，并由 Cloud 登录页和已登录壳层使用。
- 保留现有真实 API、权限边界、会话操作和安全设备流程，不使用静态业务数据替代接口。
- 让人员、设备和配对页面在真实数据、空状态、加载状态和错误状态下可读、可操作。

## 明确不做

- 不修改桌面端、Android 端或 Cloud 后端协议。
- 不伪造 new-product 中尚未有后端来源的数据（例如静态成员统计和演示设备记录）。
- 不把 `docs/` 作为运行时资源路径。

## 影响范围与验证

- `desktop/frontend/src/cloudAlignment.css`、Cloud 页面壳层和 Cloud 组件文案/布局。
- `desktop/frontend/src/assets/notemeld-cloud-logo.png`：源码内置 logo 资产。
- Cloud Web Vite/Tailwind 构建扫描范围。
- 验证：TypeScript、Cloud Web build、Cloud session/new-product surface contract tests、Cloud API smoke 和登录/设备/成员/设置接口矩阵。

## 风险与回滚

改动只在 Cloud Web 路由和静态资源构建范围内；若视觉调整需要回滚，可回退 Cloud 壳层 CSS 与 `CloudHeader` 结构，CloudClient 和后端数据不受影响。

## 2026-09-19 原型信息层级收敛

- 页面目标：C02 直接进入运行看板；C03 默认让消息区占满会话列表右侧；C04/C05 保留页面标题与主操作但移除解释性副标题；C06 用左侧分类切换唯一的右侧设置面板。
- 组件映射：继续复用 Cloud Top Header、Tabs、Card、Composer、Button 和本地 Lucide 图标；品牌入口统一使用 `assets/logo.png`，不增加新组件或图标实现。
- 状态与边界：删除未登录预览横幅只改变静态原型展示，不改变真实 Cloud 登录、API 鉴权、数据来源和错误状态。原型与真实数据边界继续由功能注册表和系统文档记录。
- 验收：C02/C03/C04/C06 不出现预览横幅；C02 不出现重复页面标题块；C04/C05 不出现指定副标题；C03 默认无摘要栏预留宽度且输入区完整可见；C06 每次只显示当前选中分类的面板，并支持键盘点击。
