# Agent ToolDriver 产品能力链路执行规格

Canonical requirement: [`../../requirements/2026-08-19-agent-tool-driver-chain.md`](../../requirements/2026-08-19-agent-tool-driver-chain.md)

## 生产代码

### `backend/app/agent_host/drivers/tools.py`

- 定义稳定产品错误 code 与安全文案。
- `describe(names)` 兼容 sync/async registry。
- `invoke(call, context, on_progress)`：
  1. 校验 call id、tool name、arguments object。
  2. 通过 `registry.get_tool()` 确认 capability，并读取 `input_schema`/`parameters`。
  3. 校验 required、基础类型、字符串/数字边界。
  4. 只调用 `registry.invoke()`，不直接调用业务服务。
  5. 返回 `{call_id, output:{ok:true,result}}`。
  6. 将产品错误转换为 `{call_id, output:{ok:false,error:{code,message}}}`。
- 不把 context、arguments、异常原文写入日志或结果。

### `backend/app/agent_host/capabilities.py`

- 保持 `wiki:search`、`note:search`、`note:read` 有界只读 descriptor。
- 未知 capability、非法输入、Note 不存在分别使用显式产品异常。
- 继续复用 `WikiSearch`、`search_note_documents_by_title`、`read_note_document_by_title`。

### `backend/app/agent_host/native_executor.py`

- `tool.describe` 通过 ToolDriver，而不是直接绕到 registry。
- `tool.invoke` 调用 ToolDriver 后校验 ToolResult call id/output，ABI driver completion 返回 `result.output`。
- 产品级错误仍是 `ok:true` ToolResult，交由 SDK 写 tool message 并继续下一轮；Host/ABI 格式错误才是 driver-level `ok:false`。

## 测试

- `test_tool_driver.py`：sync/async describe、成功结果、未知工具、非法参数、权限、业务、异常脱敏。
- `test_capabilities.py`：现有服务调用、未知/不存在分类。
- `test_native_executor.py`：ToolResult output ABI 映射。
- `test_tool_scheduler_integration.py`：使用已安装并校验的 standalone SDK native artifact，验证完整两轮模型链与共享 Host 多 Session 隔离。

## 验证命令

```bash
python3 -m compileall backend/app
PYTHONPATH=backend python3 -m pytest backend/tests/agent_host -q
```

若主工作树 venv 未安装 pytest，使用本机现有 pytest runner 与该 venv 的应用依赖组合执行，并在验证证据中如实记录。
