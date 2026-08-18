# Change Spec：Agent Host 收口第一阶段

日期：2026-08-18
状态：Implemented（NoteMeld 侧）

## 当前现状

NoteMeld 已通过独立 `notemeld-agent-sdk` 的 Python binding 加载 Rust native runtime。UI、CLI 和 `/api/agent/v1` 共用 NoteMeld Conversation，但 Host 仍有两个收口问题：产品工具请求会被统一标记为未接入，取消请求会直接把数据库 Turn 置为终态。

## 本次目标

1. 将 Note/Wiki 只读能力通过 `NoteMeldToolDriver` 接到 Host 的 product capability registry。
2. 取消只向同一个 native Turn 发送 cancel；数据库先记录 `cancelling`，最终状态由 SDK terminal event 决定。
3. 保持事件回放、幂等和历史 Conversation 结构不变。

## 明确不做

- 不接入 Harbor。
- 不把产品数据库表暴露给 SDK。
- 不在 NoteMeld 重新实现 Agent loop、工具调度或审批状态机。
- 不伪造 SDK 尚未提供的 approval resolve ABI。

## 影响范围

- `backend/app/agent_host/`：新增产品能力适配和 tool.invoke 路由。
- `/api/agent/v1/turns/{turn_id}/cancel`：改为 `cancelling` 请求语义。
- `agent_store`：支持非终态控制事件有序落库。
- `docs/system/`：同步运行架构和 API 语义。

## 验收

- Agent Host focused tests 通过。
- ToolDriver 可调用 `wiki:search`、`note:search`、`note:read`，未知能力 fail-closed。
- cancel 不直接产生 `cancelled`，并在 native handle 注册竞态后重试 cancel。
- Python 编译和 diff check 通过。

## 剩余风险

独立 SDK FFI 当前仍需后续版本补齐模型工具描述传递和 approval resolve ABI；本阶段 Host 已完成适配边界，但不能宣称审批闭环或真实模型工具循环全部完成。
