export type FeatureGuideEvidenceType = 'requirement_and_code' | 'code_fact' | 'needs_requirement'

export interface FeatureGuideEvidence {
  label: string
  path: string
  section?: string
}

export interface FeatureGuideEntry {
  id: string
  title: string
  summary: string
  userValue: string
  behavior: string[]
  productEvidence: FeatureGuideEvidence[]
  codeEvidence: FeatureGuideEvidence[]
  dataAndStates: string[]
  demoLimit: string
  evidenceType: FeatureGuideEvidenceType
}

const requirement = (section: string): FeatureGuideEvidence => ({
  label: '静态演示与功能讲解需求',
  path: 'docs/requirements/2026-08-13-static-product-demo-and-feature-guide.md',
  section,
})

const productRules: FeatureGuideEvidence = {
  label: '产品硬规则',
  path: 'docs/system/product-rules.md',
  section: '用户体验偏好',
}

const guide = (
  id: string,
  title: string,
  summary: string,
  userValue: string,
  codePath: string,
  behavior: string[],
  dataAndStates: string[],
  demoLimit: string,
): FeatureGuideEntry => ({
  id,
  title,
  summary,
  userValue,
  behavior,
  productEvidence: [requirement('功能讲解系统'), productRules],
  codeEvidence: [{ label: '当前实现', path: codePath }],
  dataAndStates,
  demoLimit,
  evidenceType: 'requirement_and_code',
})

