# 静态产品演示验证记录

日期：2026-08-13

## 自动验证

- `node --experimental-strip-types --test tests/staticDemoGuide.test.mjs`：通过。
- `node --test tests/staticDemoContracts.test.mjs tests/staticDemoRuntime.test.mjs tests/staticDemoPreviewScript.test.mjs`：3/3 通过。
- `pnpm test:contracts`：通过。
- `pnpm build`：通过。
- `pnpm build:demo`：通过；Vite 仅报告已有大 chunk 与第三方 lottie `eval` 警告。
- fixture/runtime 契约覆盖 synthetic 数据、secret/绝对路径扫描、未知 endpoint fail closed、reset、状态矩阵与 scheduler dispose。

用户已明确要求忽略仓库中与本需求无关的 5 个基线失败；本记录不把它们归因于静态演示，也未修改相关代码。

## 浏览器验证

使用无后端的 `vite preview` 在 `127.0.0.1:43175` 验证：

- `/new`
- `/notes/demo-note-success`
- `/notes/demo-note-running`
- `/notes/demo-note-failed`
- `/notes/demo-note-canceled`
- `/wiki`
- `/styles`
- `/settings/model`
- `/settings/transcriber`
- `/settings/download`
- `/settings/data-migration`
- `/settings/usage`
- `/settings/monitor`
- `/settings/mcp-servers`
- `/settings/research-search`
- `/about`

以上 16 个路由均由地址栏直接打开并产生可见 DOM，浏览器 error 日志为 0。发现并修复一次深层路由资源基址问题：demo build 从 `./` 改为 `/` 后，笔记和设置深层路由可刷新；正式 build 的 `./` 未改变。

右键“风格模板”验证结果：停留在原路由，右侧展示名称、用户价值、当前行为、产品依据、代码依据、数据状态和演示限制；关闭后正常导航。桌面 1440×720 抽查显示侧边栏、工作区、输入框和控制栏沿用正式组件与 design token，未使用截图作为页面内容。

## 隔离结论与剩余边界

- 演示 mode 的请求由内存 runtime 处理，未知调用不回退到 `/api`。
- 桌面注册、文件选择、更新与聊天流在 demo mode 走模拟分支。
- fixture 只含合成数据，不含真实用户正文、密钥、Cookie、token 或绝对本地路径。
- 未建立逐像素 CI；视觉结论是基于正式组件复用、10 张 `docs/product` 基准检查和桌面浏览器抽查。字体渲染、浏览器缩放及截图视口可能造成细微差异。
