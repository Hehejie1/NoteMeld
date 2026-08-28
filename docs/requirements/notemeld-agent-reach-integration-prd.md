# NoteMeld x Agent Reach 集成 PRD：把多平台搜索与爬取变成个人知识库入口

更新时间：2026-06-10

## 1. 背景

NoteMeld 的定位是本地优先的个人知识库。它不是单次视频总结工具，而是把视频、网页、文件、AI 对话和用户自己的研究过程持续沉淀为笔记、Wiki、知识图谱和 MCP 能力的知识工作台。

个人知识库的核心链路不是“写一篇笔记”这么简单，而是：

```text
搜索发现 -> 平台爬取 -> 内容清洗 -> 转写/解析 -> 生成笔记 -> 入库 -> Wiki/向量检索/MCP 复用
```

NoteMeld 当前已经具备部分采集能力，包括 B 站、YouTube、抖音、网页链接、本地文件、音视频转写和网页/文档摄入等。但“搜索发现”和“更多平台接入”仍然不够系统：

- 用户需要先在外部平台搜索，再复制链接回 NoteMeld。
- 不同平台的搜索、登录、Cookie、代理、状态检测没有统一入口。
- MCP 客户端可以调用 NoteMeld 读写知识库，但还缺少“从外部平台发现资料并导入”的完整工具链。
- 部署监控目前能展示后端、FFmpeg、Whisper、MCP 等状态，但还不能展示采集连接器的可用性。

Agent Reach 的价值正好补在这个位置。它不是传统框架，而是一个 CLI Agent 联网脚手架，核心能力是把多平台工具选型、安装、配置和状态检测标准化。对 NoteMeld 来说，Agent Reach 最值得吸收的不是“外部 Agent 如何调用命令”，而是它的多平台连接器思想、doctor 状态检测、Cookie 配置流程和渠道分层。

## 2. Agent Reach 概述

Agent Reach 解决的是 CLI Agent 联网的装配问题。它不在 Agent 与上游平台之间增加运行时代理层，而是做三件事：

- `install`：安装上游工具、配置环境、注册 Agent 使用说明。
- `doctor`：检测每个渠道是否可用，并给出修复建议。
- `uninstall`：清理配置、skills 和 MCP 配置。

安装完成后，Agent 直接调用上游工具，例如：

- 网页读取：Jina Reader。
- YouTube/B 站：`yt-dlp`、`bili-cli`。
- GitHub：`gh CLI`。
- RSS：`feedparser`。
- Twitter/X：`twitter-cli` + Cookie。
- Reddit：`rdt-cli` 或代理/Cookie 方案。
- 小红书：`xhs-cli` 或 MCP 服务。
- 抖音：`douyin-mcp-server`。
- Exa 搜索：通过 MCP/mcporter 接入。

Agent Reach 的核心启发：

- 平台能力按 channel 拆分。
- 每个 channel 负责检查自身依赖、认证状态和可用性。
- 实际调用保持可替换，不把所有平台包进一个封闭框架。
- Cookie、代理、Token、安装状态都应该被诊断系统清晰展示。
- Agent 可以通过 SKILL.md 或 MCP 自动发现可用能力。

## 3. 集成目标

本 PRD 的目标是把 Agent Reach 的多平台搜索与爬取能力整合进 NoteMeld，成为 NoteMeld 的“采集连接器层”。

目标不是简单把 Agent Reach 当外部工具挂在旁边，而是把它的能力产品化到 NoteMeld 中：

- 用户可以在 NoteMeld 中直接搜索主题。
- NoteMeld 返回多个平台的搜索结果。
- 用户选择结果后，一键生成笔记、加入研究队列或沉淀到 Wiki。
- 部署监控展示各采集连接器状态。
- MCP 暴露搜索、导入、研究主题等工具，供 Claude Code、Cursor、Trae、OpenClaw 等调用。
- Agent Reach 可作为外部兼容增强，但 NoteMeld 要有自己的统一连接器接口。

