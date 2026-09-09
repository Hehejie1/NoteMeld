# new-product 应用查询快照契约

日期：2026-09-08  
状态：Implemented in desktop prototype backend  
范围：APP01 笔记应用、APP03 监控应用

## 目的

为应用层提供稳定的只读查询边界，避免 APP01 直接拼接会话数据、APP03 由浏览器并行请求多个状态接口后产生不一致的健康结论。

## APP01 笔记库

`GET /api/notes/library`

查询参数：

- `q`：可选标题搜索字符串。
- `offset`：非负整数，默认 `0`。
- `limit`：`1..100`，默认 `50`。
- `wiki_status`：可选 Wiki 状态过滤。
- `status`：可选笔记状态过滤。

响应 `data`：

```json
{
  "items": [
    {
      "taskId": "task-id",
      "title": "笔记标题",
      "sourceUrl": "",
      "platform": "",
      "modelName": "",
      "style": "",
      "status": "SUCCESS",
      "wikiStatus": "ready",
      "createdAt": "2026-09-08T00:00:00+00:00",
      "updatedAt": "2026-09-08T00:00:00+00:00"
    }
  ],
  "pagination": {"offset": 0, "limit": 50, "total": 1}
}
```

数据权威是 `note_documents`，通过有效的 `conversations` 关联过滤软删除记录。该接口不返回正文，不执行 Wiki 重建，不触发 Agent 或文件读取；详情仍通过会话/笔记详情链路读取。

## APP03 监控快照

`GET /api/monitoring/snapshot?days=1`

`days` 范围为 `1..31`。后端在一次请求内固定 UTC `start_at/end_at`，聚合现有 usage、task summary、deploy status 和插件运行状态。

响应 `data` 的核心字段：

```json
{
  "window": {"days": 1, "start_at": "...", "end_at": "..."},
  "health": {
    "status": "healthy|degraded",
    "components": {"backend": "healthy", "cuda": "unavailable", "plugins": "degraded"}
  },
  "usage": {"total_tokens": 0, "record_count": 0, "overview": {}},
  "tasks": {"task_count": 0, "call_count": 0, "running": 0, "completed": 0, "failed": 0, "other": 0},
  "runtime": {},
  "plugins": {"ready": true, "failed_plugins": [], "status": "ready"}
}
```

当前 usage task summary 没有独立 Agent lifecycle status 时，任务会进入 `other`，不能被前端显示成 completed/running。后续接入 Agent diagnostics 聚合时，必须保留来源和同一时间窗口。

## 安全和失败语义

- 两个接口均为只读，不创建任务、不更新配置、不安装插件、不授权设备。
- 非法分页/时间窗口由 FastAPI 参数校验返回 `422`。
- 插件数据库不可用时返回 `plugins.status=unavailable` 和总体 `degraded`，不能返回 `ready=true`。
- 状态接口失败必须保留错误范围；客户端展示 degraded/unavailable，不将网络错误转成 healthy。
- 任何新增聚合字段必须回写 `docs/system/api-inventory.md` 和接口矩阵，并添加契约测试。
