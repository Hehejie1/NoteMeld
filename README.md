<div align="center">
  <h1>NoteMeld</h1>
  <p><b>源知库 · 你的专属知识库</b></p>
  <p>
    <img src="https://img.shields.io/badge/license-MIT-blue.svg" />
    <img src="https://img.shields.io/badge/frontend-react%2019-blue" />
    <img src="https://img.shields.io/badge/backend-fastapi-green" />
    <img src="https://img.shields.io/badge/runtime-python%203.11%2B-yellow" />
    <img src="https://img.shields.io/badge/desktop-tauri-purple" />
    <img src="https://img.shields.io/badge/status-MVP-success" />
  </p>
</div>

---

## ✨ 项目简介

<p align="center">
  <img src="./docs/index.png" alt="NoteMeld 首页预览" width="100%" />
</p>

**NoteMeld（源知库）** 是一款自托管的 AI 知识工作台，面向那些长期学习、持续研究、反复输出的人。

它不是一个单纯“保存资料”的笔记工具，而是把你每天接触的内容，逐步沉淀为**可追溯、可复用、可持续增长的个人知识库**。

在 NoteMeld 里，你平时接触的多源信息会被汇入同一个知识层：

- 🌐 **阅读**：网页文章、本地文件
- 🎬 **观看**：Bilibili / YouTube / 抖音 / 快手 / 视频号等平台视频
- 💬 **对话**：与 AI 交流的过程与结论

每一次记录都会同时产出两件东西：

- 一篇结构化 Markdown 笔记，方便你直接阅读、复盘、继续编辑
- 一份知识包（实体 / 概念 / 证据 / 关系），自动汇入项目级 Wiki，供后续检索、引用和问答调用

这意味着你不再只是“收藏了一条链接”或“记下了一段聊天”，而是在持续构建属于自己的知识网络。

> NoteMeld 不走传统 RAG 路线，而是采用 **Wiki-First Retrieval**：先把内容编译成结构化知识层，再进行检索、引用和问答。相比先堆原文再临时检索，它更强调可追溯、可复用、可持续增长，小机器也能稳定运行。

### 它适合谁

- 想长期学习某个主题的人：如 AI、产品、历史、投资、技术栈
- 在做持续项目研究的人：如产品调研、创业准备、竞品分析、行业跟踪
- 有输出需求的人：如写博客、做视频、写报告、做分享、做课程
- 经常和 AI 深度讨论，希望把结论长期沉淀下来的人

### 它解决什么问题

- **信息易失**：看过、聊过、想过的内容很快忘掉
- **知识分散**：网页、视频、文件、AI 对话散落在不同平台
- **复用困难**：写作、决策、学习时又得重新搜索和整理
- **观点无证据**：知道一个结论，却找不到来源、上下文和依据

NoteMeld 的目标不是帮你“记更多”，而是帮你把零散输入逐步变成稳定、可追溯、可调用的个人认知资产。

### 三步走

| 步骤 | 做什么 |
|---|---|
| **1. 多源采集** | 粘一条链接 / 上传一个文件 / 接入一段 AI 对话 |
| **2. 结构化笔记** | Plan → Map → Reduce 的 Refine Engine 自动生成 Markdown 笔记 |
| **3. 沉淀为 Wiki** | 抽取知识包，自动汇入实体 / 概念图谱，永久可查询 |

---

## 🖼️ 产品预览

### 结构化笔记

NoteMeld 会把视频、网页或文件内容整理成可直接阅读的 Markdown 笔记，并保留来源、关键截图、时间线和总结脉络。

<p align="center">
  <img src="./docs/note.png" alt="NoteMeld 结构化笔记" width="100%" />
</p>

### Wiki 知识图谱

每篇笔记都会进一步抽取知识包，汇入项目级 Wiki。你可以围绕实体、概念、观点和证据持续追踪一个主题的演化。

<p align="center">
  <img src="./docs/wiki.png" alt="NoteMeld Wiki 知识图谱" width="100%" />
</p>

---

## 🧭 如何使用

最推荐的使用方式，不是把它当成“第二个收藏夹”，而是当成你的**个人研究台**和**长期上下文层**。

### 典型使用场景

- **长期学习**：持续收集课程、文章、视频与自己的理解，逐步形成主题知识图谱
- **项目研究**：把竞品资料、行业访谈、思考过程和 AI 讨论统一沉淀，方便后续反复调用
- **内容创作**：积累素材、观点、证据和案例，写文章或做分享时直接从自己的库里取材
- **决策支持**：围绕职业选择、技术选型、投资判断等议题，保留证据链和历史推理
- **个人反思**：把重要对话、阶段性结论和复盘沉淀下来，形成长期的思维档案

### 最佳实践

- **围绕长期主题建库**：优先聚焦 1 到 3 个你会持续投入的主题，不要一开始什么都收
- **优先采高密度内容**：与其保存 20 条噪音资讯，不如沉淀 3 条真正值得反复回看的内容
- **保留你的解释层**：除了原文，也要保存自己的判断、总结、质疑和结论
- **重视结构化加工**：采集只是入口，真正的价值来自整理后的 Markdown 笔记和 Wiki 知识包
- **让知识参与后续工作**：写作、汇报、继续提问、做决策时，优先回到自己的库，而不是重新搜索全网
- **持续增量，不求一次完美**：个人知识库应该像花园一样生长，而不是一次性建模工程

