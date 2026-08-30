# Change Spec：桌面端侧加密运行时与安全落盘

更新时间：2026-08-30

## 0. 预检查

云服务 requirements 已声明 `cryptography`，但桌面 sidecar 的核心打包依赖没有声明；原 E2EE 原语位于 PyInstaller 不收集的 `cloud/` namespace。开发虚拟环境已有依赖，因此既有源码测试无法发现发布包缺口。

## 1. 目标

- cloud 与桌面 packaged backend 锁定相同的 `cryptography` 运行时。
- 将 Python/桌面端侧 E2EE canonical 实现放入 `backend/app/cloud_sync/e2ee.py`，由现有 `collect_submodules("app")` 收集。
- 删除 cloud 侧仅供客户端使用的加密 helper，避免 cloud/backend 物理分离被反向 import 破坏；cloud Relay 只消费 opaque protocol，不获得私钥或解密能力。
- token 临时文件创建即为 `0600`，写入和 rename 具备崩溃安全边界，替换失败保留旧值并清理临时文件。
- 拒绝包含 NUL 的握手 identity、非法 key 长度和非严格 Base64 输入。

## 2. 明确不做

- 不在本切片接入 macOS Keychain、Windows Credential Manager 或 Linux Secret Service；平台 adapter 后续提供 32-byte store key 和设备私钥。
- 不启动 WebSocket，也不改变 cloud relay 的 opaque/non-persistent 语义。
- 不把进程内 `SessionCipher` cursor 当作 durable mailbox/replay cursor 的替代品。

## 3. 验收

- cloud 与 desktop requirements 包含相同精确 crypto pin。
- canonical E2EE 模块可被桌面 PyInstaller 收集，cloud 源码不反向导入 backend。
- E2EE round trip、AAD authentication、replay/rekey 与非法输入测试通过。
- token replace 失败后仍能读取旧 token，且不存在遗留临时文件。
