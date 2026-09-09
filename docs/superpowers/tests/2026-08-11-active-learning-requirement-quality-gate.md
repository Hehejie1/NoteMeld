# 主动学习空间 Requirement Quality Gate

日期：2026-08-11
Canonical requirement：[`docs/requirements/2026-08-01-notemeld-agent-deep-learning-canvas.md`](../../requirements/2026-08-01-notemeld-agent-deep-learning-canvas.md)

## 结论

状态：通过，允许进入 Plan / Spec。

## 必过项

| 检查项 | 结果 | 证据 |
| --- | --- | --- |
| 保留用户原始意图 | ✅ | requirement §1 保留原始知识看板需求，并追加 2026-08-11 主动学习、本地+互联网、学术+GitHub 的确认 |
| 用户、场景、痛点、价值清楚 | ✅ | §2 明确“收藏/搜索不等于掌握”，新增掌握证据和专业来源缺口 |
| 目标是产品结果 | ✅ | §3 定义多源研究、持续画布、学习单元、证据评估、复习闭环 |
| 非目标明确 | ✅ | §4 排除 V1 多 Agent、未经确认的批量采集、用停留时长判定掌握 |
| 当前事实有代码依据 | ✅ | §5 对应 Wiki、Agent runtime、memory、workspace、web_search 雏形与前端图谱依赖 |
| 验收标准可验证 | ✅ | §7 共 11 条 GIVEN/WHEN/THEN，覆盖来源、持久化、掌握判定和失败降级 |
| 正常与失败路径 | ✅ | §8/§10 覆盖空结果、半失败、跳过诊断、来源冲突、断网和任务取消 |
| 约束完整 | ✅ | §9 覆盖本地优先、敏感配置、SSRF、成本、兼容和 mastery 证据 |
| 系统冲突已检查 | ✅ | §12 检查 product rules、data model、API、known pitfalls 与本地数据边界 |
| 开放问题不阻塞 | ✅ | §11 记录所有产品决策均已由用户确认 |
| 无敏感数据 | ✅ | 文档仅使用示例 endpoint 和占位来源，不含真实 key/token/payload |

## 不允许项

- 未把需求写成文件级实施方案；文件与接口细节进入 Plan/Spec。
- 未在需求层假定数据库字段；V1 持久化方案由 Spec 决定。
- 未用“优化/完善”代替可观察结果。
- 未删除或替代现有 Search、Wiki、Note、Chat、MCP、桌面或源码入口。

