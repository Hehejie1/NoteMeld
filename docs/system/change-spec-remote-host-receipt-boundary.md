# Change Spec：Remote Host Received Receipt 边界

更新时间：2026-08-30

## 0. 预检查

已阅读系统文档并检查 Relay envelope、Python protocol、durable mailbox 和 tests。当前云 Relay 能返回 `relay_accepted`，但本地 Host 没有统一 adapter 保证 command 已持久化后才回 `received`。

## 1. 目标

- 提供 `RemoteHostAuthority` 作为“已完成 AEAD 解密”到本地 durable queue 的唯一入站边界。
- 严格校验 frame、目标设备、会话/发送设备/epoch 授权及 command JSON shape。
- 只有 `DurableSessionMailbox.enqueue()` 提交成功后才生成无明文的 `received` receipt。
- 统一映射 `invalid_frame`、`wrong_recipient`、`permission_denied`、`invalid_payload`、`queue_full`、`recovery_required`、`payload_conflict`、`authority_mismatch` 和安全的 `host_unavailable`。
- 暴露 claim/complete/fail/recover/rotate authority 薄适配，不复制 Agent loop。

## 2. 明确不做

- 不在 Host adapter 内解密或保存设备私钥；平台安全层必须先用 frame AAD 验证 AEAD。
- 不把 `relay_accepted` 当作 delivered，也不让云端创建本地 receipt。
- 不在本次启动常驻 WebSocket 或调用 Agent SDK；executor 后续消费 claim 结果。

## 3. 影响与兼容

新增 `backend/app/cloud_sync/remote_host.py` 和导出，不修改现有本地 router、数据库或 Agent runtime。同步收紧 Python `RemoteFrame` 的字段类型、大小和 strict Base64 nonce 校验，与 Web validator 方向一致。

## 4. 验收

- receipt 返回时重开 SQLite 仍可看到 command。
- 同 request 重试不重复入队，receipt 不含 input。
- 错 recipient、未授权、额外字段、错误 JSON 和空 identity fail closed。
- Host 通过同一 adapter 仍保持单 active Turn 和显式崩溃恢复。
