# NoteMeld Semantic Infinite Whiteboard Design Spec

日期：2026-08-14
状态：Ready for implementation
Canonical requirement：`docs/requirements/2026-08-14-notemeld-semantic-infinite-whiteboard.md`
前置基线：`docs/requirements/2026-08-13-notemeld-research-note-whiteboard.md`

## 1. 决策摘要

- 唯一无限画布运行时选用 `@xyflow/react@12.11.3`，协议 MIT。
- 不依赖 React Flow Pro 代码、模板或服务；画布默认 attribution 保留，根目录第三方 NOTICE 记录上游仓库与 MIT 协议。
- React Flow 只处理坐标投影和交互；SQLite 中的 NoteMeld `Whiteboard/Card/Relation` 是权威业务模型。
- 旧 Sigma/Graphology 保留给 Wiki 图谱和 legacy LearningCanvas fallback，不继续承担新白板编辑。
- 白板是未发布草稿与空间结构的权威；Note 是用户确认发布的线性快照；Wiki 只编译 Note。

## 2. 系统上下文与增量边界

```mermaid
flowchart LR
  C["中间对话"] --> R["研究编译"]
  R --> LC["LearningCanvas v1/v2\n兼容产物"]
  R --> WB["Whiteboard\n可编辑草稿"]
  WB --> CARD["Cards"]
  WB --> REL["Relations"]
  WB -->|"用户确认发布"| NOTE["标准 Note"]
  NOTE --> WIKI["Wiki contribution / index"]
  CARD -->|"框选"| CTX["后端编译上下文"]
  REL --> CTX
  CTX --> C
```

保留现有行为：

- 学习标签仍是确定性研究入口，不新增 conversation mode。
- 歧义澄清阶段不创建 Note 或白板。
- 本地 Wiki + Academic + GitHub + 可选 Web 的搜索规则不变。
- Note 初次成功仍是研究正文成功边界；白板 seed 失败不诱导用户重复生成 Note。
- 现有 Wiki 页的 Sigma 图、学习掌握证据和 v1/v2 Canvas JSON 不删除。

## 3. 依赖与合规

### 3.1 包变更

`frontend/package.json`：

```json
{
  "dependencies": {
    "@xyflow/react": "12.11.3"
  }
}
```

- 必须使用精确版本，不使用 `^` 或 `~`。
- `frontend/pnpm-lock.yaml` 由 `pnpm add --save-exact @xyflow/react@12.11.3` 生成，不手工改 lockfile。
- 新建 `THIRD_PARTY_NOTICES.md`，记录包名、版本、上游 URL、MIT 和用途。
- 代码和文档不复制 Pro-only 的 undo/redo、copy/paste、helper-lines 示例实现。

### 3.2 自主可控边界

- 不在后端存储 React Flow `Node/Edge/Viewport` 对象。
- 前端 adapter 只在 `whiteboardProjection.ts` 完成 domain 与 React Flow 互转。
- 框架更换时只替换 projection/canvas 组件，API、SQLite 和 Note 发布契约不变。

## 4. 后端数据模型

### 4.1 ORM 文件

新建 `backend/app/db/models/whiteboard.py`，并在 `backend/app/db/models/__init__.py` 与 `backend/app/db/init_db.py` 导入，保证 `Base.metadata.create_all()` 可见。

#### `whiteboards`

| 字段 | 类型 | 约束 / 语义 |
| --- | --- | --- |
| `id` | String | PK，`wb_<uuid>` |
| `conversation_id` | String | FK `conversations.id`，index，必填 |
| `title` | String | 1–200 字符 |
| `description` | Text | 最多 2000 字符 |
| `schema_version` | Integer | 固定 `1` |
| `revision` | Integer | 初始 `1`，每次成功 mutation +1 |
| `viewport_json` | Text | `{x,y,zoom}`，只存通用数值 |
| `legacy_canvas_id` | String nullable | unique，用于幂等 seed |
| `status` | String | `active | archived` |
| `created_at/updated_at/deleted_at` | DateTime | 软删除白板，卡片内部删除为事务硬删 |

索引：`(conversation_id, updated_at)`，`legacy_canvas_id UNIQUE`。

#### `whiteboard_cards`

