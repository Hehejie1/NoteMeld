# 主动学习空间（本地知识、互联网研究、学习画布与掌握验证）

日期：2026-08-01（2026-08-12 增量更新）
作者 / Agent：doc-driven 流程
状态：Planned（核心纵向闭环已实现；完整验收仍在推进）
关联对话 / 任务：Pi 框架分析 → 分层架构确认 → P4-P5 深入学习 → 主动学习闭环确认
关联系统文档：`docs/system/current-architecture.md`、`docs/system/data-model.md`、`docs/system/product-rules.md`、`docs/system/known-pitfalls.md`、[P2-P3 notemeld-agent](2026-08-01-notemeld-agent-research-assistant.md)
验证证据：[`docs/superpowers/tests/2026-08-11-notemeld-active-learning-space.md`](../superpowers/tests/2026-08-11-notemeld-active-learning-space.md)

## 1. 原始需求

> "深入学习我的定义是用户抛出一个观点，通过 wiki 知识检索和 web 搜索相关知识，整理成知识看板（除了知识报告，还有知识重点【根据用户记忆情况推荐用户优先观看的重点】），然后用户可以基于相关节点内容继续提问深入核心。所以这两个都需要，而且体验更高一些。"
>
> 画布："一图胜万物，很多东西使用图形结构可以快速了解之间的关系。"
>  - P4：先做只读点击 + 节点简单文字（label/摘要）修改；后续再扩展全功能手动编辑 + AI 对话式编辑
>
> 搜索：search_web 做抽象层，默认支持 Tavily 和 SearXNG（自托管），其余后面补。
>
> 2026-08-11 增量确认：NoteMeld 当前不能只做收集和 Search；用户希望 Search 对话能够生成学习白板，告诉自己需要学习什么，并通过后续互动真正掌握内容。方案选择为“持续演化的学习空间”，V1 以单 Agent 的阶段化角色实现，多 Agent 学习组织作为后续演进。
>
> 知识来源必须结合：(1) NoteMeld 已收集内容；(2) 互联网搜索、采集和编译；(3) 学术内容和 GitHub 项目作为重点搜索类型。
>
> 2026-08-12 交互确认：学术论文与 GitHub 项目不是用户需要开关的高级设置，而是学习模式的默认研究来源；普通网页只有在用户配置 Tavily 或 SearXNG 后才加入。首页输入区在“聊天 / 笔记”旁增加“学习”，用户选择后提交主题即自动创建学习空间。对话区返回学习总结与下一步引导，完整学习画布固定展示在右侧面板。

## 2. 背景和问题

- **当前用户是谁**：想快速、深入学习某个研究方向/观点的个人用户
- **当前场景是什么**：用户在会话输入框写 "帮我梳理一下 3D Gaussian Splatting 对比 NeRF 的最新进展" 或 "我觉得 RAG 的未来不在 chunk-size 调优而在知识结构" 这类观点/方向
- **当前痛点是什么**：
  1. 现有 Wiki 只给结果（实体/概念/图谱），不提供从"用户观点/方向"到"结构化研究看板"的综合流程；用户要自己翻多个 source/entity/concept 页面拼
  2. 没有 Web 搜索能力，本地知识缺的时候必须跳出 NoteMeld 去 Google/ArXiv，搜到的视频/文章又得手动丢回首页表单编译
  3. 没有"知识重点"的优先级排序，所有概念平级展示；用户看了 1 个小时不知道哪些对自己最重要（和他自己的已掌握程度不匹配）
  4. 图谱（graph.json）当前只在独立 Wiki 页面看，和对话流是两张皮；对话里讨论到的关系图要切页去看，不能嵌在对话里直接点击深入
  5. "学习路径"完全靠用户自己规划；Agent 不主动说"先看 A 再看 B，因为 C 依赖 A 和 B"
  6. 现有 mastery 只是可被 Agent 写入的分值，没有诊断题、主动回忆、应用任务和延迟复测作为证据；系统会把“讲过”误当成“学会”
  7. 通用网页搜索无法表达论文与 GitHub 项目的专有元数据、版本和权威来源，难以支持学术研究与工程学习
