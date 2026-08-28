# 笔记输出格式与 Wiki 抽取可靠性修复

日期：2026-08-13
作者 / Agent：Codex
状态：Ready for Plan
关联对话 / 任务：笔记被整篇渲染为代码块；Wiki 5/5 chunk 返回空内容
关联系统文档：`docs/system/current-architecture.md`、`product-rules.md`、`data-model.md`、`api-inventory.md`、`known-pitfalls.md`

## 1. 原始需求

修复两类已复现问题：知识卡片风格的笔记被错误包裹为 `html` 代码围栏；Wiki 结构化抽取在推理模型产生 token 但 `message.content` 为空时，错误地把全部分块判为无内容。

## 2. 背景和问题

- 当前用户：使用 NoteMeld 编译视频/网页内容并进入 Wiki 消费知识的用户。
- 当前场景：笔记生成成功后在右侧笔记/Wiki 视图查看结果。
- 当前痛点：错误格式让整篇笔记成为灰色代码块；推理输出未被适配层保留导致 Wiki 只生成空的基础页。
- 为什么现在做：问题破坏“AI 编译知识，人验证和消费”的核心闭环，且会诱导无效重试并增加模型成本。

## 3. 目标结果

- Markdown 风格直接要求模型输出裸 Markdown，保存前对整篇错误围栏进行安全归一化。
- OpenAI 兼容适配层保留 `reasoning_content` 和真实 `finish_reason`。
- Wiki 仅在推理字段包含可验证 JSON 时恢复结果；否则区分截断、仅推理无最终 JSON、真正空响应和网络失败。
- 调整 Wiki 输出预算与结构数量上限，降低推理模型耗尽输出预算的概率。

## 4. 非目标

- 不重做笔记主题视觉系统或前端 Markdown 渲染器。
- 不改变 Wiki 数据模型、HTTP 返回结构或 Provider 配置页面。
- 不把任意推理文字当作最终答案，不隐藏真实网络错误。

## 5. 当前系统事实

- 已有类似能力：`html_to_markdown`、笔记风格 `output_formats`、Wiki 分块抽取与 source-only 降级。
- 当前入口：笔记生成任务、Wiki 异步抽取/增强任务、右侧 Markdown/Wiki 视图。
- 当前写入：`note_documents.content` 及现有笔记结果文件；Wiki contribution/status 沿用现有结构。
- 当前限制：Markdown-only 风格 prompt 仍强制 HTML；格式转换只识别真实 HTML 标签；notemeld-ai 非流式结果未透传推理字段和结束原因。
- 相关坑点：不能只在前端修渲染；不能把 LLM 兼容响应的空 `content` 等同于没有生成；失败原因必须可追踪。

## 6. 用户故事

- 作为知识消费者，我希望生成笔记按选择的格式正常阅读，并在 Wiki 抽取失败时看到准确原因，以便判断是重试、换模型还是检查网络。

## 7. 验收标准

1. GIVEN Markdown-only 风格，WHEN 模型返回被单一 `html`/`markdown` 围栏包住的 Markdown，THEN 持久化内容为裸 Markdown且内部代码块不受影响。
2. GIVEN 模型返回真实 HTML 且目标为 Markdown，WHEN 保存笔记，THEN 仍使用现有 HTML→Markdown 转换。
3. GIVEN兼容 Provider 返回空 `content`、合法结构 JSON 位于 `reasoning_content`，WHEN Wiki 抽取，THEN 系统恢复并校验 JSON。
4. GIVEN 推理字段只有过程文本或输出因 token 长度截断，WHEN Wiki 抽取，THEN错误分别说明“无最终 JSON”或“输出被截断”，而不是统一 empty content。
5. 正常非推理模型、工具调用、使用量记录、网页笔记和现有 Wiki source-only 降级行为保持兼容。

## 8. 输入 / 输出样例

### 输入

- `````html\n# 标题\n正文\n`````，目标格式 `markdown`。
- `content=""`，`reasoning_content="BEGIN_JSON\n{...}\nEND_JSON"`。

### 输出

- `# 标题\n正文`。
- 通过既有 schema 归一化后的 Wiki Analysis payload。

### 反例或失败样例

- 推理字段仅为自然语言思考：不得直接作为 Wiki JSON 使用。
- 文档正文中的局部代码围栏：不得被剥离。

## 9. 约束

- 兼容源码、桌面、CLI 既有调用链；不新增数据库迁移。
- 仅处理“整个模型结果是单一围栏”的确定性错误，避免误伤正文。
- 不暴露模型推理内容到 UI，只用于验证后的结构化恢复或错误分类。
- Wiki token 预算仍可由环境变量覆盖。

## 10. 边界场景

- 空内容：保留明确 empty response 错误。
- 网络失败：保留 Provider 的网络/超时分类。
- 任务中断：沿用现有 partial Wiki 与重试入口。
- 旧数据：代码修复不自动批量改写；明确目标可安全归一化或重新生成。
- 大数据量：继续分块，限制单块抽取对象数量。

## 11. 开放问题

无阻塞问题。

## 12. 与系统事实的冲突检查

- 产品规则：一致，提升知识编译可消费性和可验证性。
- 数据模型：无字段语义变化。
- API：无结构变化，仅细化既有错误文本。
- known pitfalls：新增 LLM reasoning-only 与整篇错误围栏防线。
- 本地/线上：影响所有使用兼容 Provider 的笔记与 Wiki 抽取；保持 Provider 无关。
- 已确认交互：不改变右侧笔记/Wiki 切换和重试入口。

## 13. Superpowers 交接

- 是否 Ready for Plan：是。
- 下一步：生成 plan/spec，以 TDD 实现并验证。
- 必须覆盖：五条验收标准、Provider 兼容、网页/视频双入口、错误分类、系统文档同步。

