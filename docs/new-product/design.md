# NoteMeld Desktop Prototype Design

## Product documentation and explanation mode

`docs/new-product/config/feature-registry.json` is the configuration source for
page features, architecture layers, data ownership, and open decisions. Each
feature records its description, API/capability mapping, storage tables, state
transitions, implementation status, and explicit selector bindings. The
prototype catalog provides two modes: Preview performs normal page interaction;
Explain intercepts bound element clicks and opens a dialog with the feature
mapping. A01, A02, and A03 are separate documentation surfaces for multi-platform
architecture, data design, and the complete feature registry.

## Design read

本项目是本地优先的开发者 Agent 工作台，不是营销页。视觉方向是冷静、中性、可长时间阅读的工作台，使用单一 NoteMeld 蓝色作为操作强调色。页面信息层级、区域职责和交互语义在浅色与深色主题中保持一致。

设计模式：保留现有信息架构的定向演进。

## Dials

- `DESIGN_VARIANCE: 4`：稳定、克制，优先可扫描性。
- `MOTION_INTENSITY: 3`：只使用页面进入、状态反馈和按钮反馈，不使用持续装饰动效。
- `VISUAL_DENSITY: 6`：工作台需要承载会话、能力和设置列表，但使用留白与分组控制密度。

## Semantic tokens

### Light

| Token | Value | Usage |
|---|---|---|
| `--nm-bg` | `#f7f8fb` | Agent 主工作区背景 |
| `--nm-surface` | `#ffffff` | 侧栏、卡片、输入区 |
| `--nm-surface-muted` | `#f1f3f8` | 工具调用、次级控件背景 |
| `--nm-border` | `#dfe4ec` | 主边框 |
| `--nm-border-soft` | `#edf0f5` | 分隔线 |
| `--nm-text` | `#202533` | 主文本 |
| `--nm-muted` | `#7d879a` | 说明、次级文本 |
| `--nm-accent` | `#4b7cf3` | 主按钮、选中态、链接 |
| `--nm-accent-strong` | `#2864e8` | hover、焦点和强调文本 |
| `--nm-accent-soft` | `#e8efff` | 选中背景、轻提示 |

### Dark

| Token | Value | Usage |
|---|---|---|
| `--nm-bg` | `#101522` | Agent 主工作区背景 |
| `--nm-surface` | `#181f31` | 侧栏、卡片、输入区 |
| `--nm-surface-muted` | `#202a40` | 工具调用、次级控件背景 |
| `--nm-border` | `#303b55` | 主边框 |
| `--nm-border-soft` | `#27324a` | 分隔线 |
| `--nm-text` | `#f2f5fc` | 主文本 |
| `--nm-muted` | `#9da9c0` | 说明、次级文本 |
| `--nm-accent` | `#769aff` | 主按钮、选中态、链接 |
| `--nm-accent-strong` | `#9fb7ff` | hover、焦点和强调文本 |
| `--nm-accent-soft` | `#22345d` | 选中背景、轻提示 |

主题只替换语义 token，不改变布局、组件顺序、圆角规则或操作含义。禁止在单个页面中途切换主题色块。

## Component rules

- 圆角规则：卡片和面板 `10px` 到 `14px`，小控件 `7px` 到 `9px`，发送按钮保持圆形。
- 边框优先于阴影表达区域关系；阴影只用于浮层、输入区和 hover 提升。
- 所有可操作元素必须有 hover、focus-visible 和 active 状态；不能只靠颜色表示状态。
- 核心操作保持完整文字，窄宽度下次要文字可收缩，但通过 tooltip 或 aria-label 保留语义。
- 图标统一复用本地 vendor 的 Lucide 开源图标库，沿用 `icon-workflow` 的 outline、24px 网格、2px round stroke、`currentColor` 规则。禁止 emoji、icon font 和未经注册的自绘 SVG。

## Motion rules

- 动效只服务于层级、反馈或状态变化。页面内容进入使用短暂 opacity/translate，按钮使用轻微位移反馈。
- 不动画布局属性；只动画 `transform` 和 `opacity`。
- 不使用持续循环动效，不为静态信息添加 GSAP。
- `prefers-reduced-motion: reduce` 下所有过渡与进入动画降级为即时状态。

## Desktop page contract

- 桌面端保留四个页面：D01 新对话、D03 会话列表与详情、D06 插件应用、D09 设置。
- D01/D03 继续使用 Agent、侧边文件面板、底部命令行/日志面板的工作区结构；两个面板独立控制。
- D06 顶部左侧是能力 Tab，右侧是搜索、刷新和当前类型的添加操作。
- D09 左侧是设置分类，右侧是对应内容；浅深色只替换语义颜色。

