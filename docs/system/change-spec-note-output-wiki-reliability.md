# Change Spec：笔记输出格式与 Wiki 抽取可靠性

日期：2026-08-13
状态：Approved for implementation
Canonical requirement：`docs/requirements/2026-08-13-note-output-wiki-reliability.md`

## 0. 预检查

- [x] 已阅读五份必读系统文档、搜索相关前后端代码、存储和测试。
- [x] 已用本地任务数据确认整篇 `html` 围栏内实际为 Markdown。
- [x] 已用 usage 记录确认 5 个 chunk 均消耗约 1600 completion tokens，但适配后 `content` 为空。
- [x] 已确认不需要数据库迁移，不影响线上外部服务状态。

## 1. 当前系统现状

- 模块：`note_style_prompt_builder`、视频/网页 Note 生成器、notemeld-ai Provider、`NotemeldGPT` 兼容响应、`KnowledgeExtractor`。
- 数据：现有 `note_documents`、笔记输出 JSON/Markdown、Wiki contribution/job；结构不变。
- API/UI：继续使用既有笔记与 Wiki 重试接口；前端 ReactMarkdown 的行为正确。
- 缺陷：格式意图在 prompt 与保存阶段不一致；OpenAI 兼容响应丢弃推理字段和真实结束原因；Wiki 对所有空 content 使用同一错误。

## 2. 本次目标

- 建立共享笔记输出归一化边界，并由视频/网页入口共同调用。
- 按 `output_formats` 生成正确的风格指令。
- 在 Provider→NotemeldGPT→Wiki 链路保留推理内容与结束原因。
- 只恢复合法 JSON，提供可操作的失败分类，并降低输出截断概率。
- 保留普通模型、真实 HTML 转 Markdown、source-only Wiki 与重试行为。

## 3. 明确不做

- 不调整前端视觉主题、Markdown 组件、SQLite schema、Wiki schema。
- 不展示 chain-of-thought，不把非结构化 reasoning 当答案。
- 不批量重写所有历史笔记。

## 4. 冲突分析

- 与产品规则、数据模型、API 结构均不冲突。
- HTTP 错误字段结构不变，仅错误详情更精确，需同步 API inventory。
- 无桌面、MCP、迁移、打包入口变化；源码和 sidecar 共用同一后端代码。
- 防止重新引入“前端遮盖脏内容”“模型适配层吞字段”“错误不可诊断”等坑点。

## 5. 影响范围

- 后端：笔记风格 prompt、共享输出归一化、`note.py`、`web_note.py`、AI stream/provider、NotemeldGPT、KnowledgeExtractor。
- 前端/桌面：无代码改动。
- 测试：新增格式归一化、prompt 契约、reasoning/finish_reason 透传、Wiki 受控恢复与错误分类测试；运行相关回归、合同测试和 build。
- 文档：requirement、plan、spec、test evidence、architecture、API inventory、known pitfalls。

## 6. 实施方案

### 后端

- 新增无状态 `note_output_normalizer`：只剥离完整单围栏；检测真实 HTML；按目标格式复用 `html_to_markdown`。
- Markdown-only prompt 改为裸 Markdown；HTML-only 与双格式继续以 HTML 为源。
- `CompleteResult` 增加可选 `finish_reason`；Provider 读取 `reasoning_content`；兼容响应透传二者。
- KnowledgeExtractor 优先 final content；仅从完整 JSON、JSON fence 或 BEGIN/END 标记恢复 reasoning；按 finish reason 分类；默认预算提升并收紧单块输出上限。
- 日志与 UI 不包含 reasoning 原文。

### 前端

- 无需改动；既有失败提示展示后端细化原因。

### 并发/超时

- 不改变队列/锁。Wiki 仍沿用现有 Provider 超时；提高的是最大输出 token，不是请求无限等待。

## 7. 数据变更

- 无表/字段/文件结构/迁移变化。
- 新生成内容自动正确；指定历史笔记可用同一确定性 normalizer 修复，失败可从备份/原任务结果恢复。

## 8. 接口变更

- 无新增、删除或请求/响应结构变化。
- Wiki job 的 `error` 文本由统一 empty content 细化为 truncated、reasoning-without-final-json、empty 或 Provider network error。
- 前端/MCP 无调用调整；更新 `docs/system/api-inventory.md` 错误语义。

## 9. UI/交互变更

- 成功：笔记以正常 Markdown/HTML 渲染。
- 失败：Wiki 警告中的原因可指导用户重试、调整模型或检查网络。
- 加载、空状态、桌面/浏览器差异不变。

## 10. 测试方案

- TDD：先增加失败测试并确认 RED，再最小实现 GREEN。
- 聚焦：note output/prompt、AI provider/adapter、KnowledgeExtractor。
- 回归：后端 Wiki/Note/AI 相关测试、前端 contracts/build、compileall、diff check。
- 手动：用原始 fenced Markdown fixture 和 reasoning-only canned response 验证。

## 11. 验收标准

- [ ] 整篇错误围栏被安全修复，局部围栏保留。
- [ ] Markdown-only prompt 与持久格式一致。
- [ ] reasoning/finish_reason 完整透传。
- [ ] 合法 JSON 可恢复，非 JSON reasoning 不泄露且错误可分类。
- [ ] 聚焦与核心回归通过，本地服务重启可测试。

## 12. 风险和回滚

- 风险：围栏判断误伤；以“整个输出恰好是一个围栏”为硬条件。
- 风险：reasoning 里混入不完整 JSON；恢复前必须 `json.loads` 且走既有 schema 归一化。
- 降级：恢复失败仍走 source-only，不写伪结构化知识。
- 回滚：移除共享 normalizer 调用与新增字段读取即可；无数据迁移需要反向处理。

## 13. Agent 必答问题

- 影响模块：笔记生成/风格、LLM 兼容层、Wiki 抽取和状态提示。
- 类似能力：已有 HTML 转 Markdown、分块抽取、source-only fallback，直接复用。
- 产品/数据冲突：无；不改 schema。
- known pitfalls：重点防止脏输出入库、reasoning 丢失和模糊错误。
- 本地/线上：代码路径同时影响，当前只修改本地工作区，不调用外部写操作。
- 最小改动：共享 normalizer + 四层字段透传/恢复，不改前端。
- 回归测试：格式边界、prompt、Provider、adapter、Wiki 三类空响应、现有 Note/Wiki contracts。

