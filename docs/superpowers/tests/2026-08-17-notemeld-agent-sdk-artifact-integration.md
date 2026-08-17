# NoteMeld Agent SDK artifact 接入验证证据

Canonical requirement：`../../requirements/2026-08-17-notemeld-agent-sdk-artifact-integration.md`

## 自动化门禁

```bash
PYTHONPATH=backend pytest -q \
  backend/tests/agent_host/test_agent_sdk_artifact_contract.py \
  backend/tests/agent_host/test_agent_cli.py \
  backend/tests/agent_host/test_runtime_loader.py
```

结果：`20 passed in 4.33s`。其中 CLI 测试覆盖首次事件为空后的轮询、sequence 去重，以及“状态先终态、terminal event 随事务刚可见”的最终 replay 竞态。

```bash
bash -n run_notemeld.sh scripts/notemeld
python3 -m py_compile scripts/notemeld-agent.py
git diff --check
```

结果：全部通过。

扩展运行 `PYTHONPATH=backend pytest -q backend/tests/agent_host`：`34 passed, 8 failed`。8 项失败均在本变更 focused 范围之外：5 项因当前 pytest 环境未安装 `pytest-asyncio`，1 项为既有 preference mock 对所有 session 返回同一值，2 项为既有 TurnManager 测试未提供 conversation/agent_turns 数据库或相应 mock。未将这些失败冒充为通过，也未在本任务中安装依赖或修改无关测试。

## 真实 SDK wheel/native fake turn

输入 artifact：

```text
/Users/hehejie/ai/notemeld-agent-sdk/dist-native/x86_64-apple-darwin/notemeld_agent_sdk-0.1.0-py3-none-macosx_11_0_x86_64.whl
```

在临时 Python 3.14 venv 中以 `pip install --no-deps` 安装，确认包内存在 `notemeld_agent_sdk/native/libnotemeld_agent.dylib`，随后用 packaged `Runtime` 和 fake model driver 执行 Turn。

关键结果：

```text
SDK_VERSION=0.1.0
SCHEMA_VERSION=1
events=6
terminal=turn.succeeded
```

临时 venv 已移动到系统废纸篓，可恢复或清理。

## 清理门禁

- 已删除无生产/CI 调用的 `agent-sdk/examples/python-host/test_smoke.py`。
- 已禁用并删除 Python oracle rollback 行为；`python`、`python-oracle`、`legacy` 均 fail-closed。
- `agent-sdk/bindings/python` 暂未删除：NoteMeld 生产 runtime 不引用它，但当前仓库的 SDK artifact CI 与契约测试仍将它作为输入；必须先把 CI 迁到独立 SDK 仓库。
- `backend/app/agent/core` 暂未删除：仍有 11 个生产 adapter/service 调用，且 native executor 的 tool driver 尚未完成替代。按 Spec 禁止误删。
