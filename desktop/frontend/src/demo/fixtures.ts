import type { DemoFixtureSeed } from './types.ts'

const now = '2026-08-13T09:00:00.000Z'

const markdown = `# 10 分钟搞懂 AI Agent 底层逻辑：精简笔记

## 核心结论

**AI Agent 不是普通聊天机器人，而是“大模型 + 规划 + 记忆 + 工具 + 反馈闭环”的智能体。**

普通大模型更像高级问答机器；Agent 能理解目标、拆解任务、调用工具、观察结果，并根据反馈持续调整。

## AI Agent 与普通大模型的区别

### 普通 LLM

- 主要能力是文本生成与问答。
- 流程通常是 Input → Output。
- 面对复杂任务时容易一步错、步步错。

### AI Agent

- 围绕目标持续行动。
- 具备感知环境、思考规划、调用工具和执行反馈的闭环。
- 适合研究、自动化和长链路任务。`

const document = {
  taskId: 'demo-doc-success',
  title: '10 分钟搞懂 AI Agent 底层逻辑：精简笔记',
  content: markdown,
  sourceUrl: 'https://example.com/videos/agent-introduction',
  platform: 'bilibili',
  modelName: 'qwen-demo',
  style: 'knowledge_card',
  status: 'SUCCESS',
  wikiStatus: 'success',
  createdAt: now,
}

const baseFormData = {
  video_url: '',
  link: false,
  screenshot: false,
  platform: '',
  quality: 'medium',
  model_name: 'qwen-demo',
  provider_id: 'demo-local',
  style: 'knowledge_card',
  extras: '',
}

const progressMessage = (taskId: string, status: 'pending' | 'running' | 'success' | 'failed', step: string) => ({
  id: `message-${taskId}`,
  role: 'assistant',
  message_type: 'note_progress',
  content: status === 'failed' ? '模拟任务失败，可重试或切换其他演示状态。' : `模拟任务阶段：${step}`,
  status,
  meta: { task_id: taskId, current_step: step, detail: `模拟任务阶段：${step}` },
  createdAt: now,
  updatedAt: now,
  error: status === 'failed',
})

