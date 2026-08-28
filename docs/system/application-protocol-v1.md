# NoteMeld Application Protocol v1

状态：Active canonical protocol

本文是 NoteMeld 应用协议的长期权威文档。需求、执行计划、执行规格和验证证据只能引用本文，不能取代本文定义协议语义。

## 1. 协议与包边界

协议标识为 `notemeld.application.v1`。Application 是有界面的复杂工作空间；它可以包含自己的 HTML/CSS/JavaScript UI、可选后端、实例数据、运行记录和 Artifact。无界面确定性处理属于 Plugin 或 Workflow，不应伪装成 Application。

应用包以独立目录为边界：

```text
applications/<app-id>/
├── manifest.json
├── ui/<entry>
├── backend/<entrypoint>       # 可选
├── assets/
├── migrations/
└── README.md
```

Host 只在可信应用根目录下扫描一级目录。发现阶段只读取并校验 `manifest.json`、计算摘要和生成 catalog，不执行 UI 或 backend。用户点击后才进入实例和运行时生命周期。

## 2. Manifest

最小 manifest：

```json
{
  "protocol": "notemeld.application.v1",
  "id": "example.app",
  "version": "1.0.0",
  "name": "Example",
  "description": "A NoteMeld application",
  "ui": {"entry": "ui/index.html"},
  "runtime": {
    "kind": "managed-worker",
    "desktop_kind": "process-jsonl",
    "web_kind": "managed-worker",
    "entry": "backend/entrypoint"
  },
  "platforms": {"desktop": "supported", "web": "supported", "mobile": "unsupported"},
  "capabilities": ["wiki.read"],
  "permissions": [],
  "storage": {"scope": "application-instance", "workspace": "default"}
}
```

Host 必须拒绝协议不匹配、空或非法 id/version/name、缺失 UI entry、路径穿越、绝对路径、重复或未知 capability/permission、非法平台值、未支持 runtime、公开 listener、缺少包 entry 或超过包大小限制的包。权限和 capability 是申请声明，最终授权由 Host 决定。

可选声明包括配置 schema 和应用 migration registry。配置由 Host 在 runtime 启动前校验并按 app/instance 命名空间保存；敏感配置不能注入普通 UI 日志。

## 3. 生命周期与运行状态

默认生命周期：

```text
discovered → validated → cataloged
  → configuring → instance_ready → runtime_starting
  → bridge_ready → ui_loading → ready
  → stopping → stopped
```

任何阶段失败都进入可观察的 `failed` 或 `needs_attention`，不能显示空白页面或静默回退旧页面。Application Run 至少支持：`queued`、`running`、`waiting_user`、`cancelled`、`failed`、`completed`、`interrupted`。

Host 重启后，无法证明仍由当前 Host 持有 transport 的非终态 Run 必须收敛为 `interrupted`；未知非幂等请求不得自动重放。

## 4. Runtime transport

### Desktop `process-jsonl`

应用 backend 是 Host 监督的独立进程，通过继承的 stdin/stdout 通信，不监听公开 TCP 端口。Host 固定 cwd、环境变量、workspace 映射、网络出口和资源限制；应用不能取得宿主 session token、数据库连接或任意系统路径。

stdout 必须一行一个 JSON object，不能混入日志。Host 首先发送：

```json
{"protocol":"notemeld.application.v1","type":"hello","request_id":"<uuid>","app_id":"example.app","instance_id":"<id>","run_id":"<id>","sdk_version":"1.0.0"}
```

应用返回匹配身份、协议、SDK 版本和 request id 的 `type=ready`。调用使用 `type=invoke`，应用返回匹配 request id 和运行上下文的 `type=result`。EOF、非法 JSON、身份不匹配、超时、非零退出和错误 frame 必须转换为明确的 transport/runtime 错误。

### Web `managed-worker`

Web UI/backend 通过 Host gateway 调用受控 worker，不直连应用公网服务。应用版本是不可变部署单元，Host 注入 app/instance/user/run context，并控制超时、内存、CPU、并发、请求/响应大小、存储和网络出口。长任务统一登记为 Application Run/Job，可观察、可取消、可恢复。

当前 NoteMeld 已提供本地 managed-worker seam；真实云端 worker 部署属于后续 adapter，不改变本协议。

## 5. Host Bridge 与 Capability

所有调用都绑定 `app_id + instance_id + run_id`，Host 每次重新校验应用启用状态、平台、manifest、用户授权、实例归属和 capability authority。应用不得直接调用 NoteMeld 内部 router、ORM、SQLite 或宿主 DOM。

标准 capability 命名空间：

| Capability | 语义 |
| --- | --- |
| `wiki.read` | 读取 Wiki graph、节点详情、文章和分页/摘要数据 |
| `workspace.file.*` | 读写当前应用 workspace 的逻辑 file reference |
| `app.data.*` | 读写当前应用实例命名空间数据 |
| `artifact.*` | 创建和读取带来源的应用 Artifact |
| `agent.run` | 复用现有 Agent Host 发起受约束的 Agent Turn |
| `plugin.invoke` | 调用已安装、启用且获授权的插件 capability |

当前 HTTP bridge 入口为：

```text
POST /api/applications/runs/{run_id}/capability
POST /api/applications/runs/{run_id}/invoke
```

Wiki v1 adapter 实现 `wiki.read` 的 `graph` 和 `article` 方法。其他 capability 先冻结名称和授权边界，待对应 adapter 实现后开放。

## 6. 数据、文件与安全

- Application、ApplicationInstance、ApplicationRun、ApplicationArtifact 和 ApplicationSetting 属于独立应用域。
- 应用数据不能复制 Note/Wiki 事实；Wiki 的 graph/article 继续由既有 Wiki domain store 和 Note authority 维护。
- 默认 workspace 通过 `workspace://` 逻辑引用暴露；用户可在设置中修改根目录，Host 必须保持应用和实例隔离。
- 应用只能访问自己的 workspace 和声明 capability；不能使用绝对路径、`..`、宿主密钥、Cookie、session token 或内部数据库。
- 结构化结果应保存为可追踪 Artifact 或既有 Note/Whiteboard 引用，包含来源和运行上下文。

## 7. 版本兼容

协议版本、manifest version、SDK version、capability schema 和 artifact schema 分开版本化。Host 必须先校验协议主版本；minor 扩展只能增加可选字段或新 capability，不得改变已有字段和错误语义。破坏性变更提升协议主版本。应用声明的移动端不支持时必须显示明确状态，不得伪装可运行。

## 8. 当前实现范围

已实现：内建包发现、按需加载、Application Host、workspace/instance/run、桌面 JSONL handshake、Web 本地 managed-worker seam、Wiki capability 和 Wiki 应用 UI。

后续实现：用户应用包安装/升级、真实云端 worker、通用 HTML iframe/WebView 隔离加载、完整 Agent/Plugin/File/Artifact adapter、移动端独立 UI 和 Agent 自动生成应用。