| 字段 | 类型 | 约束 / 语义 |
| --- | --- | --- |
| `id` | String | PK，`card_<uuid>` |
| `whiteboard_id` | String | FK `whiteboards.id`，index |
| `card_type` | String | `markdown | web | file | whiteboard` |
| `title` | String | 1–200 字符 |
| `description` | Text | 最多 2000 字符 |
| `content_json` | Text | 按 card type 校验的 JSON |
| `source_refs_json` | Text | 最多 20 条有界来源 |
| `x/y` | Float | 画布世界坐标 |
| `width/height` | Float | 最小 `220x120`，最大 `960x720` |
| `z_index` | Integer | 局部叠放顺序 |
| `collapsed` | Boolean | 默认 `true` |
| `created_at/updated_at` | DateTime | 审计时间 |

索引：`whiteboard_id`，`(whiteboard_id, z_index)`。

#### `whiteboard_relations`

| 字段 | 类型 | 约束 / 语义 |
| --- | --- | --- |
| `id` | String | PK，`rel_<uuid>` |
| `whiteboard_id` | String | FK `whiteboards.id`，index |
| `source_card_id/target_card_id` | String | FK `whiteboard_cards.id`，两者不同 |
| `relation_type` | String | `related | supports | challenges | depends_on | contains | custom` |
| `label` | String | 最多 160 字符 |
| `description` | Text | 最多 2000 字符 |
| `line_type` | String | `bezier | straight | smoothstep` |
| `direction` | String | `none | forward | backward | both` |
| `source_refs_json/style_json` | Text | 有界来源与允许的样式 token |
| `created_at/updated_at` | DateTime | 审计时间 |

索引：`whiteboard_id`，`source_card_id`，`target_card_id`。

#### `whiteboard_note_links`

| 字段 | 类型 | 约束 / 语义 |
| --- | --- | --- |
| `whiteboard_id` | String | PK/FK `whiteboards.id` |
| `note_task_id` | String | UNIQUE/FK `note_documents.task_id` |
| `published_revision` | Integer | 最后成功发布的 board revision |
| `published_at/updated_at` | DateTime | 发布时间 |

SQLite 当前未全局强制 `PRAGMA foreign_keys=ON`，本次不改全局连接语义。`WhiteboardRepository` 必须在事务内显式验证端点归属，删除卡片时先删关系，删白板时显式处理三张从表。

### 4.2 Domain / API models

新建 `backend/app/models/whiteboard.py`：

```python
CardType = Literal["markdown", "web", "file", "whiteboard"]
RelationType = Literal["related", "supports", "challenges", "depends_on", "contains", "custom"]
LineType = Literal["bezier", "straight", "smoothstep"]
RelationDirection = Literal["none", "forward", "backward", "both"]

class WhiteboardSourceRef(BaseModel):
    source_id: str
    source_type: str
    title: str
    url: str | None = None
    task_id: str | None = None

class WhiteboardCard(BaseModel):
    id: str
    type: CardType
    title: str
    description: str = ""
    content: dict[str, Any]
    source_refs: list[WhiteboardSourceRef]
    position: WhiteboardPosition
    size: WhiteboardSize
    z_index: int = 0
    collapsed: bool = True

class WhiteboardRelation(BaseModel):
    id: str
    source_card_id: str
    target_card_id: str
    relation_type: RelationType = "related"
    label: str = ""
    description: str = ""
    line_type: LineType = "bezier"
    direction: RelationDirection = "forward"
    source_refs: list[WhiteboardSourceRef] = Field(default_factory=list)
    style: dict[str, Any] = Field(default_factory=dict)

class WhiteboardSnapshot(BaseModel):
    id: str
    conversation_id: str
    title: str
    description: str
    schema_version: int
    revision: int
    viewport: WhiteboardViewport
    cards: list[WhiteboardCard]
    relations: list[WhiteboardRelation]
    note_link: WhiteboardNoteLink | None
    legacy_canvas_id: str | None
```

#### 卡片 content 校验

- markdown：只接受非空 `markdown: str`，最多 100,000 字符。
- web：必须有 `url`，解析后 scheme 只允许 `http/https`；可选 `preview_title/preview_image/media_type`。
- file：必须有 `upload_id`，通过现有 upload store 验证存在与 conversation 归属；不接受 `path`。
- whiteboard：必须有 `child_whiteboard_id`，归属同 conversation，并通过 DFS 检查无自引用/祖先循环。

## 5. Repository 和事务语义

新建 `backend/app/services/whiteboard_repository.py`：