## 4. 用户价值

### 4.1 对普通用户

用户不需要在多个平台之间切换：

```text
打开 NoteMeld -> 输入研究主题 -> 选择来源 -> 勾选结果 -> 生成笔记/Wiki
```

例如：

- 搜索“Agent Reach CLI Agent 联网”，自动从网页、GitHub、YouTube、B 站、V2EX、微博等来源发现资料。
- 勾选 5 条结果，自动生成 5 篇资料笔记。
- 再生成一篇综合研究报告。
- 所有内容自动进入 Wiki 和 MCP，可被后续 Agent 调用。

### 4.2 对重度知识工作者

NoteMeld 变成持续研究入口：

- 跟踪一个产品或技术主题。
- 定期搜索更新。
- 把结果沉淀为结构化笔记。
- 在 Wiki 中形成主题知识网络。
- 通过 MCP 把知识库接入日常编码和写作工具。

### 4.3 对外部 CLI Agent

外部 Agent 不只可以读取 NoteMeld 已有笔记，还可以调用 NoteMeld 去搜索和导入新资料：

```text
notemeld_search_sources(query="MCP RAG 个人知识库", platforms=["web", "github", "youtube"])
notemeld_import_source(url="https://...")
notemeld_research_topic(query="Agent Reach 架构分析", limit=10)
```

## 5. 产品范围

## 5.1 第一阶段：低风险搜索与导入

第一阶段优先集成稳定、低风控、适合个人知识库的来源：

- Web/Jina：网页读取和正文提取。
- Exa：全网语义搜索。
- GitHub：仓库、Issue、代码搜索。
- RSS：订阅源解析和条目导入。
- YouTube：视频搜索，结果复用现有 YouTube 下载器和转写能力。
- B 站：视频搜索，结果复用现有 Bilibili 下载器。
- 微博/V2EX：热榜、搜索、帖子/动态读取。

第一阶段的核心不是平台数量，而是打通统一链路：

```text
搜索结果 -> 选择 -> 导入任务 -> 生成笔记 -> 入库/Wiki
```

## 5.2 第二阶段：Cookie/登录平台

第二阶段接入需要登录、Cookie、代理或更高维护成本的平台：

- Twitter/X。
- 小红书。
- Reddit。
- 雪球。
- LinkedIn。
- 抖音增强能力。

这些平台要明确风险提示：

- Cookie 等同完整登录权限。
- 推荐使用专用小号。
- 不支持批量刷帖、批量评论、批量发推。
- 平台接口或反爬策略变化可能导致失效。

## 5.3 第三阶段：研究工作流

第三阶段做成完整研究工作流：

- 多平台并发搜索。
- 搜索结果去重和聚类。
- 批量导入。
- 自动生成主题研究报告。
- 自动更新 Wiki。
- 支持周期性主题追踪。
- MCP 一键触发研究任务。

## 6. 非目标

本集成不应该让 NoteMeld 变成不受控的爬虫平台。

明确不做：

- 不做大规模数据采集管线。
- 不做批量发帖、点赞、评论、刷互动。
- 不承诺 Cookie 平台的生产级稳定性。
- 不绕过平台付费墙、登录墙或访问限制。
- 不把所有上游工具强行封成一个不可替换 SDK。
- 不把用户 Cookie 上传到远端服务器。

## 7. 核心概念：采集连接器

建议在 NoteMeld 中新增 `Source Connector`，即“采集连接器”层。

连接器负责：

- 检测平台是否可用。
- 检测依赖工具是否安装。
- 检测 Cookie/Token/代理是否配置。
- 提供搜索能力。
- 提供详情抓取能力。
- 将搜索结果转换为 NoteMeld 可导入的来源。

连接器不负责：

- 生成最终笔记。
- 管理 Wiki。
- 管理向量索引。
- 替代现有下载器。

