# Change Spec：Cloud 设备绑定 Token

更新时间：2026-08-30

## 0. 预检查

已阅读系统架构、产品规则、数据模型、API inventory、known pitfalls，并检查 `cloud/app.py`、`cloud/db.py`、Python/Web cloud client 及 cloud backend tests。

## 1. 当前系统现状

Cloud 已有账户 login/PAT、设备注册、Ed25519 challenge、设备撤销和 scoped API。Bearer token 仅绑定用户；设备撤销只撤销 grant，因此泄漏到已撤销设备的 token 仍可访问 API。

## 2. 本次目标

- 已注册设备完成最近一次 Ed25519 私钥证明后，可用账户 token 领取短期 `device-api` token。
- token 持久化 `device_id`、audience、scope 和 expiry，只保存摘要。
- 设备撤销在同一事务撤销其 grant 和全部设备 token；后续请求稳定返回 401。
- token rotation 保留设备绑定、audience、scope 和 expiry。
- 设备公钥轮换撤销旧设备 token 并要求重新 proof；client 交换成功后用设备 token 替换本地账户 token。
- 默认原子撤销用于交换的 bootstrap token，避免被撤销设备继续持有不受设备状态约束的账户凭证；独立可信管理端可显式保留源 token。

## 3. 明确不做

- 不实现每个 HTTP 请求的 DPoP 签名；本次是“签发时 PoP + TLS bearer + 安全存储”边界。
- 不改变账户 login/PAT，也不让 device token 创建 PAT 或其他 device token。
- 不开发原生平台私钥存储 UI。

## 4. 冲突分析

改动不触及本地 Note/Conversation/Agent 表，不改变 `/api`、MCP、CLI 或桌面启动。`tokens.device_id` 是 nullable 向前兼容补列；旧账户 token 保持可用。设备 token scope 禁止 `*`、`admin` 和 `auth.token`。

## 5. 影响范围

- Cloud：`cloud/db.py`、`cloud/app.py`
- Adapter：`backend/app/cloud_sync/client.py`、`frontend/src/services/cloud.ts`
- API：新增 `POST /v1/devices/{device_id}/token`；`GET /v1/auth/me` 和 token list 增加 audience/device_id 投影。
- 测试：Cloud backend、Python adapter、Web source contract。

## 6. 实施与验收

1. `tokens` 增加 nullable `device_id`，旧库启动时幂等补列。
2. token 签发要求账户 audience、`device.write` scope、active device 和五分钟内有效的 Ed25519 proof；签发与默认撤销源 token 位于同一事务。
3. device token 有 5 分钟至 30 天的期限和非提权 scope allowlist。
4. auth join active device 状态；设备撤销原子撤销设备 token。
5. 覆盖未证明拒绝、签发、scope、轮换、设备撤销后 401 和 client path/payload。

回滚时可停止调用新增 endpoint；nullable 列和旧 token 均保持兼容，不需要破坏性 schema 回滚。