```python
class WhiteboardRevisionConflict(ValueError):
    def __init__(self, current_revision: int): ...

class WhiteboardRepository:
    def create(self, conversation_id: str, title: str, description: str = "") -> WhiteboardSnapshot: ...
    def list_for_conversation(self, conversation_id: str) -> list[WhiteboardSummary]: ...
    def get(self, conversation_id: str, whiteboard_id: str) -> WhiteboardSnapshot: ...
    def apply_mutations(
        self,
        conversation_id: str,
        whiteboard_id: str,
        base_revision: int,
        operations: list[WhiteboardOperation],
    ) -> WhiteboardMutationResult: ...
    def soft_delete(self, conversation_id: str, whiteboard_id: str) -> None: ...
```

`apply_mutations` 在一个 SQLAlchemy session transaction 中：

1. 加载归属于 conversation 且未删除的 board。
2. 比较 `base_revision == board.revision`，不匹配则不执行任何 operation。
3. 按 payload 顺序验证并执行所有 operation；任一失败整个回滚。
4. 设置 `revision += 1` 和 `updated_at`。
5. 返回最小 delta 及新 revision，不每次返回完整大白板。

### 5.1 Mutation union

```python
WhiteboardOperation = Annotated[
    CardCreateOp | CardUpdateOp | CardDeleteOp | CardMoveResizeOp |
    RelationCreateOp | RelationUpdateOp | RelationDeleteOp | ViewportUpdateOp,
    Field(discriminator="op"),
]
```

| `op` | payload | 业务规则 |
| --- | --- | --- |
| `card.create` | 完整 card | id 不存在，content 按 type 校验 |
| `card.update` | `card_id + patch` | type 变更时必须同时提交新 content |
| `card.delete` | `card_id` | 同事务删除所有相关边 |
| `card.move_resize` | `items[]` | 一次拖拽/框选移动合并为一个 op |
| `relation.create` | 完整 relation | 端点存在、同 board、不自连 |
| `relation.update` | `relation_id + patch` | 端点重连时重新验证 |
| `relation.delete` | `relation_id` | 只删当前 board relation |
| `viewport.update` | `{x,y,zoom}` | 缩放 `0.1–2.5`，使用 500ms debounce |

### 5.2 撤销和重做

- 前端 `WhiteboardCommandStack` 保存最近 100 个 `{forward, inverse}` 命令。
- 命令仅在 mutation 成功后进入 undo stack。undo 会把 inverse 作为新 mutation 提交，因此服务端 revision 继续单调递增。
- 拖拽在 `onNodeDragStart` 记录旧位置，`onNodeDragStop` 生成一个 forward/inverse，不把中间帧入栈。
- 刷新后 undo/redo stack 清空；本次不提供跨会话持久历史。

## 6. HTTP API

新建 `backend/app/routers/whiteboard.py`，在 `backend/app/__init__.py` 以 `/api` 前缀注册。所有普通响应使用 `{code,msg,data}`。

| 方法 | 路径 | 请求 | 返回 |
| --- | --- | --- | --- |
| POST | `/conversations/{cid}/whiteboards` | `title/description` | 完整 `WhiteboardSnapshot` |
| GET | `/conversations/{cid}/whiteboards` | 无 | `WhiteboardSummary[]` |
| GET | `/conversations/{cid}/whiteboards/{wid}` | 无 | 完整 snapshot |
| DELETE | `/conversations/{cid}/whiteboards/{wid}` | 无 | `{deleted:true}`，软删 |
| POST | `/conversations/{cid}/whiteboards/{wid}/mutations` | `base_revision/operations[]` | `WhiteboardMutationResult` |
| POST | `/conversations/{cid}/whiteboards/{wid}/context` | `revision/card_ids/relation_ids/label` | 权威 `ConversationContextRef` |
| POST | `/conversations/{cid}/whiteboards/{wid}/publish-note` | `base_revision/scope/card_ids/relation_ids/provider_id/model_name` | `WhiteboardPublishResult` |
| POST | `/conversations/{cid}/whiteboards/from-learning-canvas/{canvas_id}` | 无 | 幂等 snapshot |

错误语义：

- `400`：schema/content/URL/nested-cycle/端点校验失败。
- `403/404`：对象不属于 conversation 或不存在；对外文案不暴露对象真实存在性。
- `409`：revision conflict，`data.current_revision`。
- `422`：Pydantic 请求契约错误。
- `500/503`：持久化或发布失败，只返回安全阶段和可重试文案。