- **为什么现在要做**：System A（知识编译）+ P2-P3 Agent 基础设施都齐了后，这是 NoteMeld 区别于普通 Q&A + RAG 的核心差异化能力（"AI 研究助手"的"研究"二字落地）；现在不做就停留在"笔记生成器 + 聊天"层面

## 3. 目标结果

- **目标 1（多源研究抽象层）**：在现有 `WebSearchProvider` 雏形上形成统一研究接口，V1 包含通用 Web（Tavily / SearXNG）、学术（arXiv；Crossref/Semantic Scholar 作为后续 adapter）和 GitHub（官方 Search API）三类来源；统一输出 `ResearchSource {source_type,title,url,snippet,published_at?,authors?,repository?,stars?,license?,version?,provider}`。搜索失败时按来源独立降级，不因一个 provider 失败丢掉本地结果。学术与 GitHub 永远作为学习模式默认来源，不提供关闭开关；Settings 只配置可选的普通网页 provider、超时和本机凭证，凭证不回显。
- **目标 2（持续演化的学习画布）**：统一数据结构 `LearningCanvas {goal,nodes,edges,clusters,path,sessions,review_queue}`。节点除 Wiki 图谱信息外，包含 `priority/mastery/mastery_evidence/sources/summary/prerequisites/status/next_review_at`；持久化到会话工作空间 `canvases/{canvas_id}.json`。对话流中渲染富媒体学习空间，可展开全屏。P4 阶段：
  - 画布节点**只读点击**：点击 → 前端发 user_message "深入讲一下 node.label 这个 {type}，重点结合 sources 里的内容"
  - 画布节点**简单文字修改**：双击 label 改名字 / 修改 summary 文本；保存后写入画布 JSON
  - 不做：节点拖拽布局、新增节点/连线、删除（留到 P5）
- **目标 3（主动学习长任务 = build_learning_canvas Skill）**：流程 8 步：
  1. **本地检索**：search_knowledge（Wiki + 笔记）拿本地 contribution + entity/concept
  2. **初始诊断**：用 3-7 个开放题或应用题采集用户已有认知；未作答时不得推断为已掌握
  3. **缺口判断 + 搜索询问**：按“本地已有 / 证据不足 / 完全缺失”分类，询问用户是否补充通用 Web、论文、GitHub 项目及时间范围
  4. **外部搜索 + 自主编译（先确认采集）**：搜索结果先以候选来源展示；只有用户确认的来源才进入现有 NoteMeld 采集与编译链路。长任务期间可取消单个或全部编译
  5. **综合生成**：生成知识报告、重点列表、学习画布和依赖排序后的学习路径；每个节点必须可追溯到本地 contribution 或外部来源
  6. **学习单元**：按路径逐个执行“短讲解 → 不看资料主动回忆 → 反馈 → 应用/迁移任务”，而不是一次性输出长报告
  7. **证据化评估**：根据 recall/explain/apply/transfer 四类证据更新 mastery；LLM 自评、阅读时长和“已经展示过”不能单独提高 mastery
  8. **间隔复习**：将未稳定掌握节点放入 review_queue；延迟复测通过后才标为 mastered，并把结果写回 research_space
- **目标 4（前端体验）**：首页输入区提供“聊天 / 笔记 / 学习”三种提交意图。学习模式提交后，对话区显示精简总结、来源状态、建议先学内容和继续提问引导；右侧学习面板展示目标与诊断 / 重点 / 画布 / 学习路径 / 当前学习单元 / 待复习。若同一会话同时存在笔记与学习空间，右侧提供“学习 / 笔记”切换并默认打开最新学习空间。所有产物落入工作空间，可从会话侧栏再次打开。
- **目标 5（Agent 边界）**：V1 使用一个 Agent 的研究员、课程设计师、导师、考官四个阶段，不引入多 Agent 调度；数据结构和任务边界为后续拆成多 Agent 保留稳定接口。

## 4. 非目标