export const featureGuideCatalog: Record<string, FeatureGuideEntry> = {
  'nav-new-note': guide('nav-new-note', '新建笔记', '进入统一输入工作台。', '把网页、视频、文件、对话或研究主题交给 NoteMeld 处理。', 'frontend/src/layouts/AppLayout.tsx', ['清空当前选择并进入 /new', '在输入框中选择聊天、笔记或学习意图'], ['会话列表', '模型列表', '笔记风格'], '静态演示只模拟提交，不调用真实生成后端。'),
  'nav-styles': guide('nav-styles', '风格模板', '管理笔记输出结构和表达风格。', '让同一份来源按知识卡片、深度研究、会议纪要等方式编译。', 'frontend/src/pages/StylesPage/index.tsx', ['搜索模板', '创建或编辑模板', '预览输出'], ['note_styles', '模板提取任务'], '创建、保存和删除只修改演示内存。'),
  'nav-wiki': guide('nav-wiki', 'Wiki 应用', '查看 NoteMeld 编译出的知识关系图。', '从应用入口继续核验实体、概念、来源和关系。', 'frontend/src/apps/wiki/WikiApplication.tsx', ['打开应用入口', '切换类型/社群视图', '缩放或聚焦节点'], ['applications', 'wiki.read', 'entities', 'concepts', 'sources'], '图数据来自固定 fixture，不执行 Wiki rebuild。'),
  'nav-applications': guide('nav-applications', '应用', '打开由 NoteMeld Host 管理的应用。', '从应用入口进入 Wiki 等内建应用并查看运行状态。', 'frontend/src/pages/Applications/index.tsx', ['查看应用状态', '打开 Wiki 应用'], ['applications', 'Application Host'], '静态演示使用固定应用清单。'),
  'nav-settings': guide('nav-settings', '设置', '配置模型、转写、下载、迁移和集成。', '让本地优先的知识编译链路适配用户设备和服务。', 'frontend/src/pages/SettingPage/index.tsx', ['进入设置后选择子页面'], ['providers', 'models', '本地配置文件'], '所有保存、下载和连接测试均为模拟。'),
  'nav-about': guide('nav-about', '关于', '查看版本与更新状态。', '确认当前 NoteMeld 版本并了解更新能力。', 'frontend/src/pages/AboutPage.tsx', ['检查更新', '展示下载进度'], ['桌面 updater'], '不会访问更新服务器或重启应用。'),
  'composer-submit': guide('composer-submit', '提交输入', '按当前意图提交聊天、笔记或研究任务。', '把一次输入转化为对话、结构化 Note 或研究白板。', 'frontend/src/pages/HomePage/components/ChatComposer.tsx', ['校验输入和模型', '创建/复用会话', '触发对应 service'], ['conversations', 'conversation_messages', 'note task'], '演示使用内存回复和模拟任务状态机。'),
  'wiki-view-mode': guide('wiki-view-mode', 'Wiki 视图模式', '按知识类型或社区结构组织图谱。', '帮助用户从语义类型和主题聚类两个角度理解知识网络。', 'frontend/src/apps/wiki/WikiApplication.tsx', ['类型视图按节点 type 上色', '社群视图按 community 聚类'], ['WikiGraph nodes/edges/clusters'], '切换只作用于演示图。'),
  'styles-create': guide('styles-create', '新建风格模板', '创建自定义笔记编译格式。', '让用户定义骨架、约束、规则与示例。', 'frontend/src/pages/StylesPage/index.tsx', ['打开模板助手与编辑抽屉', '填写并保存模板'], ['note_styles', 'template_extraction_tasks'], '提取助手不会调用模型；保存后刷新将恢复默认 fixture。'),
  'settings-model': guide('settings-model', 'AI 模型设置', '管理 Provider 和可用模型。', '为总结、Wiki、对话和研究选择推理能力。', 'frontend/src/pages/SettingPage/Model.tsx', ['选择 Provider', '配置模型能力和上下文窗口'], ['providers', 'models', 'model_capabilities'], '连接测试和凭证保存均为模拟且不存秘密。'),
  'settings-transcriber': guide('settings-transcriber', '音频转写配置', '选择音视频转文字引擎和本地模型。', '在字幕不可用时，为视频知识编译提供文本输入。', 'frontend/src/pages/SettingPage/transcriber.tsx', ['选择转写引擎', '下载或切换模型'], ['transcriber config', 'model status'], '下载按钮只展示模拟结果。'),
  'settings-download': guide('settings-download', '下载配置', '配置不同内容平台的采集凭证。', '提高受限视频和平台内容的可获取性。', 'frontend/src/pages/SettingPage/Downloader.tsx', ['选择平台', '保存 Cookie'], ['downloader config'], '不接收或保存真实 Cookie。'),
  'settings-migration': guide('settings-migration', '数据与迁移', '导出、导入并重建本地索引。', '帮助用户迁移本地知识资产且保持可检索。', 'frontend/src/pages/SettingPage/DataMigration.tsx', ['选择迁移包', '模拟导入/导出/reindex'], ['migration jobs'], '不读写磁盘或正式数据。'),
  'settings-usage': guide('settings-usage', 'Token 消耗', '按任务和模型查看推理用量。', '理解知识编译成本和调用分布。', 'frontend/src/pages/SettingPage/Usage.tsx', ['筛选并查看汇总/明细'], ['model_usage_records'], '展示固定合成统计。'),
  'settings-monitor': guide('settings-monitor', '部署监控', '查看后端、转写、FFmpeg 和 MCP 状态。', '快速判断本地运行链路是否健康。', 'frontend/src/pages/SettingPage/Monitor.tsx', ['刷新状态', '复制 MCP 地址'], ['deploy status'], '状态固定为演示值。'),
  'settings-mcp': guide('settings-mcp', 'MCP 服务器', '管理可按需发现的第三方 MCP 能力。', '让 Agent 在用户启用后调用外部工具。', 'frontend/src/pages/SettingPage/McpServers.tsx', ['添加、编辑、启用或删除 server'], ['mcp_servers config'], '不会建立 MCP 连接或执行工具。'),
  'settings-research': guide('settings-research', '研究搜索', '配置普通 Web 搜索补充来源。', '在本地 Wiki、学术和 GitHub 基线之外补充网页证据。', 'frontend/src/pages/SettingPage/ResearchSearch.tsx', ['选择搜索 Provider', '保存 endpoint'], ['research_search config'], '不会发起外部搜索。'),
  'about-update': guide('about-update', '检查更新', '检查并安装桌面新版本。', '让本地应用获得新版功能和修复。', 'frontend/src/pages/AboutPage.tsx', ['检查版本', '展示 release notes 和进度'], ['Tauri updater'], '完整流程由浏览器定时器模拟。'),
}

export const getFeatureGuide = (id: string): FeatureGuideEntry | undefined => featureGuideCatalog[id]
