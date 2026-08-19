# Agent ToolDriver 产品能力链路验证证据

Canonical requirement: [`../../requirements/2026-08-19-agent-tool-driver-chain.md`](../../requirements/2026-08-19-agent-tool-driver-chain.md)

## 通过

- `.venv/bin/python -m compileall -q backend/app`
  - 结果：exit 0。
- `PYTHONPATH=<pytest-runner>:backend PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest backend/tests/agent_host -q`
  - 结果：`92 passed, 2 warnings in 16.13s`。
- `PYTHONPATH=<pytest-runner>:backend PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest backend/tests/agent_host backend/tests/knowledge/test_knowledge_retrieval.py -q`
  - 最终生产代码调整后结果：`96 passed in 13.90s`。
- `PYTHONPATH=<pytest-runner>:backend PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest backend/tests/agent_host/test_capabilities.py backend/tests/agent_host/test_tool_driver.py backend/tests/agent_host/test_native_executor.py backend/tests/agent_host/test_tool_scheduler_integration.py backend/tests/knowledge/test_knowledge_retrieval.py -q`
  - 结果：`23 passed in 3.51s`。
  - 真实 standalone SDK artifact 覆盖：正常 ToolResult→第二轮模型；未知工具、非法参数、执行异常分类结果→第二轮模型；共享 Host 的两个并发 Session 结果隔离。

## 全后端回归

- `PYTHONPATH=<pytest-runner>:backend PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest backend/tests -q`
  - 结果：`649 passed, 2 failed in 59.53s`。
  - 失败 1：`test_wiki_retry_uses_saved_runtime_config`，全量同进程运行时测试 DB 缺少 `note_documents`；单独在 main 基线运行该用例通过，属于既有收集/全局 DB 隔离问题，与 ToolDriver diff 无关。
  - 失败 2：`test_export_service_writes_structured_package`，期望 fixture 的 `static/screenshots/shot-1.jpg`，实际 export service 使用全局截图根；main 基线同用例也失败，与 ToolDriver diff 无关。

## 环境说明

- 主工作树 `.venv` 包含应用依赖和 standalone Agent SDK，但未安装 pytest。
- 验证使用本机已有 pytest 8.4.2 的纯 Python runner 包，应用依赖和 native SDK 仍来自主工作树 `.venv`；未修改或安装主工作树环境。
