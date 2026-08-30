# Change Spec：LAN-first 认证直连与云 Relay 回退

更新时间：2026-08-30

## 0. 预检查

已有 `connection_candidates()` 会优先尝试 LAN 地址，但候选 URL 指向云 Relay 路径，本地 FastAPI 没有对应端点；如果平台继续携带 cloud bearer 连接 `ws://`，局域网监听者可直接窃取凭证。Python 和 Web 帧加密算法也分别为 ChaCha20-Poly1305 与 AES-GCM，无法互通。

## 1. 目标

- 云端新增 `/v1/lan/authorize`：只接受绑定宿主设备、具有 `grant.read` 的 `device-api` token，返回最长 60 秒的 controller 公钥、Grant、scope、workspace 和 authority epoch 断言。
- 本地新增 `/v1/lan/connect/{session_id}`：不接受 cloud bearer，执行 peer-IP 绑定的一次性 Ed25519 hello/challenge/proof。
- 只允许显式 RFC1918、IPv4 link-local/loopback、IPv6 ULA/link-local/loopback 地址；拒绝 unspecified、multicast、公开和文档保留地址。
- 授权后只接受 assertion 精确绑定的 `notemeld.sync.v1` command frame，并限制握手大小、握手时间、帧大小和每分钟帧数。
- Python/desktop 与 WebCrypto 统一 AES-256-GCM；canonical fixture 同时由 Python 和 Node WebCrypto 解密验证。
- `EncryptedRemoteHostHandler` 完成 AEAD → `RemoteHostAuthority` → durable mailbox 链路；只有提交成功才返回无业务内容的最小 received receipt。
- handler 的业务结果必须使用反向 encrypted `RemoteFrame`；明文响应只允许 receipt allowlist。

## 2. 安全边界

- LAN endpoint 只是候选地址，不能授予权限。
- 控制端不向 LAN peer 发送 account/device/share token。
- 云断言必须匹配 session、controller、host、Grant、workspace 和 epoch；客户端不能扩展 scope。
- challenge 一次性、短期、绑定实际 socket peer 地址，并有全局/单 peer pending 与 verification 限流。
- authorization 最长 60 秒；到期关闭连接并重新向云端验证，以限制撤销传播窗口。
- E2EE session key 和设备私钥仍由平台 Keychain/Keystore/Secret Service 管理，云端和 LAN transport 都不持有明文业务 payload。

## 3. 明确不做

- 本切片不实现 mDNS/Bonjour/NSD 自动发现，也不解决 IPv6 link-local interface scope 映射。
- 不在启动时从环境变量读取长期 device token 或私钥；平台安全存储 adapter 后续显式安装 `LanDirectService`。
- Web `openRelayWebSocket()` 只为 cloud Relay 候选发送 bearer 子协议；LAN 候选必须由调用方提供 `LanHandshake`，缺少时自动回退 Relay。
- 不在 LAN transport 内复制 Agent loop；durable command 仍由 canonical Host/SDK executor 消费。
- cloud Relay 多实例 Pub/Sub adapter 仍是独立后续工作。

## 4. 验收

- account token、错误宿主 token、撤销/过期/错误 workspace Grant 无法获得 LAN 断言。
- proof 无法重放，不能跨 peer IP 使用，过期和错误签名 fail-closed。
- 错 session/sender/recipient/epoch/type/sequence 的 frame 被拒绝。
- AES-GCM tag 验证和 durable enqueue 都成功后才返回 received；队列重开后 command 仍存在。
- LAN 不可达时既有 `connect_with_fallback()` 继续尝试 cloud Relay。