## 7. LearningCanvas 幂等 seed

新建 `backend/app/services/whiteboard_seed_service.py`：

```python
class WhiteboardSeedService:
    def ensure_from_learning_canvas(
        self,
        conversation_id: str,
        canvas_id: str,
    ) -> WhiteboardSnapshot: ...
```

算法：

1. 用 `LearningCanvasStore.load(conversation_id, canvas_id)` 读取旧数据。
2. 按 `legacy_canvas_id` 查新 board，存在即返回。
3. 在同一 DB transaction 创建 board/cards/relations/note link；并发唯一约束冲突后重读。
4. node 转 markdown card：`title=user_label||label`，`description=user_summary||summary`，`content.markdown` 组合标题与摘要，`source_ids` 从 `canvas.sources` 恢复有界来源。
5. edge 转 relation；不存在端点的边丢弃并记录 safe diagnostic。
6. 初始布局使用确定性网格：`columns=ceil(sqrt(count))`，`x=(i%columns)*340`，`y=floor(i/columns)*220`，卡片 `300x170`。
7. 若 `document_task_id` 存在且 Note 属于 conversation，建立 `published_revision=1` 链接；否则无 note link。

新研究 ready 路径在 Canvas 保存后调用 seed，compact `learning_canvas` message meta 新增可选 `whiteboard_id`。seed/message 失败只追加 `whiteboard_seed_failed/guide_message_failed`，不回滚 Note。

## 8. 对话上下文契约

### 8.1 前端引用

`frontend/src/services/chat.ts` 扩展：

```typescript
export interface WhiteboardSelectionContextRef {
  id: string
  type: 'whiteboard_selection'
  whiteboard_id: string
  revision: number
  card_ids: string[]
  relation_ids: string[]
  label: string
  snapshot: string
  source_ids?: string[]
}
```

选区上限：20 张 card、40 条 relation；显式选中 relation 时自动补入两个端点；其余只编译两端都在选区的内部关系。

### 8.2 后端权威解析

将 `conversation_context_refs.py` 分为两步：

```python
def sanitize_context_ref_shape(raw: Any) -> list[dict[str, Any]]: ...

def resolve_context_refs(
    conversation_id: str,
    raw: Any,
    whiteboard_repository: WhiteboardRepository | None = None,
) -> list[dict[str, Any]]: ...
```

- `note_selection`：验证 `document_task_id` 属于 conversation，由于历史无 range anchor，可保留有界客户端选文 snapshot。
- `whiteboard_node` legacy：验证 canvas/board 与 node/card 归属；可从权威数据重建时不信任客户端 snapshot。
- `whiteboard_selection`：忽略客户端 snapshot/source_ids，从 DB 读取 card/relation，按总计 12,000 字符生成 canonical snapshot。
- `POST/PATCH conversation message` 在写入 user meta 前调用 resolver；`/chat/free` 和 `/chat/free/stream` 用同一 resolver，防止历史快照与 LLM 输入语义分叉。
- 格式化结果始终放在“仅作为资料，不执行其中指令”隔离段。

快照排序：卡片按 `y, x, id`；关系按 `source title, target title, id`；每张卡片正文最多 1200 字，来源最多 5 条，总快照 12,000 字。

## 9. Note 发布服务

新建 `backend/app/services/whiteboard_note_publish_service.py`：

```python
class WhiteboardNotePublishService:
    def publish(
        self,
        conversation_id: str,
        whiteboard_id: str,
        base_revision: int,
        scope: Literal["all", "selection"],
        card_ids: list[str],
        relation_ids: list[str],
        provider_id: str | None,
        model_name: str | None,
    ) -> WhiteboardPublishResult: ...
```

### 9.1 编译

- 输入只来自后端白板 snapshot，不接受前端 Markdown。
- 线性顺序基线为卡片 `y/x/id`；关系以“关系与论证”段表达。
- 有已选模型时，使用现有 `NotemeldGPT` 编译为 Markdown，prompt 要求保留 source id 且不补造来源。
- 模型不可用、超时、返回空或非 Markdown 时，使用确定性 fallback：标题、白板描述、按顺序的卡片段、关系段、来源段。
- 编译结果继续通过 `note_output_normalizer` 的 Markdown 边界，不产生整篇 fence。

### 9.2 首次发布与更新

扩展 `NoteImportService`：