### 一条简单的个人工作流

1. **每天采集**：把值得沉淀的网页、视频、文件、AI 对话收进来
2. **每周整理**：挑出最重要的 3 到 5 条内容生成结构化笔记
3. **每月回顾**：看看一个主题下反复出现了哪些概念、人物、证据和争议
4. **优先回用**：下一次写东西、做方案、继续提问时，先查自己的库

## 🔧 功能特性

### 内容采集
- 多平台视频：Bilibili、YouTube、抖音、快手、本地视频
- 网页文章与本地文档：清洗 HTML、抽取正文 / 元数据 / 社交信号，支持 Markdown、PDF、Office、图片、音视频等上传
- Markdown 上传兼容浏览器 `application/octet-stream` / `binary/octet-stream` MIME 识别偏差
- B 站 / YouTube 字幕优先：有官方字幕时跳过音频转写，省时省钱
- 网页兜底：视频下载、音频下载或转写失败时，自动切换网页抓取继续生成
- 浏览器扩展：在原页面直接发起任务，附带本地登录态 Cookie

### 笔记生成
- 多模态视频理解：转录 + 智能视觉采样（按转录线索定位关键帧）
- 笔记格式可选：要点、总结、思维导图、引文 + 时间戳跳转、自动截图
- Refine Engine：长内容自动 Map-Reduce，超长输入也能稳定出稿
- 多模型支持：OpenAI / DeepSeek / Qwen / 任意 OpenAI 兼容供应商
- 多种本地转写：Faster-Whisper、MLX-Whisper（Apple Silicon）、Groq、必剪 BCut

### 知识库
- 知识包模型：每篇笔记产出 `entity / concept / evidence / claim / relation`
- Wiki 图谱：实体类型分组的左侧树 + 中央力导图 + 右侧元数据洞察
- 可溯源：每个实体 / 概念都关联回原始来源链接和时间戳
- 增量沉淀：跨任务的实体合并与概念聚类（演进中）

### 工程能力
- 自托管：后端 FastAPI，前端 React，数据本地持久化
- 桌面端：Tauri 壳 + Python backend sidecar，支持 macOS / Windows 打包
- Sidecar 文件系统：每个任务保留 SummaryInput / Plan / Refine 轨迹，便于复盘与排障
- 网关超时韧性：多模态推理被 ALB / 网关超时（502/503/504/524）时，图片自动阶梯降级（8 → 4 → 2 → 0）
- SQLite 持久化任务、Provider、Model、用量统计
- MCP 接入：把 NoteMeld 作为本地知识工具接入 Trae 等 AI IDE

## 🚀 快速开始

### 环境要求

- macOS / Windows / Linux
- Python 3.11+
- Node 20+
- pnpm（通过 corepack 启用即可）
- ffmpeg
- 一个 LLM Provider Key（OpenAI / DeepSeek / Qwen 任选其一）

### 一键安装（推荐）

macOS：

```bash
curl -fsSL https://notemeld.wiki/install.sh | bash
notemeld
```

Windows PowerShell：

```powershell
irm https://notemeld.wiki/install.ps1 | iex
notemeld
```

Linux：

```bash
curl -fsSL https://notemeld.wiki/install.sh | bash
notemeld
```

安装后会注册 `notemeld` 命令，并将应用、数据、日志隔离到用户目录下的 `.notemeld`。

### 源码启动

```bash
git clone <your-repo-url> notemeld
cd notemeld
cp .env.example .env

# 启动后端 + 前端
bash run_notemeld.sh
```

启动成功后：
- 前端：<http://127.0.0.1:3015>
- 后端：<http://127.0.0.1:8483>

首次启动会自动创建 Python 虚拟环境、安装依赖、生成 `.env`。

### 运行模式

当前仓库同时兼容三种运行方式，并通过 `NOTEMELD_RUNTIME_MODE` 区分：

- `source-script`：`bash run_notemeld.sh`
- `source-cli`：`notemeld` / `notemeld start`
- `desktop`：Tauri 桌面壳 + Python backend sidecar

当前默认行为：

- `run_notemeld.sh` 会自动注入 `NOTEMELD_RUNTIME_MODE=source-script`
- `notemeld` 会自动注入 `NOTEMELD_RUNTIME_MODE=source-cli`
- 桌面端会由 Tauri 壳注入 `NOTEMELD_RUNTIME_MODE=desktop`

手动覆盖示例：

```bash
NOTEMELD_RUNTIME_MODE=source-script bash run_notemeld.sh
NOTEMELD_RUNTIME_MODE=source-cli notemeld start
```

### 桌面端开发与打包

`desktop/` 用于承载 Tauri 桌面壳、sidecar 启动逻辑和桌面构建配置。桌面端不会替换源码启动入口，`run_notemeld.sh` 和 `notemeld` 仍然保留并继续可用。

本地开发桌面端骨架：

