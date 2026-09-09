# 多端同步需求与方案专家评审

日期：2026-08-29  
评审对象：Requirement / Plan / Spec 及当前 NoteMeld 仓库事实  
评审维度：安全、分布式稳定性、性能、平台交付、商用运维

## 总结结论

产品方向可行，但当前方案还不能称为商用安全规格。建议先完成 P0 阻塞门禁，再进行一期 mock/内部联调；P1 项目在公网 Beta 前完成。

## P0 阻塞项

1. 用户名不唯一，不能用于唯一登录定位；必须使用云端 `login_handle/account_id + password` 或已注册 device token。
2. relay 不能继续使用“GET after cursor”的伪历史语义；应使用实时长连接，宿主 `received` receipt 才是成功边界，断线不落云端且不自动重试。
3. E2EE 目前只有 AEAD/sequence 描述，缺少成熟握手、设备认证、抗 MITM、前向保密、重连密钥轮换、设备撤销和多设备成员变更。
4. queue authority 缺 lease/fencing/epoch；云端多实例或宿主崩溃可能双执行。需要持久 command ledger、CAS admit、崩溃恢复和 `needs_attention`。
5. 云端 Agent 必须补 tenant/workspace 隔离、工具 allowlist、沙箱、文件路径边界、MCP SSRF 防护、资源/并发配额和网络出口策略。
6. API 缺 JSON schema、错误码、幂等键、事件 cursor/gap、版本兼容和分页/大小限制，无法支撑多端并行实现。
7. 云端 workspace 本地磁盘缺少原子写、备份恢复、容量告警、加密、迁移和磁盘满策略；当前只能视为单节点开发/内部部署方案。
8. relay 必须禁止请求体日志、APM body、崩溃 dump 和请求录制；只能保留最小化元数据和安全审计字段。

## P1：公网 Beta 前完成

- 管理员 bootstrap 的轮换、RBAC、限流、审计和事故响应。
- token/密码/恢复密钥、设备丢失、全量撤销和 share token 管理。
- 事件/快照分段、大文件分片、断点续传、保留和删除语义。
- 移动端后台 WebSocket/推送/省电/系统杀进程恢复。
- Windows/macOS/Linux 的签名、安装、更新、回滚和 Linux 发布矩阵。
- 插件/Application 签名、兼容矩阵、撤销和关联数据边界。
- 计费/配额、滥用封禁、SLO、告警、状态页、备份和隐私导出/删除。
- load、chaos、fuzz、迁移、跨端 contract 和安全回归测试。

## P2：后续增强

- 真正直连的 WebRTC/QUIC + STUN/TURN；当前先使用 relay-mediated E2EE。
- 云 workspace 对象存储、多副本 HA 和跨区域容灾。
- 字段级冲突自动合并和完整应用 marketplace。

## 已写回文档

- Requirement 已补充三种数据面、登录主体、relay 实时语义和商用门禁。
- Plan 已补充 FastAPI/cloud 目录、Agent 复用方式、P0 安全阶段和一期 vertical slice。
- Spec 已补充 login handle、password hash、WebSocket relay、host receipt、非持久化 RemoteFrame 和 P0/P1 门禁。

## 用户后续确认（2026-08-29）

- 云端账号由 bootstrap admin 管理，普通用户由后台 CRUD 创建；本地 profile name 与云端登录身份分离。
- 第一版允许局域网优先连接，失败回退云端 relay；relay 仍不持久化 remote 消息。
- E2EE 采用成熟开源密码库，不自研密码学；云 workspace 默认云端本地磁盘。
- 云 workspace 提供原子写/崩溃恢复、备份恢复、容量告警和迁移状态可见性；读默认允许，写/删/执行需授权。
