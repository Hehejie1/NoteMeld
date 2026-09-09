# NoteMeld 主动学习空间 V1 验证证据

日期：2026-08-11
Canonical requirement：[`docs/requirements/2026-08-01-notemeld-agent-deep-learning-canvas.md`](../../requirements/2026-08-01-notemeld-agent-deep-learning-canvas.md)
Plan：[`docs/superpowers/plans/2026-08-11-notemeld-active-learning-space.md`](../plans/2026-08-11-notemeld-active-learning-space.md)
Spec：[`docs/superpowers/specs/2026-08-11-notemeld-active-learning-space.md`](../specs/2026-08-11-notemeld-active-learning-space.md)

## 结论

状态：**核心纵向闭环已实现并通过定向验证；完整需求尚未达到 Implemented。**

已经形成可运行链路：本地 Wiki 优先 → 已启用的 Web/arXiv/GitHub 候选搜索 → 持久化 LearningCanvas → 对话内学习卡 → 开始学习 → learner answer + rubric 证据 → provisional → 48 小时到期 review → mastered → 刷新/重启恢复。

仍未完成的完整验收项见“剩余范围”。因此 requirement/index 保持 `Planned`，不虚报全量交付。

## 2026-08-12 学习入口与右侧面板增量

状态：**已实现并通过自动化与真实浏览器纵向验收。**

- 首页 composer 已出现“聊天 / 笔记 / 学习”；学习仅接受明确文本目标，上传与 URL 自动推断不会伪装成已参与研究。
- 学术论文和 GitHub 固定为默认研究范围；Settings 不再提供开关或 GitHub 配置，只保留可选 Tavily/SearXNG 普通网页配置。
- 学习创建不使用前端固定超时，在任何异步操作前获取跨 composer 共享提交锁并持久化构建状态；canvas 返回成功后即视为成功，后续消息刷新/导航失败只降级提示。旧请求仅在用户仍停留于发起页时自动导航，避免超时、双击、路由卸载或后处理失败产生重复 canvas。
- 对话只渲染 compact 学习总结；完整画布、路径、当前学习与来源在右侧面板恢复。同会话存在笔记时保留“学习 / 笔记”切换，笔记消失后自动回到学习面板。

真实浏览器验收使用隔离临时数据目录，完成以下路径：进入 `/new` → 点击“学习” → 输入 AI Agent 学习目标 → 创建成功 → 导航到会话 → 对话显示 8 节点摘要 → 右侧显示学习路径、当前单元和 arXiv 来源 → 点击“开始学习”后出现主动回忆和应用任务。设置页同时确认默认学术/GitHub 文案与仅 Web 可配置行为。临时数据已移至废纸篓，未写入用户正式数据目录。

最终只读代码复审确认：固定前端超时、canvas 成功后的错误回滚、跨路由重复提交/导航劫持、Learn→Note URL 回退和错误重试语义均已闭环；未发现 Critical 或 Important。保留的非阻塞取舍是同步研究没有用户取消入口，但每个 provider 仍受后端 5–30 秒超时约束。

## TDD 证据

实施期间先观察到以下预期 RED：

- 缺少 `app.models.learning_canvas`、`research_search`、`learning_canvas_service`、learning router/tools 时，新增测试均因模块或接口不存在失败。
- 渐进式能力目录未注册 learning tools 时，capability contract 因缺少 `create_learning_tools` 失败。
- 最近画布恢复未实现时，store/tool tests 因缺少 `latest()` 失败。
- rubric 未校验时，空答案、缺字段、越界分数和低分通过四个用例全部失败。
- PATCH 节点说明未实现时，API 返回 405，前端 source contract 找不到 `request.patch`。

对应实现后均转为 GREEN。

## 验证命令与结果

### 后端定向回归