现有下载器继续负责拿到具体 URL 后的内容下载、字幕、转写和媒体处理。连接器负责“发现 URL 和元数据”。

## 8. 后端设计

建议新增目录：

```text
backend/app/connectors/
  base.py
  registry.py
  web.py
  exa.py
  github.py
  rss.py
  youtube.py
  bilibili.py
  douyin.py
  weibo.py
  v2ex.py
  twitter.py
  xiaohongshu.py
  reddit.py
  xueqiu.py
  linkedin.py
```

### 8.1 统一接口

```python
class ConnectorStatus:
    name: str
    label: str
    available: bool
    configured: bool
    requires_auth: bool
    message: str | None
    fix_hint: str | None


class SearchResult:
    id: str
    platform: str
    title: str
    url: str
    summary: str | None
    author: str | None
    published_at: str | None
    media_type: str | None
    raw: dict


class SourceConnector:
    name: str
    label: str

    def check(self) -> ConnectorStatus:
        ...

    def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        ...

    def fetch(self, url: str) -> SearchResult:
        ...
```

### 8.2 Registry

连接器注册中心统一管理可用平台：

```python
CONNECTORS = {
    "web": WebConnector(),
    "exa": ExaConnector(),
    "github": GithubConnector(),
    "rss": RssConnector(),
    "youtube": YoutubeConnector(),
    "bilibili": BilibiliConnector(),
}
```

优点：

- 部署监控可以直接读取状态。
- 搜索 API 可以按平台调度。
- MCP 工具可以复用同一套逻辑。
- 后续接 Agent Reach 外部配置时也有统一入口。

### 8.3 API

建议新增路由：

```text
GET  /api/connectors
POST /api/connectors/recheck
POST /api/connectors/search
POST /api/connectors/import
POST /api/connectors/{platform}/configure
```

示例：

```json
POST /api/connectors/search
{
  "query": "Agent Reach CLI Agent 联网",
  "platforms": ["web", "github", "youtube", "bilibili"],
  "limit": 10
}
```

返回：

```json
{
  "results": [
    {
      "id": "github:Panniantong/Agent-Reach",
      "platform": "github",
      "title": "Panniantong/Agent-Reach",
      "url": "https://github.com/Panniantong/Agent-Reach",
      "summary": "给 AI Agent 一键装上互联网能力",
      "author": "Panniantong",
      "published_at": null,
      "media_type": "repository"
    }
  ]
}
```

导入：

```json
POST /api/connectors/import
{
  "result": {
    "platform": "youtube",
    "url": "https://www.youtube.com/watch?v=..."
  },
  "style": "deep_research",
  "add_to_wiki": true
}
```

## 9. 前端设计

### 9.1 首页入口

首页输入框增加模式切换：

- 粘贴链接。
- 上传文件。
- 搜索资料。

搜索资料模式：

```text
输入主题：Agent Reach 是什么？
来源：全网 / GitHub / YouTube / B站 / RSS / 微博 / V2EX
按钮：搜索资料
```

### 9.2 搜索结果页

搜索结果列表展示：

- 平台图标。
- 标题。
- 摘要。
- 作者/来源。
- 发布时间。
- URL。
- 当前可导入状态。

操作：

- 生成笔记。
- 加入研究队列。
- 加入 Wiki。
- 忽略。
- 打开原链接。

### 9.3 连接器设置页

设置页新增“采集连接器”：

```text
Web/Jina       可用
Exa 搜索       未配置
GitHub         可用 / 未登录
YouTube        可用
B站            可用
Twitter/X      未配置 Cookie
小红书          未配置 Cookie
Reddit         未配置代理或登录
RSS            可用
```

每个连接器提供：

- 状态。
- 依赖工具。
- Cookie/Token/代理配置。
- 修复建议。
- 测试连接。

### 9.4 部署监控

部署监控新增“采集连接器”卡片：

```text
采集连接器
可用：8
需要配置：3
异常：1
按钮：查看详情 / 重新检测
```