- 不做：画布节点拖拽布局 / 手写新增节点与连线 / 自由编辑（P5 再做，P4 只做只读点击 + label/summary 简单改文字）
- 不做：引入更多 Web 搜索 provider（Brave / Bing / SerpAPI 等，先抽象 + Tavily/SearXNG 默认）
- 不做：浏览器原生搜索（crawl 整站、JS 渲染抓取），只做搜索 API 返回的 snippet + URL，内容抓取复用现有 WebNoteGenerator 的降级能力
- 不做：多人协作看板、实时共享、评论回复
- 不做：移动端画布渲染适配（先桌面浏览器 + Tauri WebView）
- 不做：AI 主动定期更新某研究空间的知识看板（主动推荐）；本期只响应用户显式触发
- 不做：V1 引入研究员/导师/考官等多个独立 Agent、Agent 间消息总线、权限和组织管理；这些属于方案 3 的后续演进
- 不做：把阅读完成、停留时长或 Agent 已讲解直接视为 mastered
- 不做：未经用户确认就批量采集外部网页、论文附件或 GitHub 仓库
- 不做：为 V1 新增 `conversation.mode=learning`、SQLite 字段或迁移；“学习”是显式提交意图，持久会话仍使用兼容的 `chat` mode
- 不做：点击“学习”标签后在空输入状态立即发起请求；只有用户提交主题时才开始研究

## 5. 当前系统事实

- 已有类似能力：
  - Wiki graph.json：已存 `{nodes, edges, clusters}`（位于 `note_results/wiki/graph.json`）；字段为基础图谱字段
  - Wiki 单篇 contribution：已存 entity/concept/claim/evidence/relation/source/summary/topics（`note_results/wiki/contributions/*.json`）
  - 向量检索：`VectorStoreManager.query(task_id, q, n_results=6)`（单任务）；跨任务/Wiki 检索靠独立实现（search_knowledge 工具本期封装）
  - WebNoteGenerator：已有网页抓取 + Markdown 化能力（可复用做搜索结果 landing）
  - NoteGenerator：已有视频编译能力（compile_source 工具复用 P2 已封装）
  - P3 Agent runtime：已有 workspace、memory、skill_loader、long_task、task_card SSE、Research Space 与 `masteries/open_questions/outputs`
  - 工作空间已预留 `canvases/`，前端已有 Markmap 和 Wiki 图谱渲染依赖，但没有 Learning Canvas 消息类型与学习状态机
  - `backend/app/services/web_search.py` 已有 provider protocol 和结果归一化雏形，但 `get_web_search_provider()` 除 disabled 外尚未提供真实 provider
