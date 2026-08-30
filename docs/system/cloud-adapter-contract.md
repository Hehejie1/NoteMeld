# NoteMeld 跨端云同步适配契约

本文定义桌面端、Web、Android、iOS 和 Harmony 对 `cloud/` 与
`backend/app/cloud_sync/` 的最小接入边界。Agent loop、会话状态机和命令
队列语义由宿主 runtime 负责，平台适配层不得复制实现。

## 设备身份

每个安装实例生成一个持久化的随机安装标识；设备 ID 使用
`<platform>-<install-id>`，其中 platform 取 `desktop`、`web`、`android`、
`ios` 或 `harmony`。安装标识不是密码，也不能从设备 ID 推导 Token。

平台安全存储要求：

- 桌面端：系统 Keychain/Credential Manager/Secret Service。
- Web：加密 IndexedDB；禁止把云 Token 写入 localStorage。
- Android：Android Keystore。
- iOS：Keychain，使用 device-only 访问级别。
- Harmony：系统安全存储。

## 设备生命周期

登录成功后适配层必须：

1. 注册设备（重复注册必须安全幂等）。
2. 发送一次立即心跳。
3. 按云端 `device_online_ttl_seconds` 的三分之一左右周期发送心跳。
4. 注销或宿主停止时停止定时器。

心跳失败不能删除本地会话或队列；下次网络恢复时先重新注册/心跳，再恢复
Relay 或同步任务。

## 连接策略

1. 使用受控端上报的私有 LAN endpoint 尝试 `ws://` 直连。
2. LAN 连接失败后回退到云端 `wss://` Relay。
3. 远程云端地址必须是 HTTPS；HTTP 只允许本机开发地址。
4. Relay 只传递加密 envelope，不发送明文会话内容。

## Relay envelope

所有平台必须实现同一协议版本 `notemeld.sync.v1`，并校验：

- `session_id`、发送方和接收方设备 ID。
- 单调递增的发送序列号和 `authority_epoch`。
- `frame_id`、12 字节 nonce、`frame_type`。
- AEAD ciphertext 和绑定 envelope 元数据的 AAD。

收到 `host_offline`、`invalid_envelope` 或权限错误时，控制端必须将本次
发送标记为失败；不能把未送达消息伪装成本地已完成。受控端收到命令后先
写入本地 durable mailbox，再回传 receipt；处理完成后再标记 mailbox
completed。

## 本地队列与恢复

平台适配层只调用 `DurableSessionMailbox`（或等价的原生实现）：

- `enqueue` 使用客户端 request id 幂等。
- `pop` 后状态为 admitted，崩溃重启后必须可恢复。
- 用户选择继续时回到 queued，选择放弃时变为 abandoned。
- 队列和本地会话数据不得放入云端 Relay 的临时消息存储。

## workspace 与本地专属数据

本地 workspace 默认只读；写入、删除和危险工具必须经过宿主确认。分享快照
可以同步会话历史、摘要、压缩信息、长期记忆、工具记录和 workspace 文件，
但必须排除本地密钥、Token、插件包、Skill 包和 Application 包。远端展示
缺失工具时应提示“当前设备不可用”，不得静默执行替代工具。
