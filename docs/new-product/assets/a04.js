(() => {
  const html = String.raw;
  const card = (title, body) => `<article class="nm-surface design-demo"><h3>${title}</h3>${body}</article>`;
  const demoButton = (label, variant = 'secondary') => `<button class="nm-button" data-variant="${variant}" data-nm-toast="${label}：参考交互已触发">${label}</button>`;
  const icon = (name, size = '16') => `<span class="nm-icon nm-icon-${name} nm-icon-${size}" aria-hidden="true"></span>`;
  const section = (label, title, intro, render) => ({ label, title, intro, render });

  const values = {
    overview: section('价值观总览', '设计价值观', 'NoteMeld 的界面不是装饰层，而是帮助用户理解、验证和继续使用 AI 产出的知识工具。', () => html`<div class="value-hero"><div><span class="nm-badge" data-status="info">NOTEMELD PRINCIPLE</span><h3>AI 编译知识，人验证和消费</h3><p>所有交互都应降低理解成本，同时保留来源、状态、权限和恢复路径，让用户可以放心地把 AI 纳入自己的工作流。</p></div><div class="value-quote">“好的界面让用户更清楚，而不是更依赖。”<small>NoteMeld design north star</small></div></div><div class="principle-grid"><div class="principle-card"><b>01</b><div><strong>清晰优先</strong><p>先让用户看懂当前页面、状态和下一步，再考虑装饰。</p></div></div><div class="principle-card"><b>02</b><div><strong>简化交互</strong><p>减少步骤，但不隐藏来源、权限、风险和重要状态。</p></div></div><div class="principle-card"><b>03</b><div><strong>状态透明</strong><p>让 Agent 的执行、等待、失败和恢复都可被理解。</p></div></div><div class="principle-card"><b>04</b><div><strong>安全可逆</strong><p>危险操作明确确认，失败保留上下文，离线不伪造成功。</p></div></div></div>${card('公共系统边界','<div class="boundary-grid"><div><span class="nm-badge" data-status="running">负责</span><p>Tokens、基础控件、状态反馈、弹层、导航原语、动效与可访问性。</p></div><div><span class="nm-badge" data-status="waiting">不负责</span><p>Session、Agent、Workspace、Wiki、设备管理和 Cloud 业务流程。</p></div></div>')}`),
    principles: section('价值观 · 判断标准', '判断设计好坏的内在标准', '把亲密性、对齐、对比、重复等通用原则转译为 NoteMeld 的可验收标准。', () => html`<div class="judgement-table"><div><strong>原则</strong><strong>在 NoteMeld 中意味着</strong><strong>验收问题</strong></div><div><strong>亲密性</strong><span>输入、运行位置、Workspace、权限和结果放在同一任务上下文。</span><span>用户是否能在当前区域完成主要判断？</span></div><div><strong>对齐</strong><span>会话、消息、工具、来源和产物保持稳定的阅读轴线。</span><span>相同信息是否出现在可预测的位置？</span></div><div><strong>对比</strong><span>用户消息、Agent 输出、工具调用、审批和错误具有明确层级。</span><span>用户能否快速分辨谁做了什么？</span></div><div><strong>重复</strong><span>相同动作、状态、权限和反馈使用相同的组件和文案。</span><span>用户能否凭经验预测新页面行为？</span></div><div><strong>即时反应</strong><span>提交、处理中、成功、失败和离线状态都有即时反馈。</span><span>操作后是否会出现无反馈的等待？</span></div></div><div class="design-doc-note">原则发生冲突时，优先保护可理解性、安全性和用户控制权。</div>`),
    adaptive: section('价值观 · 跨端适配', '跨端一致，不强求相同', '桌面、网页和移动端共享语义与层级，但根据屏幕、输入方式和使用距离选择不同呈现。', () => html`${card('同一语义的跨端表达','<table class="adaptation-matrix"><thead><tr><th>语义</th><th>桌面 / Web</th><th>移动端</th><th>不变的契约</th></tr></thead><tbody><tr><td>选择一个值</td><td>Popover / Dropdown</td><td>Sheet / 全屏选择层</td><td>当前值、搜索、确认和取消语义一致</td></tr><tr><td>危险确认</td><td>居中 Dialog</td><td>底部 Sheet 或全屏层</td><td>风险说明、取消、危险动作和不可逆提示</td></tr><tr><td>更多操作</td><td>Popover / Context Menu</td><td>Action Sheet</td><td>主动作可见，次级动作不抢占上下文</td></tr><tr><td>长列表</td><td>表格 / 多列列表</td><td>卡片 / 单列列表</td><td>标题、状态、时间和关键操作优先级一致</td></tr></tbody></table>')}${card('响应式判断','<div class="rule-list"><span>先隐藏次要元数据，不压缩主要内容。</span><span>触摸目标不小于平台可接受的最小尺寸。</span><span>移动端优先使用单列和局部滚动。</span><span>复杂桌面面板转为 Sheet 或独立页面。</span></div>')}`),
    states: section('价值观 · 状态', '状态透明与用户控制', 'Agent 产品的状态决定用户是否信任结果、继续等待或介入处理。', () => html`${card('状态流','<div class="component-anatomy"><span>idle 空闲</span><i>→</i><span>submitting 提交中</span><i>→</i><span>running 运行中</span><i>→</i><span>completed 已完成</span></div><div class="component-anatomy"><span>running 运行中</span><i>→</i><span>waiting approval 等待审批</span><i>→</i><span>failed / cancelled</span></div>')}<div class="demo-grid">${card('<span class="nm-badge" data-status="running">运行中</span>系统正在工作','<p>显示当前动作、运行位置和可用的停止/暂停操作。</p>')}${card('<span class="nm-badge" data-status="waiting">等待审批</span>需要用户介入','<p>说明风险范围、请求的权限和批准后会发生什么。</p>')}</div>`),
    access: section('价值观 · 可访问', '可访问性默认开启', '可访问性不是生产实现最后补上的质量项，而是基础原语的默认行为。', () => html`${card('基础检查清单','<div class="checklist">'+['交互元素优先使用原生语义元素','键盘可以到达、操作和退出每个交互层','Icon Button 必须有 aria-label 或可见 tooltip','动态状态通过文字和 status/live region 传达','颜色不是表达状态的唯一方式','动画在 reduced-motion 下即时完成','错误信息说明原因和下一步'].map(item=>`<label><input type="checkbox" checked><span>${item}</span></label>`).join('')+'</div>')}<div class="aria-example"><div><strong>设计系统默认</strong><code>label → input · focus-visible → ring · status → text</code></div><div><strong>页面验收</strong><code>Tab 顺序可预测 · Esc / Back 可退出</code></div></div>`)
  };

  const components = {
    foundations: section('Design Tokens', 'Design Tokens', '所有平台共享语义 token；平台可以改变具体实现，但不改变 token 的层级与含义。', () => html`${card('语义色板','<div class="color-grid">'+[['背景','--nm-color-bg'],['表面','--nm-color-surface'],['次级表面','--nm-color-surface-muted'],['主文本','--nm-color-text'],['次级文本','--nm-color-text-muted'],['边界','--nm-color-border'],['操作强调','--nm-color-accent'],['成功','--nm-color-success'],['警告','--nm-color-warning'],['危险','--nm-color-danger']].map(([name,token])=>`<div class="color-token"><i style="background:var(${token})"></i><strong>${name}</strong><code>${token}</code></div>`).join('')+'</div>')}<div class="demo-grid">${card('Spacing / Radius','<div class="spacing-list"><div><span style="width:4px"></span><strong>4px</strong><code>--nm-space-1</code></div><div><span style="width:16px"></span><strong>16px</strong><code>--nm-space-4</code></div><div><span style="width:32px"></span><strong>32px</strong><code>--nm-space-8</code></div></div>')}${card('主题规则','<p>浅色与深色只替换语义 token，不改变布局、组件顺序和操作含义。</p>')}</div>`),
    typography: section('Typography', 'Typography & Iconography', '文字层级与图标共同决定信息密度。图标辅助识别，不替代文字。', () => html`${card('文字层级','<div class="type-specimen"><span class="type-label">Display / 32</span><h1>把知识变成可验证的结果</h1><span class="type-label">Heading / 20</span><h2>Agent 运行摘要</h2><span class="type-label">Body / 14</span><p>正文使用正常行高，辅助信息使用 muted 语义色。</p><span class="type-label">Code / 13</span><code class="code-sample">workspace.read({ path: "report.md" })</code></div>')}${card('图标规范','<div class="icon-grid">'+[['search','搜索'],['plus','添加'],['more','更多'],['close','关闭'],['check','完成'],['warning','警告'],['open','打开'],['file','文件']].map(([iconName,name])=>`<button class="icon-example" type="button" aria-label="${name}" data-nm-toast="${name}">${icon(iconName)}<strong>${name}</strong><small>outline / currentColor</small></button>`).join('')+'</div><div class="icon-rhythm"><strong>NoteMeld 图标韵律</strong><span>尺寸：16 / 20 / 24 / 32px</span><span>线宽：1.5px（16–20）· 2px（24–32）</span><span>元素：点与圆角使用 8 的倍数，保持视觉重量平衡</span><span>原则：准确 · 简单 · 节奏 · 平衡；禁止 emoji、icon font 和未注册 SVG</span></div>')}`),
    layout: section('Layout & Motion', 'Layout, Density & Motion', '布局原语定义节奏和层级，动效只服务层级变化、状态反馈和操作确认。', () => html`${card('布局原语','<div class="component-anatomy"><span>Container</span><i>→</i><span>Stack / Inline</span><i>→</i><span>Grid</span><i>→</i><span>Split Pane</span><i>→</i><span>Scroll Area</span></div><div class="density-demo"><div><span>紧凑密度</span><small>管理列表 / 桌面</small></div><div style="padding-block:12px"><span>标准密度</span><small>默认工作区</small></div><div style="padding-block:16px"><span>舒适密度</span><small>移动端 / 阅读</small></div></div>')}${card('动效参考','<div class="motion-stage"><button class="nm-button" data-variant="primary" data-motion-demo>播放进入动效</button><div class="motion-card" data-motion-card><strong>Agent 已连接</strong><span>只动画 opacity 与 transform</span></div></div>')}`),
    actions: section('Actions', 'Buttons & Icon Buttons', '按钮通过 variant 表达动作等级；Icon Button 必须提供可访问名称。', () => html`${card('动作层级','<div class="demo-row">'+[demoButton('主操作','primary'),demoButton('次要操作'),demoButton('辅助操作','ghost'),demoButton('删除','danger'),'<button class="nm-icon-button" aria-label="更多操作" data-nm-toast="更多操作"><span class="nm-icon nm-icon-more" aria-hidden="true"></span></button>','<button class="nm-button" data-variant="primary" disabled>不可用</button>'].join('')+'</div>')}${card('尺寸','<div class="demo-row"><button class="nm-button" data-variant="secondary" data-size="sm">Small</button><button class="nm-button" data-variant="secondary">Medium</button><button class="nm-button" data-variant="secondary" data-size="lg">Large</button></div>')}`),
    fields: section('Form Controls', 'Inputs, Selects & Textareas', '字段必须有 label、焦点态、帮助文本和错误反馈。', () => html`${card('字段组合','<div class="field-demo"><label>Workspace 名称<span class="nm-field"><input aria-label="Workspace 名称" placeholder="输入名称"></span><small>用于显示和筛选，不影响本地路径。</small></label><label>运行位置<span class="nm-field"><select aria-label="运行位置"><option>本地 Agent</option><option>云端会话</option><option>远程设备</option></select></span></label><label>任务说明<span class="nm-field"><textarea aria-label="任务说明" rows="3" placeholder="告诉 Agent 你想完成什么"></textarea></span></label></div>')}${card('字段状态','<div class="demo-grid"><label class="field-state">默认<span class="nm-field"><input placeholder="未聚焦"></span></label><label class="field-state field-error">错误<span class="nm-field"><input value="无效路径" aria-invalid="true"></span><small>请输入可访问的 Workspace。</small></label></div>')}`),
    selection: section('Selection', 'Checkbox, Radio, Switch & Tabs', '选择控件要清楚表达单选、多选、开关和分组导航的不同语义。', () => html`${card('选择控件','<div class="selection-grid"><label class="check-control"><input type="checkbox" checked><span></span>保存到 Workspace</label><label class="check-control"><input type="checkbox"><span></span>允许后台运行</label><label class="radio-control"><input type="radio" name="runtime" checked><span></span>本地 Agent</label><label class="radio-control"><input type="radio" name="runtime"><span></span>云端会话</label><button class="switch-control" type="button" aria-pressed="false" data-switch-demo><span></span><b>通知</b></button></div>')}${card('分段与标签页','<div class="segmented" role="tablist"><button class="active" role="tab" aria-selected="true">全部</button><button role="tab" aria-selected="false">运行中</button><button role="tab" aria-selected="false">已完成</button></div>')}`),
    navigation: section('Navigation', 'Navigation, Menus & Pagination', '导航提供位置感和层级感；当前项、返回、更多和危险菜单必须有明确状态。', () => html`${card('导航原语','<div class="nav-demo"><nav class="mini-sidebar"><strong>工作台</strong><button class="active">会话</button><button>Workspace</button><button>设置</button></nav><div class="mini-content"><div class="breadcrumbs"><a href="#">工作台</a><span>/</span><strong>会话详情</strong></div><div class="tabs-line"><button class="active">消息</button><button>事件</button><button>产物</button></div><p>桌面使用侧栏或顶栏，移动端使用抽屉和返回导航。</p></div></div>')}${card('适配原则','<div class="rule-list"><span>桌面：侧栏 / 顶栏 / Popover</span><span>移动：抽屉 / 返回 / Action Sheet</span><span>窄屏：隐藏次要信息而非压缩主内容</span></div>')}`),
    display: section('Data Display', 'Cards, Lists, Tables & Code', '数据展示负责扫描和对比，不负责承担业务流程。', () => html`${card('列表与表格','<div class="data-list"><div><span class="avatar-dot">N</span><strong>整理研究报告.md</strong><small>刚刚 · Markdown</small><span class="nm-badge" data-status="completed">已完成</span></div><div><span class="avatar-dot">A</span><strong>检查系统架构</strong><small>正在读取 Workspace</small><span class="nm-badge" data-status="running">运行中</span></div></div><table class="mini-table"><thead><tr><th>名称</th><th>状态</th><th>更新时间</th></tr></thead><tbody><tr><td>产品设计文档</td><td><span class="nm-badge" data-status="info">已索引</span></td><td>今天 10:42</td></tr><tr><td>会议转写</td><td><span class="nm-badge" data-status="waiting">待审核</span></td><td>昨天 18:20</td></tr></tbody></table>')}`),
    feedback: section('Feedback', 'Toast, Alert, Progress & States', '反馈必须说明发生了什么、当前是否安全、下一步能做什么。', () => html`${card('反馈类型','<div class="feedback-stack"><div class="alert info"><b>提示</b><span>Workspace 已切换。</span></div><div class="alert success"><b>成功</b><span>文件已保存，可以继续验证来源。</span></div><div class="alert warning"><b>注意</b><span>远程设备当前离线。</span></div><div class="alert danger"><b>失败</b><span>无法读取文件，请检查权限后重试。</span></div></div><div class="progress-demo"><div><span>索引知识库</span><strong>68%</strong></div><div class="progress-track"><i style="width:68%"></i></div></div>')}${card('空、错、加载','<div class="demo-grid"><div class="state-card"><div class="nm-state"><strong>暂无内容</strong><p>说明为什么为空，以及用户下一步能做什么。</p></div></div><div class="state-card"><div class="nm-state" data-state="error"><strong>加载失败</strong><p>保留可理解的原因和重试动作。</p></div></div></div>')}`),
    overlay: section('Overlay', 'Dialog, Drawer, Sheet & Popover', '桌面偏向 Dialog，移动偏向 Sheet；层级、关闭、焦点和危险操作规则一致。', () => html`${card('弹层结构','<div class="overlay-demo"><div class="popover-demo"><span class="popover-anchor">更多操作</span><div class="popover-panel"><button>复制链接</button><button>移动到 Workspace</button><button class="danger">删除会话</button></div></div><div class="demo-dialog"><strong>删除此 Workspace？</strong><p>删除后当前端的本地引用将被移除，该操作不可撤销。</p><div class="demo-row">'+demoButton('取消')+demoButton('确认删除','danger')+'</div></div></div>')}${card('移动端变化','<div class="design-doc-note">Dialog 在移动端可以变为 Bottom Sheet 或全屏层；内容、风险说明、取消和确认语义不变。</div>')}`)
  };

    const advancedDateBody = '<div class="date-demo" data-date-demo><div class="date-trigger" role="combobox" tabindex="0" aria-haspopup="dialog" aria-expanded="false"><input data-date-label aria-label="日期" value="2026年09月05日" inputmode="numeric" autocomplete="off"><span class="icon-chevron" aria-hidden="true"></span></div><div class="date-popover" hidden><div class="date-panel-header"><strong>2026年09月</strong><button type="button" data-date-clear aria-label="清除日期">清除</button></div><div class="date-grid">' + Array.from({length: 21}, (_, index) => { const day = String(index + 1).padStart(2, '0'); return `<button type="button" data-date-value="2026年09月${day}日" aria-selected="${day === '05'}" class="${day === '05' ? 'selected' : ''}">${day}</button>`; }).join('') + '</div></div></div>';
    components.advancedFields = section('Advanced Fields', 'Autocomplete, Number, Date & Time', '当选项很多、数值有约束或时间需要精确表达时，使用专门原语，不把所有场景塞进 Select。', () => html`${primitive('Autocomplete','输入 + 建议列表','<div class="autocomplete-demo"><span class="search-prefix">⌕</span><input aria-label="搜索组件" value="Select"><div class="autocomplete-options"><button><strong>Select</strong><small>Data Entry</small></button><button><strong>Select API</strong><small>Documentation</small></button></div></div>','输入驱动建议，支持键盘上下选择和空结果说明。')}${primitive('Number Input','数值 / 步进','<div class="number-input" data-number-demo><button type="button" aria-label="减少" data-number-action="decrease">−</button><input aria-label="数量" type="number" inputmode="numeric" min="0" max="10" step="1" value="3"><button type="button" aria-label="增加" data-number-action="increase">＋</button></div>','显示最小值、最大值和步进，避免只允许手动输入。')}${primitive('Date / Time Picker','日期 / 时间',advancedDateBody,'桌面可用 Popover，移动端转为 Sheet；时区和格式必须明确。')}`);
  components.upload = section('Upload', 'Upload & Transfer', '文件导入是知识库的入口，必须表达文件类型、进度、权限和失败恢复。', () => html`${primitive('Upload Dropzone','拖拽 / 选择文件','<div class="upload-dropzone"><strong>拖入文件到这里</strong><span>支持 Markdown、PDF、音频 · 单文件不超过 200MB</span><button class="nm-button" data-variant="secondary" data-nm-toast="选择文件">选择文件</button></div>','拖拽是桌面增强能力，移动端必须保留系统文件选择入口。')}${primitive('Upload Item','队列 / 进度','<div class="upload-item"><span class="file-glyph">MD</span><div><strong>产品设计文档.md</strong><small>正在索引 · 68%</small></div><button class="nm-icon-button" aria-label="取消上传">×</button></div>','队列项可取消、重试和查看错误原因。')}${primitive('Transfer','两侧移动 / 批量','<div class="transfer-demo"><div><small>可选文件</small><span>会议纪要.md</span><span>需求评审.pdf</span></div><b>→</b><div><small>已加入 Workspace</small><span>产品设计.md</span></div></div>','适合需要在两个集合之间批量移动的场景。')}`);
  components.dataExtras = section('Data Display Extras', 'Badge, Timeline, Tree & Tooltip', '数据展示还有状态标记、时间顺序、层级关系和解释性提示四类常见原语。', () => html`${primitive('Badge / Tag','短状态 / 分类','<div class="demo-row"><span class="nm-badge" data-status="running">运行中</span><span class="nm-badge" data-status="waiting">待审批</span><span class="tag-demo">知识库</span></div>','Badge 表示状态，Tag 表示分类，不混用。')}${primitive('Timeline','事件顺序','<ol class="timeline"><li><b>已创建会话</b><small>10:36 · 本地 Agent</small></li><li><b>读取 Workspace</b><small>10:37 · 12 个文件</small></li><li class="current"><b>等待审批</b><small>现在 · 需要用户确认</small></li></ol>','事件顺序必须可扫描，并突出当前节点。')}${primitive('Tree','层级 / 文件结构','<div class="tree-demo"><span>⌄ Workspace</span><span>　⌄ docs</span><span>　　 report.md</span><span>　　 design.md</span></div>','树节点需要清晰缩进、展开状态和键盘路径。')}${primitive('Tooltip','补充解释','<button class="tooltip-trigger" data-nm-toast="这是补充说明">悬停或聚焦查看说明 <span>?</span></button>','只补充不适合常驻的信息，不能承载关键操作。')}`);
  components.feedbackExtras = section('Feedback Extras', 'Spin, Result & Skeleton', '加载、成功和失败结果有不同的持续时间与用户动作，必须分别设计。', () => html`${primitive('Spin','短等待 / 局部','<div class="spin-demo"><i></i><span>正在读取 Workspace…</span></div>','短暂局部等待使用 Spin，不要让用户面对空白区域。')}${primitive('Result','完成 / 失败结果','<div class="result-demo"><b>✓</b><strong>索引完成</strong><span>已处理 24 个文件，发现 3 个可关联知识。</span><button class="nm-button" data-variant="primary" data-nm-toast="查看知识库">查看知识库</button></div>','结果页要给出状态、摘要和下一步动作。')}${primitive('Skeleton','结构占位','<div class="skeleton-demo"><i></i><i></i><i></i></div>','Skeleton 应复现内容结构，避免跳动和错误暗示。')}`);

  const nav = document.querySelector('[data-design-doc-nav]');
  const content = document.querySelector('[data-design-doc-content]');
  const title = document.querySelector('[data-design-doc-title]');
  const intro = document.querySelector('[data-design-doc-intro]');
  const menus = document.querySelectorAll('[data-design-menu]');
  const groups = {
    values: [['设计原则', [['overview','设计价值观总览'],['principles','判断设计的标准'],['adaptive','跨端适配原则'],['states','状态透明与用户控制'],['access','可访问性默认开启']]]],
    components: [['基础设计', [['foundations','Color / Spacing / Radius（颜色 / 间距 / 圆角）'],['typography','Typography / Iconography（字体 / 图标）'],['layout','Layout / Motion（布局 / 动效）']]], ['通用', [['button','Button（按钮）'],['iconButton','Icon Button（图标按钮）']]], ['数据录入', [['autocomplete','AutoComplete（自动完成）'],['checkbox','Checkbox（多选框）'],['datePicker','DatePicker（日期选择）'],['input','Input（输入框）'],['inputNumber','InputNumber（数字输入）'],['mentions','Mentions（提及）'],['radio','Radio（单选框）'],['rate','Rate（评分）'],['select','Select（选择器）'],['slider','Slider（滑动输入）'],['switch','Switch（开关）'],['timePicker','TimePicker（时间选择）'],['transfer','Transfer（穿梭框）'],['uploadComponent','Upload（上传）']]], ['数据展示', [['badge','Badge（徽标）'],['table','Table（表格）'],['tag','Tag（标签）'],['timeline','Timeline（时间线）'],['tree','Tree（树形控件）'],['tooltip','Tooltip（文字提示）']]], ['反馈', [['alert','Alert（警告提示）'],['empty','Empty（空状态）'],['spin','Spin（加载中）'],['progress','Progress（进度）'],['result','Result（结果）']]], ['导航', [['breadcrumb','Breadcrumb（面包屑）'],['menu','Menu（菜单）'],['pagination','Pagination（分页）'],['tabs','Tabs（标签页）']]], ['弹层', [['modal','Modal（对话框）'],['drawer','Drawer（抽屉）'],['popover','Popover（气泡卡片）']]], ['布局', [['divider','Divider（分割线）']]]]
  };

  const parameterSets = {
    TimePicker: [['value','dayjs | null','—','当前时间值'],['defaultValue','dayjs | null','—','初始时间'],['format','string','HH:mm:ss','展示与输入格式'],['placeholder','string','请选择时间','无值时提示'],['hourStep','number','1','小时选项步长'],['minuteStep','number','1','分钟选项步长'],['secondStep','number','1','秒选项步长'],['use12Hours','boolean','false','是否使用 12 小时制'],['allowClear','boolean | object','true','是否显示清除操作'],['needConfirm','boolean','—','是否需要点击确认提交'],['changeOnScroll','boolean','false','滚动时间列时是否立即选中'],['inputReadOnly','boolean','false','是否只读输入框'],['disabledTime','function','—','返回不可选时间'],['hideDisabledOptions','boolean','false','是否隐藏禁用选项'],['showNow','boolean','—','是否显示当前时间快捷操作'],['presets','{ label, value }[]','[]','快捷时间选项'],['open','boolean','false','是否受控展开'],['placement','bottomLeft | bottomRight | topLeft | topRight','bottomLeft','面板位置'],['status','error | warning | success | validating','—','校验状态'],['variant','outlined | borderless | filled | underlined','outlined','输入框变体'],['disabled','boolean','false','是否禁用'],['renderExtraFooter','function','—','面板底部扩展内容'],['onChange','function','—','时间变化回调'],['onClear','function','—','清除回调'],['onOpenChange','function','—','面板展开变化回调']],
    DatePicker: [['value','dayjs | null','—','当前日期值'],['defaultValue','dayjs','—','初始日期值'],['defaultPickerValue','dayjs','—','面板初始日期'],['pickerValue','dayjs','—','受控面板日期'],['format','string | string[]','YYYY-MM-DD','展示与输入格式'],['picker','date | week | month | quarter | year','date','选择粒度'],['multiple','boolean','false','是否允许多选'],['disabledDate','function','—','返回不可选日期'],['minDate','dayjs','—','最小可选日期'],['maxDate','dayjs','—','最大可选日期'],['showTime','boolean | object','false','是否同时选择时间'],['needConfirm','boolean','—','是否需要点击确定提交'],['open','boolean','—','受控展开状态'],['showNow','boolean','—','是否显示当前日期快捷操作'],['allowClear','boolean | object','true','是否显示清除操作'],['inputReadOnly','boolean','false','是否只读输入框'],['size','small | middle | large','middle','控件尺寸'],['placement','bottomLeft | bottomRight | topLeft | topRight','bottomLeft','面板位置'],['status','error | warning','—','校验状态'],['variant','outlined | borderless | filled | underlined','outlined','输入框变体'],['disabled','boolean','false','是否禁用'],['onChange','function','—','日期变化回调'],['onOk','function','—','点击确认回调'],['onOpenChange','function','—','面板展开变化回调'],['onPanelChange','function','—','面板日期或粒度变化回调']],
    'Select': [['value','string | number | LabeledValue','—','当前选中值'],['defaultValue','string | number','—','初始选中值'],['options','Option[]','[]','候选项集合'],['placeholder','string','—','无值时提示'],['allowClear','boolean','false','是否允许清除'],['showSearch','boolean','false','是否支持搜索'],['mode','single | multiple | tags','single','选择模式'],['labelInValue','boolean','false','是否返回标签和值'],['open','boolean','—','受控展开状态'],['placement','bottomLeft | bottomRight | topLeft | topRight','bottomLeft','面板位置'],['size','large | middle | small','middle','选择框尺寸'],['status','error | warning','—','校验状态'],['variant','outlined | borderless | filled | underlined','outlined','选择框变体'],['disabled','boolean','false','是否禁用'],['onChange','function','—','选中值变化回调'],['onSearch','function','—','搜索词变化回调']],
    'Input': [['value','string','—','当前文本值'],['placeholder','string','—','无值时提示'],['allowClear','boolean','false','是否显示清除操作'],['maxLength','number','—','最大字符数'],['status','default | error | warning','default','校验状态'],['disabled','boolean','false','是否禁用']],
    'Input Number': [['value','number | null','—','当前数值'],['min','number','—','最小值'],['max','number','—','最大值'],['step','number','1','步进值'],['precision','number','—','小数精度'],['controls','boolean','true','是否显示加减按钮'],['disabled','boolean','false','是否禁用']],
    'AutoComplete': [['value','string','—','当前输入值'],['defaultValue','string','—','初始输入值'],['options','Option[]','[]','建议项集合'],['placeholder','string','—','无值时提示'],['allowClear','boolean','false','是否显示清除操作'],['filterOption','boolean | function','true','是否过滤建议项'],['backfill','boolean','false','是否用高亮项回填输入'],['disabled','boolean','false','是否禁用'],['onSelect','function','—','选择建议项回调'],['onSearch','function','—','搜索词变化回调']],
    'Radio': [['defaultValue','string | number','—','初始选中值'],['value','string | number','—','当前选中值'],['options','Option[]','[]','互斥选项集合'],['optionType','default | button','default','选项呈现类型'],['buttonStyle','outline | solid','outline','按钮式 Radio 外观'],['size','small | middle | large','middle','控件尺寸'],['disabled','boolean','false','是否禁用'],['onChange','function','—','选中值变化回调']],
    'Icon Button': [['icon','IconName','—','图标名称'],['size','sm | md | lg','md','图标按钮尺寸'],['tooltip','string','—','悬停提示文案'],['loading','boolean','false','是否加载中'],['disabled','boolean','false','是否禁用']],
    'Button': [['type','primary | default | dashed | text | link','default','按钮类型'],['size','small | middle | large','middle','按钮尺寸'],['shape','default | circle | round','default','按钮形状'],['loading','boolean | object','false','是否加载中'],['disabled','boolean','false','是否禁用'],['danger','boolean','false','是否危险操作'],['onClick','function','—','点击回调']],
    'Checkbox': [['checked','boolean','false','是否选中'],['indeterminate','boolean','false','是否为半选状态'],['disabled','boolean','false','是否禁用'],['onChange','function','—','选中状态变化回调']],
    'Mentions': [['value','string','—','当前输入内容'],['options','Option[]','[]','提及候选项'],['prefix','string | string[]','@','触发候选列表的前缀'],['split','string',' ','插入候选项后的分隔符'],['disabled','boolean','false','是否禁用']],
    'Rate': [['value','number','0','当前评分'],['count','number','5','评分总数'],['allowHalf','boolean','false','是否允许半星'],['allowClear','boolean','true','是否允许清除'],['disabled','boolean','false','是否禁用'],['onChange','function','—','评分变化回调']],
    'Slider': [['value','number | number[]','0','当前值或范围'],['min','number','0','最小值'],['max','number','100','最大值'],['step','number | null','1','步进值'],['range','boolean','false','是否为范围选择'],['marks','object','—','刻度标记'],['tooltip','object','—','提示层配置'],['disabled','boolean','false','是否禁用']],
    'Switch': [['checked','boolean','false','当前开关状态'],['defaultChecked','boolean','false','初始开关状态'],['loading','boolean','false','是否加载中'],['size','small | default','default','控件尺寸'],['disabled','boolean','false','是否禁用'],['onChange','function','—','状态变化回调']],
    'Transfer': [['dataSource','TransferItem[]','[]','源数据集合'],['targetKeys','string[]','[]','右侧已选项 key'],['showSearch','boolean','false','是否支持搜索'],['oneWay','boolean','false','是否单向移动'],['pagination','object | boolean','false','是否分页'],['onChange','function','—','集合变化回调']],
    'Upload': [['fileList','UploadFile[]','—','受控文件列表'],['accept','string','—','允许的文件类型'],['multiple','boolean','false','是否允许多选'],['maxCount','number','—','最大文件数'],['beforeUpload','function','—','上传前校验'],['onChange','function','—','文件状态变化回调']],
    'Badge': [['count','ReactNode','—','徽标内容或数量'],['dot','boolean','false','是否只显示小圆点'],['status','success | processing | default | error | warning','—','预设状态'],['color','string','—','自定义颜色'],['offset','[number, number]','—','偏移量']],
    'Table': [['columns','Column[]','[]','列定义'],['dataSource','object[]','[]','行数据'],['rowKey','string | function','key','行唯一标识'],['pagination','object | false','—','分页配置'],['loading','boolean | object','false','加载状态'],['rowSelection','object','—','行选择配置']],
    'Tag': [['closable','boolean','false','是否可关闭'],['color','string','—','标签颜色'],['bordered','boolean','true','是否显示边框'],['onClose','function','—','关闭回调']],
    'Timeline': [['items','Item[]','[]','时间节点集合'],['mode','left | right | alternate','—','节点布局模式'],['pending','ReactNode','false','是否显示进行中节点'],['reverse','boolean','false','是否倒序展示']],
    'Tree': [['treeData','DataNode[]','[]','树节点数据'],['checkedKeys','Key[]','[]','选中节点 key'],['expandedKeys','Key[]','[]','展开节点 key'],['selectable','boolean','true','是否可选择节点'],['checkable','boolean','false','是否显示复选框'],['loadData','function','—','异步加载子节点']],
    'Tooltip': [['title','ReactNode','—','提示内容'],['placement','Placement','top','弹层位置'],['trigger','hover | focus | click','hover','触发方式'],['open','boolean','—','受控显示状态'],['mouseEnterDelay','number','0.1','显示延迟']],
    'Alert': [['message','ReactNode','—','主提示内容'],['description','ReactNode','—','详细说明'],['type','success | info | warning | error','info','提示类型'],['closable','boolean','false','是否可关闭'],['showIcon','boolean','false','是否显示图标'],['action','ReactNode','—','辅助操作']],
    'Empty': [['image','ReactNode | string','默认插图','空状态插图'],['description','ReactNode','暂无数据','说明文案'],['imageStyle','CSSProperties','—','插图样式']],
    'Spin': [['spinning','boolean','true','是否显示加载'],['size','small | default | large','default','加载器尺寸'],['tip','ReactNode','—','加载提示'],['delay','number','—','延迟显示毫秒数']],
    'Progress': [['percent','number','0','完成百分比'],['status','normal | exception | active | success','normal','进度状态'],['showInfo','boolean','true','是否显示百分比'],['strokeColor','string | object','—','进度颜色'],['type','line | circle | dashboard','line','进度形态']],
    'Result': [['status','success | error | info | warning | 404 | 403 | 500','info','结果状态'],['title','ReactNode','—','结果标题'],['subTitle','ReactNode','—','补充说明'],['extra','ReactNode','—','下一步操作'],['icon','ReactNode','—','自定义图标']],
    'Breadcrumb': [['items','ItemType[]','[]','层级项集合'],['separator','ReactNode','/','层级分隔符'],['params','object','—','动态路由参数']],
    'Menu': [['items','ItemType[]','[]','菜单项集合'],['mode','vertical | horizontal | inline','vertical','菜单布局'],['selectedKeys','string[]','[]','选中项 key'],['openKeys','string[]','[]','展开项 key'],['selectable','boolean','true','是否可选择'],['onClick','function','—','菜单点击回调']],
    'Pagination': [['current','number','—','当前页码'],['pageSize','number','10','每页条数'],['total','number','0','数据总数'],['showSizeChanger','boolean','—','是否显示页大小选择'],['showQuickJumper','boolean','false','是否支持快速跳转'],['onChange','function','—','分页变化回调']],
    'Tabs': [['items','TabItemType[]','[]','标签项集合'],['activeKey','string','—','当前激活项'],['type','line | card | editable-card','line','标签页样式'],['centered','boolean','false','是否居中'],['destroyOnHidden','boolean','false','隐藏时销毁内容'],['onChange','function','—','切换回调']],
    'Modal': [['open','boolean','false','是否显示'],['title','ReactNode','—','标题'],['okText','ReactNode','确定','确认按钮文案'],['cancelText','ReactNode','取消','取消按钮文案'],['onOk','function','—','确认回调'],['onCancel','function','—','取消回调'],['centered','boolean','false','是否垂直居中']],
    'Drawer': [['open','boolean','false','是否显示'],['title','ReactNode','—','标题'],['placement','top | right | bottom | left','right','展开方向'],['width','string | number','378','宽度'],['closable','boolean','true','是否显示关闭按钮'],['onClose','function','—','关闭回调']],
    'Popover': [['content','ReactNode','—','浮层内容'],['title','ReactNode','—','浮层标题'],['trigger','hover | focus | click','hover','触发方式'],['placement','Placement','top','弹层位置'],['open','boolean','—','受控显示状态'],['onOpenChange','function','—','显示状态回调']],
    'Divider': [['orientation','left | right | center','center','文字方向'],['dashed','boolean','false','是否虚线'],['plain','boolean','false','是否使用普通文字样式'],['size','small | middle | large','small','分隔间距']]
    ,'Text Input': [['value','string','—','当前文本值'],['placeholder','string','—','无值时提示'],['allowClear','boolean','false','是否显示清除操作'],['maxLength','number','—','最大字符数'],['disabled','boolean','false','是否禁用']],
    'Textarea': [['value','string','—','当前文本值'],['placeholder','string','—','无值时提示'],['autoSize','boolean | object','false','是否按内容自动调整高度'],['maxLength','number','—','最大字符数'],['disabled','boolean','false','是否禁用']],
    'Field States': [['status','default | error | warning','default','校验状态'],['disabled','boolean','false','是否禁用'],['aria-describedby','string','—','关联帮助或错误说明']],
    'Button States': [['type','primary | default | dashed | text | link','default','按钮类型'],['size','small | middle | large','middle','按钮尺寸'],['disabled','boolean','false','是否禁用'],['loading','boolean | object','false','是否加载中']],
    'Select · Desktop / Web': [['value','string | number','—','当前选中值'],['options','Option[]','[]','候选项集合'],['placement','bottomLeft | bottomRight','bottomLeft','桌面弹层位置'],['open','boolean','—','受控展开状态'],['showSearch','boolean','false','是否支持搜索'],['allowClear','boolean','false','是否允许清除']],
    'Select · Mobile': [['value','string | number','—','当前选中值'],['options','Option[]','[]','候选项集合'],['open','boolean','—','受控展开状态'],['showSearch','boolean','false','是否支持搜索'],['allowClear','boolean','false','是否允许清除']],
    'Sidebar Navigation': [['items','ItemType[]','[]','导航项集合'],['selectedKeys','string[]','[]','当前选中项'],['collapsed','boolean','false','是否折叠'],['onSelect','function','—','选中项变化回调']],
    'Breadcrumbs': [['items','ItemType[]','[]','层级项集合'],['separator','ReactNode','/','层级分隔符']],
    'Tabs Navigation': [['items','TabItemType[]','[]','标签项集合'],['activeKey','string','—','当前激活项'],['onChange','function','—','切换回调']],
    'Code Block': [['code','string','—','代码内容'],['language','string','text','语法高亮语言'],['copyable','boolean | object','false','是否支持复制'],['wrap','boolean','false','是否换行']],
    'List Item': [['dataSource','object[]','[]','列表数据'],['renderItem','function','—','列表项渲染函数'],['loading','boolean','false','加载状态'],['split','boolean','true','是否显示分割线']],
    'Toast': [['message','ReactNode','—','通知内容'],['description','ReactNode','—','详细说明'],['duration','number','4.5','自动关闭秒数'],['placement','top | bottom','top','通知位置'],['onClose','function','—','关闭回调']],
    'Empty / Error': [['image','ReactNode | string','默认插图','状态插图'],['description','ReactNode','暂无数据','说明文案'],['action','ReactNode','—','恢复操作']],
    'Dialog': [['open','boolean','false','是否显示'],['title','ReactNode','—','标题'],['content','ReactNode','—','内容'],['onOk','function','—','确认回调'],['onCancel','function','—','取消回调']],
    'Drawer / Sheet': [['open','boolean','false','是否显示'],['placement','top | right | bottom | left','right','展开方向'],['width','string | number','378','桌面宽度'],['height','string | number','—','移动端高度'],['onClose','function','—','关闭回调']],
    'Date / Time Picker': [['value','dayjs | null','—','当前日期或时间值'],['format','string','YYYY-MM-DD HH:mm:ss','展示与输入格式'],['showTime','boolean | object','false','是否同时选择时间'],['allowClear','boolean','true','是否允许清除'],['disabled','boolean','false','是否禁用']],
    'Upload Dropzone': [['fileList','UploadFile[]','—','受控文件列表'],['accept','string','—','允许的文件类型'],['multiple','boolean','false','是否允许多选'],['maxCount','number','—','最大文件数'],['beforeUpload','function','—','上传前校验']],
    'Upload Item': [['file','UploadFile','—','当前文件'],['status','uploading | done | error | removed','uploading','文件状态'],['percent','number','—','上传进度'],['onRemove','function','—','移除回调']],
    'Badge / Tag': [['status','success | processing | default | error | warning','—','徽标状态'],['count','ReactNode','—','徽标数量'],['color','string','—','标签颜色'],['closable','boolean','false','标签是否可关闭']],
    'Skeleton': [['active','boolean','false','是否启用动画'],['avatar','boolean | object','false','是否显示头像占位'],['paragraph','boolean | object','true','是否显示段落占位'],['loading','boolean','true','是否显示占位']],
  };
  parameterSets.Card = [['title','ReactNode','—','卡片标题'],['extra','ReactNode','—','标题栏辅助内容'],['bordered','boolean','true','是否显示边框'],['hoverable','boolean','false','是否显示悬停状态'],['size','small | default','default','卡片尺寸']];
  parameterSets.TimePicker.splice(4, 0,
    ['prefix', 'ReactNode', '—', '输入框前缀'],
    ['suffixIcon', 'ReactNode', '—', '输入框后缀图标']
  );
  parameterSets.Select.splice(4, 0, ['maxCount', 'number', '—', '多选时允许的最大选项数']);
  parameterSets.Modal.splice(4, 0,
    ['maskClosable', 'boolean', 'true', '点击遮罩是否关闭'],
    ['keyboard', 'boolean', 'true', '按 Escape 是否关闭']
  );
  parameterSets.Drawer.splice(4, 0,
    ['maskClosable', 'boolean', 'true', '点击遮罩是否关闭'],
    ['keyboard', 'boolean', 'true', '按 Escape 是否关闭']
  );
  parameterSets.Input.splice(4, 0, ['showCount', 'boolean | object', 'false', '是否展示字符计数']);
  parameterSets.Autocomplete = parameterSets.AutoComplete;
  parameterSets['Number Input'] = parameterSets['Input Number'];
  parameterSets.InputNumber = parameterSets['Input Number'];
  parameterSets['Primary Button'] = parameterSets.Button;
  parameterSets['Secondary Button'] = parameterSets.Button;
  parameterSets['Ghost Button'] = parameterSets.Button;
  parameterSets['Danger Button'] = parameterSets.Button;
  parameterSets['Date / Time Picker'] = [['value','dayjs | null','—','当前日期或时间值'],['format','string','YYYY-MM-DD HH:mm:ss','展示与输入格式'],['picker','date | week | month | quarter | year','date','选择粒度'],['multiple','boolean','false','是否允许多选日期'],['showTime','boolean | object','false','是否同时选择时间'],['showNow','boolean','true','是否显示当前时间快捷操作'],['presets','{ label, value }[]','[]','快捷日期选项'],['allowClear','boolean','true','是否允许清除'],['inputReadOnly','boolean','false','是否只读输入框'],['size','small | middle | large','middle','控件尺寸'],['variant','outlined | borderless | filled | underlined','outlined','输入框变体'],['placement','bottomLeft | bottomRight | topLeft | topRight','bottomLeft','面板位置'],['disabled','boolean','false','是否禁用']];
  parameterSets['Text Input'] = parameterSets.Input;
  parameterSets.Textarea = [['value','string','—','当前文本值'],['placeholder','string','—','无值时提示'],['autoSize','boolean | object','false','是否按内容自动调整高度'],['maxLength','number','—','最大字符数'],['disabled','boolean','false','是否禁用']];
  parameterSets['Badge / Tag'] = [['status','success | processing | default | error | warning','—','徽标状态'],['count','ReactNode','—','徽标内容或数量'],['color','string','—','标签颜色'],['closable','boolean','false','标签是否可关闭']];
  parameterSets.Timeline = [['items','Item[]','[]','时间节点集合'],['mode','left | right | alternate','—','节点布局模式'],['pending','ReactNode','false','是否显示进行中节点'],['reverse','boolean','false','是否倒序展示']];
  parameterSets.Tree = [['treeData','DataNode[]','[]','树节点数据'],['checkedKeys','Key[]','[]','勾选节点 key'],['expandedKeys','Key[]','[]','展开节点 key'],['selectedKeys','Key[]','[]','选中节点 key'],['selectable','boolean','true','是否可选择节点'],['checkable','boolean','false','是否显示复选框'],['loadData','function','—','异步加载子节点']];
  parameterSets.Tooltip = [['title','ReactNode','—','提示内容'],['placement','Placement','top','弹层位置'],['trigger','hover | focus | click','hover','触发方式'],['open','boolean','—','受控显示状态'],['mouseEnterDelay','number','0.1','悬停显示延迟秒数']];
  parameterSets.Spin = [['spinning','boolean','true','是否显示加载'],['size','small | default | large','default','加载器尺寸'],['tip','ReactNode','—','加载提示'],['delay','number','—','延迟显示毫秒数']];
  parameterSets.Result = [['status','success | error | info | warning | 404 | 403 | 500','info','结果状态'],['title','ReactNode','—','结果标题'],['subTitle','ReactNode','—','补充说明'],['extra','ReactNode','—','下一步操作']];
  parameterSets.Skeleton = [['active','boolean','false','是否启用动画'],['avatar','boolean | object','false','是否显示头像占位'],['paragraph','boolean | object','true','是否显示段落占位'],['loading','boolean','true','是否显示占位']];
  parameterSets.DatePicker = parameterSets.DatePicker.filter(([param]) => param !== 'presets');
  parameterSets.DatePicker.splice(10, 0, ['presets', '{ label, value }[]', '[]', '快捷日期选项']);
  const componentZhNames = {
    'Button': '按钮', 'Primary Button': '主按钮', 'Secondary Button': '次按钮', 'Ghost Button': '幽灵按钮', 'Danger Button': '危险按钮',
    'Icon Button': '图标按钮', 'Text Input': '文本输入框', 'Input': '输入框', 'Textarea': '多行输入框', 'Input Number': '数字输入', 'InputNumber': '数字输入', 'Number Input': '数字输入', 'AutoComplete': '自动完成', 'Autocomplete': '自动完成',
    'Checkbox': '多选框', 'DatePicker': '日期选择', 'TimePicker': '时间选择', 'Date / Time Picker': '日期 / 时间选择', 'Mentions': '提及',
    'Radio': '单选框', 'Rate': '评分', 'Select': '选择器', 'Select · Desktop / Web': '桌面选择器', 'Select · Mobile': '移动端选择器',
    'Slider': '滑动输入', 'Switch': '开关', 'Transfer': '穿梭框', 'Upload': '上传', 'Upload Dropzone': '上传拖拽区', 'Upload Item': '上传队列项',
    'Badge': '徽标', 'Tag': '标签', 'Badge / Tag': '徽标 / 标签', 'Table': '表格', 'List Item': '列表项', 'Card': '卡片', 'Code Block': '代码块',
    'Timeline': '时间线', 'Tree': '树形控件', 'Tooltip': '文字提示', 'Alert': '警告提示', 'Empty': '空状态', 'Empty / Error': '空状态 / 错误',
    'Spin': '加载中', 'Progress': '进度', 'Result': '结果', 'Toast': '轻提示', 'Field States': '字段状态', 'Button States': '按钮状态',
    'Sidebar Navigation': '侧栏导航', 'Breadcrumb': '面包屑', 'Breadcrumbs': '面包屑', 'Tabs': '标签页', 'Tabs Navigation': '标签页导航',
    'Menu': '菜单', 'Pagination': '分页', 'Modal': '对话框', 'Dialog': '对话框', 'Drawer': '抽屉', 'Drawer / Sheet': '抽屉 / 底部面板',
    'Popover': '气泡卡片', 'Divider': '分割线', 'Skeleton': '骨架屏', 'Select · Desktop / Web': '桌面选择器', 'Select · Mobile': '移动端选择器'
  };
  const parameterTable = (name) => {
    const invalidNames = new Set(['name', 'component', 'componentName', 'contract', 'capability', name, componentZhNames[name]]);
    const invalidNormalized = new Set([...invalidNames].map(item => item.replace(/\s+/g, '').toLocaleLowerCase()));
    const rows = (parameterSets[name] || []).filter(([param, type]) => {
      const candidate = String(param || '').trim();
      const normalized = candidate.replace(/\s+/g, '').toLocaleLowerCase();
      return /^[A-Za-z][A-Za-z0-9.-]*$/.test(candidate)
        && !invalidNames.has(candidate)
        && !invalidNormalized.has(normalized)
        && typeof type === 'string'
        && type.trim();
    });
    return `<div class="parameter-block"><div class="parameter-title"><strong>参数</strong></div><table class="parameter-table"><thead><tr><th>参数名</th><th>类型</th><th>默认值</th><th>含义</th></tr></thead><tbody>${rows.map(([param, type, defaultValue, meaning]) => `<tr><td>${String(param).trim()}</td><td>${type}</td><td>${defaultValue}</td><td>${meaning}</td></tr>`).join('')}</tbody></table></div>`;
  };
  const primitive = (name, contract, body, meta = '') => {
    const splitPlatforms = body.includes('select-reference') || body.includes('platform-pair');
    const different = ['Table', 'Tabs', 'Modal', 'Drawer', 'Transfer'].includes(name);
    const sampleCard = (platform, label, markup) => `<section class="platform-sample" data-sample-platform="${platform}"><h4>${label}</h4>${markup}</section>`;
    const sample = splitPlatforms ? body : different
      ? `<div class="platform-pair">${sampleCard('desktop', 'PC端', body)}${sampleCard('mobile', '移动端', body.replaceAll('modal-title', 'modal-title-mobile').replaceAll('drawer-title', 'drawer-title-mobile'))}</div>`
      : sampleCard('shared', 'PC端 / 移动端', body);
    const displayName = componentZhNames[name] ? `${name}（${componentZhNames[name]}）` : name;
    return `<article class="nm-surface primitive-showcase"><div class="primitive-heading"><h3>${displayName}</h3></div>${parameterTable(name)}<h3 class="demo-section-title">代码演示</h3><div class="primitive-body">${sample}</div></article>`;
  };
  const selectOptions = [['local','本地 Agent','当前设备运行'],['cloud','云端会话','远程执行与协同'],['remote','远程设备','已授权的运行节点']];
  const selectMarkup = (mode) => `<div class="select-reference ${mode}" data-select-demo="${mode}"><div class="select-mode-label">${mode === 'desktop' ? 'Desktop / Web · Popover' : 'Mobile · Bottom Sheet'}</div><label class="select-mode-toggle"><input type="checkbox" data-select-multiple>多选模式</label><div class="select-shell"><button type="button" class="select-trigger" role="combobox" aria-expanded="false" aria-controls="select-options-${mode}" aria-label="运行位置"><span>本地 Agent</span><span class="icon-chevron" aria-hidden="true"></span></button><div class="select-options" id="select-options-${mode}" role="listbox" aria-label="运行位置选项" aria-multiselectable="false">${selectOptions.map(([value,label,desc], index) => `<button type="button" class="select-option${index === 0 ? ' selected' : ''}" role="option" aria-selected="${index === 0}" data-value="${value}"><span><strong>${label}</strong><small>${desc}</small></span>${index === 0 ? `<i>${icon('check')}</i>` : ''}</button>`).join('')}</div></div><small class="select-caption">触发器 32px · 选项 36px · 键盘 ↑↓ / Enter / Esc</small></div>`;

  components.actions = section('Actions', 'Buttons & Icon Buttons', '动作按风险和频率分级；每个变体独立验证，不把不同语义混成一个“按钮集合”。', () => html`${primitive('Primary Button','主操作 / 一次一个','<button class="nm-button" data-variant="primary" data-nm-toast="创建会话">创建会话</button>','强调当前流程唯一的继续动作。')}${primitive('Secondary Button','次要操作','<button class="nm-button" data-variant="secondary" data-nm-toast="打开 Workspace">打开 Workspace</button>','保留边界，避免与主操作竞争。')}${primitive('Ghost Button','低强调操作','<button class="nm-button" data-variant="ghost" data-nm-toast="查看详情">查看详情</button>','用于工具栏和上下文中的低风险动作。')}${primitive('Danger Button','不可逆 / 高风险','<button class="nm-button" data-variant="danger" data-nm-toast="删除操作">删除 Workspace</button>','必须伴随风险说明和可取消路径。')}${primitive('Icon Button','纯图标动作','<button class="nm-icon-button" aria-label="更多操作" data-nm-toast="更多操作">⋯</button>','必须有 aria-label；图标不能独自承担不可逆语义。')}${primitive('Button States','尺寸 / 禁用 / 加载','<div class="demo-row"><button class="nm-button" data-size="sm">Small</button><button class="nm-button">Medium</button><button class="nm-button" data-size="lg">Large</button><button class="nm-button" data-variant="primary" data-loading-demo>加载</button><button class="nm-button" data-variant="primary" disabled>Disabled</button></div>','默认高度 32px，small 24px，large 40px；loading 时禁止重复提交。')}`);
  components.fields = section('Form Controls', 'Fields & Selects', '字段是独立原语：label、控件、帮助文本、错误和焦点态必须能被分别复用。Select 不使用原生下拉菜单作为视觉参考。', () => html`${primitive('Text Input','单行文本 / 搜索','<label class="standalone-field">Workspace 名称<span class="nm-field"><input aria-label="Workspace 名称" placeholder="输入名称"></span><small>用于显示和筛选。</small></label>','桌面与移动保持语义一致，移动端扩大触摸区域。')}${primitive('Textarea','多行文本 / 指令','<label class="standalone-field">任务说明<span class="nm-field"><textarea aria-label="任务说明" rows="3" placeholder="告诉 Agent 你想完成什么"></textarea></span></label>','按内容增长，避免把长文本压进单行输入。')}${primitive('Select · Desktop / Web','Popover / Listbox',selectMarkup('desktop'),'32px 触发器、36px 选项、对齐触发器宽度；不使用浏览器原生选项层。')}${primitive('Select · Mobile','Bottom Sheet / Listbox',selectMarkup('mobile'),'同一选择语义转为底部 Sheet，选项可触摸，保留取消和确认。')}${primitive('Field States','Default / Error / Disabled','<div class="field-state-stack"><label class="standalone-field">错误<span class="nm-field field-error"><input value="无效路径" aria-invalid="true" aria-describedby="path-error"></span><small id="path-error">请输入可访问的 Workspace。</small></label><label class="standalone-field">禁用<span class="nm-field"><input value="只读路径" disabled></span></label></div>','错误不能只变红，必须提供原因和下一步。')}`);
  components.selection = section('Selection', 'Checkbox, Radio, Switch & Tabs', '选择原语分别表达多选、单选、布尔开关和内容分组，不能通过外观猜测语义。', () => html`${primitive('Checkbox','多选 / 可并列','<label class="check-control"><input type="checkbox" checked><span></span>保存到 Workspace</label>','允许同时选择多个互不排斥的选项。')}${primitive('Radio','单选 / 互斥','<div class="demo-row"><label class="radio-control"><input type="radio" name="runtime2" checked><span></span>本地 Agent</label><label class="radio-control"><input type="radio" name="runtime2"><span></span>云端会话</label></div>','选项少且互斥时优先使用 Radio。')}${primitive('Switch','即时布尔状态','<button class="switch-control" type="button" aria-pressed="false" data-switch-demo><span></span><b>通知</b></button>','适合即时生效的开关，不替代需要提交的表单选择。')}${primitive('Tabs','同层内容切换','<div class="segmented" role="tablist"><button class="active" role="tab" aria-selected="true">全部</button><button role="tab" aria-selected="false">运行中</button><button role="tab" aria-selected="false">已完成</button></div>','Tab 只切换同一上下文中的内容，不承担页面导航。')}`);
  components.navigation = section('Navigation', 'Navigation, Menus & Pagination', '导航原语为用户提供位置感、层级感和返回路径；每个原语独立承担一种空间关系。', () => html`${primitive('Sidebar Navigation','持久位置 / 桌面','<nav class="mini-sidebar standalone-nav"><strong>工作台</strong><button class="active">会话</button><button>Workspace</button><button>设置</button></nav>','桌面保留持久侧栏，移动端转为抽屉。')}${primitive('Breadcrumbs','层级位置 / 返回','<div class="breadcrumbs"><a href="#">工作台</a><span>/</span><strong>会话详情</strong></div>','只在层级确实存在时显示，不重复页面标题。')}${primitive('Tabs Navigation','同级页面导航','<div class="tabs-line"><button class="active">消息</button><button>事件</button><button>产物</button></div>','当前项必须可见，并与内容区域保持对齐。')}${primitive('Pagination','长列表分页','<div class="pagination-demo" data-pagination-demo><div class="pagination"><button aria-label="上一页">‹</button><button class="active">1</button><button>2</button><button>3</button><button aria-label="下一页">›</button></div><label class="pagination-size">每页 <select aria-label="每页条数"><option>10</option><option>20</option><option>50</option></select> 条</label><label class="pagination-jumper">跳至 <input type="number" min="1" max="3" value="1" aria-label="跳转页码"> 页</label><output data-pagination-info aria-live="polite">第 1 页 · 每页 10 条</output></div>','移动端优先保留前后翻页和当前页；页大小切换与快速跳页保持可用。')}`);
  components.display = section('Data Display', 'Cards, Lists, Tables & Code', '数据展示原语负责扫描、比较和定位；它们不暗含业务流程。', () => html`${primitive('Card','内容分组 / 层级','<div class="display-card"><strong>整理研究报告.md</strong><p>刚刚 · Markdown · 12 个来源</p><span class="nm-badge" data-status="completed">已完成</span></div>','Card 是容器，不自动赋予点击行为。')}${primitive('List Item','扫描 / 状态','<div class="data-list standalone-list"><div><span class="avatar-dot">N</span><strong>检查系统架构</strong><span class="nm-badge" data-status="running">运行中</span></div><div><span class="avatar-dot">A</span><strong>会议转写</strong><span class="nm-badge" data-status="waiting">待审核</span></div></div>','标题、状态、时间和主操作按固定优先级排列。')}${primitive('Table','多列比较','<table class="mini-table"><thead><tr><th>名称</th><th>状态</th><th>更新时间</th></tr></thead><tbody><tr><td>产品设计文档</td><td>已索引</td><td>今天 10:42</td></tr><tr><td>会议转写</td><td>待审核</td><td>昨天 18:20</td></tr></tbody></table>','仅在多列比较明显优于卡片时使用。')}${primitive('Code Block','命令 / 可复制','<code class="code-sample">workspace.read({ path: "report.md" })</code>','代码使用等宽字体，并提供复制反馈。')}`);
  components.feedback = section('Feedback', 'Toast, Alert, Progress & States', '反馈原语分别对应短暂通知、持续提示、过程进度和空/错/加载状态。', () => html`${primitive('Toast','短暂 / 非阻塞','<button class="nm-button" data-variant="secondary" data-nm-toast="文件已保存">触发 Toast</button>','不承载关键决策，重要信息必须在页面内留存。')}${primitive('Alert','持续 / 上下文提示','<div class="alert warning"><b>注意</b><span>远程设备当前离线。</span></div>','提示原因、影响和下一步，不能只用颜色。')}${primitive('Progress','过程 / 可预期','<div class="progress-demo"><div><span>索引知识库</span><strong>68%</strong></div><div class="progress-track"><i style="width:68%"></i></div></div>','能估算时展示进度，不能估算时展示当前阶段。')}${primitive('Empty / Error','空状态 / 错误','<div class="state-card"><div class="nm-state" data-state="error"><strong>加载失败</strong><p>保留可理解的原因和重试动作。</p></div></div>','状态说明必须带动作或恢复路径。')}`);
  components.overlay = section('Overlay', 'Dialog, Drawer, Sheet & Popover', '弹层原语共享焦点、关闭、遮罩和层级契约，但根据屏幕与任务复杂度选择不同形态。', () => html`${primitive('Popover','短菜单 / 局部上下文','<div class="popover-demo standalone-popover"><span class="popover-anchor">更多操作</span><div class="popover-panel"><button>复制链接</button><button>移动到 Workspace</button><button class="danger">删除会话</button></div></div>','桌面靠近触发点，移动端通常升级为 Action Sheet。')}${primitive('Dialog','确认 / 阻断决策','<div class="demo-dialog"><strong>删除此 Workspace？</strong><p>删除后当前端的本地引用将被移除，该操作不可撤销。</p><div class="demo-row"><button class="nm-button" data-variant="secondary">取消</button><button class="nm-button" data-variant="danger">确认删除</button></div></div>','危险动作必须明确风险，并提供取消。')}${primitive('Drawer / Sheet','侧向 / 底部容器','<div class="responsive-overlay"><div><span>Desktop</span><strong>右侧 Drawer</strong><small>保留主上下文</small></div><div><span>Mobile</span><strong>底部 Sheet</strong><small>适配触摸和单列阅读</small></div></div>','同一内容契约，改变容器方向和进入方式。')}`);
  const single = (label, title, intro, name, contract, body, rule) => {
    const canonicalName = componentZhNames[label] ? label : name;
    const normalizedTitle = title.includes('（') || !componentZhNames[canonicalName]
      ? title
      : `${canonicalName}（${componentZhNames[canonicalName]}）`;
    return section(label, normalizedTitle, intro, () => html`${primitive(name, contract, body, rule)}`);
  };
  components.button = single('Button', 'Button 按钮', '按钮用于触发即时操作。使用明确的动作动词，并根据风险选择层级。', 'Button', 'Primary / Default / Dashed / Text / Link', '<div class="demo-row"><button class="nm-button" data-variant="primary">创建会话</button><button class="nm-button" data-variant="secondary">默认</button><button class="nm-button" data-variant="dashed">虚线</button><button class="nm-button" data-variant="ghost">文本</button><button class="nm-button" data-variant="link">链接</button><button class="nm-button" data-variant="danger">删除</button><button class="nm-button" data-variant="primary" data-loading-demo>加载</button><button class="nm-button" data-variant="secondary" disabled>禁用</button></div>', '主操作每个上下文只保留一个；不可逆动作使用 danger。');
  components.iconButton = single('Icon Button', 'Icon Button 图标按钮', '只使用图标表达高频、可识别的操作；必须提供 aria-label。', 'Icon Button', 'Tooltip / aria-label / 24·32·40', '<div class="demo-row"><button class="nm-icon-button" aria-label="搜索"><span class="nm-icon nm-icon-search" aria-hidden="true"></span></button><button class="nm-icon-button" aria-label="更多"><span class="nm-icon nm-icon-more" aria-hidden="true"></span></button><button class="nm-icon-button" aria-label="关闭"><span class="nm-icon nm-icon-close" aria-hidden="true"></span></button></div>', '图标辅助识别，不能替代关键文案。');
  components.input = single('Input', 'Input 输入框', '输入框用于短文本、搜索和可编辑值。', 'Input', 'value / placeholder / allowClear / disabled', '<div class="field-state-stack"><label class="standalone-field">Workspace 名称<span class="clearable-input" data-clearable-input><span class="nm-field"><input value="产品设计文档" placeholder="输入名称"></span><button type="button" aria-label="清空输入" data-clear-input><span class="nm-icon nm-icon-close" aria-hidden="true"></span></button></span></label><label class="standalone-field">错误<span class="nm-field field-error"><input value="无效路径" aria-invalid="true"></span><small>请输入可访问的 Workspace。</small></label></div>', '默认控件高度 32px；allowClear 开启后点击右侧 × 清空全部文本。');
  components.inputNumber = single('InputNumber', 'InputNumber（数字输入）', '数字输入提供步进、边界和直接编辑能力。', 'InputNumber', 'value / min / max / step / precision', '<div class="number-input" data-number-demo><button type="button" aria-label="减少" data-number-action="decrease"><span class="nm-icon nm-icon-minus" aria-hidden="true"></span></button><input aria-label="数量" type="number" inputmode="numeric" min="0" max="10" step="1" value="3"><button type="button" aria-label="增加" data-number-action="increase"><span class="nm-icon nm-icon-plus" aria-hidden="true"></span></button></div>', '只接受数字；当前范围 0–10，步长为 1，按钮和键盘输入保持同一规则。');
  components.autocomplete = single('AutoComplete', 'AutoComplete（自动完成）', '当选项数量较多且用户可能知道目标值时，使用输入驱动的建议列表。', 'AutoComplete', 'Input + Suggestions + Empty', '<div class="autocomplete-demo"><span class="search-prefix"><span class="nm-icon nm-icon-search" aria-hidden="true"></span></span><input aria-label="搜索组件" value="Select"><div class="autocomplete-options"><button><strong>Select</strong><small>Data Entry</small></button><button><strong>Select API</strong><small>Documentation</small></button></div></div>', '键盘上下选择，空结果必须有解释。');
  components.checkbox = single('Checkbox', 'Checkbox 多选框', 'Checkbox 表示可同时选择的多个选项。', 'Checkbox', 'Checked / Indeterminate / Disabled', '<div class="selection-stack"><label class="check-control"><input type="checkbox" checked><span></span>保存到 Workspace</label><label class="check-control"><input type="checkbox" data-indeterminate="true"><span></span>已选择部分文件</label><label class="check-control"><input type="checkbox" disabled><span></span>不可用选项</label></div>', '选项互斥时使用 Radio，不要用 Checkbox 模拟单选。');
  const datePickerDemo = (mode = 'desktop') => html`<div class="date-demo ${mode}" data-date-demo data-platform-mode="${mode}"><div class="date-trigger" role="combobox" tabindex="0" aria-haspopup="dialog" aria-expanded="false"><input data-date-label aria-label="日期" value="2026年09月05日" inputmode="numeric" autocomplete="off"><span class="icon-chevron" aria-hidden="true"></span></div><div class="date-popover" hidden><div class="date-panel-header"><strong>2026年09月</strong><button type="button" data-date-clear aria-label="清除日期">清除</button></div><div class="date-grid">${['01','02','03','04','05','06','07','08','09','10','11','12','13','14','15','16','17','18','19','20','21'].map(day => html`<button type="button" data-date-value="2026年09月${day}日" aria-selected="${day === '05'}" class="${day === '05' ? 'selected' : ''}">${day}</button>`).join('')}</div><label class="date-option date-time-option"><input type="checkbox" data-date-show-time>同时选择时间</label><input type="time" data-date-time value="14:30" aria-label="选择时间" hidden><label class="date-option">尺寸 <select data-date-size aria-label="控件尺寸"><option value="middle">中</option><option value="small">小</option><option value="large">大</option></select></label><label class="date-option">变体 <select data-date-variant aria-label="控件变体"><option value="outlined">描边</option><option value="borderless">无边框</option><option value="filled">填充</option><option value="underlined">下划线</option></select></label></div></div>`;
  const datePickerPair = () => `<div class="platform-pair"><section><h4>PC端 · Popover 日历</h4>${datePickerDemo('desktop')}</section><section><h4>移动端 · Sheet 日历</h4>${datePickerDemo('mobile')}</section></div>`;
  components.datePicker = single('Date Picker', 'DatePicker（日期选择）', '日期选择用于需要标准化日期格式的场景。', 'DatePicker', 'value / defaultValue / format / picker / disabledDate / showTime / allowClear / disabled', datePickerPair(), '点击触发器展开日历；桌面使用 Popover，移动端使用 Sheet；范围选择由独立的 RangePicker 原语承担。');
  components.mentions = single('Mentions', 'Mentions 提及', '在输入中引用成员、Agent 或上下文对象。', 'Mentions', 'Trigger @ + Suggestions', '<div class="autocomplete-demo"><span class="search-prefix">@</span><input aria-label="提及对象" placeholder="输入 @ 选择 Agent"><div class="autocomplete-options"><button><strong>本地 Agent</strong><small>运行节点</small></button><button><strong>研究报告</strong><small>Workspace 文件</small></button></div></div>', '候选项需要来源和类型，避免同名对象混淆。');
  components.radio = single('Radio', 'Radio 单选框', 'Radio 表示一组互斥选项，选项较少时优先使用。', 'Radio', 'Checked / Disabled / Group', '<div class="demo-row"><label class="radio-control"><input type="radio" name="runtime3" checked><span></span>本地 Agent</label><label class="radio-control"><input type="radio" name="runtime3"><span></span>云端会话</label><label class="radio-control"><input type="radio" name="runtime3" disabled><span></span>不可用</label></div>', '少于五个互斥选项时，优先让选项直接可见。');
  components.rate = single('Rate', 'Rate 评分', 'Rate 用于表达离散的主观评价或质量反馈。', 'Rate', 'Value / Half / Readonly', '<div class="rate-demo" data-rate-demo aria-label="评分"><button type="button" data-rate-value="1" aria-label="1 星">☆</button><button type="button" data-rate-value="2" aria-label="2 星">☆</button><button type="button" data-rate-value="3" aria-label="3 星">☆</button><button type="button" data-rate-value="4" aria-label="4 星">☆</button><button type="button" data-rate-value="5" aria-label="5 星">☆</button><output data-rate-output>0 / 5</output><label class="rate-option"><input type="checkbox" data-rate-allow-half>允许半星</label><label class="rate-option"><input type="checkbox" data-rate-allow-clear checked>允许清除</label><label class="rate-option"><input type="checkbox" data-rate-readonly>只读</label><label class="rate-option"><input type="checkbox" data-rate-disabled>禁用</label></div>', '点击评分；重复点击当前分值时，allowClear 开启才清除。');
  components.select = single('Select', 'Select 选择器', 'Select 用于从一组候选项中选择一个值。它在桌面与移动端使用不同容器，但共享同一语义契约。', 'Select', 'Desktop Popover / Mobile Bottom Sheet / Listbox', `${selectMarkup('desktop')}${selectMarkup('mobile')}`, 'Desktop 使用紧凑 Popover；Mobile 使用触摸友好的 Bottom Sheet。');
  components.slider = single('Slider', 'Slider 滑动输入', 'Slider 用于连续范围中的近似选择，并显示当前值。', 'Slider', 'Min / Max / Step / Range / Tooltip', '<label class="slider-option"><input type="checkbox" data-slider-range>范围模式</label><div class="slider-demo" data-slider-demo><input type="range" min="0" max="100" value="68" aria-label="进度" data-slider-start><input type="range" min="0" max="100" value="82" aria-label="范围结束" data-slider-end hidden><output>68</output></div><div class="slider-labels"><span>0</span><strong data-slider-value>68</strong><span>100</span></div>', '精确值输入使用 Input Number，范围选择才使用 Slider。');
  components.switch = single('Switch', 'Switch 开关', 'Switch 表示即时生效的布尔状态。', 'Switch', 'On / Off / Loading / Disabled', '<button class="switch-control" type="button" aria-pressed="false" data-switch-demo><span></span><b>通知</b></button>', '不用于需要提交后才生效的表单状态。');
  const timePickerDemo = (mode = 'desktop') => { const hours = Array.from({length: 24}, (_, index) => String(index).padStart(2, '0')); const minutes = Array.from({length: 60}, (_, index) => String(index).padStart(2, '0')); const seconds = Array.from({length: 60}, (_, index) => String(index).padStart(2, '0')); return html`<div class="time-picker-demo ${mode}" data-time-demo data-platform-mode="${mode}" data-time-hour="14" data-time-minute="30" data-time-second="00"><div class="date-trigger time-trigger" role="combobox" tabindex="0" aria-haspopup="dialog" aria-expanded="false"><input data-time-label aria-label="时间" value="14:30:00" inputmode="numeric" autocomplete="off"><span class="icon-chevron" aria-hidden="true"></span></div><div class="time-options"><label class="time-option"><input type="checkbox" data-time-need-confirm>选择后点击确定</label><label class="time-option"><input type="checkbox" data-time-use12>12 小时制</label><label class="time-option">尺寸 <select data-time-size aria-label="控件尺寸"><option value="middle">中</option><option value="small">小</option><option value="large">大</option></select></label><label class="time-option">变体 <select data-time-variant aria-label="控件变体"><option value="outlined">描边</option><option value="borderless">无边框</option><option value="filled">填充</option><option value="underlined">下划线</option></select></label><label class="time-option">时 <select data-time-hour-step aria-label="小时步长"><option>1</option><option>2</option><option>3</option></select></label><label class="time-option">分 <select data-time-minute-step aria-label="分钟步长"><option>1</option><option>5</option><option>15</option></select></label><label class="time-option">秒 <select data-time-second-step aria-label="秒步长"><option>1</option><option>5</option><option>15</option></select></label></div><div class="time-popover" hidden><div class="time-panel-header"><strong>选择时间</strong><div><select data-time-meridiem aria-label="上午或下午"><option value="AM">上午</option><option value="PM" selected>下午</option></select><button type="button" data-time-now>现在</button><button type="button" data-time-clear>清除</button></div></div><div class="time-columns"><div class="time-column" role="listbox" aria-label="小时">${hours.map(hour => `<button type="button" role="option" aria-selected="${hour === '14'}" data-time-part="hour" data-time-value="${hour}" class="${hour === '14' ? 'selected' : ''}">${hour}</button>`).join('')}</div><div class="time-column" role="listbox" aria-label="分钟">${minutes.map(minute => `<button type="button" role="option" aria-selected="${minute === '30'}" data-time-part="minute" data-time-value="${minute}" class="${minute === '30' ? 'selected' : ''}">${minute}</button>`).join('')}</div><div class="time-column" role="listbox" aria-label="秒">${seconds.map(second => `<button type="button" role="option" aria-selected="${second === '00'}" data-time-part="second" data-time-value="${second}" class="${second === '00' ? 'selected' : ''}">${second}</button>`).join('')}</div></div><div class="time-panel-footer"><small>HH:mm:ss · minuteStep 1</small><button type="button" class="nm-button" data-time-confirm hidden>确定</button></div></div></div>`; };
  const timePickerPair = () => `<div class="platform-pair"><section><h4>PC端 · Popover 时间列</h4>${timePickerDemo('desktop')}</section><section><h4>移动端 · Sheet 时间列</h4>${timePickerDemo('mobile')}</section></div>`;
  components.timePicker = single('Time Picker', 'TimePicker（时间选择）', '时间选择必须与日期和粒度一起表达。', 'TimePicker', 'value / format / hourStep / minuteStep / secondStep / use12Hours / allowClear / needConfirm', timePickerPair(), '跨端保持格式、时区和时间粒度语义一致；桌面使用 Popover，移动端使用 Sheet。');
  components.transfer = single('Transfer', 'Transfer 穿梭框', 'Transfer 用于在两个集合之间批量移动条目。', 'Transfer', 'Source / Target / Search / Batch', '<div class="transfer-demo"><div><small>可选文件</small><input type="search" placeholder="搜索文件" aria-label="搜索可选文件"><span>会议纪要.md</span><span>需求评审.pdf</span></div><b>→</b><div><small>已加入 Workspace</small><input type="search" placeholder="搜索文件" aria-label="搜索已加入文件"><span>产品设计.md</span></div></div>', '移动端使用单列集合和底部确认动作。');
  components.uploadComponent = single('Upload', 'Upload 上传', 'Upload 是文件导入的入口，需要表达类型、大小、预览、进度和失败恢复。', 'Upload', 'fileList / accept / multiple / maxCount / beforeUpload / onChange', '<div class="upload-dropzone" data-upload-demo><span class="upload-visual" aria-hidden="true"><span class="nm-icon nm-icon-upload"></span></span><strong>拖入文件到这里</strong><span>支持 Markdown、PDF、图片、音频 · 单文件不超过 200MB</span><label class="nm-button" data-variant="secondary">选择文件<input type="file" data-upload-input multiple accept=".md,.pdf,image/*,audio/*"></label><div class="upload-list" data-upload-list></div></div>', '桌面支持拖拽和缩略图预览；移动端保留系统文件选择，类型、数量和失败提示由外部参数控制。');
  components.badge = single('Badge', 'Badge 徽标', 'Badge 表达短状态或数量，不承载复杂交互。', 'Badge', 'count / dot / status / color', '<div class="badge-demo" data-badge-demo><div class="demo-row"><span class="nm-badge" data-badge-view data-status="running">3</span><span class="nm-badge" data-status="waiting">待审批</span><span class="nm-badge" data-status="failed">失败</span></div><label>数量 <input type="number" min="0" max="99" value="3" data-badge-count></label><label><input type="checkbox" data-badge-dot>点状</label><label>状态 <select data-badge-status><option value="running">processing</option><option value="completed">success</option><option value="waiting">warning</option><option value="failed">error</option></select></label></div>', '状态颜色不能是唯一信息来源；数量和点状模式必须保持相同语义。');
  components.table = single('Table', 'Table 表格', 'Table 用于多列比较和批量管理。', 'Table', 'Header / Row / Sort / Empty', '<table class="mini-table"><thead><tr><th>名称</th><th>状态</th><th>更新时间</th></tr></thead><tbody><tr><td>产品设计文档</td><td>已索引</td><td>今天 10:42</td></tr><tr><td>会议转写</td><td>待审核</td><td>昨天 18:20</td></tr></tbody></table>', '移动端转为单列列表，保留同样的信息优先级。');
  components.tag = single('Tag', 'Tag 标签', 'Tag 用于分类、筛选和表达可移除的上下文。', 'Tag', 'Default / Closable / Checkable', '<div class="demo-row tag-demo-row" data-tag-demo><button type="button" class="tag-demo is-checked">知识库</button><button type="button" class="tag-demo">Markdown</button><button type="button" class="tag-demo tag-closable">本地 <span aria-hidden="true">×</span></button></div>', 'Tag 是分类，Badge 是状态；可选标签可切换，closable 标签必须能独立关闭。');
  components.timeline = single('Timeline', 'Timeline 时间线', 'Timeline 按时间顺序表达 Agent 事件、来源和审批节点。', 'Timeline', 'Past / Current / Future', '<ol class="timeline"><li><b>读取 Workspace</b><small>10:37 · 12 个文件</small></li><li class="current"><b>等待审批</b><small>现在 · 需要用户确认</small></li></ol>', '当前节点必须突出，失败节点必须保留恢复路径。');
  components.tree = single('Tree', 'Tree 树形控件', 'Tree 用于文件、知识和层级关系的展开与选择。', 'Tree', 'Expand / Select / Load', '<div class="tree-demo" data-tree-demo><button type="button" data-tree-toggle aria-expanded="true">⌄ Workspace</button><div data-tree-children><button type="button" data-tree-toggle aria-expanded="true">⌄ docs</button><div data-tree-children><button type="button">　report.md</button><button type="button">　design.md</button></div></div></div>', '展开状态、缩进和键盘路径必须稳定。');
  components.tooltip = single('Tooltip', 'Tooltip 文字提示', 'Tooltip 补充解释性信息，不承载关键操作。', 'Tooltip', 'Hover / Focus / Delay', '<button class="tooltip-trigger" data-nm-toast="这是补充说明">悬停或聚焦查看说明 <span>?</span></button>', '移动端需要等价的点击或帮助入口。');
  components.alert = single('Alert', 'Alert 警告提示', 'Alert 是持续存在的上下文提示，需要说明影响和下一步。', 'Alert', 'message / description / type / closable / showIcon / action', '<div class="alert warning" data-closable="true"><span class="alert-icon" aria-hidden="true">!</span><b>注意</b><span>远程设备当前离线。</span></div>', '不能只改变颜色而没有状态文字；可关闭提示必须保留清晰的关闭入口。');
  components.empty = single('Empty', 'Empty 空状态', 'Empty 说明为什么暂时没有内容，并提供下一步。', 'Empty', 'image / description / action / imageStyle', '<div class="state-card"><div class="nm-state empty-visual"><div class="empty-illustration"><i></i><b>✦</b><span></span></div><strong>暂无知识内容</strong><p>选择 Workspace 后，NoteMeld 会把文件整理成可验证的知识。</p><button class="nm-button" data-variant="primary">选择 Workspace</button></div></div>', '空状态不是空白页面；插图说明当前语境，动作指向下一步。');
  components.spin = single('Spin', 'Spin 加载中', 'Spin 用于短时、局部且无法估算进度的等待。', 'Spin', 'spinning / size / tip / delay', '<div class="spin-demo" data-spin-demo><div class="spin-orbit" data-spin-indicator role="status" aria-live="polite"><i></i><b></b><span>✦</span></div><div><strong data-spin-title>正在编译知识</strong><small data-spin-tip>读取 Workspace 中的来源与结构…</small></div></div>', '用有语义的局部动画表达 Agent 正在工作；可估算时使用 Progress。');
  components.progress = single('Progress', 'Progress 进度', 'Progress 用于可估算的长任务，并让用户知道是否可以离开。', 'Progress', 'Percent / Status / Success', '<div class="progress-demo"><div><span>索引知识库</span><strong>68%</strong></div><div class="progress-track"><i style="width:68%"></i></div></div>', '进度不能伪造底层任务状态。');
  components.result = single('Result', 'Result 结果', 'Result 汇总完成、失败或需要用户介入的最终状态。', 'Result', 'Icon / Title / Extra action', '<div class="result-demo"><b>✓</b><strong>索引完成</strong><span>已处理 24 个文件。</span><button class="nm-button" data-variant="primary">查看知识库</button></div>', '结果要有明确下一步，而不是只显示成功图标。');
  components.modal = single('Modal', 'Modal 对话框', 'Modal 阻断当前流程，用于确认、编辑或解释重要决策。', 'Modal', 'open / title / okText / cancelText / onOk / onCancel / centered', '<div class="modal-demo" data-modal-demo><button type="button" class="nm-button" data-variant="danger" data-modal-open>打开危险确认</button><div class="demo-dialog" role="dialog" aria-modal="true" aria-labelledby="modal-title" hidden><strong id="modal-title">删除此 Workspace？</strong><p>删除后当前端的本地引用将被移除，该操作不可撤销。</p><div class="demo-row"><button type="button" class="nm-button" data-variant="secondary" data-modal-close>取消</button><button type="button" class="nm-button" data-variant="danger" data-modal-close>确认删除</button></div></div></div>', '桌面使用居中 Dialog；移动端转为 Bottom Sheet，风险和动作顺序不变。');
  components.drawer = single('Drawer', 'Drawer 抽屉', 'Drawer 从侧边进入，用于保留主上下文的辅助内容。', 'Drawer', 'open / title / placement / width / closable / onClose', '<div class="drawer-demo" data-drawer-demo><button type="button" class="nm-button" data-variant="secondary" data-drawer-open>打开辅助内容</button><aside class="demo-drawer" role="dialog" aria-modal="true" aria-labelledby="drawer-title" hidden><div><strong id="drawer-title">Workspace 来源</strong><button type="button" class="nm-icon-button" aria-label="关闭抽屉" data-drawer-close><span class="nm-icon nm-icon-close" aria-hidden="true"></span></button></div><p>保留主上下文，在侧边查看来源和运行信息。</p></aside></div>', '桌面从右侧进入；移动端根据任务转为 Bottom Sheet 或全屏层。');
  components.popover = single('Popover', 'Popover 气泡卡片', 'Popover 承载靠近触发点的短内容或局部菜单。', 'Popover', 'Anchor / Placement / Dismiss', '<div class="popover-demo standalone-popover"><span class="popover-anchor">更多操作</span><div class="popover-panel"><button>复制链接</button><button>移动到 Workspace</button><button class="danger">删除会话</button></div></div>', '不承载关键说明；移动端升级为 Action Sheet。');
  components.breadcrumb = single('Breadcrumb', 'Breadcrumb 面包屑', 'Breadcrumb 表达页面层级，并提供返回上级的路径。', 'Breadcrumb', 'Items / Separator / Current', '<div class="breadcrumbs"><a href="#">工作台</a><span>/</span><a href="#">Workspace</a><span>/</span><strong>会话详情</strong></div>', '只有存在层级关系时才显示。');
  components.pagination = single('Pagination', 'Pagination 分页', 'Pagination 用于长列表的页码导航。', 'Pagination', 'current / pageSize / total / showSizeChanger / showQuickJumper', '<div class="pagination-demo" data-pagination-demo><div class="pagination"><button aria-label="上一页">‹</button><button class="active">1</button><button>2</button><button>3</button><button aria-label="下一页">›</button></div><label class="pagination-size">每页 <select aria-label="每页条数"><option>10</option><option>20</option><option>50</option></select> 条</label><label class="pagination-jumper">跳至<input type="number" min="1" max="3" value="1" aria-label="跳转页码">页</label><output data-pagination-info aria-live="polite">第 1 页 · 每页 10 条</output></div>', '移动端优先保留当前页、前后翻页；页大小切换和快速跳页保持可用。');
  components.tabs = single('Tabs', 'Tabs 标签页', 'Tabs 在同一上下文中切换同级内容。', 'Tabs', 'Tablist / Tab / Panel / Selected', '<div class="tabs-line"><button class="active">消息</button><button>事件</button><button>产物</button></div>', 'Tab 只切换内容，不代替页面导航。');
  components.menu = single('Menu', 'Menu 菜单', 'Menu 提供一组有层级的操作或导航项。', 'Menu', 'Item / Group / Separator / Danger', '<div class="popover-demo standalone-popover menu-reference"><button type="button" class="popover-anchor" aria-label="打开操作菜单">操作菜单</button><div class="popover-panel menu-demo" hidden><button type="button">打开会话</button><button type="button">复制链接</button><hr><button type="button" class="danger">删除会话</button></div></div>', '菜单由触发器定位，支持选中、关闭和危险项分组。');
  components.divider = single('Divider', 'Divider 分割线', 'Divider 分隔同一层级中的内容，不制造新的容器。', 'Divider', 'Horizontal / Vertical / Text', '<div class="divider-demo"><span>会话上下文</span><hr><span>Agent 产物</span></div>', '分割线服务于结构，不替代间距。');

  let activeMenu = 'values';
  const renderNav = () => { nav.innerHTML = groups[activeMenu].map(([heading, items]) => `<h2>${heading}</h2>${items.map(([id,label]) => `<button type="button" data-section="${id}">${label}</button>`).join('')}`).join(''); };
  const normalizeLegacyIcons = () => {
    const iconNames = {'⌕':'search','⋯':'more','−':'minus','＋':'plus','×':'close','✓':'check','‹':'chevron-left','›':'chevron-right'};
    content.querySelectorAll('button, .result-demo>b, .search-prefix').forEach(node => {
      const name = iconNames[node.textContent.trim()];
      if (!name || node.children.length) return;
      node.textContent = '';
      const iconNode = document.createElement('span');
      iconNode.className = 'nm-icon nm-icon-' + name;
      iconNode.setAttribute('aria-hidden', 'true');
      node.append(iconNode);
    });
  };
  const bind = () => {
    window.NoteMeldDesignSystem?.markLegacyPrimitives();
    window.NoteMeldDesignSystem?.bindPrimitiveActions();
    document.querySelectorAll('.primitive-showcase .nm-button, .primitive-showcase .nm-icon-button').forEach(button => {
      if (button.disabled || button.dataset.demoActionBound || button.dataset.loadingDemo || button.hasAttribute('data-nm-toast')) return;
      if (button.closest('[data-upload-demo], [data-modal-demo], [data-drawer-demo]') || button.querySelector('input[type="file"]')) return;
      button.dataset.demoActionBound = 'true';
      button.addEventListener('click', () => {
        const label = button.getAttribute('aria-label') || button.textContent.trim() || '按钮';
        window.NoteMeldDesignSystem?.notify(`${label}：参考交互已触发`);
      });
    });
    document.querySelectorAll('[data-modal-demo] .demo-dialog').forEach(dialog => { dialog.dataset.boundModal = 'true'; });
    if (!document.body.dataset.nmOverlayDismissBound) {
      document.body.dataset.nmOverlayDismissBound = 'true';
      document.addEventListener('pointerdown', event => {
        const target = event.target;
        document.querySelectorAll('.select-reference:not(.is-closed), .date-demo.is-open, .time-picker-demo.is-open, .popover-demo .popover-panel:not([hidden])').forEach(container => {
          if (container.contains(target)) return;
          const select = container.matches('.select-reference') ? container : container.closest('.select-reference');
          if (select && select.querySelector('[data-select-open]')?.checked !== true) { select.classList.add('is-closed'); select.querySelector('.select-trigger')?.setAttribute('aria-expanded', 'false'); }
          const demo = container.matches('.date-demo, .time-picker-demo') ? container : container.closest('.date-demo, .time-picker-demo');
          if (demo && demo.querySelector('[data-date-open-control], [data-time-open]')?.checked !== true) { demo.classList.remove('is-open'); demo.querySelector('.date-popover, .time-popover')?.setAttribute('hidden', ''); demo.querySelector('.date-trigger')?.setAttribute('aria-expanded', 'false'); }
          if (container.matches('.popover-panel')) container.setAttribute('hidden', '');
        });
      });
    }
    document.querySelectorAll('[data-platform-target]').forEach(button => { button.onclick = () => { const panel = button.closest('.primitive-showcase'); const platform = button.dataset.platformTarget; panel.dataset.platform = platform; panel.querySelectorAll('[data-platform-target]').forEach(item => { const selected = item === button; item.classList.toggle('active', selected); item.setAttribute('aria-selected', String(selected)); }); }; });
    document.querySelectorAll('.primitive-showcase').forEach(showcase => {
      const heading = showcase.querySelector('.primitive-heading h3')?.textContent || '';
      const radios = [...showcase.querySelectorAll('.radio-control')];
      if (!heading.startsWith('Radio') || !radios.length || showcase.dataset.radioOptionsBound) return;
      showcase.dataset.radioOptionsBound = 'true';
      const group = radios[0].parentElement;
      radios.forEach(label => {
        const input = label.querySelector('input');
        if (input) input.dataset.baseDisabled = String(input.disabled);
      });
      const options = document.createElement('div');
      options.className = 'radio-options';
      options.innerHTML = '<label>选项类型 <select data-radio-option-type aria-label="Radio 选项类型"><option value="default">普通</option><option value="button">按钮</option></select></label><label>按钮样式 <select data-radio-button-style aria-label="Radio 按钮样式"><option value="outline">描边</option><option value="solid">实心</option></select></label><label>尺寸 <select data-radio-size aria-label="Radio 尺寸"><option value="small">小</option><option value="middle" selected>中</option><option value="large">大</option></select></label><label><input type="checkbox" data-radio-disabled>整体禁用</label>';
      group.after(options);
      const sync = () => {
        const disabled = options.querySelector('[data-radio-disabled]')?.checked === true;
        group.dataset.radioStyle = options.querySelector('[data-radio-button-style]')?.value || 'outline';
        group.dataset.radioOptionType = options.querySelector('[data-radio-option-type]')?.value || 'default';
        group.dataset.radioSize = options.querySelector('[data-radio-size]')?.value || 'middle';
        radios.forEach(label => {
          const input = label.querySelector('input');
          if (!input) return;
          input.disabled = disabled || input.dataset.baseDisabled === 'true';
          label.classList.toggle('is-disabled', input.disabled);
        });
      };
      options.querySelectorAll('select,input').forEach(control => control.addEventListener('change', sync));
      sync();
    });
    document.querySelectorAll('.primitive-showcase').forEach(showcase => {
      const heading = showcase.querySelector('.primitive-heading h3')?.textContent || '';
      const input = showcase.querySelector('[data-clearable-input] input');
      const field = input?.closest('.nm-field');
      const stack = input?.closest('.field-state-stack');
      if (!heading.startsWith('Input（') || !input || !field || !stack || showcase.dataset.inputOptionsBound) return;
      showcase.dataset.inputOptionsBound = 'true';
      const options = document.createElement('div');
      options.className = 'input-options';
      options.innerHTML = '<label>状态 <select data-input-status aria-label="Input 状态"><option value="default">默认</option><option value="success">成功</option><option value="warning">警告</option><option value="error">错误</option></select></label><label>最大长度 <select data-input-max-length aria-label="Input 最大长度"><option value="0">不限</option><option value="20">20</option><option value="40">40</option></select></label><label><input type="checkbox" data-input-show-count>显示字数</label><label><input type="checkbox" data-input-disabled>禁用</label>';
      stack.after(options);
      const clear = input.closest('[data-clearable-input]')?.querySelector('[data-clear-input]');
      const count = document.createElement('small'); count.className = 'input-count'; count.setAttribute('aria-live', 'polite'); count.hidden = true; input.closest('[data-clearable-input]')?.append(count);
      const sync = () => {
        const disabled = options.querySelector('[data-input-disabled]')?.checked === true;
        const maxLength = Number(options.querySelector('[data-input-max-length]')?.value || 0);
        const status = options.querySelector('[data-input-status]')?.value || 'default';
        input.disabled = disabled;
        if (maxLength > 0) input.maxLength = maxLength;
        else input.removeAttribute('maxlength');
        field.dataset.status = status;
        field.classList.toggle('is-disabled', disabled);
        count.hidden = options.querySelector('[data-input-show-count]')?.checked !== true;
        count.textContent = maxLength > 0 ? `${input.value.length} / ${maxLength}` : `${input.value.length}`;
        if (clear) clear.hidden = disabled || !input.value || input.closest('[data-clearable-input]')?.querySelector('[data-input-allow-clear]')?.checked !== true;
      };
      options.querySelectorAll('select,input').forEach(control => control.addEventListener('change', sync));
      input.addEventListener('input', sync);
      sync();
    });
    document.querySelectorAll('.primitive-showcase').forEach(showcase => {
      const heading = showcase.querySelector('.primitive-heading h3')?.textContent || '';
      if (!heading.startsWith('Button（') || showcase.dataset.buttonOptionsBound) return;
      showcase.dataset.buttonOptionsBound = 'true';
      const sample = document.createElement('div');
      sample.className = 'button-api-demo';
      sample.innerHTML = '<button type="button" class="nm-button" data-button-api-target>示例按钮</button><div class="button-api-options"><label>类型 <select data-button-type aria-label="Button 类型"><option value="primary">主按钮</option><option value="secondary">默认</option><option value="dashed">虚线</option><option value="ghost">文本</option><option value="link">链接</option></select></label><label>尺寸 <select data-button-size aria-label="Button 尺寸"><option value="sm">小</option><option value="md" selected>中</option><option value="lg">大</option></select></label><label>形状 <select data-button-shape aria-label="Button 形状"><option value="default">默认</option><option value="round">圆角</option><option value="circle">圆形</option></select></label><label><input type="checkbox" data-button-danger>危险</label><label><input type="checkbox" data-button-loading>加载中</label><label><input type="checkbox" data-button-disabled>禁用</label></div>';
      showcase.querySelector('.primitive-body')?.append(sample);
      const button = sample.querySelector('[data-button-api-target]');
      const sync = () => {
        const type = sample.querySelector('[data-button-type]')?.value || 'primary';
        const danger = sample.querySelector('[data-button-danger]')?.checked === true;
        const loading = sample.querySelector('[data-button-loading]')?.checked === true;
        const disabled = sample.querySelector('[data-button-disabled]')?.checked === true;
        const size = sample.querySelector('[data-button-size]')?.value || 'md';
        const shape = sample.querySelector('[data-button-shape]')?.value || 'default';
        button.dataset.variant = danger ? 'danger' : type;
        button.dataset.size = size;
        button.dataset.shape = shape;
        button.disabled = disabled || loading;
        button.setAttribute('aria-busy', String(loading));
        button.textContent = loading ? '加载中…' : '示例按钮';
      };
      sample.querySelectorAll('select,input').forEach(control => control.addEventListener('change', sync));
      button.addEventListener('click', () => window.NoteMeldDesignSystem?.notify('Button：参考交互已触发'));
      sync();
    });
    document.querySelectorAll('[data-loading-demo]').forEach(button => button.addEventListener('click', () => { if (button.getAttribute('aria-busy') === 'true') return; button.setAttribute('aria-busy', 'true'); button.disabled = true; button.textContent = '加载中…'; window.setTimeout(() => { button.setAttribute('aria-busy', 'false'); button.disabled = false; button.textContent = '加载'; }, 900); }));
    document.querySelectorAll('[data-clearable-input]').forEach(wrapper => { const input = wrapper.querySelector('input'); const clear = wrapper.querySelector('[data-clear-input]'); if (!input || !clear) return; const control = document.createElement('label'); control.className = 'input-option'; control.innerHTML = '<input type="checkbox" data-input-allow-clear>允许清除'; wrapper.parentElement?.append(control); const sync = () => { clear.hidden = !control.querySelector('input')?.checked || !input.value; }; clear.addEventListener('click', () => { input.value = ''; input.dispatchEvent(new Event('input', { bubbles: true })); input.focus(); sync(); }); input.addEventListener('input', sync); control.querySelector('input')?.addEventListener('change', sync); sync(); });
    document.querySelectorAll('[data-rate-demo]').forEach(demo => { let value = 0; const stars = [...demo.querySelectorAll('[data-rate-value]')]; const output = demo.querySelector('[data-rate-output]'); const allowHalf = demo.querySelector('[data-rate-allow-half]'); const allowClear = demo.querySelector('[data-rate-allow-clear]'); const readonly = demo.querySelector('[data-rate-readonly]'); const disabled = demo.querySelector('[data-rate-disabled]'); demo.setAttribute('role', 'radiogroup'); const sync = () => { const isReadonly = readonly?.checked === true; const isDisabled = disabled?.checked === true; demo.classList.toggle('is-readonly', isReadonly); demo.classList.toggle('is-disabled', isDisabled); stars.forEach(star => { const rating = Number(star.dataset.rateValue); const active = rating <= value; const half = !active && allowHalf?.checked === true && rating - 0.5 === value; star.classList.toggle('active', active); star.classList.toggle('half', half); star.textContent = active || half ? '★' : '☆'; star.disabled = isReadonly || isDisabled; star.setAttribute('aria-disabled', String(isReadonly || isDisabled)); star.setAttribute('aria-pressed', String(active || half)); star.setAttribute('aria-checked', String(rating === value || rating - 0.5 === value)); star.setAttribute('aria-label', `${rating - (half ? 0.5 : 0)} 星`); }); if (output) { output.textContent = `${value} / ${stars.length}`; output.setAttribute('aria-live', 'polite'); } demo.setAttribute('aria-label', `${value} 星评分`); }; stars.forEach(star => { star.setAttribute('role', 'radio'); star.addEventListener('click', event => { if (readonly?.checked || disabled?.checked) return; const next = Number(star.dataset.rateValue); const half = allowHalf?.checked === true && event.offsetX < star.offsetWidth / 2; const nextValue = half ? next - 0.5 : next; value = value === nextValue && allowClear?.checked !== false ? 0 : nextValue; sync(); }); star.addEventListener('keydown', event => { if (readonly?.checked || disabled?.checked || !['ArrowLeft', 'ArrowRight', 'Home', 'End', 'Enter', ' '].includes(event.key)) return; event.preventDefault(); const index = stars.indexOf(star); if (event.key === 'Enter' || event.key === ' ') { const next = Number(star.dataset.rateValue); value = value === next && allowClear?.checked !== false ? 0 : next; sync(); return; } const nextIndex = event.key === 'Home' ? 0 : event.key === 'End' ? stars.length - 1 : Math.max(0, Math.min(stars.length - 1, index + (event.key === 'ArrowRight' ? 1 : -1))); stars[nextIndex]?.focus(); value = allowHalf?.checked === true && !['Home', 'End'].includes(event.key) ? Math.max(0, Math.min(stars.length, value + (event.key === 'ArrowRight' ? 0.5 : -0.5))) : Number(stars[nextIndex]?.dataset.rateValue || 0); sync(); }); }); allowHalf?.addEventListener('change', () => { if (!allowHalf.checked && value % 1 !== 0) value = Math.round(value); sync(); }); readonly?.addEventListener('change', sync); disabled?.addEventListener('change', sync); allowClear?.addEventListener('change', sync); sync(); });
    document.querySelectorAll('[data-slider-demo]').forEach(demo => { const start = demo.querySelector('[data-slider-start]'); const end = demo.querySelector('[data-slider-end]'); const output = demo.querySelector('output'); const value = demo.closest('.platform-sample')?.querySelector('[data-slider-value]'); const rangeToggle = demo.parentElement?.querySelector('[data-slider-range]'); if (!start || demo.dataset.sliderBound) return; demo.dataset.sliderBound = 'true'; const options = document.createElement('div'); options.className = 'slider-options'; options.innerHTML = '<label><input type="checkbox" data-slider-tooltip>显示提示</label><label><input type="checkbox" data-slider-disabled>禁用</label>'; demo.after(options); const sync = () => { const isRange = rangeToggle?.checked === true; const disabled = options.querySelector('[data-slider-disabled]')?.checked === true; const showTooltip = options.querySelector('[data-slider-tooltip]')?.checked === true; if (end) end.hidden = !isRange; if (start && end && isRange && Number(start.value) > Number(end.value)) end.value = start.value; [start, end].forEach(input => { if (input) input.disabled = disabled; }); const text = isRange && end ? `${start.value} – ${end.value}` : start.value || ''; if (output) output.textContent = showTooltip ? `${text} · 当前值` : text; if (value) value.textContent = text; demo.classList.toggle('is-disabled', disabled); demo.setAttribute('aria-label', isRange ? `范围 ${text}` : `值 ${text}`); }; [start, end].forEach(input => input?.addEventListener('input', sync)); rangeToggle?.addEventListener('change', sync); options.querySelectorAll('input').forEach(input => input.addEventListener('change', sync)); sync(); });
    document.querySelectorAll('[data-tree-demo]').forEach(tree => { tree.querySelectorAll('[data-tree-toggle]').forEach(toggle => { const children = toggle.nextElementSibling; const label = toggle.textContent.replace(/^[⌄›]\s*/, '').trim(); const sync = () => { const open = toggle.getAttribute('aria-expanded') === 'true'; if (children) children.hidden = !open; toggle.textContent = `${open ? '⌄' : '›'} ${label}`; }; toggle.addEventListener('click', () => { toggle.setAttribute('aria-expanded', String(toggle.getAttribute('aria-expanded') !== 'true')); sync(); }); sync(); }); });
    document.querySelectorAll('[data-tree-demo]').forEach(tree => {
      if (tree.dataset.treeKeyboardBound) return;
      tree.dataset.treeKeyboardBound = 'true';
      tree.setAttribute('role', 'tree');
      tree.setAttribute('aria-multiselectable', 'false');
      const items = [...tree.querySelectorAll('button')];
      items.forEach((item, index) => {
        item.setAttribute('role', 'treeitem');
        item.tabIndex = index === 0 ? 0 : -1;
        item.setAttribute('aria-selected', 'false');
        if (item.hasAttribute('data-tree-toggle')) item.setAttribute('aria-expanded', item.getAttribute('aria-expanded') || 'false');
        item.addEventListener('click', () => {
          if (item.hasAttribute('data-tree-toggle')) return;
          if (options.querySelector('[data-tree-checkable]')?.checked === true) {
            const checked = item.getAttribute('aria-checked') === 'true';
            item.setAttribute('aria-checked', String(!checked));
            item.classList.toggle('is-checked', !checked);
          }
          if (options.querySelector('[data-tree-selectable]')?.checked === false) return;
          items.forEach(candidate => { candidate.classList.remove('is-selected'); candidate.setAttribute('aria-selected', 'false'); });
          item.classList.add('is-selected');
          item.setAttribute('aria-selected', 'true');
        });
      });
      const options = document.createElement('div');
      options.className = 'tree-options';
      options.innerHTML = '<label><input type="checkbox" data-tree-selectable checked>允许选择</label><label><input type="checkbox" data-tree-checkable>显示复选框</label><button type="button" class="tree-load-button" data-tree-load>加载子节点</button>';
      tree.after(options);
      const syncTreeOptions = () => {
        const selectable = options.querySelector('[data-tree-selectable]')?.checked !== false;
        const checkable = options.querySelector('[data-tree-checkable]')?.checked === true;
        tree.classList.toggle('is-checkable', checkable);
        items.filter(item => !item.hasAttribute('data-tree-toggle')).forEach(item => {
          if (!selectable) { item.classList.remove('is-selected'); item.setAttribute('aria-selected', 'false'); }
          item.setAttribute('aria-checked', checkable ? item.getAttribute('aria-checked') || 'false' : 'false');
        });
      };
      options.querySelectorAll('input').forEach(input => input.addEventListener('change', syncTreeOptions));
      syncTreeOptions();
      options.querySelector('[data-tree-load]')?.addEventListener('click', () => {
        const parent = items.find(item => item.textContent.replace(/^[⌄›]\s*/, '').trim() === 'docs');
        const children = parent?.nextElementSibling;
        if (!children || children.querySelector('[data-tree-lazy-child]')) return;
        const child = document.createElement('button');
        child.type = 'button';
        child.textContent = '　knowledge.md';
        child.dataset.treeLazyChild = 'true';
        child.setAttribute('role', 'treeitem');
        child.setAttribute('aria-selected', 'false');
        child.setAttribute('aria-checked', 'false');
        child.addEventListener('click', () => {
          if (options.querySelector('[data-tree-checkable]')?.checked === true) {
            const checked = child.getAttribute('aria-checked') === 'true';
            child.setAttribute('aria-checked', String(!checked));
            child.classList.toggle('is-checked', !checked);
          }
          if (options.querySelector('[data-tree-selectable]')?.checked === false) return;
          items.filter(item => !item.hasAttribute('data-tree-toggle')).forEach(item => { item.classList.remove('is-selected'); item.setAttribute('aria-selected', 'false'); });
          child.classList.add('is-selected');
          child.setAttribute('aria-selected', 'true');
        });
        children.append(child);
        options.querySelector('[data-tree-load]').textContent = '已加载';
        options.querySelector('[data-tree-load]').disabled = true;
      });
      const moveFocus = (item, delta) => {
        const visible = items.filter(candidate => !candidate.hidden && candidate.offsetParent !== null);
        const index = visible.indexOf(item);
        const next = Math.max(0, Math.min(visible.length - 1, index + delta));
        visible.forEach(candidate => { candidate.tabIndex = -1; });
        visible[next]?.setAttribute('tabindex', '0');
        visible[next]?.focus();
      };
      items.forEach(item => item.addEventListener('keydown', event => {
        if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
          event.preventDefault();
          const visible = items.filter(candidate => !candidate.hidden && candidate.offsetParent !== null);
          if (event.key === 'Home') { visible.forEach(candidate => { candidate.tabIndex = -1; }); visible[0]?.setAttribute('tabindex', '0'); visible[0]?.focus(); return; }
          if (event.key === 'End') { visible.forEach(candidate => { candidate.tabIndex = -1; }); visible[visible.length - 1]?.setAttribute('tabindex', '0'); visible[visible.length - 1]?.focus(); return; }
          moveFocus(item, event.key === 'ArrowDown' ? 1 : -1);
        } else if (event.key === 'ArrowRight' && item.hasAttribute('data-tree-toggle')) {
          if (item.getAttribute('aria-expanded') !== 'true') { event.preventDefault(); item.click(); }
        } else if (event.key === 'ArrowLeft' && item.hasAttribute('data-tree-toggle')) {
          if (item.getAttribute('aria-expanded') === 'true') { event.preventDefault(); item.click(); }
        } else if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault(); item.click();
        }
      }));
    });
    document.querySelectorAll('[data-time-demo]').forEach(demo => {
      const trigger = demo.querySelector('.date-trigger');
      const popover = demo.querySelector('.time-popover');
      const label = demo.querySelector('[data-time-label]');
      if (popover && trigger) { const demoIndex = [...document.querySelectorAll('[data-time-demo]')].indexOf(demo) + 1; popover.id = popover.id || `nm-time-panel-${demoIndex}`; popover.setAttribute('role', 'dialog'); popover.setAttribute('aria-label', '选择时间'); trigger.setAttribute('aria-controls', popover.id); }
      const parts = ['hour', 'minute', 'second'];
      const triggerClear = document.createElement('button');
      triggerClear.type = 'button';
      triggerClear.className = 'time-clear-trigger';
      triggerClear.setAttribute('aria-label', '清除时间');
      triggerClear.innerHTML = '<span class="nm-icon nm-icon-close" aria-hidden="true"></span>';
      trigger?.append(triggerClear);
      const allowClear = document.createElement('label');
      allowClear.className = 'time-option';
      allowClear.innerHTML = '<input type="checkbox" data-time-allow-clear checked>允许清除';
      demo.querySelector('.time-options')?.append(allowClear);
      const changeOnScroll = document.createElement('label'); changeOnScroll.className = 'time-option'; changeOnScroll.innerHTML = '<input type="checkbox" data-time-change-on-scroll>滚动即时选择'; demo.querySelector('.time-option')?.after(changeOnScroll);
      const formatPicker = document.createElement('label'); formatPicker.className = 'time-option'; formatPicker.innerHTML = '格式 <select data-time-format><option value="HH:mm:ss">HH:mm:ss</option><option value="HH:mm">HH:mm</option></select>'; demo.querySelector('.time-option')?.before(formatPicker);
      const prefixToggle = document.createElement('label');
      prefixToggle.className = 'time-option';
      prefixToggle.innerHTML = '<input type="checkbox" data-time-prefix>显示前缀';
      demo.querySelector('.time-options')?.append(prefixToggle);
      const footerToggle = document.createElement('label');
      footerToggle.className = 'time-option';
      footerToggle.innerHTML = '<input type="checkbox" data-time-extra-footer>附加页脚';
      demo.querySelector('.time-options')?.append(footerToggle);
      const prefix = document.createElement('span');
      prefix.className = 'time-prefix';
      prefix.setAttribute('aria-hidden', 'true');
      prefix.textContent = '◷';
      trigger?.insertBefore(prefix, label);
      const extraFooter = document.createElement('div');
      extraFooter.className = 'time-extra-footer';
      extraFooter.textContent = '时区：Asia/Shanghai · 24 小时制';
      extraFooter.hidden = true;
      popover?.querySelector('.time-panel-footer')?.before(extraFooter);
      const currentKey = part => `time${part[0].toUpperCase()}${part.slice(1)}`;
      const disabledTime = document.createElement('label'); disabledTime.className = 'time-option'; disabledTime.innerHTML = '<input type="checkbox" data-time-disabled-time>禁用 18:00 后'; demo.querySelector('.time-option')?.after(disabledTime);
      const hideDisabled = document.createElement('label'); hideDisabled.className = 'time-option'; hideDisabled.innerHTML = '<input type="checkbox" data-time-hide-disabled>隐藏禁用项'; disabledTime.after(hideDisabled);
      const inputReadOnly = document.createElement('label'); inputReadOnly.className = 'time-option'; inputReadOnly.innerHTML = '<input type="checkbox" data-time-input-readonly>只读输入框'; hideDisabled.after(inputReadOnly);
      const showNow = document.createElement('label'); showNow.className = 'time-option'; showNow.innerHTML = '<input type="checkbox" data-time-show-now checked>显示现在'; inputReadOnly.after(showNow);
      const disabledControl = document.createElement('label'); disabledControl.className = 'time-option'; disabledControl.innerHTML = '<input type="checkbox" data-time-disabled-control>禁用控件'; showNow.after(disabledControl);
      const openControl = document.createElement('label'); openControl.className = 'time-option'; openControl.innerHTML = '<input type="checkbox" data-time-open>受控展开'; disabledControl.after(openControl);
      const presets = document.createElement('div'); presets.className = 'time-presets'; presets.setAttribute('aria-label', '快捷时间'); presets.innerHTML = '<span>快捷时间</span><button type="button" data-time-preset="09:00:00">09:00</button><button type="button" data-time-preset="12:00:00">12:00</button><button type="button" data-time-preset="18:00:00">18:00</button>'; demo.querySelector('.time-columns')?.before(presets);
      const sizePicker = demo.querySelector('[data-time-size]');
      const variantPicker = demo.querySelector('[data-time-variant]');
      const statusPicker = document.createElement('label'); statusPicker.className = 'time-option'; statusPicker.innerHTML = '状态 <select data-time-status aria-label="校验状态"><option value="default">默认</option><option value="success">成功</option><option value="warning">警告</option><option value="error">错误</option><option value="validating">校验中</option></select>'; variantPicker?.closest('label')?.after(statusPicker);
      const placementPicker = document.createElement('label'); placementPicker.className = 'time-option'; placementPicker.innerHTML = '位置 <select data-time-placement aria-label="面板位置"><option value="bottomLeft">左下</option><option value="bottomRight">右下</option><option value="topLeft">左上</option><option value="topRight">右上</option></select>'; statusPicker.after(placementPicker);
      const isConfirmMode = () => demo.querySelector('[data-time-need-confirm]')?.checked === true;
      const isOpenControlled = () => openControl.querySelector('input')?.checked === true;
      const activeParts = () => demo.querySelector('[data-time-format]')?.value === 'HH:mm' ? parts.slice(0, 2) : parts;
      const use12Hours = () => demo.querySelector('[data-time-use12]')?.checked === true;
      const stepFor = part => Number(demo.querySelector(`[data-time-${part}-step]`)?.value || 1);
      const formatValue = (draft = false) => { const values = activeParts().map(part => demo.dataset[draft ? `draft${part[0].toUpperCase()}${part.slice(1)}` : currentKey(part)]); if (!values.every(Boolean)) return ''; if (!use12Hours()) return values.join(':'); const hour = Number(values[0]); return `${String(hour % 12 || 12).padStart(2, '0')}:${values.slice(1).join(':')} ${hour >= 12 ? 'PM' : 'AM'}`; };
      const normalizeDisabledTime = () => { if (demo.querySelector('[data-time-disabled-time]')?.checked !== true) return; const draft = isConfirmMode() && demo.classList.contains('is-open'); const key = part => draft ? `draft${part[0].toUpperCase()}${part.slice(1)}` : currentKey(part); let hour = Number(demo.dataset[key('hour')] || 0); let minute = Number(demo.dataset[key('minute')] || 0); let second = Number(demo.dataset[key('second')] || 0); if (hour > 18) hour = 18; if (hour === 18 && minute > 0) minute = 0; if (hour === 18 && minute === 0 && second > 0) second = 0; demo.dataset[key('hour')] = String(hour).padStart(2, '0'); demo.dataset[key('minute')] = String(minute).padStart(2, '0'); demo.dataset[key('second')] = String(second).padStart(2, '0'); };
      const sync = () => {
        // Ant Design's needConfirm keeps panel changes in a draft until OK is pressed.
        // The trigger/input therefore always reflects the committed value while open.
        const value = formatValue(false);
        if (label) { label.value = value; label.placeholder = '请选择时间'; }
        if (label) label.readOnly = inputReadOnly.querySelector('input')?.checked === true;
        if (trigger) { trigger.dataset.size = sizePicker?.value || 'middle'; trigger.dataset.variant = variantPicker?.value || 'outlined'; trigger.dataset.status = statusPicker.querySelector('select')?.value || 'default'; }
        prefix.hidden = prefixToggle.querySelector('input')?.checked !== true;
        extraFooter.hidden = footerToggle.querySelector('input')?.checked !== true;
        if (popover) popover.dataset.placement = placementPicker.querySelector('select')?.value || 'bottomLeft';
        const disabled = disabledControl.querySelector('input')?.checked === true;
        if (trigger) { trigger.disabled = disabled; trigger.classList.toggle('is-disabled', disabled); trigger.setAttribute('aria-disabled', String(disabled)); }
        if (trigger) { trigger.setAttribute('aria-expanded', String(demo.classList.contains('is-open'))); trigger.setAttribute('aria-haspopup', 'dialog'); }
        if (openControl.querySelector('input')?.checked === true && !disabled && !demo.classList.contains('is-open')) {
          parts.forEach(part => { demo.dataset[`draft${part[0].toUpperCase()}${part.slice(1)}`] = demo.dataset[currentKey(part)] || ''; });
          demo.classList.add('is-open');
          if (popover) popover.hidden = false;
          trigger?.setAttribute('aria-expanded', 'true');
        }
        triggerClear.hidden = disabled || allowClear.querySelector('input')?.checked === false || !formatValue(false);
        demo.querySelector('[data-time-confirm]')?.toggleAttribute('hidden', !isConfirmMode());
        demo.querySelector('[data-time-now]')?.toggleAttribute('hidden', showNow.querySelector('input')?.checked !== true);
        const meridiem = demo.querySelector('[data-time-meridiem]');
        if (meridiem) { meridiem.hidden = !use12Hours(); const valueKey = isConfirmMode() && demo.classList.contains('is-open') ? 'draftHour' : currentKey('hour'); const hour = Number(demo.dataset[valueKey] || 0); meridiem.value = hour >= 12 ? 'PM' : 'AM'; }
        demo.querySelectorAll('.time-column').forEach(column => { column.hidden = !activeParts().includes(column.querySelector('[data-time-part]')?.dataset.timePart); });
        const footer = demo.querySelector('.time-panel-footer small'); if (footer) footer.textContent = `${demo.querySelector('[data-time-format]')?.value || 'HH:mm:ss'} · hourStep ${stepFor('hour')} · minuteStep ${stepFor('minute')} · secondStep ${stepFor('second')}`;
        parts.forEach(part => demo.querySelectorAll(`[data-time-part="${part}"]`).forEach(item => {
          const selectedValue = demo.dataset[isConfirmMode() && demo.classList.contains('is-open') ? `draft${part[0].toUpperCase()}${part.slice(1)}` : currentKey(part)];
          const numeric = Number(item.dataset.timeValue);
          const inMeridiem = part !== 'hour' || !use12Hours() || (meridiem?.value === 'PM' ? numeric >= 12 : numeric < 12);
          const inStep = numeric % stepFor(part) === 0;
          const selectedHour = Number(demo.dataset[isConfirmMode() && demo.classList.contains('is-open') ? 'draftHour' : currentKey('hour')] || 0);
          const selectedMinute = Number(demo.dataset[isConfirmMode() && demo.classList.contains('is-open') ? 'draftMinute' : currentKey('minute')] || 0);
          const disabledAfterSix = demo.querySelector('[data-time-disabled-time]')?.checked === true;
          const blocked = disabledAfterSix && ((part === 'hour' && numeric > 18) || (part === 'minute' && (selectedHour > 18 || (selectedHour === 18 && numeric > 0))) || (part === 'second' && (selectedHour > 18 || (selectedHour === 18 && (selectedMinute > 0 || numeric > 0)))));
          item.hidden = !inMeridiem || !inStep || (blocked && demo.querySelector('[data-time-hide-disabled]')?.checked);
          item.disabled = Boolean(blocked);
          item.setAttribute('aria-disabled', String(Boolean(blocked)));
          if (part === 'hour') item.textContent = use12Hours() ? String(numeric % 12 || 12).padStart(2, '0') : item.dataset.timeValue;
          const selected = item.dataset.timeValue === selectedValue;
          item.classList.toggle('selected', selected);
          item.setAttribute('aria-selected', String(selected));
          item.tabIndex = selected ? 0 : -1;
        }));
      };
      const close = (commit = false) => { if (isConfirmMode() && commit) parts.forEach(part => { demo.dataset[currentKey(part)] = demo.dataset[`draft${part[0].toUpperCase()}${part.slice(1)}`] || ''; }); if (isOpenControlled()) { sync(); return; } demo.classList.remove('is-open'); popover.hidden = true; trigger.setAttribute('aria-expanded', 'false'); sync(); };
      trigger?.addEventListener('click', () => { if (disabledControl.querySelector('input')?.checked === true || isOpenControlled()) return; const open = !demo.classList.contains('is-open'); if (open) parts.forEach(part => { demo.dataset[`draft${part[0].toUpperCase()}${part.slice(1)}`] = demo.dataset[currentKey(part)] || ''; }); demo.classList.toggle('is-open', open); popover.hidden = !open; trigger.setAttribute('aria-expanded', String(open)); demo.querySelector('[data-time-confirm]')?.toggleAttribute('hidden', !isConfirmMode()); if (open) { sync(); requestAnimationFrame(() => { const selectedItems = [...demo.querySelectorAll('.time-column .selected:not([hidden]):not(:disabled)')]; selectedItems.forEach(item => item.scrollIntoView({ block: 'center' })); selectedItems[0]?.focus(); }); } });
      demo.querySelectorAll('[data-time-part]').forEach(option => option.addEventListener('click', () => {
        if (option.disabled) return;
        const part = option.dataset.timePart;
        demo.dataset[isConfirmMode() && demo.classList.contains('is-open') ? `draft${part[0].toUpperCase()}${part.slice(1)}` : currentKey(part)] = option.dataset.timeValue;
        normalizeDisabledTime();
        sync();
      }));
      demo.querySelectorAll('.time-column').forEach(column => column.addEventListener('wheel', event => {
        if (!demo.querySelector('[data-time-change-on-scroll]')?.checked) return;
        event.preventDefault(); const items = [...column.querySelectorAll('[data-time-part]:not([hidden]):not(:disabled)')]; const selected = column.querySelector('.selected:not([hidden]):not(:disabled)'); const index = Math.max(0, items.indexOf(selected)); const next = Math.max(0, Math.min(items.length - 1, index + (event.deltaY > 0 ? 1 : -1))); items[next]?.click();
      }, { passive: false }));
      demo.querySelectorAll('.time-column').forEach(column => {
        let scrollTimer;
        column.addEventListener('scroll', () => {
          if (!demo.querySelector('[data-time-change-on-scroll]')?.checked) return;
          window.clearTimeout(scrollTimer);
          scrollTimer = window.setTimeout(() => {
            const items = [...column.querySelectorAll('[data-time-part]:not([hidden]):not(:disabled)')];
            if (!items.length) return;
            const center = column.getBoundingClientRect().top + column.clientHeight / 2;
            const nearest = items.reduce((best, item) => {
              const distance = Math.abs(item.getBoundingClientRect().top + item.offsetHeight / 2 - center);
              return !best || distance < best.distance ? { item, distance } : best;
            }, null);
            nearest?.item.click();
          }, 80);
        }, { passive: true });
      });
      demo.querySelector('[data-time-clear]')?.addEventListener('click', () => { if (allowClear.querySelector('input')?.checked === false) return; parts.forEach(part => { demo.dataset[currentKey(part)] = ''; demo.dataset[`draft${part[0].toUpperCase()}${part.slice(1)}`] = ''; }); sync(); close(true); trigger.focus(); });
      triggerClear.addEventListener('click', event => { event.stopPropagation(); if (allowClear.querySelector('input')?.checked === false) return; parts.forEach(part => { demo.dataset[currentKey(part)] = ''; demo.dataset[`draft${part[0].toUpperCase()}${part.slice(1)}`] = ''; }); sync(); close(true); trigger.focus(); });
      demo.querySelector('[data-time-now]')?.addEventListener('click', () => { const now = new Date(); const values = [now.getHours(), now.getMinutes(), now.getSeconds()]; parts.forEach((part, index) => { demo.dataset[isConfirmMode() ? `draft${part[0].toUpperCase()}${part.slice(1)}` : currentKey(part)] = String(values[index]).padStart(2, '0'); }); sync(); if (!isConfirmMode()) close(true); });
      presets.querySelectorAll('[data-time-preset]').forEach(button => button.addEventListener('click', () => { const values = button.dataset.timePreset.split(':'); parts.forEach((part, index) => { demo.dataset[isConfirmMode() && demo.classList.contains('is-open') ? `draft${part[0].toUpperCase()}${part.slice(1)}` : currentKey(part)] = values[index] || '00'; }); normalizeDisabledTime(); sync(); if (!isConfirmMode()) close(true); }));
      demo.querySelector('[data-time-confirm]')?.addEventListener('click', () => { close(true); trigger.focus(); });
      demo.querySelector('[data-time-need-confirm]')?.addEventListener('change', event => { if (!demo.classList.contains('is-open')) return; if (event.target.checked) parts.forEach(part => { demo.dataset[`draft${part[0].toUpperCase()}${part.slice(1)}`] = demo.dataset[currentKey(part)] || ''; }); else parts.forEach(part => { demo.dataset[currentKey(part)] = demo.dataset[`draft${part[0].toUpperCase()}${part.slice(1)}`] || ''; }); demo.querySelector('[data-time-confirm]')?.toggleAttribute('hidden', !isConfirmMode()); sync(); });
      demo.querySelector('[data-time-format]')?.addEventListener('change', sync);
      demo.querySelectorAll('[data-time-use12], [data-time-hour-step], [data-time-minute-step], [data-time-second-step], [data-time-hide-disabled], [data-time-input-readonly], [data-time-show-now], [data-time-size], [data-time-variant], [data-time-status], [data-time-placement], [data-time-allow-clear], [data-time-prefix], [data-time-extra-footer]').forEach(control => control.addEventListener('change', sync));
      demo.querySelector('[data-time-disabled-time]')?.addEventListener('change', () => { normalizeDisabledTime(); sync(); });
      demo.querySelector('[data-time-meridiem]')?.addEventListener('change', event => { const draft = isConfirmMode() && demo.classList.contains('is-open'); const key = part => draft ? `draft${part[0].toUpperCase()}${part.slice(1)}` : currentKey(part); const hour = Number(demo.dataset[key('hour')] || 0); const next = event.target.value === 'PM' ? (hour % 12) + 12 : hour % 12; demo.dataset[key('hour')] = String(next).padStart(2, '0'); sync(); });
      label?.addEventListener('change', () => { const match = label.value.trim().match(/^(\d{1,2}):(\d{1,2})(?::(\d{1,2}))?\s*(AM|PM)?$/i); if (!match) { sync(); return; } let hour = Number(match[1]); const typedHour = hour; const values = [hour, Number(match[2]), Number(match[3] || 0)]; const invalid12Hour = use12Hours() && (!match[4] || typedHour < 1 || typedHour > 12); if (use12Hours() && match[4]) { hour %= 12; if (match[4].toUpperCase() === 'PM') hour += 12; values[0] = hour; } const invalidRange = values[0] > 23 || values[1] > 59 || values[2] > 59; const invalidStep = parts.some((part, index) => values[index] % stepFor(part) !== 0); const invalidDisabledTime = demo.querySelector('[data-time-disabled-time]')?.checked === true && (values[0] > 18 || (values[0] === 18 && (values[1] > 0 || values[2] > 0))); if (invalid12Hour || invalidRange || invalidStep || invalidDisabledTime) { sync(); return; } const draft = isConfirmMode() && demo.classList.contains('is-open'); ['hour', 'minute', 'second'].forEach((part, index) => { const key = draft ? `draft${part[0].toUpperCase()}${part.slice(1)}` : currentKey(part); demo.dataset[key] = String(values[index]).padStart(2, '0'); }); sync(); });
      label?.addEventListener('blur', () => label.dispatchEvent(new Event('change', { bubbles: true })));
      label?.addEventListener('input', () => { if (/^\d{1,2}:\d{2}(?::\d{2})?(?:\s*(?:AM|PM))?$/i.test(label.value.trim())) label.dispatchEvent(new Event('change', { bubbles: true })); });
      disabledControl.querySelector('input')?.addEventListener('change', event => { if (event.target.checked && demo.classList.contains('is-open')) close(false); else sync(); });
      openControl.querySelector('input')?.addEventListener('change', event => {
        if (event.target.checked) {
          if (!demo.classList.contains('is-open')) {
            parts.forEach(part => { demo.dataset[`draft${part[0].toUpperCase()}${part.slice(1)}`] = demo.dataset[currentKey(part)] || ''; });
            demo.classList.add('is-open');
            popover.hidden = false;
          }
          sync();
          return;
        }
        close(false);
      });
      sync();
    });
    document.querySelectorAll('[data-motion-demo]').forEach(button => { button.onclick = () => document.querySelector('[data-motion-card]')?.classList.toggle('is-animated'); });
    document.querySelectorAll('.check-control input').forEach(input => {
      if (input.dataset.indeterminate === 'true') input.indeterminate = true;
      const sync = () => { input.closest('.check-control')?.setAttribute('aria-checked', input.indeterminate ? 'mixed' : String(input.checked)); };
      input.addEventListener('change', () => { input.indeterminate = false; sync(); });
      sync();
    });
    document.querySelectorAll('[data-switch-demo]').forEach(button => { if (button.dataset.switchBound) return; button.dataset.switchBound = 'true'; const options = document.createElement('div'); options.className = 'switch-options'; options.innerHTML = '<label><input type="checkbox" data-switch-loading>加载中</label><label><input type="checkbox" data-switch-disabled>禁用</label>'; button.after(options); const sync = () => { const checked = button.getAttribute('aria-pressed') === 'true'; const loading = options.querySelector('[data-switch-loading]')?.checked === true; const disabled = options.querySelector('[data-switch-disabled]')?.checked === true; button.classList.toggle('is-on', checked); button.classList.toggle('is-loading', loading); button.setAttribute('aria-checked', String(checked)); button.setAttribute('aria-busy', String(loading)); button.setAttribute('aria-disabled', String(disabled)); button.disabled = loading || disabled; }; button.setAttribute('role', 'switch'); button.addEventListener('click', () => { if (button.disabled) return; button.setAttribute('aria-pressed', String(button.getAttribute('aria-pressed') !== 'true')); sync(); }); options.querySelectorAll('input').forEach(input => input.addEventListener('change', sync)); sync(); });
    document.querySelectorAll('.mini-sidebar button, .standalone-nav button').forEach(button => { const nav = button.closest('.mini-sidebar, .standalone-nav'); if (!nav || button.dataset.navBound) return; button.dataset.navBound = 'true'; if (button.classList.contains('active')) button.setAttribute('aria-current', 'page'); button.addEventListener('click', () => { nav.querySelectorAll('button').forEach(item => { const active = item === button; item.classList.toggle('active', active); if (active) item.setAttribute('aria-current', 'page'); else item.removeAttribute('aria-current'); }); }); });
    document.querySelectorAll('.breadcrumbs a').forEach(link => { if (link.dataset.breadcrumbBound) return; link.dataset.breadcrumbBound = 'true'; link.addEventListener('click', event => { event.preventDefault(); const parent = link.closest('.breadcrumbs'); parent?.querySelectorAll('a').forEach(item => item.classList.toggle('active', item === link)); }); });
    document.querySelectorAll('.segmented button').forEach(button => { button.onclick = () => { document.querySelectorAll('.segmented button').forEach(item => item.classList.toggle('active', item === button)); }; });
    document.querySelectorAll('.tabs-line').forEach((group, groupIndex) => {
      if (group.dataset.tabsBound) return;
      group.dataset.tabsBound = 'true';
      group.setAttribute('role', 'tablist');
      const buttons = [...group.querySelectorAll('button')];
      const panel = document.createElement('div');
      panel.className = 'tabs-panel';
      panel.setAttribute('role', 'tabpanel');
      panel.id = `nm-tabs-panel-${groupIndex}`;
      group.after(panel);
      const content = {
        消息: '这里展示与当前上下文相关的消息。',
        事件: '这里展示 Agent 的执行事件与状态变化。',
        产物: '这里展示已经生成并可继续处理的知识产物。'
      };
      const activate = (button, focus = false) => {
        const index = buttons.indexOf(button);
        buttons.forEach((item, itemIndex) => {
          const selected = itemIndex === index;
          item.setAttribute('role', 'tab');
          item.id = `nm-tab-${groupIndex}-${itemIndex}`;
          item.setAttribute('aria-controls', panel.id);
          item.setAttribute('aria-selected', String(selected));
          item.tabIndex = selected ? 0 : -1;
          item.classList.toggle('active', selected);
        });
        panel.setAttribute('aria-labelledby', button.id);
        panel.textContent = content[button.textContent.trim()] || `${button.textContent.trim()}：这里展示对应内容。`;
        if (focus) button.focus();
      };
      buttons.forEach((button, index) => {
        button.addEventListener('click', () => activate(button));
        button.addEventListener('keydown', event => {
          if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
          event.preventDefault();
          const next = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + buttons.length) % buttons.length;
          activate(buttons[next], true);
        });
      });
      activate(buttons.find(button => button.classList.contains('active')) || buttons[0]);
    });
    document.querySelectorAll('.pagination').forEach(pagination => { const pageButtons = [...pagination.querySelectorAll('button:not([aria-label])')]; const previous = pagination.querySelector('[aria-label="上一页"]'); const next = pagination.querySelector('[aria-label="下一页"]'); const sync = () => { const active = pageButtons.findIndex(button => button.classList.contains('active')); if (previous) previous.disabled = active <= 0; if (next) next.disabled = active >= pageButtons.length - 1; }; pageButtons.forEach((button, index) => button.addEventListener('click', () => { pageButtons.forEach(item => item.classList.toggle('active', item === button)); sync(); })); previous?.addEventListener('click', () => { const active = pageButtons.findIndex(button => button.classList.contains('active')); if (active > 0) pageButtons[active - 1].click(); }); next?.addEventListener('click', () => { const active = pageButtons.findIndex(button => button.classList.contains('active')); if (active < pageButtons.length - 1) pageButtons[active + 1].click(); }); sync(); });
    document.querySelectorAll('.slider-demo input[type="range"]').forEach(input => { const value = input.closest('.primitive-body')?.querySelector('.slider-labels strong'); const sync = () => { if (value) value.textContent = input.value; }; input.addEventListener('input', sync); sync(); });
    document.querySelectorAll('.rate-demo:not([data-rate-demo])').forEach(rate => { const text = rate.textContent.replace(/\s/g, ''); rate.innerHTML = [...text].map((star, index) => `<button type="button" aria-label="${index + 1} 星" class="${star === '★' ? 'active' : ''}">${star === '★' ? '★' : '☆'}</button>`).join(''); const buttons = [...rate.querySelectorAll('button')]; buttons.forEach((button, index) => { button.addEventListener('click', () => buttons.forEach((item, itemIndex) => { item.classList.toggle('active', itemIndex <= index); item.textContent = itemIndex <= index ? '★' : '☆'; })); }); });
    document.querySelectorAll('.transfer-demo').forEach(transfer => {
      const columns = [...transfer.querySelectorAll(':scope > div')];
      if (columns.length < 2) return;
      transfer.querySelector(':scope > b')?.remove();
      columns.forEach(column => column.querySelectorAll('span').forEach(item => {
        item.tabIndex = 0;
        item.setAttribute('role', 'option');
        item.setAttribute('aria-selected', 'false');
        const toggle = () => { item.classList.toggle('is-selected'); item.setAttribute('aria-selected', String(item.classList.contains('is-selected'))); };
        item.addEventListener('click', toggle);
        item.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); toggle(); } });
      }));
      const actions = document.createElement('div');
      actions.className = 'transfer-actions';
      actions.innerHTML = '<button type="button" aria-label="移至右侧">›</button><button type="button" aria-label="移至左侧">‹</button>';
      transfer.insertBefore(actions, columns[1]);
      const options = document.createElement('div');
      options.className = 'transfer-options';
      options.innerHTML = '<label><input type="checkbox" data-transfer-one-way>单向模式</label><label><input type="checkbox" data-transfer-pagination>显示分页</label><output aria-live="polite" data-transfer-page hidden>第 1 页 · 共 1 页</output>';
      transfer.after(options);
      const reverse = actions.querySelector('[aria-label="移至左侧"]');
      const page = options.querySelector('[data-transfer-page]');
      const syncOptions = () => { const oneWay = options.querySelector('[data-transfer-one-way]')?.checked === true; const paged = options.querySelector('[data-transfer-pagination]')?.checked === true; reverse.hidden = oneWay; reverse.disabled = oneWay; page.hidden = !paged; };
      const move = direction => { const source = direction > 0 ? columns[0] : columns[1]; const target = direction > 0 ? columns[1] : columns[0]; [...source.querySelectorAll('span.is-selected')].forEach(item => { item.classList.remove('is-selected'); item.setAttribute('aria-selected', 'false'); target.append(item); }); };
      actions.querySelector('[aria-label="移至右侧"]').addEventListener('click', () => move(1));
      reverse.addEventListener('click', () => move(-1));
      options.querySelectorAll('input').forEach(input => input.addEventListener('change', syncOptions));
      syncOptions();
    });
    document.querySelectorAll('.transfer-demo').forEach(transfer => transfer.querySelectorAll('input[type="search"]').forEach(input => { const column = input.parentElement; input.addEventListener('input', () => { const query = input.value.trim().toLocaleLowerCase(); column?.querySelectorAll('span[role="option"]').forEach(item => { item.hidden = Boolean(query && !item.textContent.toLocaleLowerCase().includes(query)); }); }); }));
    document.querySelectorAll('.tree-demo').forEach(tree => { tree.querySelectorAll('span').forEach(item => { item.tabIndex = 0; item.setAttribute('role', 'treeitem'); item.addEventListener('click', () => item.classList.toggle('is-selected')); }); });
    document.querySelectorAll('.tree-demo').forEach(tree => { const nodes = [...tree.querySelectorAll('span')]; const setVisibility = (node, visible) => { node.hidden = !visible; node.classList.toggle('is-tree-hidden', !visible); node.style.setProperty('display', visible ? '' : 'none', 'important'); }; const toggleBranch = (index, descendants) => { const node = nodes[index]; if (!node) return; const open = node.dataset.expanded !== 'true'; node.dataset.expanded = String(open); node.textContent = `${open ? '⌄' : '›'} ${node.textContent.replace(/^[⌄›]\s*/, '')}`; node.setAttribute('aria-expanded', String(open)); descendants.forEach(childIndex => { if (nodes[childIndex]) setVisibility(nodes[childIndex], open); }); }; if (nodes[0]) { nodes[0].dataset.expanded = 'true'; nodes[0].setAttribute('aria-expanded', 'true'); nodes[0].addEventListener('click', event => { event.stopPropagation(); toggleBranch(0, [1, 2, 3]); }); } if (nodes[1]) { nodes[1].dataset.expanded = 'true'; nodes[1].setAttribute('aria-expanded', 'true'); nodes[1].addEventListener('click', event => { event.stopPropagation(); toggleBranch(1, [2, 3]); }); } });
    document.querySelectorAll('.popover-anchor').forEach((anchor, index) => {
      const panel = anchor.parentElement?.querySelector('.popover-panel');
      if (!panel || anchor.dataset.popoverBound) return;
      anchor.dataset.popoverBound = 'true';
      if (!panel.hasAttribute('hidden')) panel.hidden = true;
      const panelId = panel.id || `nm-popover-${index + 1}`;
      panel.id = panelId;
      anchor.setAttribute('role', 'button');
      anchor.setAttribute('aria-controls', panelId);
      anchor.setAttribute('aria-expanded', 'false');
      anchor.tabIndex = 0;
      const items = () => [...panel.querySelectorAll('button:not([disabled])')].filter(item => !item.hidden && item.offsetParent !== null);
      const close = (restore = false) => { panel.hidden = true; anchor.setAttribute('aria-expanded', 'false'); if (restore) anchor.focus(); };
      const open = () => {
        panel.hidden = false;
        const placement = anchor.closest('.primitive-showcase')?.querySelector('[data-popover-placement]')?.value || 'bottom';
        if (placement === 'top') { panel.style.top = `${anchor.offsetTop - panel.offsetHeight - 8}px`; panel.style.left = `${anchor.offsetLeft}px`; }
        else if (placement === 'left') { panel.style.top = `${anchor.offsetTop}px`; panel.style.left = `${anchor.offsetLeft - panel.offsetWidth - 8}px`; }
        else if (placement === 'right') { panel.style.top = `${anchor.offsetTop}px`; panel.style.left = `${anchor.offsetLeft + anchor.offsetWidth + 8}px`; }
        else { panel.style.top = `${anchor.offsetTop + anchor.offsetHeight + 8}px`; panel.style.left = `${anchor.offsetLeft}px`; }
        anchor.setAttribute('aria-expanded', 'true');
        if (panel.classList.contains('menu-demo')) items()[0]?.focus();
      };
      const triggerMode = () => anchor.closest('.primitive-showcase')?.querySelector('[data-popover-trigger]')?.value || 'click';
      anchor.addEventListener('click', () => { if (triggerMode() !== 'click') return; if (panel.hidden) open(); else close(); });
      anchor.addEventListener('mouseenter', () => { if (triggerMode() === 'hover') open(); });
      anchor.addEventListener('mouseleave', event => { if (triggerMode() === 'hover' && !panel.contains(event.relatedTarget)) close(); });
      panel.addEventListener('mouseenter', () => { if (triggerMode() === 'hover') open(); });
      panel.addEventListener('mouseleave', event => { if (triggerMode() === 'hover' && !anchor.contains(event.relatedTarget)) close(); });
      anchor.addEventListener('focus', () => { if (triggerMode() === 'focus') open(); });
      anchor.addEventListener('blur', () => { if (triggerMode() === 'focus') window.setTimeout(() => { if (!anchor.contains(document.activeElement) && !panel.contains(document.activeElement)) close(); }, 0); });
      panel.addEventListener('focusin', () => { if (triggerMode() === 'focus') open(); });
      anchor.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); if (panel.hidden) open(); else close(true); } else if (event.key === 'Escape') { event.preventDefault(); close(true); } });
      panel.addEventListener('keydown', event => { if (event.key !== 'Escape') return; event.preventDefault(); close(true); });
    });
    document.querySelectorAll('.tag-demo').forEach(tag => { if (!tag.querySelector('button')) { const close = document.createElement('button'); close.type = 'button'; close.className = 'tag-close'; close.setAttribute('aria-label', '关闭标签'); close.textContent = '×'; close.addEventListener('click', () => tag.remove()); tag.append(close); } });
    document.querySelectorAll('.menu-demo').forEach(menu => {
      if (menu.dataset.menuOptionsBound) return;
      menu.dataset.menuOptionsBound = 'true';
      const options = document.createElement('div');
      options.className = 'menu-options';
      options.innerHTML = '<label>模式 <select data-menu-mode aria-label="菜单模式"><option value="vertical">垂直</option><option value="horizontal">水平</option><option value="inline">内嵌</option></select></label><label><input type="checkbox" data-menu-selectable checked>允许选择</label>';
      menu.parentElement?.after(options);
      const sync = () => {
        const mode = options.querySelector('[data-menu-mode]')?.value || 'vertical';
        const selectable = options.querySelector('[data-menu-selectable]')?.checked !== false;
        menu.dataset.menuMode = mode;
        menu.dataset.menuSelectable = String(selectable);
        menu.querySelectorAll('button').forEach(item => item.setAttribute('aria-selected', String(selectable && item.classList.contains('active'))));
      };
      options.querySelectorAll('input, select').forEach(control => control.addEventListener('change', sync));
      sync();
    });
    document.querySelectorAll('.upload-dropzone:not([data-upload-demo])').forEach(zone => { const button = zone.querySelector('button'); if (!button || zone.querySelector('input[type="file"]')) return; const fileInput = document.createElement('input'); const list = document.createElement('ul'); list.className = 'upload-file-list'; fileInput.type = 'file'; fileInput.multiple = true; fileInput.accept = '.md,.pdf,audio/*'; fileInput.hidden = true; fileInput.addEventListener('change', () => { const files = [...fileInput.files]; zone.querySelector('strong').textContent = files.length ? `${files.length} 个文件已选择` : '拖入文件到这里'; list.replaceChildren(...files.map(file => { const item = document.createElement('li'); item.innerHTML = `<span>${file.name}</span><button type="button" aria-label="移除文件">×</button>`; item.querySelector('button').addEventListener('click', () => item.remove()); return item; })); }); zone.append(fileInput, list); button.removeAttribute('data-nm-toast'); button.addEventListener('click', () => fileInput.click()); });
    document.querySelectorAll('.demo-dialog').forEach(dialog => { if (dialog.dataset.boundModal) return; dialog.dataset.boundModal = 'true'; dialog.setAttribute('role', 'dialog'); dialog.setAttribute('aria-modal', 'true'); const trigger = document.createElement('button'); trigger.type = 'button'; trigger.className = 'nm-button'; trigger.dataset.variant = 'secondary'; trigger.textContent = '打开对话框'; dialog.before(trigger); dialog.hidden = true; let backdrop; const close = () => { dialog.hidden = true; backdrop?.remove(); backdrop = undefined; trigger.focus(); }; trigger.addEventListener('click', () => { backdrop = document.createElement('div'); backdrop.className = 'nm-modal-backdrop'; backdrop.addEventListener('click', close); document.body.append(backdrop); dialog.hidden = false; dialog.querySelector('button[data-variant="danger"], button:last-child')?.focus(); }); dialog.querySelectorAll('button').forEach(button => button.addEventListener('click', close)); dialog.addEventListener('keydown', event => { if (event.key === 'Escape') { event.preventDefault(); close(); } }); });
    document.querySelectorAll('.responsive-overlay').forEach(preview => { if (preview.dataset.boundDrawer) return; preview.dataset.boundDrawer = 'true'; const trigger = document.createElement('button'); trigger.type = 'button'; trigger.className = 'nm-button'; trigger.dataset.variant = 'secondary'; trigger.textContent = '打开 Drawer / Sheet'; const panel = document.createElement('aside'); panel.className = 'drawer-preview'; panel.setAttribute('role', 'dialog'); panel.setAttribute('aria-modal', 'true'); panel.hidden = true; panel.innerHTML = '<div><strong>Workspace 详情</strong><button type="button" aria-label="关闭 Drawer">×</button></div><p>这里展示保留主上下文的辅助内容。</p>'; preview.before(trigger); preview.after(panel); const close = () => { panel.hidden = true; trigger.focus(); }; trigger.addEventListener('click', () => { panel.hidden = false; panel.querySelector('button')?.focus(); }); panel.querySelector('button')?.addEventListener('click', close); panel.addEventListener('keydown', event => { if (event.key === 'Escape') { event.preventDefault(); close(); } }); });
    document.querySelectorAll('[data-date-demo]').forEach(demo => { const popover = demo.querySelector('.date-popover'); const trigger = demo.querySelector('.date-trigger'); const month = popover?.querySelector('strong'); if (!popover || !month || popover.querySelector('.date-nav')) return; trigger?.setAttribute('aria-haspopup', 'dialog'); const nav = document.createElement('div'); nav.className = 'date-nav'; nav.innerHTML = '<button type="button" aria-label="上个月">‹</button><strong></strong><button type="button" aria-label="下个月">›</button>'; nav.querySelector('strong').textContent = month.textContent; month.replaceWith(nav); const shift = delta => { const current = nav.querySelector('strong').textContent.match(/(\d{4})年(\d{2})月/); if (!current) return; const date = new Date(Number(current[1]), Number(current[2]) - 1 + delta, 1); nav.querySelector('strong').textContent = `${date.getFullYear()}年${String(date.getMonth() + 1).padStart(2, '0')}月`; }; nav.querySelector('button:first-child').addEventListener('click', () => shift(-1)); nav.querySelector('button:last-child').addEventListener('click', () => shift(1)); });
    document.querySelectorAll('[data-time-demo]').forEach(demo => { demo.querySelector('[data-time-clear]')?.setAttribute('aria-label', '清除时间'); });
    queueMicrotask(() => document.querySelectorAll('[data-select-demo]').forEach(select => {
      const modeToggle = select.querySelector('[data-select-multiple]');
      const search = select.querySelector('.select-search-input');
      const clear = select.querySelector('.select-clear');
      const trigger = select.querySelector('.select-trigger');
      const options = [...select.querySelectorAll('.select-option')];
      const control = document.createElement('label');
      control.className = 'select-mode-toggle';
      control.innerHTML = '<input type="checkbox" data-select-show-search>支持搜索';
      select.querySelector('.select-mode-toggle')?.after(control);
      const clearControl = document.createElement('label');
      clearControl.className = 'select-mode-toggle';
      clearControl.innerHTML = '<input type="checkbox" data-select-allow-clear>允许清除';
      control.after(clearControl);
      const labelValueControl = document.createElement('label');
      labelValueControl.className = 'select-mode-toggle';
      labelValueControl.innerHTML = '<input type="checkbox" data-select-label-in-value>返回标签和值';
      clearControl.after(labelValueControl);
      const sync = () => {
        const searchable = modeToggle?.checked === true || control.querySelector('input')?.checked === true;
        if (search) { search.hidden = !searchable; search.style.setProperty('display', searchable ? 'block' : 'none', 'important'); }
        if (clear) { const allowed = clearControl.querySelector('input')?.checked === true; const hasValue = options.some(option => option.classList.contains('selected')); clear.hidden = !allowed || !hasValue; clear.style.setProperty('display', allowed && hasValue ? '' : 'none', 'important'); }
      };
      modeToggle?.addEventListener('change', sync);
      control.querySelector('input')?.addEventListener('change', sync);
      clearControl.querySelector('input')?.addEventListener('change', sync);
      clear?.addEventListener('click', () => requestAnimationFrame(sync));
      options.forEach(option => option.addEventListener('click', () => requestAnimationFrame(sync)));
      trigger?.addEventListener('click', () => requestAnimationFrame(() => {
        if (search?.hidden) options.find(option => !option.hidden)?.focus();
      }));
      sync();
    }));
    document.querySelectorAll('[data-date-demo]').forEach(demo => {
      const nav = demo.querySelector('.date-nav');
      const grid = demo.querySelector('.date-grid');
      const popover = demo.querySelector('.date-popover');
      const trigger = demo.querySelector('.date-trigger');
      if (!nav || !grid || !popover) return;
      if (!grid.previousElementSibling?.classList.contains('date-weekdays')) {
        const weekdays = document.createElement('div');
        weekdays.className = 'date-weekdays';
        weekdays.innerHTML = '<span>日</span><span>一</span><span>二</span><span>三</span><span>四</span><span>五</span><span>六</span>';
        grid.before(weekdays);
      }
      const multipleControl = document.createElement('label');
      multipleControl.className = 'date-option';
      multipleControl.innerHTML = '<input type="checkbox" data-date-multiple>允许多选';
      popover.append(multipleControl);
      const disabledDateControl = document.createElement('label');
      disabledDateControl.className = 'date-option';
      disabledDateControl.innerHTML = '<input type="checkbox" data-date-disabled-date>禁用周末';
      popover.append(disabledDateControl);
      const minDateControl = document.createElement('label');
      minDateControl.className = 'date-option';
      minDateControl.innerHTML = '<span>最早日期</span><input type="date" data-date-min value="2026-09-03" aria-label="最小可选日期">';
      popover.append(minDateControl);
      const maxDateControl = document.createElement('label');
      maxDateControl.className = 'date-option';
      maxDateControl.innerHTML = '<span>最晚日期</span><input type="date" data-date-max value="2026-09-18" aria-label="最大可选日期">';
      popover.append(maxDateControl);
      const pickerControl = document.createElement('label');
      pickerControl.className = 'date-option';
      pickerControl.innerHTML = '<span>选择粒度</span><select data-date-picker-mode aria-label="选择日期粒度"><option value="date">日期</option><option value="week">周</option><option value="month">月份</option><option value="quarter">季度</option><option value="year">年份</option></select>';
      popover.append(pickerControl);
      const showNowOption = document.createElement('label');
      showNowOption.className = 'date-option';
      showNowOption.innerHTML = '<span>显示今天</span><input type="checkbox" data-date-show-now checked>';
      popover.append(showNowOption);
      const presets = document.createElement('div');
      presets.className = 'date-presets';
      presets.setAttribute('aria-label', '快捷日期');
      presets.innerHTML = '<span>快捷日期</span><button type="button" data-date-preset="today">今天</button><button type="button" data-date-preset="tomorrow">明天</button>';
      popover.append(presets);
      const allowClearOption = document.createElement('label');
      allowClearOption.className = 'date-option';
      allowClearOption.innerHTML = '<span>允许清除</span><input type="checkbox" data-date-allow-clear checked>';
      popover.append(allowClearOption);
      const needConfirmOption = document.createElement('label');
      needConfirmOption.className = 'date-option';
      needConfirmOption.innerHTML = '<span>选择后点击确定</span><input type="checkbox" data-date-need-confirm>';
      popover.append(needConfirmOption);
      const inputReadOnlyOption = document.createElement('label');
      inputReadOnlyOption.className = 'date-option';
      inputReadOnlyOption.innerHTML = '<span>只读输入框</span><input type="checkbox" data-date-input-readonly>';
      popover.append(inputReadOnlyOption);
      const disabledOption = document.createElement('label');
      disabledOption.className = 'date-option';
      disabledOption.innerHTML = '<span>禁用控件</span><input type="checkbox" data-date-disabled-control>';
      popover.append(disabledOption);
      const openOption = document.createElement('label');
      openOption.className = 'date-option';
      openOption.innerHTML = '<span>受控展开</span><input type="checkbox" data-date-open-control>';
      popover.append(openOption);
      const confirmDate = document.createElement('button');
      confirmDate.type = 'button';
      confirmDate.className = 'nm-button date-confirm';
      confirmDate.dataset.dateConfirm = '';
      confirmDate.textContent = '确定';
      popover.append(confirmDate);
      const showTimeControl = popover.querySelector('[data-date-show-time]');
      const timeControl = popover.querySelector('[data-date-time]');
      const needConfirmControl = popover.querySelector('[data-date-need-confirm]');
      const minDateInput = popover.querySelector('[data-date-min]');
      const maxDateInput = popover.querySelector('[data-date-max]');
      const openControl = popover.querySelector('[data-date-open-control]');
      const showNowControl = popover.querySelector('[data-date-show-now]');
      const sizePicker = popover.querySelector('[data-date-size]');
      const variantPicker = popover.querySelector('[data-date-variant]');
      const statusPicker = document.createElement('label');
      statusPicker.className = 'date-option';
      statusPicker.innerHTML = '<span>状态</span><select data-date-status aria-label="校验状态"><option value="default">默认</option><option value="success">成功</option><option value="warning">警告</option><option value="error">错误</option></select>';
      variantPicker?.closest('label')?.after(statusPicker);
      const placementPicker = document.createElement('label');
      placementPicker.className = 'date-option';
      placementPicker.innerHTML = '<span>位置</span><select data-date-placement aria-label="面板位置"><option value="bottomLeft">左下</option><option value="bottomRight">右下</option><option value="topLeft">左上</option><option value="topRight">右上</option></select>';
      statusPicker.after(placementPicker);
      const withTime = value => showTimeControl?.checked && timeControl?.value ? `${value} ${timeControl.value}:00` : value;
      const syncDateTime = () => {
        const multiple = multipleControl.querySelector('input')?.checked === true;
        if (showTimeControl) {
          showTimeControl.disabled = multiple;
          if (multiple) showTimeControl.checked = false;
        }
        if (timeControl) timeControl.hidden = !showTimeControl?.checked;
        confirmDate.hidden = !(showTimeControl?.checked || needConfirmControl?.checked);
        if (!showTimeControl?.checked) return;
        const dates = (demo.dataset.selectedDates || demo.dataset.selectedDate || '').split('|').filter(Boolean);
        const normalized = dates.map(item => {
          const dateOnly = item.match(/^\d{4}年\d{2}月\d{2}日/)?.[0] || item;
          return withTime(dateOnly);
        });
        demo.dataset.selectedDates = normalized.join('|');
        demo.dataset.selectedDate = normalized[0] || '';
        const label = demo.querySelector('[data-date-label]');
        if (label && normalized.length) label.value = normalized.join('、');
      };
      const syncAppearance = () => {
        trigger.dataset.size = sizePicker?.value || 'middle';
        trigger.dataset.variant = variantPicker?.value || 'outlined';
        trigger.dataset.status = statusPicker.querySelector('select')?.value || 'default';
        popover.dataset.placement = placementPicker.querySelector('select')?.value || 'bottomLeft';
        const label = demo.querySelector('[data-date-label]');
        const disabled = disabledOption.querySelector('input')?.checked === true;
        trigger.setAttribute('aria-disabled', String(disabled));
        trigger.tabIndex = disabled ? -1 : 0;
        if (label) label.readOnly = inputReadOnlyOption.querySelector('input')?.checked === true || disabled;
        trigger.classList.toggle('is-disabled', disabled);
      };
      const isOpenControlled = () => openControl?.checked === true;
      demo.dataset.selectedDates = demo.dataset.selectedDate || '';
      const renderMonth = () => {
        const current = nav.querySelector('strong').textContent.match(/(\d{4})年(\d{2})月/);
        if (!current) return;
        const year = Number(current[1]);
        const month = Number(current[2]);
        const pickerMode = pickerControl.querySelector('select')?.value || 'date';
        const firstDay = new Date(year, month - 1, 1).getDay();
        const days = new Date(year, month, 0).getDate();
        const selected = new Set((demo.dataset.selectedDates || demo.dataset.selectedDate || '').split('|').filter(Boolean));
        grid.replaceChildren();
        grid.classList.toggle('is-picker-grid', pickerMode !== 'date');
        if (pickerMode === 'week' || pickerMode === 'month' || pickerMode === 'quarter' || pickerMode === 'year') {
          const minBoundary = minDateInput?.value ? new Date(`${minDateInput.value}T00:00:00`) : null;
          const maxBoundary = maxDateInput?.value ? new Date(`${maxDateInput.value}T23:59:59`) : null;
          const values = pickerMode === 'week'
            ? Array.from({ length: 6 }, (_, index) => `${year}年第${Math.floor((firstDay + index * 7) / 7) + 1}周`)
            : pickerMode === 'month'
              ? Array.from({ length: 12 }, (_, index) => `${year}年${String(index + 1).padStart(2, '0')}月`)
              : pickerMode === 'quarter'
                ? Array.from({ length: 4 }, (_, index) => `${year}年第${index + 1}季度`)
                : Array.from({ length: 12 }, (_, index) => `${year - 5 + index}年`);
          values.forEach((value, index) => {
            const button = document.createElement('button');
            button.type = 'button';
            button.textContent = pickerMode === 'month' ? value.slice(5, 7) + '月' : pickerMode === 'quarter' ? value.slice(6) : pickerMode === 'week' ? value.slice(5) : value.slice(0, 4);
            button.dataset.dateValue = value;
            const periodStart = pickerMode === 'month' ? new Date(year, index, 1)
              : pickerMode === 'quarter' ? new Date(year, index * 3, 1)
                : pickerMode === 'year' ? new Date(Number(value.slice(0, 4)), 0, 1)
                  : null;
            const periodEnd = pickerMode === 'month' ? new Date(year, index + 1, 0, 23, 59, 59)
              : pickerMode === 'quarter' ? new Date(year, index * 3 + 3, 0, 23, 59, 59)
                : pickerMode === 'year' ? new Date(Number(value.slice(0, 4)), 11, 31, 23, 59, 59)
                  : null;
            const periodDisabled = periodStart && periodEnd && ((minBoundary && periodEnd < minBoundary) || (maxBoundary && periodStart > maxBoundary));
            button.disabled = Boolean(periodDisabled);
            button.setAttribute('aria-disabled', String(Boolean(periodDisabled)));
            const isSelected = pickerMode === 'month'
              ? [...selected].some(item => item.startsWith(value))
              : pickerMode === 'quarter'
                ? [...selected].some(item => item.startsWith(value))
                : pickerMode === 'week'
                  ? [...selected].some(item => item.startsWith(value))
              : [...selected].some(item => item.startsWith(value.slice(0, 4)));
            button.setAttribute('aria-selected', String(isSelected));
            button.classList.toggle('selected', isSelected);
            button.addEventListener('click', () => {
              if (button.disabled) return;
              demo.dataset.selectedDate = value;
              demo.dataset.selectedDates = value;
              demo.querySelector('[data-date-label]').value = value;
              if (!showTimeControl?.checked && !needConfirmControl?.checked && !isOpenControlled()) { demo.classList.remove('is-open'); popover.hidden = true; trigger.setAttribute('aria-expanded', 'false'); trigger.focus(); }
            });
            grid.append(button);
          });
          return;
        }
        for (let index = 0; index < firstDay; index += 1) {
          const blank = document.createElement('span');
          blank.setAttribute('aria-hidden', 'true');
          grid.append(blank);
        }
        for (let day = 1; day <= days; day += 1) {
          const button = document.createElement('button');
          const value = `${year}年${String(month).padStart(2, '0')}月${String(day).padStart(2, '0')}日`;
          button.type = 'button';
          button.textContent = String(day).padStart(2, '0');
          button.dataset.dateValue = value;
          const cellDate = new Date(year, month - 1, day);
          const minDate = minDateInput?.value ? new Date(`${minDateInput.value}T00:00:00`) : null;
          const maxDate = maxDateInput?.value ? new Date(`${maxDateInput.value}T23:59:59`) : null;
          const disabled = (disabledDateControl.querySelector('input')?.checked && [0, 6].includes(cellDate.getDay())) || (minDate && cellDate < minDate) || (maxDate && cellDate > maxDate);
          button.disabled = Boolean(disabled);
          button.setAttribute('aria-disabled', String(Boolean(disabled)));
          button.setAttribute('aria-selected', String(selected.has(value)));
          button.classList.toggle('selected', selected.has(value));
          button.addEventListener('click', () => {
            if (button.disabled) return;
            if (multipleControl.querySelector('input')?.checked) return;
            const nextValue = withTime(value);
            demo.dataset.selectedDate = nextValue;
            demo.dataset.selectedDates = nextValue;
            demo.querySelector('[data-date-label]').value = nextValue;
            renderMonth();
            if (showTimeControl?.checked) {
              syncDateTime();
              demo.classList.add('is-open');
              demo.querySelector('.date-popover').hidden = false;
              demo.querySelector('.date-trigger').setAttribute('aria-expanded', 'true');
              timeControl?.focus();
              return;
            }
            if (!needConfirmControl?.checked && !isOpenControlled()) { demo.classList.remove('is-open'); demo.querySelector('.date-popover').hidden = true; demo.querySelector('.date-trigger').setAttribute('aria-expanded', 'false'); demo.querySelector('.date-trigger')?.focus(); }
          });
          button.addEventListener('keydown', event => {
            if (['PageUp', 'PageDown'].includes(event.key)) {
              event.preventDefault();
              nav.querySelector(event.key === 'PageUp' ? 'button:first-child' : 'button:last-child')?.click();
              requestAnimationFrame(() => (grid.querySelector('.selected:not(:disabled)') || grid.querySelector('button:not(:disabled)'))?.focus());
              return;
            }
            if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home', 'End'].includes(event.key)) return;
            event.preventDefault();
            const cells = [...grid.children];
            const items = cells.filter(cell => cell.matches('button:not([hidden])'));
            const index = cells.indexOf(button);
            const delta = event.key === 'ArrowLeft' ? -1 : event.key === 'ArrowRight' ? 1 : event.key === 'ArrowUp' ? -7 : event.key === 'ArrowDown' ? 7 : 0;
            if (event.key === 'Home' || event.key === 'End') {
              (event.key === 'Home' ? items[0] : items[items.length - 1])?.focus();
              return;
            }
            let nextIndex = Math.max(0, Math.min(cells.length - 1, index + delta));
            while (cells[nextIndex] && !cells[nextIndex].matches('button:not([hidden])')) {
              nextIndex += delta > 0 ? 1 : -1;
              if (nextIndex < 0 || nextIndex >= cells.length) return;
            }
            cells[nextIndex]?.focus();
          });
          grid.append(button);
        }
      };
      nav.querySelectorAll('button').forEach(button => button.addEventListener('click', renderMonth));
      demo.dataset.selectedDate = demo.querySelector('[data-date-label]')?.value.trim() || '';
      if (!demo.dataset.selectedDates) demo.dataset.selectedDates = demo.dataset.selectedDate;
      grid.addEventListener('click', event => {
        const day = event.target.closest('[data-date-value]');
        if (!day || !multipleControl.querySelector('input')?.checked) return;
        const value = withTime(day.dataset.dateValue);
        const selected = new Set((demo.dataset.selectedDates || '').split('|').filter(Boolean));
        if (selected.has(value)) selected.delete(value); else selected.add(value);
        demo.dataset.selectedDates = [...selected].join('|');
        demo.dataset.selectedDate = [...selected][0] || '';
        const label = demo.querySelector('[data-date-label]');
        if (label) {
          label.value = [...selected].join('、') || '请选择日期';
          label.dispatchEvent(new Event('input', { bubbles: true }));
        }
        renderMonth();
        demo.classList.add('is-open');
        demo.querySelector('.date-popover').hidden = false;
        demo.querySelector('.date-trigger').setAttribute('aria-expanded', 'true');
      });
      multipleControl.querySelector('input')?.addEventListener('change', () => { if (!multipleControl.querySelector('input').checked) { const first = (demo.dataset.selectedDates || demo.dataset.selectedDate || '').split('|').filter(Boolean)[0] || ''; demo.dataset.selectedDate = first; demo.dataset.selectedDates = first; const label = demo.querySelector('[data-date-label]'); if (label) label.value = first; } syncDateTime(); renderMonth(); });
      disabledDateControl.querySelector('input')?.addEventListener('change', renderMonth);
      minDateInput?.addEventListener('change', renderMonth);
      maxDateInput?.addEventListener('change', renderMonth);
      pickerControl.querySelector('select')?.addEventListener('change', renderMonth);
      showTimeControl?.addEventListener('change', () => { syncDateTime(); renderMonth(); });
      needConfirmControl?.addEventListener('change', () => { syncDateTime(); });
      openControl?.addEventListener('change', event => {
        const open = event.target.checked;
        demo.classList.toggle('is-open', open);
        popover.hidden = !open;
        trigger.setAttribute('aria-expanded', String(open));
        if (open) requestAnimationFrame(() => (grid.querySelector('.selected:not(:disabled)') || grid.querySelector('button:not(:disabled)'))?.focus());
      });
      timeControl?.addEventListener('change', () => { syncDateTime(); renderMonth(); });
      confirmDate.addEventListener('click', () => { syncDateTime(); if (isOpenControlled()) return; demo.classList.remove('is-open'); popover.hidden = true; trigger.setAttribute('aria-expanded', 'false'); trigger.focus(); });
      sizePicker?.addEventListener('change', syncAppearance);
      variantPicker?.addEventListener('change', syncAppearance);
      statusPicker.querySelector('select')?.addEventListener('change', syncAppearance);
      placementPicker.querySelector('select')?.addEventListener('change', syncAppearance);
      inputReadOnlyOption.querySelector('input')?.addEventListener('change', syncAppearance);
      disabledOption.querySelector('input')?.addEventListener('change', () => { syncAppearance(); if (disabledOption.querySelector('input')?.checked) { demo.classList.remove('is-open'); popover.hidden = true; trigger.setAttribute('aria-expanded', 'false'); } });
      syncAppearance();
      syncDateTime();
      renderMonth();
      demo.querySelector('[data-date-label]')?.addEventListener('change', event => {
        const input = event.currentTarget;
        const raw = input.value.trim();
        if (!raw && demo.querySelector('[data-date-allow-clear]')?.checked !== false) {
          demo.dataset.selectedDate = '';
          demo.dataset.selectedDates = '';
          input.removeAttribute('aria-invalid');
          renderMonth();
          return;
        }
        const match = raw.match(/^(\d{4})[-年](\d{1,2})[-月](\d{1,2})日?$/);
        const year = match ? Number(match[1]) : NaN;
        const month = match ? Number(match[2]) : NaN;
        const day = match ? Number(match[3]) : NaN;
        const candidate = match ? new Date(year, month - 1, day) : null;
        const minDate = minDateInput?.value ? new Date(`${minDateInput.value}T00:00:00`) : null;
        const maxDate = maxDateInput?.value ? new Date(`${maxDateInput.value}T23:59:59`) : null;
        const valid = candidate && candidate.getFullYear() === year && candidate.getMonth() === month - 1 && candidate.getDate() === day && !(disabledDateControl.querySelector('input')?.checked && [0, 6].includes(candidate.getDay())) && !(minDate && candidate < minDate) && !(maxDate && candidate > maxDate);
        if (!valid) {
          input.setAttribute('aria-invalid', 'true');
          input.value = demo.dataset.selectedDate || '';
          return;
        }
        const value = withTime(`${year}年${String(month).padStart(2, '0')}月${String(day).padStart(2, '0')}日`);
        demo.dataset.selectedDate = value;
        demo.dataset.selectedDates = value;
        input.value = value;
        input.removeAttribute('aria-invalid');
        renderMonth();
      });
      demo.querySelector('[data-date-label]')?.addEventListener('blur', event => {
        event.currentTarget.dispatchEvent(new Event('change', { bubbles: true }));
      });
      demo.querySelector('[data-date-label]')?.addEventListener('keydown', event => {
        if (event.key !== 'Enter') return;
        event.preventDefault();
        event.currentTarget.dispatchEvent(new Event('change', { bubbles: true }));
      });
      demo.querySelector('[data-date-label]')?.addEventListener('input', event => {
        if (/^\d{4}-\d{2}-\d{2}$/.test(event.currentTarget.value.trim())) {
          event.currentTarget.dispatchEvent(new Event('change', { bubbles: true }));
        }
      });
      trigger.addEventListener('click', event => {
        if (event.target.closest('.date-clear-trigger')) return;
        if (disabledOption.querySelector('input')?.checked === true) return;
        if (isOpenControlled()) return;
        const open = !demo.classList.contains('is-open');
        demo.classList.toggle('is-open', open);
        popover.hidden = !open;
        trigger.setAttribute('aria-expanded', String(open));
        if (open) requestAnimationFrame(() => (grid.querySelector('.selected:not(:disabled)') || grid.querySelector('button:not(:disabled)'))?.focus());
      });
      const commitQuickDate = value => {
        demo.dataset.selectedDate = value;
        demo.dataset.selectedDates = value;
        demo.querySelector('[data-date-label]').value = value;
        renderMonth();
        if (showTimeControl?.checked) {
          syncDateTime();
          demo.classList.add('is-open');
          popover.hidden = false;
          trigger.setAttribute('aria-expanded', 'true');
          timeControl?.focus();
          return;
        }
        if (!isOpenControlled()) {
          demo.classList.remove('is-open');
          popover.hidden = true;
          trigger.setAttribute('aria-expanded', 'false');
          trigger.focus();
        }
      };
      const today = document.createElement('button'); today.type = 'button'; today.className = 'date-now'; today.textContent = '今天'; today.addEventListener('click', () => { const now = new Date(); if (disabledDateControl.querySelector('input')?.checked && [0, 6].includes(now.getDay())) { window.NoteMeldDesignSystem?.notify('今天不可用：周末已被禁用'); return; } commitQuickDate(withTime(`${now.getFullYear()}年${String(now.getMonth() + 1).padStart(2, '0')}月${String(now.getDate()).padStart(2, '0')}日`)); }); popover.append(today);
      presets.querySelectorAll('[data-date-preset]').forEach(button => button.addEventListener('click', () => { const now = new Date(); if (button.dataset.datePreset === 'tomorrow') now.setDate(now.getDate() + 1); if (disabledDateControl.querySelector('input')?.checked && [0, 6].includes(now.getDay())) { window.NoteMeldDesignSystem?.notify('该快捷日期不可用：周末已被禁用'); return; } commitQuickDate(withTime(`${now.getFullYear()}年${String(now.getMonth() + 1).padStart(2, '0')}月${String(now.getDate()).padStart(2, '0')}日`)); }));
      const syncDateActions = () => { today.hidden = showNowControl?.checked !== true; };
      showNowControl?.addEventListener('change', syncDateActions);
      syncDateActions();
    });
    document.addEventListener('keydown', event => { if (event.key !== 'Escape') return; document.querySelectorAll('.date-demo.is-open, .time-picker-demo.is-open').forEach(demo => { if (demo.querySelector('[data-date-open-control], [data-time-open]')?.checked === true) return; demo.classList.remove('is-open'); const popover = demo.querySelector('.date-popover, .time-popover'); const trigger = demo.querySelector('.date-trigger'); if (popover) popover.hidden = true; trigger?.setAttribute('aria-expanded', 'false'); trigger?.focus(); }); });
    document.querySelectorAll('.date-demo .date-trigger, .time-picker-demo .date-trigger').forEach(trigger => { trigger.setAttribute('aria-expanded', 'false'); trigger.setAttribute('aria-haspopup', 'dialog'); trigger.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ' || event.key === 'ArrowDown') { event.preventDefault(); trigger.click(); } }); });
    document.querySelectorAll('[data-select-demo]').forEach(select => {
      const trigger = select.querySelector('.select-trigger');
      let options = [...select.querySelectorAll('.select-option')];
      const shell = select.querySelector('.select-shell');
      const modeToggle = select.querySelector('[data-select-multiple]');
      const modePicker = document.createElement('label');
      modePicker.className = 'select-mode-toggle';
      modePicker.innerHTML = '<span>模式</span><select aria-label="选择器模式"><option value="single">单选</option><option value="multiple">多选</option><option value="tags">标签</option></select>';
      modeToggle?.closest('label')?.after(modePicker);
      modePicker.querySelector('select').value = modeToggle?.checked ? 'multiple' : 'single';
      const getMode = () => modePicker.querySelector('select')?.value || (modeToggle?.checked ? 'multiple' : 'single');
      const isMultiple = () => getMode() !== 'single';
      const search = document.createElement('input'); search.className = 'select-search-input'; search.type = 'search'; search.placeholder = '搜索选项'; search.setAttribute('aria-label', '搜索选项'); shell?.insertBefore(search, shell.querySelector('.select-options'));
      const clear = document.createElement('span'); clear.className = 'select-clear'; clear.setAttribute('role', 'button'); clear.tabIndex = 0; clear.setAttribute('aria-label', '清除选择'); clear.textContent = '×'; shell?.append(clear);
      const disabledControl = document.createElement('label'); disabledControl.className = 'select-mode-toggle'; disabledControl.innerHTML = '<input type="checkbox" data-select-disabled>禁用控件'; select.querySelector('.select-shell')?.before(disabledControl);
      const openControl = document.createElement('label'); openControl.className = 'select-mode-toggle'; openControl.innerHTML = '<input type="checkbox" data-select-open>受控展开'; disabledControl.after(openControl);
      const placementControl = document.createElement('label'); placementControl.className = 'select-mode-toggle'; placementControl.innerHTML = '<span>位置</span><select data-select-placement aria-label="选择器面板位置"><option value="bottomLeft">左下</option><option value="bottomRight">右下</option><option value="topLeft">左上</option><option value="topRight">右上</option></select>'; openControl.after(placementControl);
      const sizeControl = document.createElement('label'); sizeControl.className = 'select-mode-toggle'; sizeControl.innerHTML = '<span>尺寸</span><select data-select-size aria-label="选择器尺寸"><option value="middle">中</option><option value="small">小</option><option value="large">大</option></select>'; placementControl.after(sizeControl);
      const statusControl = document.createElement('label'); statusControl.className = 'select-mode-toggle'; statusControl.innerHTML = '<span>状态</span><select data-select-status aria-label="选择器状态"><option value="default">默认</option><option value="warning">警告</option><option value="error">错误</option></select>'; sizeControl.after(statusControl);
      const variantControl = document.createElement('label'); variantControl.className = 'select-mode-toggle'; variantControl.innerHTML = '<span>变体</span><select data-select-variant aria-label="选择器变体"><option value="outlined">描边</option><option value="filled">填充</option><option value="borderless">无边框</option><option value="underlined">下划线</option></select>'; statusControl.after(variantControl);
      const maxCountControl = document.createElement('label'); maxCountControl.className = 'select-mode-toggle'; maxCountControl.innerHTML = '<span>最多选择</span><select data-select-max-count aria-label="最多选择数量"><option value="0">不限</option><option value="1">1</option><option value="2" selected>2</option></select>'; variantControl.after(maxCountControl);
      const syncSearchVisibility = () => { const explicit = select.querySelector('[data-select-show-search]')?.checked === true; const visible = isMultiple() || explicit; search.hidden = !visible; search.style.setProperty('display', visible ? 'block' : 'none', 'important'); };
      const filterOptions = () => { const query = search.value.trim().toLocaleLowerCase(); options.forEach(option => { option.hidden = Boolean(query && !option.textContent.toLocaleLowerCase().includes(query)); }); };
      const syncValue = () => { const selected = options.filter(option => option.classList.contains('selected')); const disabled = disabledControl.querySelector('input')?.checked === true; const labelInValue = select.querySelector('[data-select-label-in-value]')?.checked === true; const limit = maxCount(); const atLimit = isMultiple() && limit > 0 && selected.length >= limit; options.forEach(option => { const optionDisabled = disabled || (atLimit && !option.classList.contains('selected')); option.disabled = optionDisabled; option.setAttribute('aria-disabled', String(optionDisabled)); }); trigger.querySelector('span').textContent = selected.map(option => { const label = option.querySelector('strong')?.textContent || ''; return labelInValue ? `${label} (${option.dataset.value || ''})` : label; }).join(isMultiple() ? '、' : '') || '请选择'; select.querySelector('[role="listbox"]')?.setAttribute('aria-multiselectable', String(isMultiple())); trigger.setAttribute('aria-disabled', String(disabled)); trigger.tabIndex = disabled ? -1 : 0; trigger.classList.toggle('is-disabled', disabled); trigger.dataset.size = sizeControl.querySelector('select')?.value || 'middle'; trigger.dataset.status = statusControl.querySelector('select')?.value || 'default'; trigger.dataset.variant = variantControl.querySelector('select')?.value || 'outlined'; clear.setAttribute('aria-disabled', String(disabled)); clear.tabIndex = disabled ? -1 : 0; clear.classList.toggle('is-disabled', disabled); };
      const maxCount = () => Number(maxCountControl.querySelector('select')?.value || 0);
      const mark = (option, selected) => { option.classList.toggle('selected', selected); option.setAttribute('aria-selected', String(selected)); option.querySelector('i')?.remove(); if (selected) option.insertAdjacentHTML('beforeend', '<i><span class="nm-icon nm-icon-check" aria-hidden="true"></span></i>'); };
      search.addEventListener('input', filterOptions); clear.addEventListener('click', event => { event.stopPropagation(); if (disabledControl.querySelector('input')?.checked === true) return; options.forEach(option => mark(option, false)); syncValue(); search.value = ''; filterOptions(); if (!isMultiple() && openControl.querySelector('input')?.checked !== true) { trigger.setAttribute('aria-expanded', 'false'); select.classList.add('is-closed'); } });
      clear.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); clear.click(); } });
      const bindOption = option => { option.onclick = () => { const selecting = !option.classList.contains('selected'); const selectedCount = options.filter(item => item.classList.contains('selected')).length; if (isMultiple() && selecting && maxCount() > 0 && selectedCount >= maxCount()) { window.NoteMeldDesignSystem?.notify(`最多选择 ${maxCount()} 项`); return; } if (isMultiple()) mark(option, selecting); else options.forEach(item => mark(item, item === option)); syncValue(); search.value = ''; filterOptions(); }; option.addEventListener('keydown', event => { const visible = options.filter(item => !item.hidden); const index = visible.indexOf(option); if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); option.click(); trigger.focus(); } else if (['ArrowDown','ArrowUp','Home','End'].includes(event.key)) { event.preventDefault(); const next = event.key === 'Home' ? 0 : event.key === 'End' ? visible.length - 1 : Math.max(0, Math.min(visible.length - 1, index + (event.key === 'ArrowDown' ? 1 : -1))); visible[next]?.focus(); } }); };
      options.forEach(bindOption);
      search.addEventListener('keydown', event => { if (event.key === 'Escape') { event.preventDefault(); trigger.setAttribute('aria-expanded', 'false'); select.classList.add('is-closed'); trigger.focus(); } else if (event.key === 'ArrowDown') { event.preventDefault(); options.find(option => !option.hidden)?.focus(); } else if (event.key === 'Enter' && getMode() === 'tags' && search.value.trim()) { event.preventDefault(); const label = search.value.trim(); const existing = options.find(option => option.querySelector('strong')?.textContent.trim().toLocaleLowerCase() === label.toLocaleLowerCase()); if (existing) { existing.click(); return; } const option = document.createElement('button'); option.type = 'button'; option.className = 'select-option selected'; option.setAttribute('role', 'option'); option.setAttribute('aria-selected', 'true'); option.dataset.value = label; option.innerHTML = `<span><strong>${label}</strong><small>自定义标签</small></span>`; select.querySelector('.select-options')?.append(option); options = [...options, option]; bindOption(option); syncValue(); search.value = ''; filterOptions(); }});
      trigger.onclick = () => { if (disabledControl.querySelector('input')?.checked === true || openControl.querySelector('input')?.checked === true) return; const expanded = trigger.getAttribute('aria-expanded') !== 'true'; trigger.setAttribute('aria-expanded', String(expanded)); select.classList.toggle('is-closed', !expanded); if (expanded) { filterOptions(); if (search.hidden) options.find(option => option.classList.contains('selected') && !option.hidden)?.focus() || options.find(option => !option.hidden)?.focus(); else search.focus(); } };
      options.forEach(option => option.addEventListener('click', () => { if (!isMultiple() && openControl.querySelector('input')?.checked !== true) { trigger.setAttribute('aria-expanded', 'false'); select.classList.add('is-closed'); } }));
      modeToggle?.addEventListener('change', () => { modePicker.querySelector('select').value = modeToggle.checked ? 'multiple' : 'single'; options.forEach((option, index) => mark(option, index === 0)); syncValue(); syncSearchVisibility(); });
      modePicker.querySelector('select')?.addEventListener('change', () => { modeToggle.checked = getMode() !== 'single'; options.forEach((option, index) => mark(option, index === 0)); syncValue(); syncSearchVisibility(); });
      select.querySelector('[data-select-label-in-value]')?.addEventListener('change', syncValue);
      select.addEventListener('change', event => { if (event.target.matches('[data-select-label-in-value]')) syncValue(); });
      disabledControl.querySelector('input')?.addEventListener('change', () => { if (disabledControl.querySelector('input')?.checked) { trigger.setAttribute('aria-expanded', 'false'); select.classList.add('is-closed'); } syncValue(); });
      openControl.querySelector('input')?.addEventListener('change', event => { if (event.target.checked) { trigger.setAttribute('aria-expanded', 'true'); select.classList.remove('is-closed'); filterOptions(); } else { trigger.setAttribute('aria-expanded', 'false'); select.classList.add('is-closed'); } });
      placementControl.querySelector('select')?.addEventListener('change', event => { select.dataset.placement = event.target.value; });
      select.dataset.placement = placementControl.querySelector('select')?.value || 'bottomLeft';
      [sizeControl, statusControl, variantControl, maxCountControl].forEach(control => control.querySelector('select')?.addEventListener('change', syncValue));
      trigger.setAttribute('aria-expanded', 'false');
      select.classList.add('is-closed');
      syncValue();
      syncSearchVisibility();
      queueMicrotask(() => { const labelValueControl = select.querySelector('[data-select-label-in-value]'); if (labelValueControl) { labelValueControl.addEventListener('change', syncValue); syncValue(); } });
      trigger.addEventListener('keydown', event => { if (event.key === 'Escape') { trigger.setAttribute('aria-expanded', 'false'); select.classList.add('is-closed'); } if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); trigger.click(); } if (event.key === 'ArrowDown' && trigger.getAttribute('aria-expanded') !== 'true') { event.preventDefault(); trigger.click(); } });
    });
    document.querySelectorAll('[data-date-demo]').forEach(demo => {
      const trigger = demo.querySelector('.date-trigger');
      const clear = demo.querySelector('[data-date-clear]');
      const triggerClear = document.createElement('button');
      triggerClear.type = 'button';
      triggerClear.className = 'date-clear-trigger';
      triggerClear.setAttribute('aria-label', '清除日期');
      triggerClear.innerHTML = '<span class="nm-icon nm-icon-close" aria-hidden="true"></span>';
      trigger?.append(triggerClear);
      const allowClearControl = demo.querySelector('[data-date-allow-clear]');
      const clearValue = () => { if (allowClearControl?.checked === false || demo.querySelector('[data-date-disabled-control]')?.checked === true) return; demo.dataset.selectedDate = ''; demo.dataset.selectedDates = ''; demo.querySelector('[data-date-label]').value = ''; if (demo.querySelector('[data-date-open-control]')?.checked !== true) { demo.classList.remove('is-open'); demo.querySelector('.date-popover').hidden = true; trigger.setAttribute('aria-expanded', 'false'); trigger.focus(); } triggerClear.hidden = true; };
      clear?.addEventListener('click', clearValue);
      triggerClear.addEventListener('click', event => { event.stopPropagation(); clearValue(); });
      const syncTriggerClear = () => { triggerClear.hidden = allowClearControl?.checked === false || !(demo.dataset.selectedDate || demo.querySelector('[data-date-label]')?.value.trim()); };
      allowClearControl?.addEventListener('change', syncTriggerClear);
      demo.querySelector('[data-date-label]')?.addEventListener('input', syncTriggerClear);
      // Calendar selection and presets update the value programmatically.
      // Sync after their handlers, including controls rendered on month changes.
      demo.addEventListener('click', () => queueMicrotask(syncTriggerClear));
      demo.addEventListener('change', () => queueMicrotask(syncTriggerClear));
      syncTriggerClear();
      demo.querySelectorAll('[data-date-value]').forEach(day => day.addEventListener('click', () => demo.querySelectorAll('[data-date-value]').forEach(item => item.setAttribute('aria-selected', String(item === day)))));
    });
    document.querySelectorAll('[data-time-demo]').forEach(demo => {
      demo.querySelectorAll('[data-time-part]').forEach(option => {
        option.addEventListener('click', () => { const part = option.dataset.timePart; demo.querySelectorAll(`[data-time-part="${part}"]`).forEach(item => item.setAttribute('aria-selected', String(item === option))); });
        option.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); if (!option.disabled) option.click(); } });
        option.addEventListener('keydown', event => { const column = option.closest('.time-column'); if (!column || !['ArrowUp','ArrowDown','ArrowLeft','ArrowRight','Home','End'].includes(event.key)) return; event.preventDefault(); const columns = [...demo.querySelectorAll('.time-column:not([hidden])')]; if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') { const columnIndex = columns.indexOf(column); const targetColumn = columns[columnIndex + (event.key === 'ArrowRight' ? 1 : -1)]; targetColumn?.querySelector('.selected:not([hidden]):not(:disabled)')?.focus(); return; } const items = [...column.querySelectorAll('[data-time-part]:not([hidden]):not(:disabled)')]; const index = items.indexOf(option); const next = event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1 : Math.max(0, Math.min(items.length - 1, index + (event.key === 'ArrowDown' ? 1 : -1))); items[next]?.focus(); });
      });
    });
    document.querySelectorAll('.autocomplete-demo').forEach(demo => {
      const input = demo.querySelector('input'); const options = [...demo.querySelectorAll('.autocomplete-options button')]; let active = -1;
      const setActive = index => { active = index; options.forEach((option, optionIndex) => { option.classList.toggle('active', optionIndex === active); option.setAttribute('aria-selected', String(optionIndex === active)); }); };
      input?.addEventListener('keydown', event => { const visible = options.filter(option => !option.hidden); const visibleIndex = visible.indexOf(options[active]); if (event.key === 'ArrowDown') { event.preventDefault(); const next = Math.min(visibleIndex + 1, visible.length - 1); setActive(options.indexOf(visible[Math.max(0, next)])); } else if (event.key === 'ArrowUp') { event.preventDefault(); const next = Math.max(visibleIndex - 1, 0); setActive(options.indexOf(visible[Math.max(0, next)])); } else if (event.key === 'Enter' && visible.includes(options[active])) { event.preventDefault(); options[active].click(); } else if (event.key === 'Escape') { event.preventDefault(); demo.classList.remove('is-open'); demo.setAttribute('aria-expanded', 'false'); setActive(-1); } });
      options.forEach(option => option.addEventListener('mouseenter', () => setActive(options.indexOf(option))));
      if (demo.querySelector('.search-prefix')?.textContent.trim() === '@') { demo.classList.remove('is-open'); input?.addEventListener('input', () => { demo.classList.toggle('is-open', input.value.includes('@')); }); input?.addEventListener('focus', () => { if (!input.value.includes('@')) demo.classList.remove('is-open'); }); }
    });
    document.querySelectorAll('.autocomplete-demo input').forEach(input => {
      const demo = input.closest('.autocomplete-demo');
      const prefix = demo?.querySelector('.search-prefix')?.textContent.trim();
      if (!demo || prefix === '@' || demo.dataset.autocompleteBound) return;
      demo.dataset.autocompleteBound = 'true';
      const options = [...demo.querySelectorAll('.autocomplete-options button')];
      const list = demo.querySelector('.autocomplete-options');
      demo.setAttribute('role', 'combobox');
      demo.setAttribute('aria-expanded', 'false');
      list?.setAttribute('role', 'listbox');
      let hasInteracted = false;
      const sync = () => {
        const query = input.value.trim().toLocaleLowerCase();
        let visible = 0;
        const filterOption = demo.querySelector('[data-autocomplete-filter-option]')?.checked !== false;
        options.forEach(option => { const match = !filterOption || !query || option.textContent.toLocaleLowerCase().includes(query); option.hidden = !match; if (match) visible += 1; });
        const open = hasInteracted && Boolean(query);
        demo.classList.toggle('is-open', open);
        demo.setAttribute('aria-expanded', String(open));
        if (list) list.dataset.empty = String(Boolean(query) && visible === 0);
      };
      input.addEventListener('input', () => { hasInteracted = true; sync(); });
      input.addEventListener('focus', () => { hasInteracted = true; sync(); });
      options.forEach(option => option.addEventListener('click', () => { input.value = option.querySelector('strong')?.textContent.trim() || option.textContent.trim(); demo.classList.remove('is-open'); demo.setAttribute('aria-expanded', 'false'); input.focus(); }));
      sync();
    });
    document.querySelectorAll('.autocomplete-demo').forEach((demo, demoIndex) => { const input = demo.querySelector('input'); const list = demo.querySelector('.autocomplete-options'); if (!input || !list) return; const listId = `nm-autocomplete-list-${demoIndex}`; list.id = list.id || listId; input.setAttribute('aria-autocomplete', 'list'); input.setAttribute('aria-controls', list.id); const options = [...demo.querySelectorAll('.autocomplete-options button')]; options.forEach((option, optionIndex) => { option.id = option.id || `${list.id}-option-${optionIndex}`; option.setAttribute('role', 'option'); }); const syncActiveDescendant = () => { const active = options.find(option => option.classList.contains('active') && !option.hidden); if (active) demo.setAttribute('aria-activedescendant', active.id); else demo.removeAttribute('aria-activedescendant'); }; input.addEventListener('keydown', () => requestAnimationFrame(syncActiveDescendant)); input.addEventListener('input', syncActiveDescendant); options.forEach(option => option.addEventListener('mouseenter', syncActiveDescendant)); syncActiveDescendant(); });
    document.querySelectorAll('.autocomplete-demo').forEach(demo => {
      const input = demo.querySelector('input');
      if (!input || demo.querySelector('[data-autocomplete-clear]') || demo.querySelector('.search-prefix')?.textContent.trim() === '@') return;
      const clear = document.createElement('button');
      clear.type = 'button';
      clear.className = 'autocomplete-clear';
      clear.dataset.autocompleteClear = '';
      clear.setAttribute('aria-label', '清除输入');
      clear.innerHTML = '<span class="nm-icon nm-icon-close" aria-hidden="true"></span>';
      input.after(clear);
      const allowClear = document.createElement('label');
      allowClear.className = 'autocomplete-option';
      allowClear.innerHTML = '<input type="checkbox" data-autocomplete-allow-clear>允许清除';
      demo.after(allowClear);
      const disabledControl = document.createElement('label');
      disabledControl.className = 'autocomplete-option';
      disabledControl.innerHTML = '<input type="checkbox" data-autocomplete-disabled>禁用';
      allowClear.after(disabledControl);
      const backfillControl = document.createElement('label');
      backfillControl.className = 'autocomplete-option';
      backfillControl.innerHTML = '<input type="checkbox" data-autocomplete-backfill>键盘回填';
      disabledControl.after(backfillControl);
      const filterControl = document.createElement('label');
      filterControl.className = 'autocomplete-option';
      filterControl.innerHTML = '<input type="checkbox" data-autocomplete-filter-option checked>本地过滤';
      backfillControl.after(filterControl);
      const sync = () => {
        const disabled = disabledControl.querySelector('input')?.checked === true;
        input.disabled = disabled;
        clear.disabled = disabled;
        clear.hidden = disabled || allowClear.querySelector('input')?.checked !== true || !input.value;
        demo.classList.toggle('is-disabled', disabled);
        demo.setAttribute('aria-disabled', String(disabled));
      };
      clear.addEventListener('click', () => { if (input.disabled) return; input.value = ''; input.dispatchEvent(new Event('input', { bubbles: true })); input.focus(); sync(); });
      input.addEventListener('input', sync);
      allowClear.querySelector('input')?.addEventListener('change', sync);
      disabledControl.querySelector('input')?.addEventListener('change', sync);
      filterControl.querySelector('input')?.addEventListener('change', () => input.dispatchEvent(new Event('input', { bubbles: true })));
      input.addEventListener('keydown', event => {
        if (!['ArrowDown', 'ArrowUp'].includes(event.key) || backfillControl.querySelector('input')?.checked !== true) return;
        requestAnimationFrame(() => {
          const active = demo.querySelector('.autocomplete-options button.active:not([hidden]) strong');
          if (active) input.value = active.textContent.trim();
        });
      });
      sync();
    });
    document.querySelectorAll('.mini-table:not(.parameter-table) th').forEach(header => {
      header.tabIndex = 0; header.setAttribute('aria-sort', 'none');
      const sort = () => { const table = header.closest('table'); const headerIndex = [...header.parentElement.children].indexOf(header); const selectionOffset = table.querySelector('thead th .table-select') ? 1 : 0; const index = headerIndex - selectionOffset; const ascending = header.getAttribute('aria-sort') !== 'ascending'; table.querySelectorAll('th').forEach(item => item.setAttribute('aria-sort', 'none')); header.setAttribute('aria-sort', ascending ? 'ascending' : 'descending'); const rows = [...table.tBodies[0].rows].sort((a, b) => { const left = a.cells[index + selectionOffset]?.textContent.trim() || ''; const right = b.cells[index + selectionOffset]?.textContent.trim() || ''; return (ascending ? 1 : -1) * left.localeCompare(right, 'zh-CN', { numeric: true }); }); rows.forEach(row => table.tBodies[0].append(row)); };
      header.addEventListener('click', sort); header.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); sort(); } });
    });
    document.querySelectorAll('.mini-table:not(.parameter-table)').forEach(table => {
      if (table.dataset.selectionBound || !table.tBodies[0]) return;
      table.dataset.selectionBound = 'true';
      const tableTitle = table.closest('.primitive-showcase')?.querySelector('.primitive-heading h3')?.textContent || '';
      if (tableTitle.startsWith('Table')) {
        const extraRows = [['知识库索引','运行中','今天 11:08'],['研究报告','已完成','今天 09:26'],['会议纪要','待处理','昨天 16:40'],['设计规范','已索引','昨天 14:12'],['模型评估','失败','周一 18:05'],['产品路线图','已索引','周一 10:21']];
        extraRows.forEach(values => { const row = table.tBodies[0].insertRow(); values.forEach(value => { const cell = row.insertCell(); cell.textContent = value; }); });
        const pager = document.createElement('div');
        pager.className = 'table-pagination';
        pager.innerHTML = '<span>每页</span><select aria-label="表格每页条数"><option value="3">3</option><option value="5">5</option><option value="10">10</option></select><span>条</span><button type="button" aria-label="表格上一页">‹</button><strong data-table-page>1</strong><button type="button" aria-label="表格下一页">›</button><small data-table-total></small>';
        table.after(pager);
        const pageSize = pager.querySelector('select'); const pageLabel = pager.querySelector('[data-table-page]'); const totalLabel = pager.querySelector('[data-table-total]');
        const renderPage = () => { const size = Number(pageSize.value); const total = table.tBodies[0].rows.length; const pages = Math.max(1, Math.ceil(total / size)); let page = Math.min(pages, Math.max(1, Number(pageLabel.textContent) || 1)); pageLabel.textContent = String(page); [...table.tBodies[0].rows].forEach((row, index) => { row.hidden = index < (page - 1) * size || index >= page * size; }); pager.querySelector('[aria-label="表格上一页"]').disabled = page === 1; pager.querySelector('[aria-label="表格下一页"]').disabled = page === pages; totalLabel.textContent = `${total} 条`; };
        pageSize.addEventListener('change', renderPage); pager.querySelector('[aria-label="表格上一页"]').addEventListener('click', () => { pageLabel.textContent = String(Math.max(1, Number(pageLabel.textContent) - 1)); renderPage(); }); pager.querySelector('[aria-label="表格下一页"]').addEventListener('click', () => { pageLabel.textContent = String(Number(pageLabel.textContent) + 1); renderPage(); }); renderPage();
      }
      const header = table.tHead?.rows[0];
      const rows = [...table.tBodies[0].rows];
      if (!header || !rows.length) return;
      const headCell = document.createElement('th');
      const headInput = document.createElement('input');
      headInput.type = 'checkbox'; headInput.className = 'table-select'; headInput.setAttribute('aria-label', '全选行');
      headCell.append(headInput); header.prepend(headCell);
      const rowInputs = rows.map((row, index) => {
        const cell = document.createElement('td');
        const input = document.createElement('input');
        input.type = 'checkbox'; input.className = 'table-select'; input.setAttribute('aria-label', `选择第 ${index + 1} 行`);
        input.addEventListener('change', () => { row.setAttribute('aria-selected', String(input.checked)); row.classList.toggle('is-selected', input.checked); headInput.checked = rowInputs.every(item => item.checked); headInput.indeterminate = rowInputs.some(item => item.checked) && !headInput.checked; });
        cell.append(input); row.prepend(cell); row.setAttribute('aria-selected', 'false'); return input;
      });
      headInput.addEventListener('change', () => { rowInputs.forEach(input => { input.checked = headInput.checked; input.dispatchEvent(new Event('change')); }); headInput.indeterminate = false; });
    });
    document.querySelectorAll('[data-badge-demo]').forEach(demo => {
      const badge = demo.querySelector('[data-badge-view]');
      const count = demo.querySelector('[data-badge-count]');
      const dot = demo.querySelector('[data-badge-dot]');
      const status = demo.querySelector('[data-badge-status]');
      const sync = () => {
        if (!badge) return;
        badge.dataset.status = status?.value || 'running';
        badge.classList.toggle('is-dot', dot?.checked === true);
        badge.textContent = dot?.checked ? '' : String(Math.max(0, Math.min(99, Number(count?.value) || 0)));
        if (count) count.value = String(Math.max(0, Math.min(99, Number(count.value) || 0)));
      };
      count?.addEventListener('input', sync); dot?.addEventListener('change', sync); status?.addEventListener('change', sync); sync();
    });
    document.querySelectorAll('.menu-demo').forEach(menu => { menu.setAttribute('role', 'menu'); const items = [...menu.querySelectorAll('button')]; items.forEach((item, index) => { item.setAttribute('role', 'menuitem'); item.tabIndex = index === 0 ? 0 : -1; item.addEventListener('click', () => { if (menu.dataset.menuSelectable === 'false') return; items.forEach(option => { option.classList.toggle('active', option === item); option.setAttribute('aria-selected', String(option === item)); }); }); item.addEventListener('keydown', event => { if (!['ArrowDown','ArrowUp','Home','End','Enter',' '].includes(event.key)) return; event.preventDefault(); if (event.key === 'Enter' || event.key === ' ') { item.click(); return; } const index = items.indexOf(item); const nextIndex = event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1 : (index + (event.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length; items.forEach((option, optionIndex) => { option.tabIndex = optionIndex === nextIndex ? 0 : -1; }); items[nextIndex].focus(); }); }); });
    document.querySelectorAll('.tooltip-trigger').forEach(trigger => {
      let timer;
      trigger.dataset.tooltipDelay = trigger.dataset.tooltipDelay || '0.1';
      const show = () => { let tip = trigger.querySelector('.nm-tooltip-content'); if (!tip) { tip = document.createElement('span'); tip.className = 'nm-tooltip-content'; tip.id = `nm-tooltip-${[...document.querySelectorAll('.tooltip-trigger')].indexOf(trigger) + 1}`; tip.setAttribute('role', 'tooltip'); tip.textContent = '这是补充说明'; trigger.append(tip); } tip.hidden = false; trigger.setAttribute('aria-describedby', tip.id); };
      const hide = () => { const tip = trigger.querySelector('.nm-tooltip-content'); if (tip) { tip.hidden = true; trigger.removeAttribute('aria-describedby'); } };
      const scheduleShow = () => { clearTimeout(timer); timer = window.setTimeout(show, Number(trigger.dataset.tooltipDelay) * 1000); };
      const triggerMode = () => control.querySelector('[data-tooltip-trigger]')?.value || 'hover';
      trigger.addEventListener('mouseenter', () => { if (triggerMode() === 'hover') scheduleShow(); }); trigger.addEventListener('focus', () => { if (triggerMode() === 'focus') show(); }); trigger.addEventListener('mouseleave', () => { if (triggerMode() === 'hover') { clearTimeout(timer); hide(); } }); trigger.addEventListener('blur', () => { if (triggerMode() === 'focus') { clearTimeout(timer); hide(); } }); trigger.addEventListener('click', event => { if (triggerMode() !== 'click') return; event.preventDefault(); const tip = trigger.querySelector('.nm-tooltip-content'); if (tip?.hidden === false) hide(); else show(); });
      const control = document.createElement('label'); control.className = 'tooltip-option'; control.innerHTML = '<span>悬停延迟</span><select aria-label="悬停延迟"><option value="0">0s</option><option value="0.1" selected>0.1s</option><option value="0.5">0.5s</option></select><span>触发方式</span><select data-tooltip-trigger aria-label="触发方式"><option value="hover" selected>悬停</option><option value="focus">聚焦</option><option value="click">点击</option></select>'; trigger.after(control); control.querySelector('select:not([data-tooltip-trigger])').addEventListener('change', event => { trigger.dataset.tooltipDelay = event.target.value; }); control.querySelector('[data-tooltip-trigger]').addEventListener('change', () => { clearTimeout(timer); hide(); });
    });
    document.querySelectorAll('.tabs-line').forEach((tablist, groupIndex) => { if (tablist.dataset.tabsBound) return; tablist.dataset.tabsBound = 'true'; tablist.setAttribute('role', 'tablist'); const panel = document.createElement('div'); panel.className = 'tabs-panel'; panel.setAttribute('role', 'tabpanel'); tablist.after(panel); const buttons = [...tablist.querySelectorAll('button')]; const sync = button => { buttons.forEach((item, index) => { const active = item === button; const id = `nm-tab-${groupIndex}-${index}`; item.classList.toggle('active', active); item.id = id; item.setAttribute('role', 'tab'); item.setAttribute('aria-selected', String(active)); item.setAttribute('aria-controls', `${id}-panel`); item.tabIndex = active ? 0 : -1; }); const activeIndex = Math.max(0, buttons.indexOf(button)); panel.id = `nm-tab-${groupIndex}-${activeIndex}-panel`; panel.textContent = `${buttons[activeIndex]?.textContent.trim() || ''}：这里展示对应的同级内容。`; }; sync(buttons.find(button => button.classList.contains('active')) || buttons[0]); buttons.forEach(button => { button.addEventListener('click', () => sync(button)); button.addEventListener('keydown', event => { if (!['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) return; event.preventDefault(); const index = buttons.indexOf(button); const next = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + buttons.length) % buttons.length; buttons[next].click(); buttons[next].focus(); }); }); });
    document.querySelectorAll('.tabs-line').forEach(tablist => {
      if (tablist.dataset.tabsOptionsBound) return;
      tablist.dataset.tabsOptionsBound = 'true';
      const options = document.createElement('div');
      options.className = 'tabs-options';
      options.innerHTML = '<label>类型 <select data-tabs-type aria-label="标签页类型"><option value="line">线型</option><option value="card">卡片</option><option value="editable-card">可编辑卡片</option></select></label><label><input type="checkbox" data-tabs-centered>居中</label><label><input type="checkbox" data-tabs-destroy>隐藏时销毁内容</label>';
      const panel = tablist.nextElementSibling?.classList.contains('tabs-panel') ? tablist.nextElementSibling : null;
      panel?.after(options);
      const sync = () => { tablist.dataset.tabsType = options.querySelector('[data-tabs-type]')?.value || 'line'; tablist.classList.toggle('is-centered', options.querySelector('[data-tabs-centered]')?.checked === true); if (panel) panel.dataset.lifecycle = options.querySelector('[data-tabs-destroy]')?.checked ? 'mounted-on-demand' : 'persistent'; };
      options.querySelectorAll('input, select').forEach(control => control.addEventListener('change', sync));
      sync();
    });
    document.querySelectorAll('.alert').forEach(alert => { alert.setAttribute('role', 'alert'); if (alert.dataset.closable !== 'true' || alert.querySelector('[data-alert-close]')) return; const close = document.createElement('button'); close.type = 'button'; close.dataset.alertClose = ''; close.setAttribute('aria-label', '关闭提示'); close.textContent = '×'; close.addEventListener('click', () => { alert.hidden = true; }); alert.append(close); });
    document.querySelectorAll('.primitive-showcase').forEach(showcase => {
      const alert = showcase.querySelector('.alert');
      if (!alert || showcase.dataset.alertOptionsBound) return;
      showcase.dataset.alertOptionsBound = 'true';
      const controls = document.createElement('div');
      controls.className = 'alert-options';
      controls.innerHTML = '<label>类型 <select data-alert-type aria-label="提示类型"><option value="info">info</option><option value="success">success</option><option value="warning" selected>warning</option><option value="error">error</option></select></label><label><input type="checkbox" data-alert-show-icon checked>显示图标</label><label><input type="checkbox" data-alert-closable checked>允许关闭</label><button type="button" class="nm-button" data-alert-reset>恢复提示</button>';
      alert.after(controls);
      const icon = alert.querySelector('.alert-icon'); const close = alert.querySelector('[data-alert-close]'); const type = controls.querySelector('[data-alert-type]');
      const sync = () => { const showIcon = controls.querySelector('[data-alert-show-icon]').checked; const closable = controls.querySelector('[data-alert-closable]').checked; const nextType = type?.value || 'warning'; alert.classList.remove('info', 'success', 'warning', 'danger'); alert.classList.add(nextType === 'error' ? 'danger' : nextType); if (icon) { icon.hidden = !showIcon; icon.textContent = nextType === 'success' ? '✓' : nextType === 'error' ? '!' : nextType === 'warning' ? '!' : 'i'; } alert.dataset.closable = String(closable); if (close) close.hidden = !closable; };
      controls.querySelectorAll('input, select').forEach(input => input.addEventListener('change', sync));
      controls.querySelector('[data-alert-reset]').addEventListener('click', () => { alert.hidden = false; controls.hidden = false; sync(); });
      close?.addEventListener('click', () => { alert.hidden = true; controls.hidden = true; });
      sync();
    });
    document.querySelectorAll('.primitive-showcase').forEach(showcase => {
      const progress = showcase.querySelector('.progress-demo');
      if (!progress || showcase.dataset.progressOptionsBound) return;
      showcase.dataset.progressOptionsBound = 'true';
      const controls = document.createElement('div');
      controls.className = 'progress-options';
      controls.innerHTML = '<label>进度 <input type="range" min="0" max="100" value="68" data-progress-percent></label><label>状态 <select data-progress-status><option value="normal">normal</option><option value="active">active</option><option value="success">success</option><option value="exception">exception</option></select></label>';
      progress.after(controls);
      const percent = controls.querySelector('[data-progress-percent]'); const status = controls.querySelector('[data-progress-status]'); const value = progress.querySelector('strong'); const bar = progress.querySelector('.progress-track i');
      const sync = () => { const next = Math.max(0, Math.min(100, Number(percent.value) || 0)); percent.value = String(next); if (value) value.textContent = `${next}%`; if (bar) { bar.style.width = `${next}%`; bar.dataset.status = status.value; } progress.dataset.status = status.value; };
      percent.addEventListener('input', sync); status.addEventListener('change', sync); sync();
    });
    document.querySelectorAll('.primitive-showcase').forEach(showcase => {
      const empty = showcase.querySelector('.empty-visual');
      if (!empty || showcase.dataset.emptyOptionsBound) return;
      showcase.dataset.emptyOptionsBound = 'true';
      const options = document.createElement('div');
      options.className = 'empty-options';
      options.innerHTML = '<label>插图 <select data-empty-image aria-label="空状态插图"><option value="default">Default</option><option value="simple">Simple</option><option value="none">无插图</option></select></label><label>描述 <select data-empty-description aria-label="空状态描述"><option value="context">语境说明</option><option value="short">暂无数据</option><option value="custom">自定义</option></select></label><input type="text" data-empty-custom placeholder="自定义描述" aria-label="自定义空状态描述" hidden><label><input type="checkbox" data-empty-action checked>显示操作</label>';
      empty.closest('.state-card')?.after(options);
      const illustration = empty.querySelector('.empty-illustration');
      const description = empty.querySelector('p');
      const action = empty.querySelector('button');
      const image = options.querySelector('[data-empty-image]');
      const descriptionMode = options.querySelector('[data-empty-description]');
      const custom = options.querySelector('[data-empty-custom]');
      const sync = () => {
        const imageMode = image.value;
        if (illustration) illustration.hidden = imageMode === 'none';
        empty.dataset.image = imageMode;
        const mode = descriptionMode.value;
        custom.hidden = mode !== 'custom';
        if (description) description.textContent = mode === 'short' ? '暂无数据' : mode === 'custom' ? (custom.value.trim() || '请输入描述') : '选择 Workspace 后，NoteMeld 会把文件整理成可验证的知识。';
        if (action) action.hidden = !options.querySelector('[data-empty-action]').checked;
      };
      options.querySelectorAll('select, input').forEach(control => control.addEventListener('input', sync));
      options.querySelectorAll('select, input').forEach(control => control.addEventListener('change', sync));
      sync();
    });
    document.querySelectorAll('.primitive-showcase').forEach(showcase => {
      const spin = showcase.querySelector('[data-spin-demo]');
      if (!spin || showcase.dataset.spinOptionsBound) return;
      showcase.dataset.spinOptionsBound = 'true';
      const options = document.createElement('div');
      options.className = 'spin-options';
      options.innerHTML = '<label><input type="checkbox" data-spin-spinning checked>加载中</label><label>尺寸 <select data-spin-size aria-label="加载器尺寸"><option value="default">default</option><option value="small">small</option><option value="large">large</option></select></label><label>延迟 <select data-spin-delay aria-label="加载延迟"><option value="0">立即</option><option value="300">300ms</option><option value="800">800ms</option></select></label><label>提示 <select data-spin-tip-value aria-label="加载提示"><option value="读取 Workspace 中的来源与结构…">读取来源</option><option value="正在同步多端状态…">同步状态</option><option value="">无提示</option></select></label>';
      spin.after(options);
      const indicator = spin.querySelector('[data-spin-indicator]');
      const tip = spin.querySelector('[data-spin-tip]');
      let timer;
      const sync = () => {
        window.clearTimeout(timer);
        const enabled = options.querySelector('[data-spin-spinning]').checked;
        const delay = Number(options.querySelector('[data-spin-delay]').value) || 0;
        const size = options.querySelector('[data-spin-size]').value;
        spin.dataset.size = size;
        if (tip) tip.textContent = options.querySelector('[data-spin-tip-value]').value;
        if (enabled && delay) {
          spin.classList.add('is-pending');
          timer = window.setTimeout(() => spin.classList.remove('is-pending'), delay);
        } else spin.classList.toggle('is-pending', enabled === false);
        if (indicator) { indicator.setAttribute('aria-busy', String(enabled)); indicator.setAttribute('aria-label', enabled ? '加载中' : '已完成'); }
      };
      options.querySelectorAll('select, input').forEach(control => control.addEventListener('input', sync));
      options.querySelectorAll('select, input').forEach(control => control.addEventListener('change', sync));
      sync();
    });
    document.querySelectorAll('.empty-visual button, .result-demo button').forEach(button => { if (!button.dataset.nmToast) { button.dataset.nmToast = button.textContent.trim() + '：参考交互已触发'; button.addEventListener('click', () => window.NoteMeldDesignSystem?.notify(button.dataset.nmToast)); } });
    document.querySelectorAll('.primitive-showcase').forEach(showcase => {
      const result = showcase.querySelector('.result-demo');
      if (!result || showcase.dataset.resultOptionsBound) return;
      showcase.dataset.resultOptionsBound = 'true';
      const options = document.createElement('label');
      options.className = 'result-options';
      options.innerHTML = '状态 <select aria-label="结果状态"><option value="success">success</option><option value="error">error</option><option value="info">info</option><option value="warning">warning</option><option value="404">404</option><option value="403">403</option><option value="500">500</option></select>';
      result.after(options);
      const select = options.querySelector('select'); const icon = result.querySelector('b'); const title = result.querySelector('strong');
      const labels = {success:'索引完成', error:'索引失败', info:'正在处理', warning:'需要确认', 404:'找不到资源', 403:'无权访问', 500:'服务异常'};
      const sync = () => { const status = select.value; result.dataset.status = status; if (icon) icon.textContent = status === 'success' ? '✓' : status === 'error' || status === '500' ? '!' : status === 'warning' ? '!' : status === '403' ? '×' : status === '404' ? '?' : '…'; if (title) title.textContent = labels[status]; };
      select.addEventListener('change', sync); sync();
    });
    document.querySelectorAll('.primitive-showcase').forEach(showcase => {
      const popover = showcase.querySelector('.standalone-popover:not(.menu-reference)');
      if (!popover || showcase.dataset.popoverOptionsBound) return;
      showcase.dataset.popoverOptionsBound = 'true';
      const options = document.createElement('div');
      options.className = 'popover-options';
      options.innerHTML = '<label>触发 <select data-popover-trigger aria-label="气泡触发方式"><option value="click">点击</option><option value="hover">悬停</option><option value="focus">聚焦</option></select></label><label>位置 <select data-popover-placement aria-label="气泡位置"><option value="bottom">下方</option><option value="top">上方</option><option value="left">左侧</option><option value="right">右侧</option></select></label>';
      popover.after(options);
    });
    document.querySelectorAll('[data-tag-demo] .tag-close').forEach(button => button.remove());
    document.querySelectorAll('[data-tag-demo]').forEach(group => group.querySelectorAll('.tag-demo').forEach(tag => { const close = tag.querySelector('.tag-closable span'); const remove = event => { event.preventDefault(); event.stopPropagation(); tag.remove(); }; close?.setAttribute('role', 'button'); close?.setAttribute('tabindex', '0'); close?.setAttribute('aria-label', '关闭标签'); close?.addEventListener('click', remove); close?.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') remove(event); }); tag.addEventListener('click', event => { if (event.target.closest('.tag-closable span')) return; tag.classList.toggle('is-checked'); tag.setAttribute('aria-pressed', String(tag.classList.contains('is-checked'))); }); tag.setAttribute('aria-pressed', String(tag.classList.contains('is-checked'))); }));
    document.querySelectorAll('[data-modal-demo], [data-drawer-demo]').forEach(demo => {
      const panel = demo.querySelector('[role="dialog"]'); const generatedTrigger = panel?.previousElementSibling; if (generatedTrigger?.matches('button') && !generatedTrigger.hasAttribute('data-modal-open') && !generatedTrigger.hasAttribute('data-drawer-open')) generatedTrigger.remove(); const open = demo.querySelector('[data-modal-open], [data-drawer-open]'); const closeButtons = [...demo.querySelectorAll('[data-modal-close], [data-drawer-close]')];
      if (demo.matches('[data-modal-demo]') && !demo.dataset.modalOptionsBound) {
        demo.dataset.modalOptionsBound = 'true';
        const options = document.createElement('div');
        options.className = 'modal-options';
        options.innerHTML = '<label><input type="checkbox" data-modal-centered checked>居中显示</label><label><input type="checkbox" data-modal-mask-closable checked>点击遮罩关闭</label><label><input type="checkbox" data-modal-keyboard checked>Escape 关闭</label>';
        demo.append(options);
        options.querySelector('input').addEventListener('change', event => { demo.dataset.modalCentered = String(event.target.checked); });
        demo.dataset.modalCentered = 'true';
      }
      if (demo.matches('[data-drawer-demo]') && !demo.dataset.drawerOptionsBound) {
        demo.dataset.drawerOptionsBound = 'true';
        const options = document.createElement('div');
        options.className = 'drawer-options';
        options.innerHTML = '<label>位置 <select data-drawer-placement aria-label="抽屉位置"><option value="right">右侧</option><option value="left">左侧</option><option value="top">顶部</option><option value="bottom">底部</option></select></label><label>宽度 <select data-drawer-width aria-label="抽屉宽度"><option value="240">240px</option><option value="320" selected>320px</option><option value="480">480px</option></select></label><label><input type="checkbox" data-drawer-mask-closable checked>点击遮罩关闭</label><label><input type="checkbox" data-drawer-keyboard checked>Escape 关闭</label>';
        demo.append(options);
        const syncDrawer = () => { demo.dataset.drawerPlacement = options.querySelector('[data-drawer-placement]').value; demo.dataset.drawerWidth = options.querySelector('[data-drawer-width]').value; };
        options.querySelectorAll('select').forEach(control => control.addEventListener('change', syncDrawer));
        syncDrawer();
      }
      let backdrop;
      const focusables = () => [...panel.querySelectorAll('button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])')].filter(item => !item.hidden && item.offsetParent !== null);
      const setOpen = value => { if (!panel) return; if (value && !backdrop) { backdrop = document.createElement('div'); backdrop.className = 'nm-modal-backdrop'; backdrop.addEventListener('click', () => { const closable = demo.matches('[data-modal-demo]') ? demo.querySelector('[data-modal-mask-closable]') : demo.querySelector('[data-drawer-mask-closable]'); if (closable?.checked !== false) setOpen(false); }); demo.parentElement?.append(backdrop); } if (!value) { backdrop?.remove(); backdrop = undefined; } panel.hidden = !value; demo.classList.toggle('is-open', value); if (value) (focusables()[0] || closeButtons[0])?.focus(); else open?.focus(); };
      open?.addEventListener('click', () => setOpen(true)); closeButtons.forEach(button => button.addEventListener('click', () => setOpen(false)));
      demo.addEventListener('keydown', event => { if (panel.hidden) return; if (event.key === 'Escape') { const keyboard = demo.matches('[data-modal-demo]') ? demo.querySelector('[data-modal-keyboard]') : demo.querySelector('[data-drawer-keyboard]'); if (keyboard?.checked === false) return; event.preventDefault(); setOpen(false); return; } if (event.key !== 'Tab') return; const items = focusables(); if (!items.length) return; const current = items.indexOf(document.activeElement); const next = event.shiftKey ? (current <= 0 ? items.length - 1 : current - 1) : (current === items.length - 1 ? 0 : current + 1); event.preventDefault(); items[next].focus(); });
    });
    document.querySelectorAll('[data-upload-demo]').forEach(demo => {
      const input = demo.querySelector('[data-upload-input]'); const list = demo.querySelector('[data-upload-list]');
      const render = files => { list.innerHTML = [...files].map((file, index) => `<div class="upload-item"><span class="file-glyph">${file.name.split('.').pop()?.toUpperCase() || 'FILE'}</span><div><strong>${file.name}</strong><small>${Math.ceil(file.size / 1024)} KB · 等待上传</small></div><button type="button" class="nm-icon-button" aria-label="移除文件" data-upload-remove="${index}"><span class="nm-icon nm-icon-close" aria-hidden="true"></span></button></div>`).join(''); list.querySelectorAll('[data-upload-remove]').forEach(button => button.addEventListener('click', () => { const next = [...files]; next.splice(Number(button.dataset.uploadRemove), 1); render(next); })); };
      input?.addEventListener('change', () => render(input.files || []));
      demo.addEventListener('dragover', event => { event.preventDefault(); demo.classList.add('is-dragover'); });
      demo.addEventListener('dragleave', () => demo.classList.remove('is-dragover'));
      demo.addEventListener('drop', event => { event.preventDefault(); demo.classList.remove('is-dragover'); render(event.dataTransfer?.files || []); });
    });
    document.querySelectorAll('[data-upload-demo]').forEach(demo => {
      if (demo.dataset.uploadContractBound) return;
      demo.dataset.uploadContractBound = 'true';
      const input = demo.querySelector('[data-upload-input]'); const list = demo.querySelector('[data-upload-list]');
      const limit = document.createElement('label'); limit.className = 'upload-limit'; limit.innerHTML = '最多 <select aria-label="最大文件数"><option value="1">1</option><option value="3" selected>3</option><option value="10">10</option></select> 个'; demo.append(limit);
      const config = document.createElement('div'); config.className = 'upload-options'; config.innerHTML = '<label>类型 <select class="nm-select-control" data-upload-accept aria-label="允许的文件类型"><option value="documents">Markdown / PDF / 图片 / 音频</option><option value="markdown">仅 Markdown</option><option value="image">仅图片</option><option value="audio">仅音频</option></select></label><label class="nm-check-control"><input type="checkbox" data-upload-multiple checked><span></span>允许多选</label>'; demo.append(config);
      const acceptPicker = config.querySelector('[data-upload-accept]'); const multiplePicker = config.querySelector('[data-upload-multiple]');
      const render = files => {
        const max = multiplePicker.checked ? Number(limit.querySelector('select').value) : 1; const accepts = file => acceptPicker.value === 'markdown' ? /\.md$/i.test(file.name) : acceptPicker.value === 'image' ? file.type.startsWith('image/') : acceptPicker.value === 'audio' ? file.type.startsWith('audio/') : /(?:\.md|\.pdf)$/i.test(file.name) || file.type.startsWith('image/') || file.type.startsWith('audio/'); const accepted = [...files].filter(accepts); const rejected = [...files].filter(file => !accepted.includes(file)); const shown = accepted.slice(0, max);
        list.replaceChildren(...shown.map((file, index) => { const item = document.createElement('div'); item.className = 'upload-item'; const preview = file.type.startsWith('image/') ? `<img class="upload-thumb" alt="" src="${URL.createObjectURL(file)}">` : `<span class="file-glyph">${file.name.split('.').pop()?.toUpperCase() || 'FILE'}</span>`; item.innerHTML = `${preview}<div><strong></strong><small>${Math.ceil(file.size / 1024)} KB · 等待上传</small></div><button type="button" class="nm-icon-button" aria-label="移除文件"><span class="nm-icon nm-icon-close" aria-hidden="true"></span></button>`; item.querySelector('strong').textContent = file.name; item.querySelector('button').addEventListener('click', () => { const next = shown.filter((_, itemIndex) => itemIndex !== index); render(next); }); return item; }));
        if (rejected.length || accepted.length > max) { const note = document.createElement('small'); note.className = 'upload-validation'; note.textContent = rejected.length ? '已忽略不支持的文件类型。' : `最多保留 ${max} 个文件。`; list.append(note); }
      };
      input?.addEventListener('change', () => render(input.files || [])); limit.querySelector('select').addEventListener('change', () => render(input?.files || [])); acceptPicker.addEventListener('change', () => { input.accept = acceptPicker.value === 'markdown' ? '.md' : acceptPicker.value === 'image' ? 'image/*' : acceptPicker.value === 'audio' ? 'audio/*' : '.md,.pdf,image/*,audio/*'; render(input?.files || []); }); multiplePicker.addEventListener('change', () => { input.multiple = multiplePicker.checked; limit.querySelector('select').disabled = !multiplePicker.checked; render(input?.files || []); });
      demo.addEventListener('drop', event => { event.preventDefault(); render(event.dataTransfer?.files || []); });
    });
    document.querySelectorAll('.upload-item [aria-label="取消上传"], .upload-item [aria-label="移除文件"]').forEach(button => button.addEventListener('click', () => button.closest('.upload-item')?.remove()));
    document.querySelectorAll('.transfer-demo').forEach(demo => {
      if (demo.dataset.transferBound) return;
      demo.dataset.transferBound = 'true';
      const panes = [...demo.querySelectorAll(':scope > div')].filter(pane => pane.querySelector('span'));
      const controls = panes.map(pane => {
        const search = pane.querySelector('input[type="search"]');
        const items = [...pane.querySelectorAll(':scope > span')].map(item => { const button = document.createElement('button'); button.type = 'button'; button.className = 'transfer-item'; button.textContent = item.textContent.trim(); button.setAttribute('role', 'option'); button.setAttribute('aria-selected', 'false'); item.replaceWith(button); return button; });
        items.forEach(item => { item.addEventListener('click', () => { item.classList.toggle('selected'); item.setAttribute('aria-selected', String(item.classList.contains('selected'))); updateCounts(); }); });
        search?.addEventListener('input', () => { const query = search.value.trim().toLocaleLowerCase(); items.forEach(item => { item.hidden = !item.textContent.toLocaleLowerCase().includes(query); }); });
        return items;
      });
      const transferButtons = demo.querySelector('b, .transfer-actions');
      if (transferButtons && controls.length === 2) {
        transferButtons.replaceChildren();
        [['right', '→', '移至右侧'], ['left', '←', '移至左侧']].forEach(([direction, label, ariaLabel]) => { const button = document.createElement('button'); button.type = 'button'; button.dataset.transferMove = direction; button.textContent = label; button.setAttribute('aria-label', ariaLabel); transferButtons.append(button); button.addEventListener('click', () => { const from = direction === 'right' ? controls[0] : controls[1]; const to = direction === 'right' ? controls[1] : controls[0]; const targetPane = direction === 'right' ? panes[1] : panes[0]; from.filter(item => item.classList.contains('selected')).forEach(item => { const index = from.indexOf(item); if (index >= 0) from.splice(index, 1); item.classList.remove('selected'); item.setAttribute('aria-selected', 'false'); to.push(item); targetPane.append(item); }); updateCounts(); }); });
      }
      const updateCounts = () => panes.forEach(pane => { const output = pane.querySelector('[data-transfer-count]'); if (output) output.textContent = `${pane.querySelectorAll('.transfer-item').length} 项`; });
      updateCounts();
    });
    document.querySelectorAll('[data-number-demo]').forEach(demo => {
      const input = demo.querySelector('input');
      if (!input || demo.dataset.numberControlsBound) return;
      demo.dataset.numberControlsBound = 'true';
      const controls = document.createElement('div');
      controls.className = 'number-options';
      controls.innerHTML = '<label><input type="checkbox" data-number-show-controls checked>显示加减按钮</label><label>步长 <select data-number-step aria-label="步长"><option value="1" selected>1</option><option value="0.1">0.1</option><option value="0.5">0.5</option><option value="2">2</option></select></label><label>精度 <select data-number-precision aria-label="精度"><option value="auto" selected>自动</option><option value="0">0</option><option value="1">1</option><option value="2">2</option></select></label><label><input type="checkbox" data-number-disabled>禁用</label>';
      demo.after(controls);
      const min = Number(input.min ?? 0); const max = Number(input.max ?? 999); const stepFor = () => Number(controls.querySelector('[data-number-step]')?.value || input.step || 1); const precisionFor = () => controls.querySelector('[data-number-precision]')?.value || 'auto';
      const buttons = { decrease: demo.querySelector('[data-number-action="decrease"]'), increase: demo.querySelector('[data-number-action="increase"]') };
      const sync = () => { const value = Number(input.value); const disabled = controls.querySelector('[data-number-disabled]')?.checked === true; const showControls = controls.querySelector('[data-number-show-controls]')?.checked !== false; const step = stepFor(); input.step = String(step); input.dataset.numberPrecision = precisionFor(); demo.classList.toggle('is-disabled', disabled); input.disabled = disabled; Object.values(buttons).forEach(button => { if (button) { button.hidden = !showControls; button.disabled = disabled || (button === buttons.decrease ? value <= min : value >= max); } }); };
      const adjust = delta => { if (input.disabled) return; const step = stepFor(); const value = Math.min(max, Math.max(min, (Number(input.value) || min) + delta * step)); const precision = precisionFor() === 'auto' ? Math.max(0, String(step).split('.')[1]?.length || 0) : Number(precisionFor()); input.value = precision ? value.toFixed(precision) : String(value); input.dispatchEvent(new Event('input', { bubbles: true })); input.dispatchEvent(new Event('change', { bubbles: true })); sync(); };
      buttons.decrease?.addEventListener('click', () => adjust(-1)); buttons.increase?.addEventListener('click', () => adjust(1));
      input.addEventListener('keydown', event => { if (event.key === 'ArrowUp' || event.key === 'ArrowDown') { event.preventDefault(); adjust(event.key === 'ArrowUp' ? 1 : -1); } });
      input.addEventListener('input', sync); controls.querySelectorAll('input, select').forEach(control => control.addEventListener('change', sync)); sync();
    });
    document.querySelectorAll('[data-number-demo]').forEach(demo => {
      if (demo.dataset.numberAriaBound) return;
      demo.dataset.numberAriaBound = 'true';
      const input = demo.querySelector('input');
      if (!input) return;
      input.setAttribute('role', 'spinbutton');
      input.setAttribute('aria-valuemin', input.min || '0');
      input.setAttribute('aria-valuemax', input.max || '999');
      const decrease = demo.querySelector('[data-number-action="decrease"]');
      const increase = demo.querySelector('[data-number-action="increase"]');
      const sync = () => {
        if (input.value !== '') input.setAttribute('aria-valuenow', input.value);
        else input.removeAttribute('aria-valuenow');
        if (decrease) decrease.setAttribute('aria-disabled', String(decrease.disabled));
        if (increase) increase.setAttribute('aria-disabled', String(increase.disabled));
      };
      input.addEventListener('input', sync);
      input.addEventListener('change', sync);
      sync();
    });
    document.querySelectorAll('.pagination').forEach(pagination => { pagination.setAttribute('role', 'navigation'); pagination.setAttribute('aria-label', '分页'); const pageButtons = [...pagination.querySelectorAll('button:not([aria-label])')]; const previous = pagination.querySelector('button[aria-label="上一页"]'); const next = pagination.querySelector('button[aria-label="下一页"]'); const sync = index => { const current = Math.max(0, Math.min(pageButtons.length - 1, index)); pageButtons.forEach((button, buttonIndex) => { const active = buttonIndex === current; button.classList.toggle('active', active); if (active) button.setAttribute('aria-current', 'page'); else button.removeAttribute('aria-current'); }); if (previous) previous.disabled = current === 0; if (next) next.disabled = current === pageButtons.length - 1; return current; }; let current = Math.max(0, pageButtons.findIndex(button => button.classList.contains('active'))); pageButtons.forEach((button, index) => { button.addEventListener('click', () => { current = sync(index); }); button.addEventListener('keydown', event => { if (!['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) return; event.preventDefault(); current = sync(event.key === 'Home' ? 0 : event.key === 'End' ? pageButtons.length - 1 : index + (event.key === 'ArrowRight' ? 1 : -1)); pageButtons[current]?.focus(); }); }); previous?.addEventListener('click', () => { current = sync(current - 1); pageButtons[current]?.focus(); }); next?.addEventListener('click', () => { current = sync(current + 1); pageButtons[current]?.focus(); }); sync(current); });
    document.querySelectorAll('[data-pagination-demo] .pagination-jumper input, .pagination-jumper input').forEach(input => {
      const demo = input.closest('[data-pagination-demo]');
      const pagination = demo?.querySelector('.pagination');
      if (!pagination) return;
      const pages = [...pagination.querySelectorAll('button:not([aria-label])')];
      const jump = () => { const page = Math.max(1, Math.min(pages.length, Number(input.value) || 1)); input.value = String(page); pages[page - 1]?.click(); };
      input.addEventListener('change', jump);
      input.addEventListener('keydown', event => { if (event.key === 'Enter') { event.preventDefault(); jump(); } });
    });
    document.querySelectorAll('[data-pagination-demo]').forEach(demo => {
      const pagination = demo.querySelector('.pagination');
      const size = demo.querySelector('.pagination-size select');
      const jumper = demo.querySelector('.pagination-jumper input');
      const info = demo.querySelector('[data-pagination-info]');
      const options = document.createElement('div');
      options.className = 'pagination-options';
      options.innerHTML = '<label><input type="checkbox" data-pagination-size-changer checked>显示页大小</label><label><input type="checkbox" data-pagination-quick-jumper checked>快速跳页</label>';
      demo.append(options);
      const sync = () => {
        const current = [...(pagination?.querySelectorAll('button:not([aria-label])') || [])].findIndex(button => button.classList.contains('active')) + 1;
        const showSize = options.querySelector('[data-pagination-size-changer]')?.checked === true;
        const showJumper = options.querySelector('[data-pagination-quick-jumper]')?.checked === true;
        const sizeField = demo.querySelector('.pagination-size');
        const jumperField = demo.querySelector('.pagination-jumper');
        if (sizeField) sizeField.hidden = !showSize;
        if (jumperField) jumperField.hidden = !showJumper;
        if (info) info.textContent = `第 ${Math.max(1, current)} 页 · 每页 ${size?.value || 10} 条`;
      };
      pagination?.querySelectorAll('button').forEach(button => button.addEventListener('click', () => requestAnimationFrame(sync)));
      size?.addEventListener('change', sync);
      jumper?.addEventListener('change', sync);
      options.querySelectorAll('input').forEach(control => control.addEventListener('change', sync));
      sync();
    });
    document.querySelectorAll('[data-number-demo] input').forEach(input => input.addEventListener('input', () => { const raw = input.value.replace(/[^0-9.-]/g, ''); const negative = raw.startsWith('-'); const unsigned = raw.replace(/-/g, ''); const [integer = '', ...decimals] = unsigned.split('.'); input.value = `${negative ? '-' : ''}${integer}${decimals.length ? `.${decimals.join('')}` : ''}`; }));
    document.querySelectorAll('[data-number-demo] input').forEach(input => { const min = Number(input.min || 0); const max = Number(input.max || 999); const normalize = () => { if (input.value.trim() === '') return; const step = Number(input.step || 1); const configuredPrecision = input.dataset.numberPrecision; const decimals = configuredPrecision && configuredPrecision !== 'auto' ? Number(configuredPrecision) : Math.max(0, String(step).split('.')[1]?.length || 0); let value = Number(input.value); if (!Number.isFinite(value)) { input.value = ''; return; } value = Math.min(max, Math.max(min, value)); if (step > 0) value = min + Math.round((value - min) / step) * step; input.value = decimals ? value.toFixed(decimals) : String(value); input.dispatchEvent(new Event('input', { bubbles: true })); }; input.addEventListener('change', normalize); input.addEventListener('blur', normalize); });
  };
  parameterSets.Switch.push(['checkedChildren', 'string | icon', '—', '开启时显示的文字或图标'], ['unCheckedChildren', 'string | icon', '—', '关闭时显示的文字或图标']);
  // Demo-only presentation: retain each control's owning root and event handlers.
  const arrangeExamples = () => {
    const gallery = content.querySelector('.icon-grid');
    if (gallery) {
      gallery.innerHTML = [['search','搜索'],['plus','添加'],['minus','减少'],['x','关闭'],['check','完成'],['ellipsis','更多'],['chevron-down','向下'],['chevron-right','向右'],['arrow-left','返回'],['arrow-up-right','跳转'],['file-text','文档'],['folder','文件夹'],['calendar','日期'],['clock','时间'],['upload','上传'],['download','下载'],['copy','复制'],['trash-2','删除'],['settings','设置'],['user','用户'],['bell','通知'],['circle-help','帮助'],['circle-alert','警告'],['refresh-cw','刷新']].map(([name,label]) => `<button class="icon-example" type="button" aria-label="${label}"><i data-lucide="${name}"></i><strong>${label}</strong><small>${name} · 16 / 20 / 24</small></button>`).join('');
      window.lucide?.createIcons({ attrs: { 'stroke-width': 2, 'aria-hidden': 'true' } });
      gallery.querySelectorAll('button').forEach(button => button.addEventListener('click', () => window.NoteMeldDesignSystem?.notify(button.querySelector('small').textContent)));
      const rhythm = content.querySelector('.icon-rhythm');
      if (rhythm) rhythm.innerHTML = '<strong>图标规范 · PC端 / 移动端共用</strong><span>24 × 24 基准网格，2px 圆端描边，currentColor。</span><span>控件内 16px，常规操作 20px，独立入口 24px；移动端扩大点击区域至 44px，不放大图形比例。</span><span>参考 Ant Design 的语义分类，复用产品已有 Lucide 图形，避免混用不同线宽和图标字体。</span>';
    }
    content.querySelectorAll('.platform-pair > section').forEach(sample => sample.classList.add('platform-sample'));
    content.querySelectorAll('.select-reference').forEach(demo => {
      demo.classList.add('platform-sample');
      demo.querySelector('.select-mode-label').textContent = demo.classList.contains('mobile') ? '移动端' : 'PC端';
      demo.querySelector('.select-caption')?.remove();
      queueMicrotask(() => {
        const controls = document.createElement('div');
        controls.className = 'demo-controls';
        demo.querySelectorAll(':scope > .select-mode-toggle').forEach(node => controls.append(node));
        demo.append(controls);
      });
    });
    content.querySelectorAll('[data-date-demo]').forEach(demo => {
      const controls = document.createElement('div');
      controls.className = 'demo-controls';
      controls.setAttribute('aria-label', '日期示例配置');
      const popover = demo.querySelector('.date-popover');
      [...popover.children].filter(node => node.matches('label, .date-option, .date-presets')).forEach(node => controls.append(node));
      demo.append(controls);
      popover.querySelector('[data-date-clear]')?.setAttribute('hidden', '');
      if (demo.classList.contains('mobile')) {
        const confirm = demo.querySelector('[data-date-need-confirm]');
        confirm.checked = true;
        confirm.dispatchEvent(new Event('change', { bubbles: true }));
      }
    });
    content.querySelectorAll('[data-upload-demo]').forEach(demo => {
      const controls = document.createElement('div');
      controls.className = 'demo-controls';
      [...demo.children].filter(node => node.matches('.upload-limit, .upload-options')).forEach(node => controls.append(node));
      const stage = document.createElement('div');
      stage.className = 'upload-dropzone';
      [...demo.children].forEach(node => stage.append(node));
      demo.classList.remove('upload-dropzone');
      demo.append(stage, controls);
    });
    content.querySelectorAll('.autocomplete-demo').forEach(demo => {
      const input = demo.querySelector('input');
      const list = demo.querySelector('.autocomplete-options');
      if (!input || !list) return;
      list.addEventListener('pointerdown', event => event.preventDefault());
      list.addEventListener('click', event => {
        const option = event.target.closest('button');
        if (!option || option.disabled) return;
        const label = option.querySelector('strong')?.textContent.trim() || option.textContent.trim();
        input.value = demo.querySelector('.search-prefix')?.textContent.trim() === '@' ? `@${label} ` : label;
        input.focus();
        input.dispatchEvent(new Event('input', { bubbles: true }));
        input.dispatchEvent(new Event('change', { bubbles: true }));
        demo.classList.remove('is-open');
        demo.setAttribute('aria-expanded', 'false');
      });
    });
    content.querySelectorAll('[data-slider-demo]').forEach(demo => {
      const start = demo.querySelector('[data-slider-start]');
      const end = demo.querySelector('[data-slider-end]');
      const track = document.createElement('div');
      track.className = 'range-track';
      demo.prepend(track);
      track.append(start, end);
      const sample = demo.closest('.platform-sample');
      sample?.querySelector('.slider-labels')?.remove();
      const rangeOption = sample?.querySelector('.slider-option');
      if (rangeOption) demo.after(rangeOption);
      const sync = event => {
        if (!end.hidden && Number(start.value) > Number(end.value)) {
          if (event?.target === end) start.value = end.value;
          else end.value = start.value;
        }
        const min = Number(start.min), max = Number(start.max);
        const percent = value => (Number(value) - min) / (max - min) * 100;
        track.style.setProperty('--range-start', `${end.hidden ? 0 : percent(start.value)}%`);
        track.style.setProperty('--range-end', `${percent(end.hidden ? start.value : end.value)}%`);
        demo.querySelector('output').textContent = end.hidden ? start.value : `${start.value} – ${end.value}`;
      };
      demo.addEventListener('input', sync);
      demo.closest('.platform-sample')?.addEventListener('change', sync);
      sync();
    });
    content.querySelectorAll('[data-switch-demo]').forEach(button => {
      const options = button.nextElementSibling;
      const label = document.createElement('label');
      label.innerHTML = '内容 <select aria-label="开关内容"><option value="text">文字</option><option value="icon">图标</option><option value="none">无</option></select>';
      options.append(label);
      const track = button.querySelector('span');
      const mark = document.createElement('i');
      mark.className = 'switch-content';
      track.append(mark);
      const sync = () => {
        const on = button.getAttribute('aria-checked') === 'true';
        const mode = label.querySelector('select').value;
        mark.innerHTML = mode === 'icon' ? icon(on ? 'check' : 'close') : mode === 'text' ? (on ? '开' : '关') : '';
      };
      button.addEventListener('click', sync);
      label.addEventListener('change', sync);
      sync();
    });
    content.querySelectorAll('[data-tree-toggle]').forEach(button => {
      const label = button.textContent.replace(/^[⌄›]\s*/, '');
      const sync = () => { button.innerHTML = `${icon(button.getAttribute('aria-expanded') === 'true' ? 'chevron-down' : 'chevron-right')}<span>${label}</span>`; };
      button.addEventListener('click', sync);
      sync();
    });
    content.querySelectorAll('[data-sample-platform="mobile"] .mini-table').forEach(table => {
      const headings = [...table.tHead.rows[0].cells].map(cell => cell.textContent);
      [...table.tBodies[0].rows].forEach(row => [...row.cells].forEach((cell, index) => { cell.dataset.column = headings[index]; }));
      table.classList.add('mobile-record-list');
    });
    content.querySelectorAll('[data-sample-platform="mobile"] [data-drawer-demo]').forEach(demo => {
      const placement = demo.querySelector('[data-drawer-placement]');
      placement.value = 'bottom';
      placement.dispatchEvent(new Event('change', { bubbles: true }));
    });
    content.querySelectorAll('.demo-drawer').forEach(panel => {
      const list = document.createElement('ul');
      list.className = 'drawer-source-list';
      ['产品设计.md', '会议纪要.md', '需求评审.pdf'].forEach(name => {
        const row = document.createElement('li');
        row.innerHTML = `${icon('file')}<span>${name}</span><small>已索引</small>`;
        list.append(row);
      });
      panel.append(list);
    });
    const controlsSelector = '.time-options,.input-options,.input-option,.radio-options,.slider-options,.slider-option,.switch-options,.transfer-options,.tabs-options,.modal-options,.drawer-options,.tooltip-option,.tree-options,.upload-options,.progress-options,.spin-options,.badge-demo>label';
    content.querySelectorAll(controlsSelector).forEach(node => node.classList.add('demo-control-row'));
    content.querySelectorAll(`${controlsSelector} select`).forEach(select => select.classList.add('nm-select-control'));
    content.querySelectorAll(`${controlsSelector} input[type="checkbox"]`).forEach(input => {
      const label = input.closest('label');
      if (!label) return;
      label.classList.add('nm-check-control');
      if (!input.nextElementSibling || !input.nextElementSibling.matches('span')) input.insertAdjacentHTML('afterend', '<span></span>');
    });
  };
  groups.components = groups.components.map(([heading, items]) => [heading, items.filter(([id]) => id !== 'result')]);
  delete components.result;
  const render = id => { const item = values[id] || components[id] || values.overview; document.querySelectorAll('[data-section]').forEach(button => { const active = button.dataset.section === id; button.classList.toggle('active', active); if (active) button.setAttribute('aria-current', 'page'); else button.removeAttribute('aria-current'); }); title.textContent = item.title; intro.textContent = item.intro; content.innerHTML = item.render(); normalizeLegacyIcons(); bind(); arrangeExamples(); window.parent !== window && window.parent.postMessage({ type:'notemeld-page-loaded', id:'A04' }, '*'); };
  menus.forEach(menu => menu.addEventListener('click', () => { activeMenu = menu.dataset.designMenu; menus.forEach(item => { const selected = item === menu; item.classList.toggle('active', selected); item.setAttribute('aria-selected', String(selected)); }); renderNav(); render(activeMenu === 'values' ? 'overview' : 'foundations'); }));
  nav.addEventListener('click', event => { const button = event.target.closest('[data-section]'); if (button) render(button.dataset.section); });
  renderNav();
  const requested = new URLSearchParams(location.search).get('component') || location.hash.slice(1);
  const componentAliases = { Upload: 'uploadComponent', IconButton: 'iconButton', InputNumber: 'inputNumber', AutoComplete: 'autocomplete', DatePicker: 'datePicker', TimePicker: 'timePicker' };
  const requestedAlias = requested && Object.entries(componentAliases).find(([alias]) => alias.toLocaleLowerCase() === requested.toLocaleLowerCase())?.[1];
  const requestedId = requested && (requestedAlias || Object.keys(components).find(id => id.toLocaleLowerCase() === requested.toLocaleLowerCase()));
  if (requestedId) { activeMenu = 'components'; menus.forEach(menu => { const selected = menu.dataset.designMenu === activeMenu; menu.classList.toggle('active', selected); menu.setAttribute('aria-selected', String(selected)); }); renderNav(); }
  render(requestedId || 'overview');
})();
