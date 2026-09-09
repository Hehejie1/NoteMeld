# L0–L3 渐进式能力路由验证证据

日期：2026-08-11  
Canonical requirement：[`docs/requirements/2026-08-11-progressive-capability-routing.md`](../../requirements/2026-08-11-progressive-capability-routing.md)

## 测试命令与关键结果

| 命令 | 结果 |
| --- | --- |
| `test -f /Users/hehejie/.codex/skills/doc-driven/SKILL.md` | PASS；`doc-driven` 已安装，frontmatter name 为 `doc-driven` |
| `python3 -m compileall backend/app` | PASS |
| `cd backend && python3 -m pytest tests/agent/test_capability_catalog.py tests/agent/test_mcp_client.py tests/test_core_mcp_generation_tools.py -q` | PASS：51 passed，4 subtests passed |
| `cd backend && python3 -m pytest tests/agent/test_agent_service_p3_integration.py tests/agent/test_chat_compat.py tests/ai/test_chat_service_migration.py -q` | PASS：33 passed |
| `cd backend && python3 -m pytest tests/agent/test_capability_catalog.py tests/agent/test_agent_service_p3_integration.py tests/agent/test_chat_compat.py tests/agent/test_mcp_client.py tests/ai/test_chat_service_migration.py tests/test_core_mcp_generation_tools.py -q` | 最终聚焦复验 PASS：84 passed，4 subtests passed |
| `cd backend && python3 -m pytest tests/agent tests/agent_core tests/ai/test_chat_service_migration.py tests/test_core_mcp_generation_tools.py -q` | PASS：214 passed，4 subtests passed |
| `pnpm test:contracts`（使用 Codex 工作区 bundled Node） | PASS：`tsc -p tsconfig.contract.json` exit 0 |
| `pnpm build`（使用 Codex 工作区 bundled Node） | PASS：Vite 生产构建完成，13078 modules transformed；仅有现存 eval/chunk-size warning |
| `scripts/run_core_regression.sh` | PASS：27 passed |
| `git diff --check -- <本需求涉及文件>` | PASS，无 whitespace error |
| `PYTHONPATH=backend python3 -m pytest backend/tests -q` | PASS：483 passed，4 subtests passed（单进程全量） |
| `PYTHONPATH=backend python3 -m pytest backend/tests/agent/test_mcp_client.py backend/tests/agent/test_mcp_config_api.py -q` | PASS：31 passed |

## 覆盖证据

- Agent free-chat hook 在模型决策前不实例化 `WikiSearch`；legacy `_prepare_free_chat_context()` 默认仍预取。
- L0 只读取 `graph.json` 元数据，包含精确实体/概念 hint，输出不超过 1200 字符；10000 节点用例有界，同一 mtime 只读取一次 graph。
- L1 不返回 schema、Wiki 正文或 MCP 敏感配置；L2 只返回选中能力 schema。
- Agent 初始工具严格为 `capability_discover`、`capability_describe`、`capability_invoke`。
- L3 Wiki search/read 复用现有服务、限制结果/正文长度，并把来源动态追加到 `sources`。
- `use_wiki=false` 同时阻止 Wiki 注册和执行。
- Skill/builtin/memory/workspace 使用来源命名空间，具体 schema 不在首轮展开。
- MCP 在 L0/L1 discovery 次数为 0；L2/L3 才发现单个 enabled server，adapter 在正常、模型异常和 SSE 客户端断开时关闭；L0/L1 不暴露 URL/header/env/token。
- 并行 L2 describe 对同一 MCP server 只执行一次 discovery；配置 API 的 auth/header/env 脱敏、占位符凭证保留和唯一 tmp 原子写均有回归测试。

## 指标

- 固定初始工具 schema 数：3。
- L0 字符硬上限：1200。
- L1/L2 默认条数：8，硬上限：20。
- Wiki search limit：1–20；Wiki page 正文：最多 12000 字符。
- MCP 同一请求同一 server：最多发现一次。

## 全量检查修复记录

原全量命令曾因 `test_core_note_task_status_api.py` 的收集期 `sys.modules` stub 未恢复而污染后续 `test_web_note_contracts.py`。现已在 router 导入后恢复自己注册的 stub，并以单进程完整后端测试作为最终门禁；最终结果见本轮最新验证记录。
