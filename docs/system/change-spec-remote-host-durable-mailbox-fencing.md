# Change Spec：Remote Host Durable Mailbox 串行与 Fencing

更新时间：2026-08-30

## 0. 预检查

已阅读系统架构、产品规则、数据模型、API inventory、known pitfalls，并检查 `backend/app/cloud_sync/queue.py`、protocol 和测试。当前类没有产品 router 调用方，属于 remote Host adapter contract。

## 1. 当前系统现状

`DurableSessionMailbox` 已用 SQLite 保存 queued/admitted command，但连续 `pop()` 可把同一 session 的多条命令同时变成 admitted；进程重启后 admitted 状态不会转为需要人工恢复；authority epoch 只记录在 command 上，没有 session fencing authority。

## 2. 本次目标

- 每个 session 同时最多一个 `admitted` Turn。
- 构造 mailbox 时通过进程级 lease owner 把上次进程遗留的 `admitted` 标成 `needs_attention`；同进程多个 adapter 不误判，恢复前阻止新 command 和下一条执行。
- 用户显式 `resume` 或 `abandon` 后才能继续。
- authority epoch 只能单调增加；轮换时 active Turn 进入 `needs_attention`，queued command 原子重绑到新 epoch，旧 epoch enqueue 被拒绝。
- 完成/失败使用 CAS 状态更新并报告是否真正终结 active command。

## 3. 明确不做

- 不复制 Agent SDK 状态机，不自动重放未知工具副作用。
- 不在本次接入 WebSocket 常驻进程或移动端 UI。
- `SessionMailbox` 仍是测试/临时进程内队列；remote Host 必须使用 durable 实现。

## 4. 影响与兼容

新增独立 `sync_mailbox_authority` 表和 nullable `sync_mailbox.lease_owner` 补列，不使用共享 `PRAGMA user_version`；启动时从旧 `sync_mailbox.authority_epoch` 幂等回填。既有 queued/completed 数据保持可读。`complete()` 由无返回值收紧为布尔 CAS 结果，当前没有生产调用方。

## 5. 验收

- 连续及跨重启 `pop()` 都不会产生第二个 active Turn。
- crash 遗留状态拒绝新 command，显式恢复后按原序继续。
- stale epoch enqueue 失败；authority rotation fence active Turn 并保留 queued 顺序。
- completed/failed/abandoned 不再出现在 pending 列表。