const conversations = [
  {
    id: 'demo-note-success',
    mode: 'note',
    title: '10 分钟搞懂 AI Agent 底层逻辑',
    status: 'SUCCESS',
    noteState: 'ready',
    platform: 'bilibili',
    linkedNoteTaskId: 'demo-doc-success',
    activeDocumentTaskId: 'demo-doc-success',
    markdown,
    formData: { ...baseFormData, video_url: document.sourceUrl, platform: 'bilibili' },
    audioMeta: {
      cover_url: '/placeholder.png',
      duration: 612,
      file_path: '',
      platform: 'bilibili',
      raw_info: {},
      title: document.title,
      video_id: 'demo-video-agent',
    },
    transcript: { full_text: '这是一段经过改写的演示转写文本。', language: 'zh', raw: {}, segments: [] },
    documents: [document],
    messages: [
      { id: 'user-1', role: 'user', message_type: 'user_input', content: '请把这个视频整理成结构化笔记。', createdAt: now, updatedAt: now },
      { id: 'assistant-1', role: 'assistant', message_type: 'assistant_text', content: '已结合内容生成笔记，并保留来源以供核验。', status: 'success', createdAt: now, updatedAt: now },
      { id: 'result-1', role: 'assistant', message_type: 'note_result', content: '笔记生成完成', status: 'success', meta: { task_id: document.taskId }, createdAt: now, updatedAt: now },
    ],
    createdAt: now,
  },
  {
    id: 'demo-note-running',
    mode: 'note',
    title: '正在编译：研究助手设计',
    status: 'PENDING',
    noteState: 'generating',
    linkedNoteTaskId: 'demo-task-running',
    pendingNoteTaskIds: ['demo-task-running'],
    formData: baseFormData,
    messages: [progressMessage('demo-task-running', 'running', 'SUMMARIZING')],
    createdAt: now,
  },
  {
    id: 'demo-note-partial',
    mode: 'note',
    title: '研究笔记：正文完成，知识抽取部分成功',
    status: 'SUCCESS',
    noteState: 'ready',
    linkedNoteTaskId: 'demo-doc-partial',
    activeDocumentTaskId: 'demo-doc-partial',
    markdown: '# 研究笔记\n\n正文已经保存，部分 Wiki 关系仍可稍后重试。',
    formData: baseFormData,
    documents: [{ ...document, taskId: 'demo-doc-partial', title: '研究笔记', wikiStatus: 'partial', content: '# 研究笔记\n\n正文已经保存，部分 Wiki 关系仍可稍后重试。' }],
    messages: [{ id: 'partial-result', role: 'assistant', message_type: 'note_result', content: '正文已生成，Wiki 为部分成功', status: 'success', meta: { task_id: 'demo-doc-partial', wiki_status: 'partial' }, createdAt: now, updatedAt: now }],
    createdAt: now,
  },
  {
    id: 'demo-note-failed',
    mode: 'note',
    title: '模拟失败：视频内容不可用',
    status: 'FAILED',
    noteState: 'failed',
    linkedNoteTaskId: 'demo-task-failed',
    formData: baseFormData,
    messages: [progressMessage('demo-task-failed', 'failed', 'FAILED')],
    createdAt: now,
  },
  {
    id: 'demo-note-canceled',
    mode: 'note',
    title: '已取消：专题研究资料',
    status: 'CANCELED',
    noteState: 'failed',
    linkedNoteTaskId: 'demo-task-canceled',
    formData: baseFormData,
    messages: [progressMessage('demo-task-canceled', 'failed', 'CANCELED')],
    createdAt: now,
  },
  {
    id: 'demo-chat',
    mode: 'chat',
    title: '从个人知识库继续研究',
    status: 'SUCCESS',
    noteState: 'none',
    formData: baseFormData,
    messages: [
      { id: 'chat-user', role: 'user', message_type: 'user_input', content: 'AI Agent 和普通大模型的核心区别是什么？', createdAt: now, updatedAt: now },
      { id: 'chat-assistant', role: 'assistant', message_type: 'assistant_text', content: '核心区别是 Agent 围绕目标持续行动，并通过工具和反馈形成闭环。', status: 'success', sources: [{ title: document.title, type: 'note', snippet: 'Agent 能理解目标、拆解任务并调用工具。' }], createdAt: now, updatedAt: now },
    ],
    createdAt: now,
  },
  {
    id: 'demo-empty',
    mode: 'chat',
    title: '空白对话',
    status: 'PENDING',
    noteState: 'none',
    formData: baseFormData,
    messages: [],
    createdAt: now,
  },
]

const styles = [
  ['knowledge_card', '知识卡片', '适合把视频、网页和对话整理成可回顾、可检索的知识资产。'],
  ['deep_research', '深度研究', '完整记录资料脉络，适合学习存档与深度研究。'],
  ['quick_summary', '快速摘要', '只保留结论、关键点和少量背景。'],
  ['action_list', '行动清单', '把方法与流程转化为下一步行动。'],
  ['meeting_notes', '会议纪要', '结构化呈现参会人、议题、决议与待办。'],
  ['video_analysis', '视频解析', '融合标题、字幕、画面与评论线索。'],
  ['web_insight', '网页提炼', '提炼页面观点并保留引用线索。'],
  ['tool_website', '工具网站', '记录网站链接、适用场景与限制。'],
  ['ai_dialogue', 'AI 对话沉淀', '沉淀问题、决策、方案和后续任务。'],
].map(([id, name, description]) => ({
  id,
  name,
  description,
  skeleton_html: '<article><section data-slot="body"></section></article>',
  style_constraints: { global: { tone: '清晰', sentence: '简洁', visual: '结构化', forbidden: [] } },
  rule_config: { global: {} },
  example_content: { html: '', markdown: '# 演示笔记' },
  output_formats: ['markdown'],
  builtin: true,
  created_at: now,
  updated_at: now,
}))

