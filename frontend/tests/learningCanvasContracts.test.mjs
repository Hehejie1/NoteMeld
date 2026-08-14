import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
const learningService = await readFile(path.join(root, 'src/services/learning.ts'), 'utf8')
const learningCard = await readFile(
  path.join(root, 'src/pages/HomePage/components/LearningCanvasCard.tsx'),
  'utf8',
)
const renderers = await readFile(path.join(root, 'src/pages/HomePage/messageRenderers.tsx'), 'utf8')
const taskStore = await readFile(path.join(root, 'src/store/taskStore/index.ts'), 'utf8')
const composer = await readFile(
  path.join(root, 'src/pages/HomePage/components/ChatComposer.tsx'),
  'utf8',
)
const home = await readFile(path.join(root, 'src/pages/HomePage/Home.tsx'), 'utf8')
const researchSearch = await readFile(
  path.join(root, 'src/pages/SettingPage/ResearchSearch.tsx'),
  'utf8',
)
const app = await readFile(path.join(root, 'src/App.tsx'), 'utf8')
const menu = await readFile(path.join(root, 'src/pages/SettingPage/Menu.tsx'), 'utf8')
const markdownViewer = await readFile(
  path.join(root, 'src/pages/HomePage/components/MarkdownViewer.tsx'),
  'utf8',
)
const learningGraph = await readFile(
  path.join(root, 'src/pages/HomePage/components/LearningCanvasGraph.tsx'),
  'utf8',
)
const sigmaGraph = await readFile(
  path.join(root, 'src/pages/WikiPage/graph/SigmaWikiGraph.tsx'),
  'utf8',
)
const graphLayout = await readFile(
  path.join(root, 'src/pages/WikiPage/graph/layout.ts'),
  'utf8',
)
const chatService = await readFile(path.join(root, 'src/services/chat.ts'), 'utf8')

assert.match(
  taskStore,
  /\| 'learning_canvas'/,
  'conversation message type 必须包含 learning_canvas',
)

assert.match(renderers, /LearningCanvasSummaryBubble/, '对话流必须使用精简学习摘要')
assert.match(
  renderers,
  /message\.message_type === 'learning_canvas'/,
  'learning_canvas 必须有显式 renderer',
)
assert.doesNotMatch(renderers, /<LearningCanvasCard/, '完整学习画布不得继续内嵌在对话流')

assert.match(home, /LearningCanvasCard/, 'Home 右侧内容区必须渲染完整学习画布')
assert.match(home, /latestLearningCanvasId/, 'Home 必须从会话恢复最近的学习画布')
assert.match(home, /白板/, '右侧内容区必须提供白板视图')
assert.match(home, /笔记/, '研究产物必须保留笔记视图')
assert.match(home, /hasLearningCanvas && !hasSelectedDocument/, '笔记被删除后必须恢复仍存在的学习面板')
assert.match(home, /notemeld:focus-research-node/, '从对话聚焦研究节点时必须自动打开白板')
assert.match(home, /status !== 'clarifying'/, '澄清阶段不得展示空白板')
assert.match(home, /label: '白板'/, '移动端必须使用白板而不是学习课程命名')
assert.match(home, /!hasLearningCanvas && !hasSelectedDocument/, '只有笔记成功时不得被聊天单栏早退隐藏')

assert.match(composer, /ComposerMode = 'note' \| 'chat' \| 'learn'/, '输入区必须支持 learn intent')
assert.match(composer, />\s*学习\s*</, '模式切换必须展示“学习”')
assert.match(composer, /submitLearning/, '学习模式必须有显式提交路径')
assert.match(composer, /createLearningCanvas/, '学习提交必须直接调用 canvas API')
assert.match(composer, /modeWasExplicitlySelectedRef\.current/, '用户显式选择模式后输入内容不得自动切换')
assert.match(composer, /modeWasExplicitlySelectedRef/, '自动模式推断不得覆盖用户手动选择的 Chat 或 Note')
assert.match(composer, /learningSubmissionLockRef/, '学习提交必须在任何异步写入前建立互斥锁')
assert.match(composer, /learningRequestInFlight/, '学习提交互斥必须跨 composer 挂载持续生效')
assert.match(composer, /window\.location\.pathname === learningOriginPath/, '旧学习请求只能在用户仍停留于发起页时自动导航')
assert.match(composer, /learningCanvasCreated/, 'canvas 创建成功必须成为不可回滚的成功边界')
assert.match(composer, /learningCanvas\.status === 'clarifying'/, '学习请求必须区分澄清与研究白板已生成')
assert.match(composer, /nextMode !== 'learn'[\s\S]*URL_REGEX/, '从学习切回 Chat/Note 时必须重新识别 URL')
assert.match(composer, /pendingUploadedFile && mode !== 'learn'/, '学习模式不得假装使用未接入的上传文件')
assert.match(renderers, /kind !== 'learning_build_progress'/, '学习构建失败不得展示会触发自由聊天的通用重试按钮')