## 10. MCP 设计

NoteMeld MCP 新增工具：

```text
notemeld_connector_status
notemeld_search_sources
notemeld_import_source
notemeld_research_topic
```

### 10.1 notemeld_search_sources

用于跨平台搜索资料。

```json
{
  "query": "Agent Reach CLI Agent 联网",
  "platforms": ["web", "github", "youtube"],
  "limit": 10
}
```

### 10.2 notemeld_import_source

把某个搜索结果导入为 NoteMeld 任务。

```json
{
  "url": "https://github.com/Panniantong/Agent-Reach",
  "platform": "github",
  "style": "deep_research"
}
```

### 10.3 notemeld_research_topic

高级工具：搜索多个来源，导入若干结果，并生成主题研究报告。

第一版可以只返回搜索结果和建议导入列表，不自动批量生成，避免任务不可控。

## 11. Agent Reach 兼容策略

NoteMeld 与 Agent Reach 的关系建议分三层：

### 11.1 原生连接器

NoteMeld 内置核心连接器，保证基础体验不依赖外部 Agent Reach：

- Web/Jina。
- Exa。
- GitHub。
- RSS。
- YouTube。
- Bilibili。
- 微博/V2EX。

### 11.2 Agent Reach 外部增强

如果检测到本机安装了 `agent-reach`，NoteMeld 可以：

- 读取 `agent-reach doctor` 状态。
- 展示 Agent Reach 已配置渠道。
- 对部分平台调用 Agent Reach 管理的上游工具。
- 复用 `~/.agent-reach/` 中的配置，但必须明确提示用户授权。

### 11.3 迁移实现

长期可以把 Agent Reach 的 channel 思路迁移为 NoteMeld 原生 connector：

- 统一配置存储。
- 统一部署监控。
- 统一 MCP 工具。
- 统一任务队列。
- 统一安全提示。

## 12. 安全与合规

### 12.1 Cookie 存储

Cookie/Token 必须本地存储，默认路径应位于桌面 App Data 目录，而不是仓库目录。

要求：

- 文件权限尽量限制为当前用户可读写。
- UI 明确提示 Cookie 风险。
- 日志不得输出 Cookie 原文。
- 导出诊断报告时自动脱敏。

### 12.2 风险提示

对 Twitter、小红书、Reddit、雪球、LinkedIn 等平台：

- 推荐使用专用小号。
- 不承诺稳定性。
- 不支持高频抓取。
- 不支持批量互动。
- 平台规则变化可能导致连接器失效。

### 12.3 代理

代理配置必须显式用户授权。

NoteMeld 不应自动购买、自动安装或自动修改系统代理。只允许：

- 用户手动填写代理。
- NoteMeld 为特定连接器传入代理环境变量。
- 部署监控展示代理是否配置。

## 13. 数据流

### 13.1 搜索导入单条资料

```text
用户输入主题
  -> /api/connectors/search
  -> connector.search()
  -> 返回 SearchResult
  -> 用户选择结果
  -> /api/connectors/import
  -> 转换为 NoteMeld note task
  -> 复用现有 NoteService / Downloader / Ingestion
  -> 生成 Markdown
  -> 入库
  -> Wiki/向量索引更新
```

### 13.2 MCP 研究主题

```text
外部 Agent 调用 notemeld_search_sources
  -> NoteMeld 返回跨平台结果
  -> Agent 选择结果
  -> 调用 notemeld_import_source
  -> NoteMeld 生成笔记
  -> Agent 调用 notemeld_search_wiki 做二次分析
```

## 14. 分阶段路线

### 阶段 1：连接器框架和稳定平台

目标：

- 建立 `connectors` 目录和统一接口。
- 支持 Web/Jina、GitHub、RSS、YouTube、Bilibili。
- 支持搜索结果导入为笔记任务。
- 部署监控展示连接器状态。
- MCP 暴露 `notemeld_search_sources`。