- 当前入口 / 页面 / API：Wiki 页（图谱可视化）、Workspace 会话页；没有学习空间入口、学术/GitHub 搜索设置或学习会话 API
- 当前数据来源和写入位置：note_results/wiki/*（Wiki 产物）；note_results/{task_id}_markdown.md + .json（笔记）；chroma/（向量）；research_spaces/*.json（P3 新增的研究空间记忆）；工作空间 canvases/（本需求新增）
- 当前限制：
  - graph.json 的 node 只有基础字段（id/label/type），没有 mastery/priority/sources/summary/position
  - 没有 Settings 里的 Web Search Provider 配置区
  - search_knowledge（跨 Wiki + 笔记综合检索）在 chat_service 里是散落的私有函数，不是公共工具
- 相关 known pitfalls：
  - Wiki rebuild latest-wins：知识看板生成是长任务，看板内部的"编译子任务取消"语义必须继承 latest-wins（新的确认覆盖旧的编译意图）
  - 慢 LLM 请求进全局锁：build_knowledge_canvas 综合步骤（多次 LLM 调用）不得持有 Wiki 全局写锁；画布写自己的工作空间目录
  - 状态不同步：看板产物要落 conversation_messages 一条 `knowledge_board` 消息，刷新页面不丢
  - 工作空间写入当前使用固定 `.tmp` 文件；学习画布存在多轮更新，实施时必须改为唯一临时文件或串行写，避免并发冲突

## 6. 用户故事

- 作为想快速入门一个方向的用户，我在会话输入 "梳理一下小语言模型推理加速的核心脉络"，WHEN Agent 跑完 build_knowledge_canvas 后，我看到一个富媒体卡片消息：
  - 报告：800 字概览 + 5 条关键 claim + 每条 evidence 回源
  - 知识重点：Top 10 节点按 "未掌握 / 高优先级" 排最前（显示 ⚠️ 或红色高亮），每条带 "预计阅读 X 分钟 / 依赖 2 个前置概念"
  - 画布：50+ 节点图，重点节点自动大尺寸 + 高亮；点击 "speculative decoding" 节点 → 自动发一条追问深入
  - 学习路径：4 步按依赖拓扑排序；我点第 1 步旁边的 "开始学习" → 直接打开对应的笔记编译页或原 source
  THEN 我在这个会话页 10 分钟内完成了原本需要 1 小时翻 Wiki 页 + 笔记详情 + 网页搜索的综合入门

- 作为本地知识已经很多、只缺最新进展的用户，我触发看板后 Agent 问 "本地已有 12 篇相关笔记，要 Web 搜索最近 6 个月的进展吗？"，我点"是 + 范围：arXiv 2026 年"，THEN 搜索 20 个结果、编译 3 篇 2026 年的新 arXiv 讲解视频、最后看板的"近期变化"章节显著标出

- 作为和 Agent 多轮深入的用户，我在知识看板画布上点击节点深入，看完 Agent 回答后，我双击节点把 label "speculative decoding" 改成 "推测解码"（中文我更习惯），又把 summary 改成 "先猜后验的 token 级并行解码技巧"，THEN 下次打开同一个研究空间的看板时，我的修改仍然保留在 canvases/{id}.json 中

- 作为真正想掌握而非收藏资料的用户，我完成“推测解码”讲解后，Agent 先让我脱离资料解释，再给一个新模型部署场景让我选择是否适用。只有两类证据均通过，节点才从 learning 进入 provisional；延迟复测通过后才进入 mastered

- 作为研究开源实现的用户，我要求学习某篇论文及其代码实现，THEN 学习空间把 arXiv 论文、GitHub 官方仓库、README/文档、最新 Release 和关键 Issue 分成不同来源类型，明确论文结论与仓库实现状态不能互相替代

## 7. 验收标准

1. GIVEN 用户在 Settings 只启用了 SearXNG（本地自托管 http://127.0.0.1:8888），WHEN 调用 search_web("3D Gaussian Splatting 最新论文 2026") 且 SearXNG 不通，THEN 抽象层返回带 `provider_down` 标记的清晰错误，不静默返回空列表；错误信息包含 "已尝试 provider=SearXNG，endpoint=http://127.0.0.1:8888，连接超时，请检查 Settings"

2. GIVEN build_knowledge_canvas 在第 3 步（自主编译前）检测到 8 个视频 URL，WHEN 弹确认框给用户，THEN 用户可以勾选其中 3 个 → 只编译这 3 个；剩下 5 个的原文 snippet 仍然进入综合（不浪费搜索结果）；每个子编译都有自己的长任务卡片（独立取消）

3. WHEN 知识看板生成完后，用户关闭浏览器第二天再打开会话，THEN 知识看板消息仍在原位置，报告/重点/画布/学习路径四个分区内容与昨天完全一致（因为都持久化了），画布节点的简单修改（label/summary）也仍然保留

4. GIVEN 一个概念 "X" 在研究空间记忆里 mastery=known（已掌握）、另一个概念 "Y" 是 unknown（未接触），WHEN 知识看板重点排序时，THEN "Y" 的优先级高于 "X"；前端 UI 上 "Y" 显示 ⚠️ 或红色高亮；"X" 显示 ☑️ 或灰色降低视觉权重

5. GIVEN 画布节点点击后前端自动发 "深入讲一下 node.label ..." 的 user 消息，WHEN Agent 回复完并在回答中新增了 2 个子概念，THEN 用户可以手动点"把这 2 个概念并入当前画布" → 新增 2 个节点 + 连线（P4 只做手动增量合并按钮，不做自动推断；P5 再升级）

6. GIVEN 学习路径的拓扑排序有 A → B → C 的依赖关系，WHEN 展示学习路径时，THEN C 不排在 A 和 B 前面；每个节点显示"前置：A、B"的引用，并带上难度等级（入门/进阶/专家）+ 预计时长估算

7. GIVEN 用户仅阅读了节点讲解但没有提交回忆或应用答案，WHEN 系统更新学习状态，THEN 该节点不得进入 mastered，`mastery_evidence` 只记录 `exposed` 而不增加可验证掌握等级

8. GIVEN 用户对一个节点完成 recall 与 apply 且立即评测通过，WHEN 评测完成，THEN 节点进入 provisional 并生成 `next_review_at`；只有到期复测再次通过后才进入 mastered

9. GIVEN 查询主题同时存在本地 Wiki、arXiv 论文和 GitHub 官方仓库，WHEN 生成学习空间，THEN 三类来源均以不同 `source_type` 出现，每个知识节点至少包含一个可打开的来源；论文元数据包含作者/发布时间，GitHub 元数据包含 owner/repo/default_branch，缺失字段显式为空而不是编造

10. GIVEN GitHub 或学术搜索网络失败，WHEN 本地 Wiki 有可用内容，THEN 学习空间仍可基于本地内容创建，并将外部缺口标记为 `blocked_external`；失败不得把当前 canvas 或 research_space 清空

11. GIVEN 用户刷新页面或重启桌面端，WHEN 再次进入原会话，THEN 当前学习节点、历史作答、mastery_evidence、review_queue 和来源仍可恢复，不能只恢复一张静态图

12. GIVEN 用户打开首页输入框，WHEN 查看模式选择，THEN 同时看到“聊天 / 笔记 / 学习”；选择“学习”后输入文字或粘贴链接不会被自动切回聊天或笔记。

13. GIVEN 用户选择“学习”并提交主题，WHEN 学习空间创建成功，THEN 学术与 GitHub 搜索无需 Settings 开关即被调用；只有已配置可用 Tavily 或 SearXNG 时才额外调用普通网页搜索。

14. GIVEN 学习空间创建成功，WHEN 会话刷新完成，THEN 对话区只显示目标、节点数、来源概况、建议先学节点和学习引导，完整图谱与学习操作出现在右侧学习面板。

15. GIVEN 同一会话已有笔记并新建学习空间，WHEN 页面显示右侧内容，THEN 默认切换到“学习”，且用户可以在“学习 / 笔记”之间切换；不删除或覆盖已有笔记。

## 8. 输入 / 输出样例

### 输入：显式触发 build_learning_canvas

```
用户: "我想真正学会小语言模型推理加速 [生成学习空间]"
   （或点击会话输入框旁的"学习"图标触发）
```

### 输出：构建中 + 构建完成两步

**Step A：长任务占位（SSE 事件）**

```
data: {"type": "task_card", "card_id": "kb-1", "kind": "build_learning_canvas", "status": "RUNNING", "title": "学习空间构建中", "progress": null}
data: {"type": "task_card_progress", "card_id": "kb-1", "status": "LOCAL_RETRIEVAL", "progress": 25, "details": "检索到 18 个本地相关贡献"}
data: {"type": "parameter_request", "request_id": "pr-gap", "skill": "build_knowledge_canvas",
  "fields": [
    {"key": "enable_web_search", "label": "本地内容较少，要 Web 搜索补充吗？", "widget": "radio", "required": true, "options": [
      {"label": "是，默认范围（近 1 年，综合网页）", "value": "default"},
      {"label": "限定范围（自定义）", "value": "custom"},
      {"label": "否，只用本地", "value": "none"}
    ]}
  ]}
... 用户选 "默认范围" ...
data: {"type": "parameter_request", "request_id": "pr-compile", "skill": "build_knowledge_canvas",
  "fields": [
    {"key": "compile_videos", "label": "搜索到 5 个视频，要一起编译吗？", "widget": "checkboxes", "required": true,
      "options": [
        {"label": "B 站：2026 年 LLM 推理加速综述 (15min)", "value": "BV1xx"},
        {"label": "YouTube: Speculative Decoding Deep Dive (22min)", "value": "dQw4w9WgXcQ"},
        {"label": "... (其余 3 个省略)", "value": "..."}
      ],
      "default_selected": ["BV1xx", "dQw4w9WgXcQ"]
    }
  ]}
data: {"type": "task_card_progress", "card_id": "kb-1", "status": "COMPILING_SOURCES", "progress": 45, "details": "编译 2 个视频，已完成 1 个；Web 搜索 28 个结果已抓取 snippet"}
data: {"type": "task_card_progress", "card_id": "kb-1", "status": "SYNTHESIZING", "progress": 80, "details": "LLM 正在综合知识报告..."}
data: {"type": "task_card", "card_id": "kb-1", "kind": "build_knowledge_canvas", "status": "SUCCESS", "progress": 100, "canvas_id": "canvas-123", "artifacts": {"report_id": "...", "canvas_id": "canvas-123", "focus_list_id": "...", "learning_path_id": "..."}}
```

**Step B：一条富媒体对话消息（message_type = learning_canvas；旧 knowledge_board 可兼容读取）**

```json
{
  "message_type": "learning_canvas",
  "role": "assistant",
  "content": "知识看板已生成：共 4 个分区，62 个知识节点，12 条编译笔记支撑。",
  "meta": {
    "canvas_id": "canvas-123",
    "report_markdown": "# 小语言模型推理加速\n\n核心思路是 **算力密度换延迟**...（完整报告 MD）",
    "focus_list": [
      {"node_id": "n-1", "label": "推测解码", "mastery": "unknown", "priority": "high", "estimated_minutes": 15, "sources": ["task-video-1"]},
      {"node_id": "n-2", "label": "KV Cache 量化", "mastery": "learning", "priority": "high", "estimated_minutes": 10, "sources": ["task-video-2", "wiki-entity-kv-cache"]},
      {"node_id": "n-3", "label": "模型剪枝", "mastery": "known", "priority": "low", "estimated_minutes": 5, "sources": []}
    ],
    "learning_path": [
      {"step": 1, "node_ids": ["n-5", "n-3"], "label": "基础：量化与剪枝入门", "difficulty": "introductory", "minutes_estimate": 20, "depends_on": []},
      {"step": 2, "node_ids": ["n-2"], "label": "KV Cache 优化家族", "difficulty": "intermediate", "minutes_estimate": 25, "depends_on": [1]},
      {"step": 3, "node_ids": ["n-1", "n-4"], "label": "推测解码与验证", "difficulty": "advanced", "minutes_estimate": 40, "depends_on": [1, 2]},
      {"step": 4, "node_ids": ["n-6"], "label": "端侧部署实战", "difficulty": "expert", "minutes_estimate": 60, "depends_on": [3]}
    ],
    "current_unit": {"node_id": "n-1", "stage": "recall", "attempt": 1},
    "review_queue": [{"node_id": "n-2", "next_review_at": "2026-08-13T09:00:00Z"}]
  }
}
```

### 反例或失败样例

- Web 搜索 0 结果 + 本地 0 结果 → 看板不"假装产出"，而是清晰返回 "未找到本地或 Web 相关内容，建议：(1) 调宽搜索范围 (2) 手动编译几篇笔记后再试"
- 编译子任务中有 2 个失败、3 个成功 → 看板仍然基于 3 个成功 + 失败的 snippet 综合 + 在报告尾部标注 "以下视频编译失败，原文 snippet 已纳入（可能缺视频原话细节）：XXX、YYY"
- 用户跳过诊断 → 所有节点 mastery 保持 unknown，系统可以给出默认路径，但必须标记“未经过能力诊断”，不得凭聊天语气猜测水平
- 论文摘要与 GitHub README 对同一能力描述冲突 → 画布保留两条带来源的 claim 并标记 conflict，不让 LLM 静默合并成单一事实

## 9. 约束

- **平台 / 设备**：Python 3.11+；画布前端复用现有 Sigma + graphology 渲染栈，不新增大型图库；桌面+源码；默认不用 GPU（纯 CPU 可跑，搜索 + LLM 仍走用户 provider）
- **性能 / 耗时**：
  - search_web 单次调用：P95 ≤ Tavily/SearXNG 的自身延迟 + 50ms 封装开销
  - 知识看板构建：本地内容 ≤ 20 contribution 时，LOCAL_RETRIEVAL + GAP_JUDGE 阶段（不含 Web 搜索/编译/综合）≤ 5s（不含 LLM）
  - 画布渲染首次：100 节点 ≤ 150ms（浏览器端）
- **隐私 / 安全**：
  - Web 搜索 API Key 存 providers 或独立配置（按 provider 体系），不回显、不打日志
  - 搜索结果的 URL 落地（抓取全文）时，复用现有 image_proxy / web_note 的 SSRF 校验（localhost/内网地址白名单）
  - 画布 JSON 不写入原始 API payload
  - 外部搜索查询会发给用户启用的 provider；界面必须明确这一边界。论文/GitHub 内容只有用户确认后才进入采集编译
- **兼容性**：
  - 现有 Wiki 页图谱（graph.json）继续可用，不作为本看板的数据主路径（扩展字段在 canvases/{id}.json 内，原 graph.json 不动）
  - 会话消息 `message_type` 新增 `knowledge_board`，旧前端不识别时 fallback 到 content 纯文本
- **成本**：Web 搜索 provider 由用户自付（Tavily 免费额度 + SearXNG 自托管零费用）；NoteMeld 不承担搜索侧成本
- **掌握判定**：mastery 必须可解释并可追溯到用户作答；任何单次 LLM 评分都要保存 rubric、答案摘要和来源节点，允许用户纠正
- **时间**：P4（search_web 抽象 + 画布数据结构 + 画布只读点击/简单改字 + 看板 Skill 流程 + 学习路径/重点）先交付；P5（画布手动编辑 + AI 对话编辑 + 自动增量更新）作为后续需求
- **第三方依赖 / License**：SearXNG 是外部服务（用户自建），不引入依赖；Tavily 用官方 Python SDK（MIT）或直接 HTTP 调用；画布渲染不引入重量级图库时优先 SVG 手写/D3 子集

## 10. 边界场景

- **空数据**：本地 0 内容 + 用户拒绝 Web 搜索 → 验收 8 已覆盖：不产生空看板
- **权限拒绝**：搜索 provider auth 失效 → search_web 返回 AuthError；看板流程停在 GAP_JUDGE 并向用户抛 Parameter Request 引导用户去 Settings 修正配置
- **网络失败**：Web 搜索中途断网 → 降级为"只用本地内容 + 搜索错误提示写入报告末尾"，不整个看板失败
- **任务中断**：用户在 4 个 compile_source 子任务中取消了第 2、3 个 → 第 1、4 个继续跑完；取消的用 snippet 代替；看板报告末尾列出被用户取消的条目
- **旧数据兼容**：旧 graph.json 没有新字段（mastery/priority/summary/position）→ 加载旧图谱转成 Canvas 时，mastery 默认 unknown、priority 默认 medium、summary 空、position 用前端自动布局算法临时算
- **大数据量**：画布节点 > 200 个时，前端自动分层 + 聚类折叠（clusters 字段已预留）；只渲染可见 cluster + 搜索过滤，不一次全量渲染 DOM
- **其他**：简单文字修改（label/summary）多人在两个标签页同时改 → 以最后保存者为准（乐观并发，不做冲突合并；失败时提示 "画布已被其他会话修改，当前修改基于旧版本。[强制覆盖 / 读取最新并重试]"）
- **复习时间到期但应用未运行**：启动时只显示待复习，不在后台自行调用 LLM；用户进入学习空间后再执行，保持本地优先与成本可控

## 11. 开放问题

无。所有阻塞项已在对话中确认：
- 画布：P4 只读点击 + 简单文字改；P5 手动编辑/AI 编辑 ✅
- 搜索：抽象层 + 默认 Tavily/SearXNG ✅
- 自主编译：优先询问用户 + 长任务期间可取消 ✅
- 产品主线：持续演化的学习空间；研究产出作为学习过程副产物 ✅
- 来源范围：本地 NoteMeld + 通用 Web + 学术 + GitHub，外部采集需确认 ✅
- Agent 形态：V1 单 Agent 阶段化角色，多 Agent 作为后续方向 ✅
- 掌握标准：解释、回忆、应用、迁移和延迟复测的行为证据；“讲过/读过”不等于学会 ✅

## 12. 与系统事实的冲突检查

- **是否和 product-rules.md 冲突**：
  - AI 编译知识，人验证消费 ✅（知识看板 = AI 综合产物；每个 claim 都带 evidence/sources 可追溯；用户点节点深入 = 人验证消费）
  - Wiki-First Retrieval ✅（本地检索优先，Web 搜索是补充不是替代）
  - 桌面 + 源码入口保留 ✅
- **是否和 data-model.md 字段语义冲突**：
  - Wiki graph.json 结构不变 ✅（扩展字段存在 canvases/*.json；graph.json 仍用于 Wiki 旧页面兼容）
  - conversation_messages.message_type 新增 knowledge_board = 字符串枚举值新增，不改变字段语义 ✅
  - task_id 作为编译子任务主键不变 ✅
- **是否和 api-inventory.md 接口语义冲突**：
  - 新增 Settings 下 Research Search 配置接口 → 实现时同步写入 `docs/system/api-inventory.md`
  - 新增画布读写接口（读 `/api/conversations/{cid}/workspace/canvases/{id}.json` 复用工作空间只读；写用内建工具 workspace_write）→ 文档补
  - 旧 chat / conversation / task_status 接口不变 ✅
- **是否会重新引入 known-pitfalls.md 中的问题**：
  - 慢 LLM 进全局写锁：综合步骤不写 Wiki 全局写锁 ✅（写工作空间）
  - latest-wins：看板内部 compile_source 子任务的取消/覆盖用子卡片独立取消，不涉及全局 Wiki rebuild ✅
  - 状态不同步：消息类型 knowledge_board 持久化进 conversation_messages ✅
- **是否影响本地数据或线上服务**：
  - 新增 canvases/ 到工作空间；复用既有 user_profile/research_spaces JSON 目录；SearXNG/Tavily/GitHub 搜索配置保存到本地 `<data_root>/config/research_search.json`，不复用 LLM providers 表
  - 无破坏性变更
- **是否影响用户已确认交互**：单一入口（会话界面增强）✅；没有新增页面或拆散现有流程
- **是否影响本地数据或线上服务**：新增会话工作空间 canvas JSON 与可选外部搜索请求；不改 Wiki live materialize，不上传用户笔记正文到搜索 provider；LLM 仍按现有 Provider 规则调用

## 13. Superpowers 交接

- 是否已达到 Ready for Plan：是；Plan/Spec 已于 2026-08-11 生成
- 推荐下一步：
  - [ ] 生成一个 V1 纵向闭环 Plan/Spec：本地检索 → 多源候选 → canvas 持久化 → 诊断/学习/评测 → 对话内渲染
  - [ ] V1 验收后再拆“自动采集编译编排”和“多 Agent 学习组织”独立需求
- 计划必须覆盖的验收标准：第 1-11 条；优先保证第 3、7、8、9、10、11 条形成真实学习闭环
- 计划必须补充的验证：
  - 人工走查：用"3DGS vs NeRF 对比"作为标准测试案例，跑完整看板流程（本地+Web+编译+综合），截图记录产物
  - 回归：Wiki 旧页面图谱加载仍正常（和画布不互扰）
  - 契约测试：新增 `test_knowledge_board_contracts.py` 覆盖空数据/半失败/取消子任务三个边界场景
