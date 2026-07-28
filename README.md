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
  <p>
    <a href="https://notemeld.wiki/">官网</a> · 
    <a href="https://notemeld.wiki/faq/">帮助文档</a> · 
    <a href="https://github.com/Hehejie1/NoteMeld/releases">下载</a>
  </p>
</div>

---

## ✨ 什么是 NoteMeld

**NoteMeld（源知库）** 是一款自托管的 AI 知识工作台，把你每天接触的网页、视频、文件和 AI 对话，沉淀为**可追溯、可复用、可持续增长的个人知识库**。

<p align="center">
  <img src="./docs/images/index.png" alt="NoteMeld 首页" width="100%" />
</p>

## 🚀 三步使用

| 步骤 | 说明 |
|---|---|
| **1. 采集** | 粘贴链接 / 上传文件 / 接入 AI 对话 |
| **2. 生成笔记** | AI 自动整理为结构化 Markdown |
| **3. 沉淀 Wiki** | 抽取实体与概念，构建个人知识图谱 |

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
bash run_notemeld.sh
```

访问：<http://127.0.0.1:3015>

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

## 📚 更多信息

- 🌐 **官网**：<https://notemeld.wiki/>
- 📖 **帮助文档**：<https://notemeld.wiki/faq/>
- 🐙 **GitHub**：<https://github.com/Hehejie1/NoteMeld>
- 💬 **问题反馈**：<https://github.com/Hehejie1/NoteMeld/issues>

## 📜 License

MIT License。详见 [LICENSE](./LICENSE)。
