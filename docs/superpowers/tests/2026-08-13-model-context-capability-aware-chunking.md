# 模型上下文与能力感知分块验证证据

日期：2026-08-13

Canonical requirement：[`docs/requirements/2026-08-13-model-context-capability-aware-chunking.md`](../../requirements/2026-08-13-model-context-capability-aware-chunking.md)

## Fresh 命令结果

### 后端定向

```bash
PYTHONPATH=backend python3 -m pytest \
  backend/tests/test_model_runtime_schema.py \
  backend/tests/test_model_runtime_catalog.py \
  backend/tests/test_model_runtime_api.py \
  backend/tests/test_token_budget.py \
  backend/tests/ai/test_models.py \
  backend/tests/ai/test_provider_compat.py \
  backend/tests/ai/test_chat_service_migration.py \
  backend/tests/ai/test_note_generator_migration.py \
  backend/tests/test_multisource_summary_contracts.py \
  backend/tests/test_multisource_video_collector_contracts.py \
  backend/tests/test_core_note_task_status_api.py -q
```

结果：exit 0；`157 passed, 13 subtests passed in 11.39s`。

### 后端全量单进程

```bash
PYTHONPATH=backend python3 -m pytest backend/tests -q
```

结果：exit 0；`621 passed, 17 subtests passed in 114.27s`；未发生 pytest 收集期 stub 污染。

### 前端契约

```bash
(cd frontend && pnpm test:contracts)
```

结果：exit 0；`tsc -p tsconfig.contract.json` 无错误。

### 前端生产构建

```bash
(cd frontend && pnpm build)
```

结果：exit 0；Vite 6.4.1 转换 13,090 个模块，`built in 1m 5s`。构建报告第三方 `lottie-web` 的 `eval` 告警和大于 500 kB 的 chunk 告警，无 TypeScript/Vite 错误。

### 核心回归

```bash
scripts/run_core_regression.sh
```

结果：exit 0；`27 passed in 1.62s`；脚本未报告失败或跳过项。

## 关键验收证据

- schema/API 契约覆盖 `models` 权威运行字段、旧 schema 仅清空两张模型配置表、幂等启动、目录精确/家族匹配、4096 fallback、完整添加/列表/删除响应及删除事务边界。
- AI/预算契约覆盖保存配置进入 `Model` / `ModelConfig` / `NotemeldGPT`、`supports_stream=false` 的 complete-to-stream 事件适配、聊天副本裁剪、tool call/result 成组和 token + byte 双预算。
- 笔记契约覆盖 `supports_vision=false` 直达 OCR 且不构造 grid/image payload、空 OCR 过滤、map/final 辅助上下文边界、Provider 上下文错误的一次 70% 重分块、缓存/checkpoint 保留，以及新笔记同步保存 task result、conversation `note_result` 和 `note_documents`。

## 失败、跳过与未验收

- 上述全部 fresh 自动化 gate 无失败且 `skip=0`；核心回归脚本未报告跳过。
- 未手动验收 Provider 编辑页“添加模型”弹窗及无内联“保存模型”。
- 未使用真实 Ollama 添加 `deepseek-r1:7b`、将端点实际窗口改为 16384，并在重启后核对 SQLite 与模型选择读取。
- 未使用真实 OCR/LLM 执行开启截图且 `supports_vision=false` 的视频笔记，未人工核对运行日志中 vision call 为 0。
- 未用 4096 实际端点重跑原 7.5 分钟视频任务。
- 未手动打开升级前历史笔记核对正文完整性。
- 因上述手动项待完成，canonical requirement 保持 `Planned`。
