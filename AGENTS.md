# AGENTS.md

本文件是 NoteMeld 项目中所有 AI Agent 和开发者的硬规则。任何新需求、方案、代码修改、Bug 修复、重构、接口变更、数据模型变更开始前，必须遵守。

## 必读文档

开始任何新需求前，必须先阅读：

- `docs/system/current-architecture.md`
- `docs/system/product-rules.md`
- `docs/system/data-model.md`
- `docs/system/api-inventory.md`
- `docs/system/known-pitfalls.md`

只读 README、只看用户描述、只根据记忆或猜测写方案，均不合格。

## 必须搜索现状

动手前必须搜索相关代码和测试：

- 相关前端页面、组件、服务调用。
- 相关后端 router、service、model、utils。
- 相关 SQLite 表、文件结构、状态文件、sidecar 文件。
- 相关契约测试、回归测试、打包脚本和文档测试。

如果找不到现状，必须继续查或向用户提问，不能猜。

## 禁止事项

- 不能直接生成孤立 PRD。
- 不能在不了解现状的情况下写实现方案。
- 不能凭猜测改数据库字段、接口语义或核心业务规则。
- 不能绕过 `docs/system/change-spec-template.md`。
- 不能只做理想化重构方案，必须基于当前真实系统。
- 不能为了局部改动删除已有能力。
- 不能做无关重构。
- 不能删除用户未明确要求删除的能力。
- 不能回滚用户或其他 Agent 的改动，除非用户明确要求。
- 不能暴露 Provider API Key、Cookie、token、用户本地路径或敏感 payload。
- 不能破坏源码启动、CLI、桌面、MCP、迁移、Wiki、上传、打包发布任一既有入口。

## Change Spec 规则

所有新需求必须先产出增量 Change Spec。模板见：

```text
docs/system/change-spec-template.md
```

Change Spec 必须回答：

- 当前系统现状是什么。
- 本次目标是什么。
- 明确不做什么。
- 和产品规则、数据模型、API、历史坑点是否冲突。
- 影响哪些模块、接口、数据、UI、测试和文档。
- 最小可行改动是什么。
- 如何测试和验收。
- 风险和回滚是什么。

用户明确要求“直接修 Bug”时，也必须至少在回复或提交说明中覆盖根因、影响范围和回归测试。

## Bug 修复规则

Bug 修复必须说明：

- 根因。
- 影响范围。
- 复现方式或证据。
- 修复点。
- 回归测试。
- 未覆盖风险。

不能只说“已修复”。没有验证证据，不得声称通过。

## 文档同步规则

修改以下内容时，必须同步更新 `docs/system/`：

- 系统架构、运行入口、部署方式。
- 产品硬规则或 UX 行为。
- SQLite 表、字段、文件结构、状态流转、缓存和统计口径。
- API 路径、请求参数、返回结构、错误语义或调用方。
- MCP 工具。
- Wiki rebuild、任务状态、桌面 sidecar、迁移、上传、打包发布等核心链路。
- 新发现的坑点和回归防线。

## 最小改动规则

- 优先复用现有模块、helper、router、service、测试模式。
- 只做满足需求的最小可行改动。
- 保持已有数据兼容。
- 保持已有 API 调用方兼容，必要时提供兼容层。
- 保持旧数据、历史状态和已有文件结构可读取。
- 涉及并发、取消、超时、文件写入时，必须考虑 race condition 和脏状态。

## 新需求前 Agent 必答问题

任何新需求开始前，Agent 必须回答：

- 这个需求影响哪些已有模块？
- 当前系统是否已有类似能力？
- 是否和产品规则冲突？
- 是否和数据模型字段语义冲突？
- 是否会重新引入 known-pitfalls 中的问题？
- 是否影响本地数据或线上服务？
- 最小可行改动是什么？
- 需要补哪些测试防止回归？

如果答不清楚，必须继续查代码、查文档、查测试，或者向用户提问，不能猜。

## 推荐验证命令

按改动范围选择验证：

```bash
python3 -m compileall backend/app
pytest backend/tests
cd frontend && pnpm test:contracts
cd frontend && pnpm build
scripts/run_core_regression.sh
```

打包、桌面、MCP、上传、迁移、Wiki 相关改动必须优先运行对应契约测试。