export const demoFixtureSeed: DemoFixtureSeed = {
  conversations,
  taskStatuses: {
    'demo-task-pending': { status: 'PENDING', progress: 5, message: '等待开始' },
    'demo-task-running': { status: 'RUNNING', progress: 62, message: '正在总结' },
    'demo-doc-success': { status: 'SUCCESS', progress: 100, message: '笔记生成完成', markdown, wiki_status: 'success' },
    'demo-task-failed': { status: 'FAILED', progress: 48, message: '模拟任务失败' },
    'demo-task-canceled': { status: 'CANCELED', progress: 31, message: '任务已取消' },
  },
  styles,
  wikiGraph: {
    nodes: [
      { id: 'concept-agent', label: 'AI Agent', type: 'concept', size: 18, community_id: 1, community_label: '智能体基础' },
      { id: 'concept-planning', label: '任务规划', type: 'concept', size: 12, community_id: 1, community_label: '智能体基础' },
      { id: 'concept-tools', label: '工具调用', type: 'concept', size: 12, community_id: 1, community_label: '智能体基础' },
      { id: 'source-video', label: document.title, type: 'source', size: 14, community_id: 2, community_label: '参考资料' },
      { id: 'entity-notemeld', label: 'NoteMeld', type: 'entity', size: 15, community_id: 3, community_label: '产品能力' },
    ],
    edges: [
      { source: 'concept-agent', target: 'concept-planning', type: 'includes', weight: 1 },
      { source: 'concept-agent', target: 'concept-tools', type: 'includes', weight: 1 },
      { source: 'source-video', target: 'concept-agent', type: 'supports', weight: 0.8 },
      { source: 'entity-notemeld', target: 'concept-agent', type: 'applies', weight: 0.7 },
    ],
    clusters: [
      { id: '1', label: '智能体基础', node_ids: ['concept-agent', 'concept-planning', 'concept-tools'], type: 'concept' },
      { id: '2', label: '参考资料', node_ids: ['source-video'], type: 'source' },
      { id: '3', label: '产品能力', node_ids: ['entity-notemeld'], type: 'entity' },
    ],
  },
  settings: {
    providers: [
      { id: 'demo-local', name: 'Ollama', logo: 'ollama', api_key: '', base_url: 'http://127.0.0.1:11434/v1', enabled: 1 },
      { id: 'demo-cloud', name: 'DeepSeek', logo: 'deepseek', api_key: '', base_url: 'https://api.example.com/v1', enabled: 1 },
    ],
    models: [
      { id: 1, provider_id: 'demo-local', model_name: 'qwen-demo', context_window_tokens: 32768, supports_vision: false, supports_stream: true, created_at: now },
      { id: 2, provider_id: 'demo-cloud', model_name: 'reasoning-demo', context_window_tokens: 65536, supports_vision: false, supports_stream: true, created_at: now },
    ],
    transcriber: {
      transcriber_type: 'faster-whisper',
      whisper_model_size: 'base',
      available_types: [{ value: 'faster-whisper', label: 'Faster Whisper（本地）' }],
      whisper_model_sizes: ['tiny', 'base', 'small', 'medium', 'large-v3'],
      mlx_whisper_available: false,
    },
    transcriberModels: {
      whisper: ['tiny', 'base', 'small', 'medium', 'large-v3'].map(model_size => ({ model_size, downloaded: model_size === 'base' || model_size === 'medium', downloading: false })),
      mlx_whisper: [],
      mlx_available: false,
    },
    downloaderConfigured: { bilibili: true, youtube: false, douyin: true, kuaishou: false, weixin: true, web: true },
    usageOverview: { prompt_tokens: 18240, completion_tokens: 6430, total_tokens: 24670, call_count: 18, task_count: 6 },
    usageRecords: [{ id: 1, task_id: 'demo-doc-success', provider_id: 'demo-local', provider_name: 'Ollama', model_name: 'qwen-demo', phase: 'summary', platform: 'bilibili', prompt_tokens: 3200, completion_tokens: 1160, total_tokens: 4360, status: 'success', duration_ms: 8420, created_at: now }],
    deployStatus: { backend: { status: 'running', port: 8483 }, cuda: { available: false, version: null, gpu_name: null }, whisper: { model_size: 'base', transcriber_type: 'faster-whisper' }, ffmpeg: { available: true }, mcp: { status: 'running', url: 'http://127.0.0.1:8483/mcp', port: 8483, tools_count: 9, auth_required: false, error: null } },
    mcpServers: { servers: { 'demo-files': { name: '本地资料演示', transport: 'stdio', enabled: true, command: 'demo-mcp', args: [], env: {} } } },
    researchSearch: { web_provider: 'searxng', searxng_endpoint: 'https://search.example.com', timeout_seconds: 12, tavily_api_key_set: false, github_token_set: false },
  },
}
