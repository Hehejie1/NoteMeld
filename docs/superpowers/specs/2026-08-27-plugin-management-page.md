# 插件管理与内置目录页面执行规格

## 1. 数据契约

在 `frontend/src/services/plugins.ts` 增加只读 `BUILTIN_PLUGIN_CATALOG`：每项包含 `plugin_id`、显示名、简介、分类、能力摘要、requested permissions、license、推荐标记和 target 状态。目录不是安装记录；安装事实继续来自 `PluginInstallation`。

目录首期覆盖当前已声明的官方能力：链接转 Note、浏览器、终端、文档转 Markdown、图片 OCR、视频获取、视频帧、音频提取和音频转写。平台字段只展示 manifest 已声明的状态，未知或未验证统一显示不可用/未验证。

## 2. 页面行为

- `/settings/plugins` 继续作为唯一页面入口。
- 默认 tab 为“插件目录”，另有“已安装” tab；已安装视图只显示后端返回的安装项与能匹配的目录元数据。
- 搜索匹配显示名、plugin id、简介和 capability id；分类和“已安装”过滤只改变投影，不发起 mutation。
- 卡片显示图标占位、名称、简介、分类、内置/已安装/启用/平台状态和动作按钮；详情弹窗显示权限、能力、版本和许可证。
- “添加插件/内容”打开弹窗，输入 Release ZIP URL、可选 SHA-256 和权限并确认安全提示；确认后调用现有 `installPlugin`，不新增 preview API。
- backend 未 ready 时只显示 gate，不调用 list 或 mutation；请求失败显示安全错误，并允许重试/关闭。
- 启用、禁用、激活和回滚继续沿用现有 API；操作期间禁用对应控件，完成后刷新列表。

## 3. 测试契约

新增 `frontend/tests/pluginManagementContracts.test.mjs`，静态断言：

1. catalog 含固定官方 plugin ids 和状态标签；
2. 页面包含目录/已安装、搜索/分类、详情和添加入口；
3. 页面继续调用 list/install/enable/disable/activate/rollback；
4. install 前要求 source URL、展示权限确认并受 `backendReady`/busy gate；
5. 页面没有执行脚本、读取 secret 或新增第二个安装状态 API。

## 4. 非目标与回滚

不修改 backend、数据库、SDK、manifest 协议、MCP 或桌面启动流程。若 UI 出现问题，可回退 `Plugins.tsx` 与 `plugins.ts`，不会改变已安装版本目录、active pointer、权限或审计记录。
