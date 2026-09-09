# NoteMeld Agent SDK 产物接入执行规格

Canonical requirement：`../../requirements/2026-08-17-notemeld-agent-sdk-artifact-integration.md`

## Task 1：启动 artifact 契约

涉及文件：

- `run_notemeld.sh`
- `scripts/notemeld`
- `packaging/scripts/build-backend-macos.sh`
- `packaging/backend/pyinstaller/backend.spec`
- `backend/tests/agent_host/test_agent_sdk_artifact_contract.py`

规格：

- 两种 launcher MUST 先尝试导入 `notemeld_agent_sdk.runtime`。
- 未安装时 MUST 要求 `NOTEMELD_AGENT_SDK_WHEEL` 指向存在的 wheel，并使用当前应用 venv 的 Python 执行 `pip install --no-deps --force-reinstall`。
- 安装后 MUST 再次 import，并验证 `SDK_VERSION=0.1.0`、`SCHEMA_VERSION=1`。
- 已安装且版本正确时 MUST 跳过 pip。
- wheel 路径、架构、import 或版本失败 MUST 阻止 Agent Host 启动。
- 打包脚本 MUST 继续从外部 wheel 收集 native resource，不从仓内 `agent-sdk/bindings/python` 复制。

验证：`bash -n`、静态 contract test、隔离 fake-python launcher test。

## Task 2：统一 CLI

涉及文件：

- `scripts/notemeld-agent.py`
- `scripts/notemeld`
- 新增 `backend/tests/agent_host/test_agent_cli.py`

规格：

- MUST 支持 `-p/--prompt`、`--conversation/--session`、`--model`、`--output/--format text|json|jsonl`。
- REPL MUST 支持 `/new`、`/resume ID`、`/sessions`、`/model [NAME]`、`/exit`。
- CLI MUST 只调用 `/api/agent/v1`，不得 import legacy Agent core 或 SDK binding。
- JSON/JSONL 模式 stdout MUST 只含协议输出；诊断写 stderr。
- Turn 创建 MUST 传递 model override；session ID 必须复用 Conversation ID。
- fake HTTP Host tests MUST 验证 URL、payload、SSE replay 和命令状态。

## Task 3：Rust-only runtime 门禁

涉及文件：

- `backend/app/agent_host/runtime.py`
- `backend/tests/agent_host/test_runtime_loader.py`

规格：

- `python`、`python-oracle`、`legacy` runtime mode MUST 返回 `AgentSdkUnavailable`。
- 生产默认 MUST 为 `rust`。
- SDK/package/schema 版本不匹配 MUST fail-closed，错误不得包含敏感值。
- 显式 development path只用于 SDK checkout 开发，不得成为打包默认路径。

## Task 4：重复 Python SDK 清理

候选文件：

- `agent-sdk/bindings/python/`
- `agent-sdk/examples/python-host/`
- `agent-sdk/scripts/build-python.sh`
- `.github/workflows/agent-sdk.yml` 中 Python artifact job
- `backend/tests/test_agent_sdk_workflow_contracts.py` 中对应契约

规格：

- 删除前 MUST 证明 NoteMeld production/runtime/packaging 不读取候选路径。
- 若候选仍承担独立 SDK CI 的唯一职责，则本轮 MUST 保留并在验证报告标记“待 SDK 仓库 CI 迁出”，不得造成工作流红灯。
- 独立 SDK 的 wheel/native artifact 是唯一生产输入；NoteMeld 不维护第二份 Python runtime。

## Task 5：legacy Python Agent core 删除门禁

候选：`backend/app/agent/core/`、`backend/tests/agent_core/` 与 `agent_service`/`sse_bridge` compatibility path。

规格：

- 执行 `rg` 建立生产 import 清单。
- 只有当 `backend/app` 生产 import 为零，且 UI/CLI/旧 chat/MCP/tool 回归入口均有替代时，才允许删除。
- 当前 native executor 的 tool driver 仍未接入时，MUST NOT 删除提供产品工具能力的 adapter/core。
- 未满足门禁的内容写入验证报告的“未完成及原因”，不得虚报清理完成。

## Task 6：文档与验证

同步：

- `docs/system/current-architecture.md`
- `docs/system/api-inventory.md`
- `docs/system/known-pitfalls.md`
- `docs/requirements/index.md`
- `docs/superpowers/tests/2026-08-17-notemeld-agent-sdk-artifact-integration.md`

最小命令：

```bash
bash -n run_notemeld.sh scripts/notemeld
python3 -m py_compile scripts/notemeld-agent.py
pytest backend/tests/agent_host/test_agent_sdk_artifact_contract.py backend/tests/agent_host/test_agent_cli.py backend/tests/agent_host/test_runtime_loader.py -q
```

真实证据：用 `/Users/hehejie/ai/notemeld-agent-sdk/dist-native/...whl` 在临时 venv 验证 import、native library 与 fake turn；不在 linked worktree 安装项目依赖或启动 live NoteMeld 栈。
