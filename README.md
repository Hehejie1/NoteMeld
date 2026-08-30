<div align="center">
  <h1>NoteMeld</h1>
  <p><b>源知库 · 你的 AI 研究助手</b></p>
  <p>
    <img src="https://img.shields.io/badge/license-MIT-blue.svg" />
    <img src="https://img.shields.io/badge/frontend-react%2019-blue" />
    <img src="https://img.shields.io/badge/backend-fastapi-green" />
    <img src="https://img.shields.io/badge/runtime-python%203.11%2B-yellow" />
    <img src="https://img.shields.io/badge/desktop-tauri-purple" />
    <img src="https://img.shields.io/badge/status-MVP-success" />
  </p>
  <p>
    <a href="https://notemeld.wiki/">官网</a> · 
    <a href="https://notemeld.wiki/faq/">帮助文档</a> · 
    <a href="https://github.com/Hehejie1/NoteMeld/releases">下载</a>
  </p>
</div>

---

## ✨ 什么是 NoteMeld

**NoteMeld（源知库）** 是你的本地 AI 研究助手：把你看过的网页、视频、音频、文件和 AI 对话，整理成以后真正用得上的个人知识。

它不只是生成一篇摘要。NoteMeld 会将来源编译为结构化 Markdown 笔记，并进一步识别主题、概念、论点、证据和关系，形成一个**可追溯、可关联、持续生长的知识库**。当你再次遇到问题时，可以搜索、问答，或让 Codex、Cursor、Claude Code 等 AI 工具调用这些知识。

NoteMeld 的核心理念是：**AI 编译知识，人验证和消费。** 你负责标记值得保存的来源、校验重要结论和做最终决定；AI 负责整理、关联和在需要时找回上下文。

### NoteMeld 能帮你什么

- **统一摄入**：将网页、视频、音频、PDF、本地文件和 AI 对话放入同一个研究入口。
- **自动整理**：生成结构化 Markdown 笔记，保留来源、时间和处理过程。
- **知识关联**：从笔记中提取实体、概念、论点、证据和关系，发现不同资料之间的联系。
- **来源问答**：回答问题时回到相关笔记和证据，方便核验，而不是只给出无依据的生成文本。
- **AI 协同**：通过 MCP 将你的知识库接入 AI IDE，让 AI 在工作时理解你过去的研究上下文。
- **本地优先**：资料保存在自己的设备上，核心产物是可读取、可迁移的 Markdown 和本地数据。

### 它不是什么

NoteMeld 不是只会收藏链接的稍后阅读工具，也不是只针对单个文件问答的聊天机器人，更不是要求你手动维护文件夹、标签和双向链接的传统笔记软件。它的目标是让知识在导入后继续被整理、验证、关联和复用。

<p align="center">
  <img src="./docs/images/index.png" alt="NoteMeld 首页" width="100%" />
</p>

## 🚀 三步使用

| 步骤 | 说明 |
|---|---|
| **1. 标记来源** | 粘贴网页或视频链接，上传文件，或导入 AI 对话 |
| **2. AI 编译知识** | 自动下载、转写、整理为 Markdown，并抽取主题、概念、论点和证据 |
| **3. 验证与复用** | 在知识库中搜索、问答、查看来源，或通过 MCP 交给你的 AI 工具使用 |

<p align="center">
  <img src="./docs/images/note.png" alt="结构化笔记" width="45%" />
  <img src="./docs/images/wiki.png" alt="Wiki 知识图谱" width="45%" />
</p>

## 📦 快速安装

### 桌面端（推荐）

从 GitHub Releases 下载 macOS / Windows 安装包：

```bash
# macOS Apple Silicon
# macOS Intel
# Windows
```

👉 <a href="https://github.com/Hehejie1/NoteMeld/releases">前往下载页面</a>

### 一键脚本安装

```bash
# macOS / Linux
curl -fsSL https://notemeld.wiki/install.sh | bash
notemeld

# Windows PowerShell
irm https://notemeld.wiki/install.ps1 | iex
notemeld
```

### 源码启动

```bash
git clone https://github.com/Hehejie1/NoteMeld.git
cd NoteMeld
cp .env.example .env
# 可选：插件仓库默认查找 NoteMeld 同级目录的 notemeld-plugins；
# 若插件仓库在其他位置，在 .env 中设置 NOTEMELD_PLUGINS_DIR
bash run_notemeld.sh
```

访问：<http://127.0.0.1:3015>

官方插件源码和 Release 包位于独立的
[`notemeld-plugins`](../notemeld-plugins/) 仓库。NoteMeld 只负责插件安装、
权限、运行时和 Note 宿主适配，不在本仓库维护插件实现；生产环境应通过
GitHub/Gitee Release 安装并经过 manifest、版本和 hash 校验。

## 🔌 MCP 接入

将 NoteMeld 作为本地知识工具接入 AI IDE：

```bash
# 默认 MCP endpoint
http://127.0.0.1:8483/mcp
```

Claude Code 示例：

```bash
claude mcp add notemeld --transport http http://127.0.0.1:8483/mcp
```

> 详细配置请参阅 <a href="https://notemeld.wiki/faq/">帮助文档</a>

---

## ⚠️ 合规使用声明

本软件定位为**个人知识管理与学习辅助工具**，旨在帮助用户整理和沉淀自己在学习、研究过程中积累的信息资源。使用本软件前，请仔细阅读以下声明：

### 用途限定
- **仅限个人使用**：本软件仅供个人学习、研究和知识整理使用，**严禁**用于任何商业用途或大规模批量处理。
- **本地优先**：所有数据处理均在您的本地设备完成，软件不会将您的内容上传至任何第三方服务器。

### 用户合规义务
- **遵守法律法规**：您必须确保使用本软件的行为符合您所在地的法律法规，包括但不限于《著作权法》《网络安全法》等。
- **遵守平台条款**：在处理来自外部平台的内容时，您必须遵守相应平台的服务条款和使用协议。
- **尊重他人权益**：不得利用本软件侵犯他人的著作权、肖像权、隐私权等合法权益。

### 免责条款
- 本软件按「现状」提供，开发者不对软件的适用性、稳定性、合法性作出任何明示或暗示的保证。
- 用户使用本软件产生的一切后果，由用户自行承担。开发者不对用户的任何滥用行为承担责任。
- 如您因使用本软件产生任何法律纠纷，开发者不承担任何连带责任。

---

## 📚 更多信息

- 🌐 **官网**：<https://notemeld.wiki/>
- 📖 **帮助文档**：<https://notemeld.wiki/faq/>
- 🐙 **GitHub**：<https://github.com/Hehejie1/NoteMeld>
- 💬 **问题反馈**：<https://github.com/Hehejie1/NoteMeld/issues>

## 📜 License

MIT License。详见 [LICENSE](./LICENSE)。
