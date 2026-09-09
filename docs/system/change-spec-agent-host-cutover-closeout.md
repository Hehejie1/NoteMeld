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
- 不在 NoteMeld 内伪造 SDK 行为；approval resolve 必须调用独立 SDK 的 native control ABI。

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

## 收口补充（2026-08-18）

独立 SDK 已补齐 `tool.describe` 到 `model.stream` 的 descriptor 传递，以及 native approval control ABI；NoteMeld Host 已对齐这两个协议。相同 `idempotency_key` 的 HTTP 重试只返回原 Turn，不重复创建 Conversation message 或启动 native turn。SDK Rust workspace 的最终 cargo gate 仍需在隔离官方 registry 缓存可用时执行；本机用户级 TUNA 配置导致的一次编译探测在编译前停止，不能当作通过证据。