```bash
cd desktop
pnpm install
pnpm tauri:dev
```

统一打包入口：

```bash
cd desktop
pnpm build:mac
pnpm build:win
```

底层脚本入口：

```bash
./packaging/scripts/build-backend-macos.sh
./packaging/scripts/build-desktop-macos.sh
./packaging/scripts/build-backend-windows.ps1
./packaging/scripts/build-desktop-windows.ps1
./packaging/scripts/smoke-test-desktop.sh
```

正式打包目标：

- `build-backend-macos.sh` 先把 Python backend 打成 `notemeld-backend` sidecar，并暂存到 `desktop/src-tauri/bin/backend/`
- `build-desktop-macos.sh` 会先执行无 bundle 编译，再显式产出 `.app` 和 `.dmg`
- 最终给用户的桌面安装包无需再下载 backend 和 frontend 源码，只保留桌面应用本体、内置前端资源和内置 backend sidecar

自动发布：

- 推送 `v*` tag 时，GitHub 会自动构建 macOS `.dmg` 和 Windows `.msi`，并上传到 Release 页面
- 也支持在 GitHub Actions 页面手动触发 `workflow_dispatch`

macOS DMG 正式发布必须同时覆盖 Apple Silicon 与 Intel：

```bash
NOTEMELD_CODESIGN_IDENTITY="Developer ID Application: <Name> (<TEAMID>)" \
NOTEMELD_NOTARY_PROFILE="notemeld-notary" \
./.trae/skills/notemeld-dmg-packaging/scripts/package-notemeld-dmg.sh --release --upload --public-verify
```

`--release` 会强制执行 Developer ID 签名、Apple notarization、`stapler staple`、Gatekeeper 校验、DMG 挂载后 `.app` 签名校验和公网 SHA256 回验。本地 ad-hoc 测试包不能替代正式发布包。

### MCP 接入（Claude Code / Cursor / Codex / OpenClaw）

NoteMeld 启动后，后端同时提供 HTTP MCP endpoint。桌面 DMG 模式固定使用 `http://127.0.0.1:8483/mcp`：

```text
http://127.0.0.1:8483/mcp
```

NoteMeld 退出后，本地后端和 MCP 服务会一起停止。

Claude Code：

```bash
claude mcp add notemeld \
  --transport http \
  http://127.0.0.1:8483/mcp
```

Cursor：

```json
{
  "mcpServers": {
    "notemeld": {
      "url": "http://127.0.0.1:8483/mcp"
    }
  }
}
```

Codex：

```toml
[mcp_servers.notemeld]
url = "http://127.0.0.1:8483/mcp"
```

小龙虾 OpenClaw：

```json
{
  "mcpServers": {
    "notemeld": {
      "transport": "http",
      "url": "http://127.0.0.1:8483/mcp"
    }
  }
}
```

配置好后，可以在 AI 工具里直接说：

```text
把 https://www.douyin.com/video/xxx 做成结构化笔记，带时间戳
```

AI 客户端会调用 `generate_note`。短任务会直接返回 Markdown；长任务超过 `maxWaitSeconds` 后会返回 `taskId`，客户端可以继续调用 `get_task` 查询进度，完成后调用 `get_note` 拉取 Markdown。

远程访问时，需要先在 NoteMeld 启动环境中配置：

```bash
export NOTEMELD_MCP_TOKEN="your-token"
```

然后在 Trae MCP server headers 里加入：

```json
{
  "mcpServers": {
    "notemeld": {
      "url": "http://127.0.0.1:8483/mcp",
      "headers": {
        "Authorization": "Bearer your-token"
      }
    }
  }
}
```

当前可用 MCP 工具：

- `generate_note`：提交视频/网页笔记任务，完成时直接返回 Markdown，超时时返回 `taskId`
- `get_task`：按 `taskId` 查询生成任务状态
- `get_note`：按 `taskId` 读取生成后的 Markdown
- `list_models`：列出本地已启用的 Provider 和模型
- `notemeld_import_note`：导入现成 Markdown 笔记并后台提取 LLM Wiki
- `notemeld_search_notes`：按标题搜索笔记
- `notemeld_read_note`：按标题读取笔记内容
- `notemeld_search_wiki`：搜索结构化 LLM Wiki
- `notemeld_read_wiki_page`：读取白名单 Wiki concept/entity 页面

可用下面的请求快速验证 MCP 握手和工具列表：

```bash
curl -s http://127.0.0.1:8483/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"Trae","version":"local"}}}'
```

```bash
curl -s http://127.0.0.1:8483/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'
```

### 开机自动启动

在 NoteMeld 设置中开启「开机自动启动 NoteMeld」后，macOS 登录时会自动打开 NoteMeld，并启动本地后端与 MCP 服务。

也可以手动配置：系统设置 → 通用 → 登录项 → 添加 `/Applications/NoteMeld.app`。


## 📜 License

MIT License。详见 [LICENSE](./LICENSE)。
---

<div align="center">
  <p><b>More Than Notes · 让每一次阅读、观看、对话，沉淀为你的专属知识库。</b></p>
  <p><sub>NoteMeld · 源知库</sub></p>
</div>