```bash
PYTHONPATH=backend pytest \
  backend/tests/learning \
  backend/tests/agent/test_learning_tools.py \
  backend/tests/agent/test_capability_catalog.py \
  backend/tests/agent/test_agent_service_p3_integration.py \
  backend/tests/agent/test_chat_compat.py -q
```

结果：`73 passed, 4 subtests passed in 4.85s`。

最后一次 learning-only 复核：

```bash
PYTHONPATH=backend pytest backend/tests/agent/test_learning_tools.py backend/tests/learning -q
```

结果：`35 passed in 1.59s`。

### 后端全量回归

直接运行：

```bash
PYTHONPATH=backend pytest backend/tests -q
```

原先的收集失败根因是 `test_core_note_task_status_api.py` 注册 `app.services.web_note` stub 后未恢复，污染同一 pytest 进程后续模块。现已在 router 导入完成后只移除本文件注册的 stub。

2026-08-12 最终单进程全量复核：`487 passed, 4 subtests passed in 32.04s`。

### 前端契约与构建

```bash
node frontend/tests/learningCanvasContracts.test.mjs
cd frontend && pnpm test:contracts
cd frontend && pnpm build
```

结果：学习空间 source contract 通过；TypeScript contract 通过；Vite production build 成功（`13078 modules transformed`，2026-08-12 最终复验 `built in 58.82s`）。构建只有既有大 chunk 与 `lottie-web eval` warning，没有新增编译错误。

本机全局 pnpm 是 11.x，而项目锁定 `pnpm@9.15.0`；验证使用 Corepack 解析出的 9.15.0 执行，没有修改 `packageManager`。

### 核心回归与静态检查

```bash
scripts/run_core_regression.sh
python3 -m compileall -q backend/app
git diff --check -- <本需求涉及文件>
```

结果：2026-08-12 最新核心回归 `27 passed in 5.58s`；Python compileall 与本需求文件范围 diff whitespace 检查通过。全工作区 `git diff --check` 仍会报告本轮开始前已 staged 的模型评估报告 EOF 空行和 `tests/shared/test_ollama_connection.py` 尾随空格，本轮未改写这些无关评估产物。

## 已覆盖的关键验收

- 本地来源排在外部来源之前；arXiv/GitHub 元数据保留，provider 部分失败不丢成功来源。
- 本地有结果时外部失败仍生成 canvas，并标记 `blocked_external`；全部为空时拒绝伪造空画布。
- Canvas 使用安全 ID、唯一临时文件和原子替换；PATCH/start/evidence 在同一路径锁内完成完整读改写，并发 evidence 不会覆盖彼此。
- 画布创建后写一条轻量 `learning_canvas` 消息，完整状态留在 workspace artifact。
- Agent 通过 L0–L3 的 `learning:*` 能力发现学习工具；可省略 canvas_id 恢复当前会话最近画布。
- 展示单元只进入 `exposed`；recall/apply 进入 provisional；未到期 review 被拒绝；到期通过才 mastered。
- 用户可持久化节点自定义标题和理解摘要；前端不能直接设置 mastered。
- 搜索密钥读取脱敏；学习卡和研究设置等待 backend ready。

## 剩余范围

以下内容仍属于 canonical requirement，但本轮纵向闭环未实现，因此不能把状态改成 `Implemented`：

1. 3–7 题的初始诊断与 mastery-aware 个性化重点排序。
2. 外部候选的用户勾选、复用现有采集/编译长任务、单个取消和部分成功综合。
3. 可选 LLM canvas synthesis，以及由后端模型直接执行 rubric 评测；当前是 Agent 生成 rubric，后端做严格结构和阈值校验。
4. 节点深入回答产生子概念后的“并入当前画布”，以及全屏/大图聚类交互。
5. provisional/mastered 向绑定 Research Space 的 mirror 写回。
6. 使用真实 provider 和“3DGS vs NeRF”案例的人工端到端网络走查与截图。

这些应继续按当前 Plan 未勾选步骤推进；多 Agent 仍保持后续演进，不进入 V1。