验收：

- 用户可以搜索 GitHub 仓库并导入为笔记。
- 用户可以搜索 YouTube/B 站视频并走现有视频笔记流程。
- 连接器状态在部署监控可见。

### 阶段 2：多平台扩展

目标：

- 接入 Exa、微博、V2EX、雪球。
- 增加连接器配置页。
- 支持 Cookie/Token/代理的本地配置和脱敏存储。
- MCP 暴露 `notemeld_import_source`。

验收：

- 用户可以在 NoteMeld 内跨平台搜索资料。
- 需要配置的平台会显示明确修复提示。
- Cookie 不出现在日志和错误信息里。

### 阶段 3：Agent Reach 兼容层

目标：

- 检测 `agent-reach` 是否安装。
- 读取 `agent-reach doctor` 状态。
- 支持调用 Agent Reach 管理的部分上游工具。
- 在设置页展示 Agent Reach 增强状态。

验收：

- 未安装 Agent Reach 时，NoteMeld 原生连接器正常工作。
- 已安装 Agent Reach 时，NoteMeld 可显示其渠道状态并复用增强能力。

### 阶段 4：研究工作流

目标：

- 支持主题研究队列。
- 支持多结果批量导入。
- 支持自动生成综合研究报告。
- 支持周期性跟踪主题。

验收：

- 用户输入主题后，可以从搜索、导入、笔记生成到研究报告形成闭环。
- Wiki 中自动形成主题相关的来源节点和概念节点。

## 15. 成功指标

产品指标：

- 用户从搜索到生成第一篇笔记的步骤不超过 3 步。
- 搜索结果导入成功率大于 80%。
- 连接器状态错误可解释率大于 90%。
- 用户无需离开 NoteMeld 即可完成资料发现和沉淀。

技术指标：

- 连接器失败不影响核心笔记功能。
- 单个连接器异常不影响其他连接器。
- Cookie/Token 日志泄露为 0。
- MCP 搜索工具返回结构化结果。
- 打包后的桌面端不依赖开发机路径。

## 16. 关键风险

### 16.1 上游工具不稳定

Agent Reach 依赖大量上游工具。平台接口变化会导致工具失效。

缓解：

- 每个平台独立 connector。
- doctor 明确错误原因。
- 失败时降级，不影响其他平台。

### 16.2 Cookie 安全

Cookie 等同登录态。

缓解：

- 本地存储。
- 日志脱敏。
- UI 风险提示。
- 推荐专用小号。

### 16.3 产品复杂度膨胀

平台过多会导致设置页、监控页和错误处理复杂。

缓解：

- 分阶段接入。
- 第一版只做稳定平台。
- 高风险平台放到高级配置中。

### 16.4 与 NoteMeld 核心定位偏离

如果过度强调爬取，NoteMeld 可能变成工具集合。

缓解：

- 所有连接器都必须服务于知识库沉淀。
- 核心操作永远是“导入为笔记 / 加入 Wiki / 供 MCP 检索”。
- 不做无知识沉淀意义的批量爬虫。

## 17. 结论

Agent Reach 与 NoteMeld 的结合是合理的，但集成方式应该是“能力吸收”，不是“外部工具堆叠”。

NoteMeld 应该把 Agent Reach 的多平台 channel、doctor、Cookie 配置和 MCP 思路转化为自己的采集连接器层，使搜索与爬取成为个人知识库的原生入口。

最终形态：

```text
Agent Reach 的连接器思想
  + NoteMeld 的任务系统
  + NoteMeld 的笔记生成
  + NoteMeld 的 Wiki/向量检索
  + NoteMeld 的 MCP
  = 面向个人知识库的多平台资料发现与沉淀系统
```

第一版建议从低风险平台开始，把统一连接器、搜索结果导入、部署监控和 MCP 工具打通。随后再逐步扩展到 Twitter、小红书、Reddit 等高价值但高风险平台。
