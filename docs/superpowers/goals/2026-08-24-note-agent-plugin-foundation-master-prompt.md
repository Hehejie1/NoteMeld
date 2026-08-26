# Note Agent 与插件化个人知识库总控 Goal 提示词

Canonical requirement：`../../requirements/2026-08-24-note-agent-plugin-foundation.md`

此提示词用于一个总控 Codex Goal。总控只维护依赖、检查点、验收状态和交接，不让多个 Agent 同时编辑两个仓库的共享文件。每个实现 Goal 的具体提示词分别位于：

- `../../../../notemeld-agent-sdk/docs/superpowers/goals/2026-08-24-stateless-note-agent-foundation-prompts.md`
- `2026-08-24-desktop-note-agent-plugin-integration-prompts.md`

```text
/goal 完成“Note Agent 与插件化个人知识库一期基础”总需求。工作区为 /Users/hehejie/ai/notemeld-project，包含两个独立 git 仓库 notemeld-agent-sdk 与 NoteMeld；任何分支、提交、测试和状态都必须按仓库隔离。先完整阅读 NoteMeld/docs/requirements/2026-08-24-note-agent-plugin-foundation.md，以及两个 child Requirement/Plan/Spec/Test/Goal 手册。

严格按以下 DAG 推进：SDK S01 →（S02 与 S04 独立 worktree 并行）→ I01 →（S03 与 S05 独立 worktree 并行）→ I02 → S06 → S07 → S08。S08 必须提供固定 SDK version/schema/ABI/commit、artifact SHA-256、supported conformance、迁移说明和 handoff；未通过时不得开始 NoteMeld 代码实现。

SDK S08 通过后，再执行 NoteMeld N01 →（N02、N03、N04 独立 worktree 并行）→ I03 →（N05、N06 独立 worktree 并行）→ I04 → N07。NoteMeld 只能消费固定 SDK artifact，不修改 SDK，不建立第二 Agent loop 或第二 Note 正文权威。N07 必须以真实桌面安装插件→链接生成 Note→外部 MCP 读取→CLI 创建关联 Note→桌面恢复关系，以及 candidate 修改 SDK 被拒绝作为纵向验收。

每个 Goal 开始前检查前置状态和固定 commit；并行 Goal 不编辑共享 manifest/migration/router/nav/ABI 文件，共享冲突由对应 I01/I02/I03/I04 集成检查点处理。每个 Goal 必须运行 Spec 测试、更新 Test evidence、提交独立分支并汇报 commit/命令/计数/风险；测试失败、UNVERIFIED 或外部工具链缺失时保持未完成，不得跳过或降低 supported 范围。未经用户授权不 push、tag、上传 Release 或自动激活 Application candidate。只有两个 child requirements 都为 Implemented 且 N07 通过，才将总 P7 标记 Implemented。
```