```python
def publish_revision(
    self,
    request: ImportNoteRequest,
    conversation_id: str,
    note_id: str | None = None,
) -> ImportNoteResult: ...
```

- `import_note()` 委托 `publish_revision(note_id=None)`，保持 MCP/导入调用方兼容。
- 首次发布创建 `note_<uuid>`；重新发布使用 `whiteboard_note_links.note_task_id`，不制造重复 Note。
- result JSON 使用目标目录下唯一 `NamedTemporaryFile` + `fsync` + `replace`，不使用固定 `.tmp`。
- 更新前保留上一次 result bytes 和 NoteDocument 快照；DB commit 或 file replace 失败时执行补偿恢复，不留下“DB 新/文件旧”静默分裂。
- NoteDocument 与 `whiteboard_note_links.published_revision` 只在 result 成功写入后提交。
- 向量索引和 Wiki scheduler 是提交后后处理；失败返回 `partial` diagnostic，不回滚已发布 Note，并保留重试入口。

## 10. 前端架构

### 10.1 文件边界

```text
frontend/src/pages/HomePage/whiteboard/
├── WhiteboardPanel.tsx              # 顶层加载/空/错误/工具栏/发布状态
├── WhiteboardCanvas.tsx             # ReactFlow 容器与交互事件
├── WhiteboardToolbar.tsx            # 创建、缩放、适配、撤销/重做、发布
├── WhiteboardSelectionToolbar.tsx   # 选区加入对话/删除/复制
├── WhiteboardCardDialog.tsx          # 四类卡片创建与编辑
├── WhiteboardRelationDialog.tsx      # 关系名称/描述/类型/线型/方向
├── WhiteboardCardNode.tsx            # memoized 紧凑卡片 shell
├── WhiteboardRelationEdge.tsx        # memoized custom edge + label/toolbar
├── WhiteboardCardContent.tsx         # 唯一 active card 的重型内容分派
├── useWhiteboardController.ts        # optimistic state/revision/mutation/command stack
├── whiteboardProjection.ts           # domain <-> React Flow 适配
├── whiteboardCommands.ts             # forward/inverse/copy-paste 纯函数
└── types.ts                          # 前端 domain types
```

新建 `frontend/src/services/whiteboard.ts`，对应第 6 节 API。

### 10.2 React Flow 配置

```tsx
<ReactFlow
  nodes={nodes}
  edges={edges}
  nodeTypes={nodeTypes}
  edgeTypes={edgeTypes}
  onlyRenderVisibleElements
  selectionOnDrag
  panOnDrag={[1, 2]}
  multiSelectionKeyCode={["Meta", "Control", "Shift"]}
  minZoom={0.1}
  maxZoom={2.5}
  onPaneDoubleClick={handlePaneDoubleClick}
  onNodeDragStart={handleNodeDragStart}
  onNodeDragStop={handleNodeDragStop}
  onConnect={handleConnect}
  onEdgeDoubleClick={handleEdgeDoubleClick}
  onSelectionChange={handleSelectionChange}
>
  <Background />
  <Controls showInteractive={false} />
  <MiniMap pannable zoomable />
</ReactFlow>
```

- `nodeTypes/edgeTypes/defaultEdgeOptions/snapGrid` 定义在模块顶层或 `useMemo`，事件用 `useCallback`。
- pane 双击使用 `screenToFlowPosition` 生成世界坐标。
- card node 使用 `NodeResizer`，只在 selected 时显示；连接点默认弱化，hover/selected 时显示。
- edge 使用 `BaseEdge + EdgeLabelRenderer/EdgeToolbar`，`onEdgeDoubleClick` 打开编辑器。
- active heavy content 全局最多一张；网页/媒体激活前只显示静态预览。

### 10.3 交互状态

`useWhiteboardController` 区分：

- `serverRevision`：最近后端确认 revision。
- `nodes/edges`：当前 optimistic 投影。
- `selectedCardIds/selectedRelationIds`：单独状态，不订阅整个 node array 计算选区。
- `activeCardId`：唯一重型内容卡。
- `pendingCommand`：网络中操作；同一 board 串行 mutation，不并发发送相同 base revision。
- `undoStack/redoStack`：最多 100 条，新操作清 redo。
- `unsavedError`：保留 command 和重试/重新加载动作。

## 11. Home 和学习流集成

`frontend/src/pages/HomePage/Home.tsx`：