## Application layer contract

主框架的“应用”是一级入口，应用内部使用自己的二级导航和业务工作区，不能把所有业务功能继续堆进 D06 或 D09 的设置列表。应用壳层必须保留当前 Workspace、连接状态、主题、权限和全局搜索等宿主语义；右侧内容由当前应用负责。

- APP01 笔记应用：笔记库、样式/模板、Wiki 图谱与文章、关系重建、旧笔记和 Markdown 导入。
- APP02 学习应用：学习空间、学习画布、掌握验证、复习、可编辑语义白板、卡片/关系和发布笔记。
- APP03 监控应用：Token/供应商/任务聚合，以及部署、GPU、CUDA、MCP、自动启动和插件/转写健康。
- APP04 系统运行：Agent Turn 诊断、Application 实例和文件权限、候选审批/安全声明、桌面更新、设备/LAN/Relay/远程帧。

视频、音频、网页采集，转写器/Whisper，下载器/Cookie，OCR、视频帧、文档解析、证据锚点和知识切片审阅属于 D06 管理的插件能力；应用只消费它们通过 Host 暴露的状态和结果。导入/导出迁移包、合并、索引重建和迁移任务保留为系统能力，不在本轮应用目录中展示。

应用页面必须区分 loading、empty、running、approval、failed、completed 和 unavailable 状态；任何指标、列表或健康状态都不得用静态数字冒充真实后端状态。

## Design system document contract

`A04 组件库设计` 是跨端设计语言的唯一原型查看入口，分为两个一级菜单：`设计价值观` 和 `组件库`。

设计价值观必须说明 NoteMeld 的产品北极星（AI 编译知识，人验证和消费）、清晰优先、简化交互但不隐藏重要信息、状态透明、安全可逆、跨端一致但不强求相同，以及可访问性默认开启。每条原则都需要有可验收的判断问题。

组件库只维护 Design Tokens、基础交互原语、状态语义和跨端适配规则，不维护 Session、Agent、Workspace、Wiki、设备管理等业务组件。基础原语的 HTML 参考实现必须能展示变体、状态、桌面/移动差异、键盘/触摸行为和错误/加载/空状态；各平台生产代码使用自己的原生实现，但遵循相同语义契约。

## Cloud page contract

- C01 是普通用户与管理员共用的认证入口；登录表单不提供角色选择，登录后的权限决定可见菜单和数据范围。
- C01 不提供自行注册。未获权限的用户只能提交访问申请，采集邮箱、设置密码、确认密码、姓名或称呼和选填申请说明；申请进入管理员人员管理，由管理员审核后再建立账号或授予权限。
- 云端准入只有两种方式：用户申请访问、管理员发送邀请。管理员不得替用户设置或查看密码；服务端只保存密码哈希。
- 申请状态为待审核、已同意、已拒绝、已撤回/已过期。审核通过后，申请记录与成员记录保持同一身份关联，不复制出第二份互不关联的数据。
- 设备配对使用一次性、短时有效凭证交换设备公钥。二维码、短码和链接禁止携带永久密钥；撤销后旧凭证立即失效。
- 用户桌面/移动设备与云端运行节点是两类实体，页面和文案不得混用。
- 云端会话复用桌面端 Agent 的视觉与操作模型，但必须标注云端运行位置、云端沙箱、后台持续运行、资源额度和共享权限。
- C02 是云端 AI 工作台而不是单个会话聊天页，优先展示云端会话入口、搜索筛选、会话状态、Workspace 上下文和后台运行摘要。
- C03 负责单个云端会话的消息、Agent 执行过程、工具调用、审批、产物和同步状态。
- 云端状态必须同时使用图标、文字和语义颜色；Light/Dark 主题保持相同层级、位置和交互含义。
- C02 桌面宽度使用紧凑导航、主会话列表和次级运行摘要；窄宽度先隐藏次要元数据，不压缩会话标题的可读宽度。
- 当前云端页面固定为六页：C01 登录页面、C02 AI 工作台、C03 云端会话、C04 人员管理、C05 设备管理、C06 设置页面。Workspace 不单独占用页面，而是作为 C02/C03 的上下文。
- C04 仅在管理员权限返回时显示；C06 中的资源、异常和审计内容也按管理员权限显示，不新增独立的 C07 页面。
- 云端工作台采用统一顶部导航 Tab：工作台、会话、设置；右上角展示当前用户信息，菜单提供修改用户信息和退出登录。C02 主体展示工作台会话列表，C03 展示单个云端会话。
- C06 设置页左侧分类固定为通用、人员管理、设备管理；人员管理和设备管理仍保留独立页面内容，设置页分类用于进入对应管理区域。