for (const pathPart of [
  '/learning-canvases',
  '/start',
  '/evidence',
  '/research-search/config',
]) {
  assert.ok(learningService.includes(pathPart), `learning service 必须包含 ${pathPart}`)
}
assert.match(learningService, /createLearningCanvas/, 'learning service 必须暴露创建画布 API')
assert.match(learningService, /timeout:\s*0/, '多源同步研究创建请求不得被前端固定超时提前中断')

assert.match(learningCard, /研究白板/, '白板必须以研究导航而不是课程命名')
for (const forbidden of ['学习路径', '待复习', '开始学习', '主动回忆', '应用任务']) {
  assert.ok(!learningCard.includes(forbidden), `研究白板首屏不得继续展示“${forbidden}”`)
}
assert.match(markdownViewer, /添加到对话/, '笔记选文右键必须能添加到对话')
assert.match(learningGraph, /onAddToConversation/, '白板节点必须能添加到对话')
assert.match(learningCard, /absolute[\s\S]*添加到对话/, '节点详情必须作为白板内的单个浮层按需展开')
assert.doesNotMatch(learningCard, /当前焦点/, '白板下方不得保留固定焦点详情区')
assert.match(learningCard, /canvas\.edges\.length === 0/, '零关系白板必须显示明确的降级提示')
assert.doesNotMatch(
  home,
  /rightContentView === 'learning'[\s\S]{0,500}<ScrollArea/,
  '桌面白板必须直接占满右侧剩余空间，不得包在页面级 ScrollArea 中',
)
assert.match(sigmaGraph, /rightClickNode/, 'Sigma 必须暴露节点右键事件')
assert.match(sigmaGraph, /contextMenuCallbackRef/, '白板右键回调变化不得重建 Sigma')
assert.match(sigmaGraph, /getNodeDisplayData\(nodeId\)/, '聚焦节点必须使用 Sigma 归一化后的 display 坐标')
assert.match(sigmaGraph, /animatedReset\(/, '适配白板必须调用相机自动 reset')
assert.doesNotMatch(sigmaGraph, /x:\s*0,\s*y:\s*0,\s*ratio:\s*1/, '适配白板不得写死错误的相机坐标')
assert.match(sigmaGraph, /new ResizeObserver/, '白板必须在右侧面板尺寸变化后重算 Sigma 画布')
assert.match(graphLayout, /graph\.size === 0/, '零关系图必须跳过 ForceAtlas2 并使用稳定紧凑布局')
assert.match(composer, /pendingContextRefs/, '输入框必须渲染待发送引用')
assert.match(composer, /context_refs/, '聊天请求必须携带结构化引用')
assert.match(taskStore, /state\.currentTaskId === taskId \? state\.pendingContextRefs : \[\]/, '切换会话必须清除待发送引用')
assert.match(chatService, /ConversationContextRef/, 'chat service 必须定义引用契约')
assert.match(renderers, /suggested_actions/, '学习摘要必须展示预测的下一步动作')
assert.match(renderers, /clarification/, '歧义研究必须在对话中渲染澄清问题')

assert.doesNotMatch(
  learningCard,
  /set[A-Za-z]*Mastery\([^)]*['"]mastered['"]\)/,
  '前端不得直接把节点设为 mastered，必须提交学习证据给后端',
)

assert.match(app, /ResearchSearch/, 'Settings 路由必须懒加载 ResearchSearch')
assert.match(app, /settings[^\n]*research-search|path="research-search"/, 'Settings 必须注册 research-search 路由')
assert.match(menu, /研究搜索/, 'Settings 菜单必须提供研究搜索入口')
assert.doesNotMatch(researchSearch, /scopeOptions/, 'Settings 不得再提供研究范围开关')
assert.doesNotMatch(researchSearch, /toggleScope/, 'Settings 不得允许关闭论文或 GitHub')
assert.match(researchSearch, /学术论文与 GitHub/, 'Settings 必须说明默认研究来源')
assert.doesNotMatch(researchSearch, /github-token/, 'Settings 不得要求用户配置 GitHub 才能学习')