- 从最新 `learning_canvas` message meta 读 `whiteboard_id`，优先渲染 `WhiteboardPanel`。
- 若只有 `canvas_id`，调用 idempotent seed API；成功后 patch compact message meta 或仅用返回 id 进入新白板。
- seed 失败显示原 `LearningCanvasCard` Sigma fallback 和“转换可编辑白板失败，仍可查看原图”，不显示空白右栏。
- 右侧 header 保留“白板 / 笔记”；无 Note 时仍显示 tab，笔记页提供发布入口。
- `revision > published_revision` 显示不阻塞的未发布标记。
- 子白板在右侧 panel 内导航，不创建新 conversation；顶部显示 breadcrumb。

`ChatComposer.tsx` 保留现有 chip 交互，扩展 `whiteboard_selection`。新引用从 `/context` API 返回，用户发送后才清空；切换 conversation 继续清空 pending refs。

## 12. 性能和稳定性

### 12.1 必须的代码级防线

- `onlyRenderVisibleElements=true`。
- 紧凑 card 不挂载 Markdown parser/iframe/video/PDF/子白板。
- 同时最多一个 active heavy content renderer。
- node/edge 组件用 `React.memo`；回调稳定；不在 card 组件订阅完整 nodes/edges。
- 拖拽/缩放过程仅改前端状态；拖拽/缩放停止后合并请求。
- relation label 默认只显示短 label，编辑控件只在 selected 时渲染。
- 后端 mutation 不返回全量 board，前端 409 才重拉 snapshot。

### 12.2 基准场景

新增 `frontend/tests/fixtures/whiteboard-500-1000.json`，只包含生成的虚构标题/摘要，无用户数据。验证时记录：

- 首次 API 响应后到画布可交互。
- 10s 平移/缩放的 median FPS。
- 连续拖拽一张卡 3s 的 mutation 请求数。
- 选中/取消一张卡时实际重渲染卡片数。

门槛：TTI `<=2.5s`，median FPS `>=45`，单次拖拽 mutation `<=1`。不满足时不以“框架本身限制”为由跳过，必须附上 profile 证据并改进 LOD/订阅边界。

## 13. 安全与输入校验

- 所有 cid/wid/card/relation id 使用安全字符和最大长度，不作为文件路径。
- web URL 限 `http/https`，预览优先复用现有外链/代理安全策略，不新增任意内网代理。
- file card 不保存 path，不绕过 upload MIME/大小/内容校验。
- Markdown 渲染沿用现有不执行原始 HTML/script 的边界。
- relation style 只接受系统枚举 token，不接受任意 CSS/HTML。
- context snapshot 不信任客户端内容，并与 system prompt 隔离。
- LLM 发布输出必须通过 Markdown normalizer；reasoning/provider payload/API key 不进 Note、白板、日志或 API。

## 14. 迁移、删除与兼容

- `Base.metadata.create_all()` 为历史 DB 幂等增表，不清空任何现有表。
- `MigrationExportService._build_counts()` 新增四表 count；数据库文件整体导出会自然包含新表。
- `MigrationMergeService` 已按共享表自动合并，但为避免 FK 顺序不稳定，`_shared_tables()` 必须对 `whiteboards -> whiteboard_cards -> whiteboard_relations -> whiteboard_note_links` 优先排序，其他表保持现有顺序。
- 导入旧包没有新表时跳过，不报错。
- 删除 conversation 时新增 `soft_delete_whiteboards_by_conversation()`，不留下可见 orphan board；可恢复 conversation 时保留数据。
- 删除已链接 Note 时清理/置空 note link，白板仍可编辑和重新发布。
- feature flag `VITE_SEMANTIC_WHITEBOARD_ENABLED` 默认开；紧急回滚设为 `false` 后显示 legacy Sigma，不删数据。

## 15. 测试规格

### 15.1 后端

新建：

- `backend/tests/whiteboard/test_whiteboard_models.py`
- `backend/tests/whiteboard/test_whiteboard_repository.py`
- `backend/tests/whiteboard/test_whiteboard_api.py`
- `backend/tests/whiteboard/test_whiteboard_seed_service.py`
- `backend/tests/whiteboard/test_whiteboard_context.py`
- `backend/tests/whiteboard/test_whiteboard_note_publish.py`

必须覆盖：

