# 招聘工作空间应用 与 Application Protocol v2

- 日期: 2026-08-30
- 作者 / Agent: Trae Agent
- 状态: 待评审
- 关联对话 / 任务: resume_bridge 能力承接评估（内嵌浏览器 / skill 编排 / 简历生成）
- 关联系统文档:
  - [current-architecture.md](file:///Users/hehejie/ai/notemeld-project/NoteMeld/docs/system/current-architecture.md)
  - [product-rules.md](file:///Users/hehejie/ai/notemeld-project/NoteMeld/docs/system/product-rules.md)
  - [data-model.md](file:///Users/hehejie/ai/notemeld-project/NoteMeld/docs/system/data-model.md)
  - [api-inventory.md](file:///Users/hehejie/ai/notemeld-project/NoteMeld/docs/system/api-inventory.md)
  - [known-pitfalls.md](file:///Users/hehejie/ai/notemeld-project/NoteMeld/docs/system/known-pitfalls.md)
  - [2026-08-27-notemeld-application-runtime-and-wiki-app.md](file:///Users/hehejie/ai/notemeld-project/NoteMeld/docs/requirements/2026-08-27-notemeld-application-runtime-and-wiki-app.md)

本文档分两部分：
- **Part A**：Application Protocol v1 的优化点清单（基于代码事实，提出 v2 需要补齐什么）。
- **Part B**：招聘工作空间应用的功能需求文档（只讲功能，不受现有实现限制）。

落地形态已确认：**在 NoteMeld 主仓做内置功能 + 扩 Agent 工具**，不通过 Application 协议的受限 runtime 承载。Part A 的价值在于把这次暴露出的协议缺口固化下来，供后续第三方应用复用。

---

# Part A：Application Protocol v1 优化点

## A1. 当前协议的实际能力边界（代码事实）

| 维度 | v1 实际状态 | 证据 |
|---|---|---|
| UI 形态 | `<iframe sandbox="allow-scripts">`，opaque origin，UI 无法自行 fetch 宿主 API | [ApplicationHost.tsx](file:///Users/hehejie/ai/notemeld-project/NoteMeld/frontend/src/app-host/ApplicationHost.tsx) |
| capability 白名单 | 声明 10 项，**实现 1 项**（`wiki.read` 的 `graph` / `article`），其余一律 501 `capability_unavailable` | [service.py](file:///Users/hehejie/ai/notemeld-project/NoteMeld/backend/app/applications/service.py) |
| permission | `permissions` 字段可声明 5 项，**执行层无任何判断代码** | 全仓库无 allow/deny 分支 |
| UI → 应用后端 | Bridge 只路由到 `invokeApplicationCapability`，`/runs/{run_id}/invoke` 前端零调用方 | ApplicationHost.tsx |
| process-jsonl runtime | `Popen([executable])` 无 argv / 无解释器前缀；`env` 只保留 `PATH`；`stderr=DEVNULL`；handshake 与每次 invoke 均 5 秒硬超时；严格串行单帧 | [runtime.py](file:///Users/hehejie/ai/notemeld-project/NoteMeld/backend/app/applications/runtime.py) |
| managed-worker runtime | 纯 stub，直接回显入参 | runtime.py |
| 进程生命周期 | `_processes` 内存 dict，宿主重启后所有 run 收敛 `interrupted` + `host_restarted` | runtime.py |
| 安装 | `validate_package` 已实现但**零调用方**，router 无 install / upload / upgrade endpoint | [manifest.py](file:///Users/hehejie/ai/notemeld-project/NoteMeld/backend/app/applications/manifest.py) |
| storage | 硬钉 `{"scope": "application-instance", "workspace": "default"}`，其他值 → `invalid_storage` | manifest.py |
| 网络 | `runtime.public_listener` / `runtime.listen` 出现即 `public_listener_denied` | manifest.py |
| 包体积 | `MAX_PACKAGE_BYTES` = 64MB | manifest.py |

结论：v1 的能力边界 = **静态 HTML/JS + iframe 沙箱 + postMessage + 只读 Wiki 数据**。任何"自带后端逻辑 + 有状态长任务 + 文件产出"的应用都无法在 v1 上运行。

## A2. 建议在 v2 补齐的协议能力

按优先级排序，每项给出问题、期望行为和验收口径。

### A2.1 capability 实现补齐（P0）

问题：`workspace.file.read` / `workspace.file.write` / `app.data.get|put|list` / `artifact.create|read` / `agent.run` / `plugin.invoke` 全部 501，应用无法读写自己的数据，也无法调用 Agent。

期望：
- `app.data.*` 落到 per-application-instance 的键值存储，key 命名空间隔离，单值上限与总配额可配置。
- `workspace.file.*` 落到显式声明的 workspace 子路径，禁止路径穿越，写入必须走 `workspace.write` permission。
- `artifact.create|read` 产出可被 Note / 导出链路引用的产物句柄，而不是裸文件路径。
- `agent.run` 以异步 run 形式返回 run_id + 事件流，不做同步阻塞。
- `plugin.invoke` 透传到插件宿主，沿用插件既有 PERMISSION_AUTHORITY 与 active pointer 语义。

验收：manifest 声明了某 capability 且 permission 满足时，调用不再返回 501；未声明时仍返回 403 `capability_denied`。

### A2.2 permission 执行层落地（P0）

问题：`workspace.read` / `workspace.write` / `network.egress` / `agent.run` / `plugin.invoke` 只在 manifest 校验时被识别，运行时不参与判断。当前唯一真实生效的判断是 `capability not in manifest.capabilities`。

期望：capability 调用前做 `capability → 所需 permission` 映射校验；`network.egress` 需能在 egress 出口处真实拦截（含域名白名单）。缺失时返回稳定错误码 `permission_denied` 并带上缺失项。

### A2.3 UI ↔ 应用后端通道打通（P0）

问题：应用即使有 process-jsonl 后端，UI 也无法调用它。

期望：Bridge 增加 `invokeRun(method, input)` 通道，映射到 `/runs/{run_id}/invoke`；前端 `missing_capabilities` 分支已存在，后端需在应用详情响应中真实返回该字段。

### A2.4 异步 Run 模型与进度事件（P1）

问题：每次 invoke 5 秒硬超时、单请求单响应、严格串行，无法承载"多轮搜索 + 抓取 + 生成"这类分钟级任务。

期望：
- invoke 支持 `mode: sync | async`；async 返回 job_id。
- 提供 job 状态查询与事件流（进度、阶段、部分结果）。
- 超时改为按 method 可配置，且有明确的取消语义。

### A2.5 可观测性：应用日志面（P1）

问题：`stderr=DEVNULL`，应用崩溃后开发者与用户都拿不到任何线索。

期望：捕获 stderr 到有大小上限的 ring buffer，提供只读日志查询接口；日志需按敏感键脱敏（复用插件侧 `SENSITIVE_INPUT_KEYS` 思路）。

### A2.6 受控运行环境（P1）

问题：`env` 只有 `PATH`，`Popen` 只传可执行文件、无 argv，导致依赖解释器或环境变量的后端无法启动。

期望：manifest 可声明 `runtime.command`（含 argv）与 `runtime.env`（白名单键，值可来自宿主注入的受控变量，禁止直接注入用户密钥）。

### A2.7 安装 / 升级 / 回滚（P1）

问题：`validate_package` 未接线，没有安装 API，没有多版本与 active pointer，没有回滚。

期望：对齐插件仓库既有语义——manifest + hash + 版本校验、install/upgrade/rollback、active pointer 切换、失败不影响当前活跃版本。

### A2.8 进程持久化与恢复（P2）

问题：`_processes` 为内存态，宿主重启即全量 `interrupted`。

期望：run 元信息持久化；重启后可恢复或明确标记为需重跑，并给出用户可见原因。

### A2.9 storage / 包体积可扩展（P2）

期望：`storage.scope` 支持 `application-instance` 之外的取值（如 `application-shared`）；包体积上限可配置，超限给出可操作提示而非直接拒绝。

### A2.10 打包资源路径不一致（P2，既有缺陷）

问题：[tauri.macos.conf.json](file:///Users/hehejie/ai/notemeld-project/NoteMeld/desktop/src-tauri/tauri.macos.conf.json) 的资源指向 `"../../applications"`，而 [tauri.conf.json](file:///Users/hehejie/ai/notemeld-project/NoteMeld/desktop/src-tauri/tauri.conf.json) 指向 `"../../../notemeld-applications/apps"`，macOS 打包可能缺失应用包。

期望：两处统一到同一来源，并在打包测试中断言应用包存在。

## A3. 本次需求为何不走 Application v1

招聘工作空间需要：内嵌真实浏览器 webview（宿主进程级能力）、长时多轮 Agent 编排、本地文件产出、PDF 导出。这四项都超出 v1 的沙箱与同步单帧模型。因此选择在 NoteMeld 主仓内置实现，同时把 A2 作为 v2 的独立演进项。

---

# Part B：招聘工作空间应用 功能需求

## 1. 原始需求

> 目前的 notemeld 有插件打开浏览器的，这里招聘软件可以使用插件打开页面进行操作，就像 chatgpt 的浏览器功能一样的，在软件里面集成浏览器。
>
> `/Users/hehejie/ai/notemeld-project/resume_bridge/.agents/skills` 这里面有一些 skill，看一下 notemeld 能不能支持。
>
> 这个简历生成主要还是先生成 md，然后套用 html 模版进行生成的，这个我理解都是代码在应用里面实现就行了。

## 2. 背景和问题

用户当前的求职工作流分散在 ResumeBridge：有头浏览器采集招聘站数据 → 一套 skill 做公司/岗位情报 → 脚本生成定制简历。三块能力各自独立，产出物散落在文件系统，没有沉淀与检索。

NoteMeld 的现状是互补的：
- Note authority + Wiki 投影 + 检索链路成熟（约 95% 可直接承接情报沉淀），而 ResumeBridge 完全没有。
- 但 NoteMeld 缺：应用内嵌浏览器、skill 机制、`web:search` / `web:fetch` / 文件写 工具、模板渲染与 PDF 导出。

核心矛盾：ResumeBridge 最不可替代的能力（有头浏览器 + 登录态采集）恰是 NoteMeld 最缺的。

## 3. 目标结果

1. NoteMeld 桌面端内可打开真实浏览器 tab，用户手动登录招聘网站后登录态被持久保留，Agent 能读取当前页面渲染后的内容。
2. NoteMeld 支持以 Markdown 提示词形式定义 skill，并能被 Agent 按 description 路由调用、支持 skill 嵌套编排。
3. Agent 具备联网搜索、抓取网页正文、写入工作区文件的工具能力。
4. 简历可先生成结构化 Markdown，再套 HTML 模板渲染，导出 A4 PDF。
5. 全流程产出物（公司情报、岗位分析、简历）落为 Note，自动进入 Wiki 与检索。

## 4. 非目标

- 不做自动投递、自动打招呼、模拟点击式批量操作。浏览器内的账号相关操作由用户手动完成。
- 不复刻 ResumeBridge 的 Playwright 多 profile 体系。
- 不迁移 ResumeBridge 的 19 张表与既有数据（本轮只做功能，不做数据迁移）。
- 不在本轮实现 Application Protocol v2（Part A 独立演进）。

## 5. 当前系统事实

- 桌面底座：Tauri 2.11.2 + wry 0.55.1，macOS 走 WKWebView、Windows 走 WebView2，两者均原生支持加载远程 URL 并持久化 Cookie。
- [Cargo.toml](file:///Users/hehejie/ai/notemeld-project/NoteMeld/desktop/src-tauri/Cargo.toml) 中 `tauri = { features = [] }`，缺 `unstable`，`WebviewBuilder` / `add_child` 不可用——这是做 tab 式浏览器的直接阻塞项。
- [capabilities/default.json](file:///Users/hehejie/ai/notemeld-project/NoteMeld/desktop/src-tauri/capabilities/default.json) 的 `core:webview:default` 不含 `allow-create-webview`，`core:window:default` 不含 `allow-create`。
- [lib.rs](file:///Users/hehejie/ai/notemeld-project/NoteMeld/desktop/src-tauri/src/lib.rs) 只注册 6 个 command；`open_external_url` 是丢给系统浏览器（macOS `open`），不是内嵌。
- **安全前置问题**：`on_page_load` 对**任意** webview 无条件 `eval(runtime_bootstrap)`，而该脚本含 session_token。加入外部站点 webview 前必须按 window/webview label 过滤。
- Agent 工具：[capabilities.py](file:///Users/hehejie/ai/notemeld-project/NoteMeld/backend/app/agent_host/capabilities.py) 的 `_DESCRIPTORS` 共 12 项，默认仅暴露 `wiki:search` / `note:search` / `note:read`。grep `web:search|web:fetch|browser:|research:` 零匹配。
- 现有联网能力：[research_search.py](file:///Users/hehejie/ai/notemeld-project/NoteMeld/backend/app/services/research_search.py) 4 个 provider（arxiv / GitHub / SearXNG / Tavily），单轮、不抓正文、limit ≤ 20；[research_search_config.py](file:///Users/hehejie/ai/notemeld-project/NoteMeld/backend/app/services/research_search_config.py) 的 `get_learning_scopes()` 里 `del requested_scopes` 强制 academic+github。
- 抓取基础：[web_source_layer.py](file:///Users/hehejie/ai/notemeld-project/NoteMeld/backend/app/services/web_source_layer.py) 的 `extract_page_context()` 是全仓库唯一 BeautifulSoup 使用点，可作为 `web:fetch` 的起点；[web_note.py](file:///Users/hehejie/ai/notemeld-project/NoteMeld/backend/app/services/web_note.py) 的 `fetch_html` 是 httpx 静态 GET，动态页会退化为 `DYNAMIC_WEB_PAGE_MESSAGE`。
- 简历领域知识已部分内置：[note_style_file_extractors.py](file:///Users/hehejie/ai/notemeld-project/NoteMeld/backend/app/services/note_style_file_extractors.py) 有 `RESUME_SECTION_HEADINGS`、`_looks_like_resume()`，`_select_renderer_profile` 会返回 `resume_professional`，但该值全仓库仅出现一次，无对应渲染分支。
- 导出：`weasyprint==65.1`、`markdown_pdf==1.7` 已在 [requirements-export.txt](file:///Users/hehejie/ai/notemeld-project/NoteMeld/packaging/backend/requirements-export.txt) 打包，代码零 import；[export.py](file:///Users/hehejie/ai/notemeld-project/NoteMeld/backend/app/utils/export.py) 是死代码（`_to_html` 等未定义、零调用）。
- `HTML_OUTPUT_START` 双格式标记只在 `note_output_normalizer.py` 出现，前端无解析方，属死产物。
- **注意**：`docs/system/current-architecture.md` 中描述的 `capability_discover / capability_describe / capability_invoke` 三元工具与 Skill 机制**代码已删除**，是过时文档，不可作为依据。
- 插件侧 [official_browser.py](file:///Users/hehejie/ai/notemeld-project/notemeld-plugins/plugins/official-browser/src/official_browser.py) 是 125 行零实现契约壳，且 `SENSITIVE_INPUT_KEYS` 封死 `cookie` / `profile` / `script`，与招聘站登录态需求根本冲突——不能作为本需求的载体。

## 6. 用户故事

1. 作为求职者，我在 NoteMeld 里打开一个浏览器 tab 访问招聘网站，手动扫码登录一次，之后重启软件仍保持登录。
2. 作为求职者，我在某个岗位详情页对 Agent 说"分析这个岗位"，Agent 直接读取当前页面内容，不需要我复制粘贴。
3. 作为求职者，我说"调研某公司"，Agent 自动执行公司情报 skill：多轮搜索、抓取正文、按来源优先级取证，产出带来源溯源的情报报告 Note。
4. 作为求职者，我说"给这家公司生成简历"，Agent 读取我的项目事实源与该公司情报，先产出定制 Markdown 简历，再渲染成 A4 PDF。
5. 作为求职者，我在 Wiki 里能看到公司、岗位、简历版本之间的关联，并能检索历史调研结论。
6. 作为求职者，Agent 要执行敏感动作（读取登录态页面、写入文件、访问外部域名）时，我能看到并批准。

## 7. 验收标准

### 7.1 内嵌浏览器

- GIVEN 桌面端已启动，WHEN 用户从工作区新建浏览器 tab 并输入 `https://www.zhipin.com`，THEN 页面在应用内正常渲染，具备前进/后退/刷新/地址栏。
- GIVEN 用户已在该 tab 内完成登录，WHEN 关闭并重启 NoteMeld，THEN 再次打开同站点仍为登录态（Cookie 持久化生效）。
- GIVEN 浏览器 tab 加载的是外部站点，WHEN `on_page_load` 触发，THEN 宿主**不得**向该 webview 注入含 session_token 的 bootstrap 脚本；注入仅对 `main` label 生效。
- GIVEN Agent 请求读取当前 tab 的页面内容，WHEN 用户未批准，THEN 读取被拒绝且给出稳定错误码；WHEN 用户批准，THEN 返回渲染后的正文文本 + 标题 + URL。
- GIVEN 浏览器 tab 中存在跨站 iframe / 弹窗，WHEN 站点尝试打开新窗口，THEN 新窗口在应用内以新 tab 承载，不外泄到系统浏览器。

### 7.2 Skill 机制

- GIVEN 一个 skill 以目录形式提供（`SKILL.md` + 可选 `references/` / `templates/`），WHEN 宿主加载，THEN frontmatter 的 `name` / `description` 被索引，正文作为提示词注入。
- GIVEN 用户输入与某 skill 的 `description` 语义匹配，WHEN Agent 规划，THEN 该 skill 被选中并按其正文流程执行。
- GIVEN 一个 orchestration skill 声明要串行调用 4 个子 skill，WHEN 执行，THEN 子 skill 依次执行且各自的 JSON 输出被逐级 merge 到最终结果。
- GIVEN skill 正文要求写入指定路径的文件，WHEN 执行，THEN 文件被写到工作区内的允许目录，且路径穿越被拒绝。
- GIVEN skill 执行超过默认 turn 上限（Agent SDK `max_turns=16`），WHEN 达到上限，THEN 返回明确的"因轮次上限中止"原因，而不是静默截断。

### 7.3 Agent 工具扩展

- GIVEN Agent 需要联网搜索，WHEN 调用 `web:search`，THEN 支持指定 scope（不被 `del requested_scopes` 强制覆盖）、支持多轮、返回结构化结果（标题 / URL / 摘要 / 来源类型）。
- GIVEN Agent 需要读正文，WHEN 调用 `web:fetch`，THEN 返回抽取后的正文；静态抓取失败时可回退到"由内嵌浏览器渲染后取 DOM"。
- GIVEN Agent 产出报告，WHEN 调用文件写工具，THEN 只能写入声明的工作区目录，且每次写入在事件流中可见。
- GIVEN 生成的报告引用了外部链接，WHEN 校验产出，THEN 所有链接必须来自本次检索命中的 URL 集合（复用 `research_note_compiler.py` 的 `markdown_urls.issubset(allowed_urls)` 防幻觉范式）。

### 7.4 简历生成与导出

- GIVEN 存在项目事实源与目标公司情报，WHEN 用户请求生成简历，THEN 先产出结构化 Markdown，章节符合 `RESUME_SECTION_HEADINGS` 约定。
- GIVEN 已有简历 Markdown，WHEN 选择一个 HTML 模板渲染，THEN 通过**数据绑定**渲染（而非仅靠 prompt 提示结构），同一份数据换模板不改变事实内容。
- GIVEN 渲染完成，WHEN 导出 PDF，THEN 输出 A4 单页/多页可控、打印 CSS 正确、中文字体不缺字。
- GIVEN 简历生成使用了禁用词黑名单与零容忍规则，WHEN 产出包含违规表述，THEN 生成被拦截并指出具体条目。

### 7.5 沉淀与检索

- GIVEN 情报报告与简历生成完成，WHEN 落库，THEN 以 Note 为唯一真相源，Wiki 作为异步投影（latest-wins 去抖）。
- GIVEN 同一公司被多次调研，WHEN 再次调研，THEN 能检索到历史结论并在报告中标注差异，而不是无脑覆盖。

## 8. 输入输出样例

### 8.1 读取当前浏览器 tab

输入（Agent 工具调用）:

```json
{ "tool": "browser:read_page", "input": { "tab_id": "tab-3", "mode": "text" } }
```

输出:

```json
{
  "url": "https://www.zhipin.com/job_detail/xxxx.html",
  "title": "前端开发工程师-上海-某公司",
  "text": "岗位职责 ... 任职要求 ...",
  "extracted_at": "2026-08-30T10:12:00+08:00"
}
```

### 8.2 公司情报 skill 输出（顶层结构）

```json
{
  "company_intro_card": { "name": "...", "stage": "...", "track": "..." },
  "source_trace": [
    { "claim": "...", "url": "https://...", "source_tier": 2, "fetched_at": "..." }
  ]
}
```

### 8.3 编排 skill 最终输出（4 个顶层 key）

```json
{
  "company_intro_card": {},
  "job_opportunity_card": {},
  "interview_attack_card": {},
  "source_trace": []
}
```

### 8.4 简历渲染请求

```json
{
  "resume_markdown_note_id": "note_123",
  "template_id": "classic_boss",
  "export": { "format": "pdf", "page": "A4" }
}
```

## 9. 约束

- 浏览器 tab 内的账号操作必须由用户手动完成；不得代替用户提交表单或投递。
- HttpOnly Cookie 不得暴露给前端 JS 或 Agent；需要携带登录态的请求只能在宿主侧完成。
- 任何日志、fixture、文档、回复中不得出现 Cookie、session token、API key 或用户绝对本地路径。
- 外部域名访问需可白名单化并可审计。
- Note 是唯一真相源，Wiki 只做投影，不得反向写回。
- Agent SDK 保持 Rust canonical runtime 单一来源，不在宿主侧复制第二套 Agent loop。
- 稳定错误码契约不得随意新增无文档的错误字符串。

## 10. 边界场景

- 站点反爬 / 风控：页面出现验证码时，Agent 停止自动读取并提示用户在 tab 内手动处理。
- 登录态失效：读取到登录墙页面时，返回明确的 `login_required` 而不是把登录页当正文抓走。
- 同一站点多账号：需要 profile 隔离时，tab 需可绑定独立存储分区。
- 动态渲染：`web:fetch` 静态抓取拿不到正文时的回退路径与用户可见提示。
- 搜索 provider 全部不可用 / 配额耗尽：skill 应降级为"仅基于已有 Note 生成"并标注证据不足。
- 长任务被打断（宿主重启 / 用户取消）：已产出的中间物是否保留，需给出确定语义。
- PDF 中文字体在打包环境缺失：需在导出前做字体可用性检查。
- 同名公司 / 同名岗位：Wiki 实体消歧策略。

## 11. 开放问题

1. 内嵌浏览器是走 Tauri 多 webview（需开 `unstable` feature + 扩 ACL），还是走独立 WebviewWindow？前者能做 tab，后者改动更小但体验不同。
2. `browser:read_page` 的审批粒度：每次读取都审批，还是按域名一次性授权？
3. skill 存放位置：随产品打包、放用户工作区、还是走插件/应用安装体系？升级与用户自定义如何共存。
4. skill 与 Agent SDK 的关系：skill 是宿主侧提示词编排，还是应下沉为 SDK 的一等概念？
5. `max_turns=16` 是否需要针对 orchestration skill 提升，以及如何避免失控成本。
6. 简历模板引擎选型（数据绑定方式）与模板的用户自定义边界。
7. 简历事实源形态：沿用 ResumeBridge 的固定路径 `PROJECT.md`，还是抽象为 NoteMeld 内的"个人事实源 Note"？
8. 是否需要 ResumeBridge 历史数据的一次性导入。

## 12. 与系统事实的冲突检查

| 需求点 | 冲突/依赖 | 说明 |
|---|---|---|
| 内嵌浏览器 tab | `tauri features = []` 缺 `unstable`；ACL 缺 `allow-create-webview` | 需先改 Cargo.toml 与 capabilities/default.json |
| 内嵌浏览器安全 | `on_page_load` 无条件注入 session_token | **必须先修**，否则外部站点可读取宿主凭证 |
| 用插件承载浏览器 | `official-browser` 的 `SENSITIVE_INPUT_KEYS` 封死 cookie/profile/script | 该插件不适合承载本需求 |
| `web:search` 多 scope | `get_learning_scopes()` 中 `del requested_scopes` 强制 academic+github | 需解除强制覆盖 |
| skill 机制 | `current-architecture.md` 描述的 Skill / capability 三元工具**代码已删** | 文档过时，不可作为实现依据 |
| 模板渲染 | 现状是 prompt 级结构提示，不是数据绑定渲染 | 范式需切换 |
| PDF 导出 | `weasyprint` / `markdown_pdf` 已打包但零 import；`export.py` 为死代码 | 需新建可用导出链路，勿复用死代码 |
| `resume_professional` | 该 renderer profile 值仅出现一次，无渲染分支 | 需补齐分支或重新定义 |
| `HTML_OUTPUT_START` | 前端无解析方 | 勿在新链路上依赖该标记 |
| Application v1 承载 | 沙箱 + 5 秒同步单帧 + capability 全 501 | 已确认不走 v1，改主仓内置 |

## 13. Superpowers 交接

建议按以下顺序拆分为可独立验证的改动：

1. **安全修复（前置，必须最先做）**：`on_page_load` 按 webview label 过滤 bootstrap 注入。可用桌面端单测/手工验证覆盖。
2. **桌面内嵌浏览器最小可用**：开 `unstable` feature、扩 ACL、新增 tab 管理 command、Cookie 持久化验证。
3. **`browser:read_page` 工具 + 审批链路**：接入 `agent_host/capabilities.py` 的 `_DESCRIPTORS`，走既有 approval。
4. **`web:search` / `web:fetch` 工具**：复用 `research_search.py` 与 `web_source_layer.extract_page_context()`，解除 scope 强制覆盖，补正文抓取与防幻觉校验。
5. **文件写工具 + 工作区路径约束**。
6. **skill 加载与路由机制**：目录扫描、frontmatter 索引、提示词注入、嵌套调用与 JSON merge。
7. **简历 Markdown 生成 + 模板数据绑定渲染 + PDF 导出 API**。
8. **Note / Wiki 沉淀与实体消歧**。
9. **Application Protocol v2（Part A）**：独立演进，按 A2 的 P0 → P2 顺序推进。