- schema 与四种 content 校验；URL/path/nested cycle 拒绝。
- 创建/编辑/拖拽/连线/删除的同事务 revision。
- 过期 revision 无部分写入；中间 operation 失败全回滚。
- 删 card 同事务删 relation；跨 board/cid 拒绝。
- legacy seed 幂等和并发；原 JSON 不变。
- context 忽略伪造 snapshot/source_ids，补端点，只编译内部边，长度上限。
- 首次发布/同 note id 更新/fallback/文件失败/DB 失败/索引或 Wiki partial。
- 导出 counts、导入顺序与旧包兼容。

### 15.2 前端

新建 `frontend/tests/whiteboardContracts.test.mjs`，并更新 `learningCanvasContracts.test.mjs`，断言：

- 依赖版本精确且没有 Pro package。
- Home 优先 WhiteboardPanel，legacy Sigma fallback 仍存在。
- `onlyRenderVisibleElements`、memoized node/edge、单 active card。
- 拖拽仅 `onNodeDragStop` 提交，连线双击编辑，框选加对话。
- 上下文 payload 只携带 ids/revision，网页/文件默认不激活。
- 发布前后的 `published_revision` 提示与失败保留。
- TypeScript contracts 和 production build 通过。

### 15.3 验证命令

```bash
PYTHONPATH=backend python3 -m pytest -q backend/tests/whiteboard backend/tests/learning backend/tests/test_conversation_context_refs.py backend/tests/test_core_migration_contracts.py
python3 -m compileall -q backend/app
cd frontend && node tests/whiteboardContracts.test.mjs
cd frontend && pnpm test:contracts
cd frontend && pnpm build
scripts/run_core_regression.sh
```

手工纵向：

1. 源码 Web 发起研究，确认初始 Note + 新白板。
2. 创建四类 card，拖拽/缩放/框选/连线/双击边备注，刷新恢复。
3. 框选卡片+关系加入对话，检查 chip、message meta 和 LLM 资料上下文。
4. 发布 Note，再改白板检查 stale 标记，更新 Note 后确认 task id 不变和 Wiki 重新调度。
5. 打开历史 v2 Canvas，确认幂等 seed 与 Sigma fallback。
6. Tauri 桌面重复 1–5，确认 backend ready 前不发业务请求。
7. 运行 500/1000 基准并在 test evidence 记录硬件/浏览器/指标。

## 16. 文档写回

实现完成后必须同步：

- `docs/system/current-architecture.md`：新白板模块、React Flow 投影和 Note 发布链。
- `docs/system/product-rules.md`：白板草稿 / Note 发布快照 / Wiki 确认边界。
- `docs/system/data-model.md`：四表、revision、context ref 和 legacy seed。
- `docs/system/api-inventory.md`：whiteboard API 及 chat/conversation 扩展。
- `docs/system/known-pitfalls.md`：禁止逐帧持久化、框架对象入库、客户端快照信任、白板/Note 静默双向同步。
- `docs/system/changelog.md`：记录从 Sigma 只读投影到语义可编辑白板。
- `docs/superpowers/tests/2026-08-14-notemeld-semantic-infinite-whiteboard.md`：只写命令、结果、性能数据、失败和剩余风险。

## 17. 风险与回滚

| 风险 | 信号 | 防线 / 回滚 |
| --- | --- | --- |
| DOM/SVG 大白板卡顿 | FPS/TTI 超门槛 | LOD、可见区渲染、单 active renderer；flag 回 Sigma |
| revision 冲突丢修改 | 409 增多 | 串行 mutation、保留 pending command、显式重载 |
| Note/DB/file 分裂 | task result 与 document 不同 | 唯一 tmp + 原快照补偿，链接 revision 最后提交 |
| 旧 Canvas 重复 seed | 多个相同 board | `legacy_canvas_id UNIQUE` + 冲突重读 |
| 嵌套白板死循环 | 导航/发布递归 | 创建/更新时 DFS 拒绝环 |
| 引用伪造 | source/snapshot 不一致 | 后端按 cid/wid/ids 重建，不信客户端文本 |
| 回滚丢数据 | 旧版不识新表 | 不 drop 新表，旧 Canvas 保留，flag 只切 UI |

## 18. 规格自审

- 每条 requirement 均有数据、API、UI 或测试落点。
- 不依赖 Pro 能力，不把框架对象当业务模型。
- 初次研究、白板草稿、Note 发布和 Wiki 后处理的成功边界不混同。
- 旧 Canvas、旧 Note、会话和 API wrapper 兼容边界已定义。
- 无未定占位符或未命名的关键接口。
