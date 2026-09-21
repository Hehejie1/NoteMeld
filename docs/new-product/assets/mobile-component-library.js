/*
 * M11 组件库（移动端预览）
 * 只展示「组件库」（不含设计价值观）：
 *  - 顶栏：返回 / 组件库 / 菜单
 *  - 点菜单出底部弹窗，按 label 分类列出模块，选中后下方展示该模块在 Android 的实现
 *  - 深色/浅色同步外部设置（body[data-theme]）
 */
(() => {
  'use strict';
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];

  // 组件库模块：按 label 分组；impl 为该组件在 Android 的实现说明
  const GROUPS = [
    {
      label: '基础设计',
      items: [
        { id: 'color', name: 'Color 颜色', android: '语义色板由 NoteMeldTheme 提供：lightColorScheme/darkColorScheme（primary、surface、error 等），Compose Color 常量，随系统/应用主题切换。' },
        { id: 'spacing', name: 'Spacing 间距', android: 'NoteMeldTokens：spacingXs/Sm/Md/Lg（4/8/12/20 dp），统一 Arrangement.spacedBy 与 padding。' },
        { id: 'radius', name: 'Radius 圆角', android: 'Material shapes：extraSmall 7、small 9、medium 12、large 14 dp；RoundedCornerShape。' },
        { id: 'typography', name: 'Typography 字体规范', android: 'NoteMeldTheme 内 MaterialTheme.typography：bodyLarge/Medium/Small、titleMedium、labelMedium 统一字号行高。' },
        { id: 'iconography', name: 'Iconography 图标', android: 'Compose Icon + painterResource（矢量资源），tint 跟随主题；lucide 图标在原型侧使用。' },
        { id: 'layout', name: 'Layout 布局', android: 'Column/Row/Box + weight、Arrangement、Modifier.fillMaxWidth；ModalBottomSheet 统一弹窗。' },
        { id: 'motion', name: 'Motion 动画', android: 'animateColorAsState、AnimatedVisibility、ModalBottomSheet 内建过渡；时长跟随 Material 动画规范。' },
      ],
    },
    {
      label: '通用',
      items: [
        { id: 'button', name: 'Button 按钮', android: 'NoteMeldActionButton / NoteMeldPrimaryButton：Material Button，containerColor=primary。' },
        { id: 'icon-button', name: 'Icon Button 图标按钮', android: 'NoteMeldIconButton / IconButton：48 dp 可点击目标，强制 contentDescription。' },
      ],
    },
    {
      label: '数据录入',
      items: [
        { id: 'autocomplete', name: 'AutoComplete 自动完成', android: 'ExposedDropdownMenuBox + OutlinedTextField（Material3），过滤候选项。' },
        { id: 'checkbox', name: 'Checkbox 多选框', android: 'Material Checkbox，accent/primary；模型多选列表即此组件。' },
        { id: 'date-picker', name: 'DatePicker 日期选择', android: 'DatePickerDialog / Material DatePicker，State 持有选择。' },
        { id: 'input', name: 'Input 输入框', android: 'NoteMeldField = OutlinedTextField，singleLine、label/placeholder 统一。' },
        { id: 'input-number', name: 'InputNumber 数字输入', android: 'KeyboardType.Number 的 OutlinedTextField + toIntOrNull 校验。' },
        { id: 'mentions', name: 'Mentions 提及', android: 'BasicTextField + VisualTransformation/选区弹层，@ 触发候选。' },
        { id: 'radio', name: 'Radio 单选框', android: 'Material RadioButton + RadioGroup 语义；弹窗单选列表。' },
        { id: 'rate', name: 'Rate 评分', android: 'Row 内可点 Icon + 状态，支持半选（weight 布局）。' },
        { id: 'select', name: 'Select 选择器', android: 'ExposedDropdownMenuBox 或自定义 Surface 点击 + ModalBottomSheet（固定高度滚动）。' },
      ],
    },
  ];

  const content = $('[data-comp-content]');
  const moduleList = $('[data-comp-module-list]');
  let currentItem = GROUPS[0].items[0];

  const refreshIcons = () => window.lucide?.createIcons({ attrs: { 'stroke-width': 2 } });
  const toast = message => {
    const node = $('[data-comp-toast]');
    node.textContent = message; node.hidden = false;
    clearTimeout(node._t);
    node._t = setTimeout(() => { node.hidden = true; }, 2200);
  };
  const closeSheets = () => {
    $$('.mobile-sheet').forEach(s => { s.hidden = true; });
    $('[data-sheet-backdrop]').hidden = true;
  };

  function renderContent() {
    content.replaceChildren();
    const head = document.createElement('div');
    head.className = 'comp-current';
    const eyebrow = document.createElement('span');
    eyebrow.className = 'comp-current-label';
    const group = GROUPS.find(g => g.items.some(i => i.id === currentItem.id));
    eyebrow.textContent = group.label;
    const title = document.createElement('h1');
    title.textContent = currentItem.name;
    head.append(eyebrow, title);

    const card = document.createElement('section');
    card.className = 'comp-impl-card';
    const cap = document.createElement('h2');
    cap.textContent = 'Android 端实现';
    const body = document.createElement('p');
    body.textContent = currentItem.android;
    card.append(cap, body);

    content.append(head, card);
    refreshIcons();
  }

  function renderModuleList() {
    moduleList.replaceChildren();
    GROUPS.forEach(group => {
      const label = document.createElement('p');
      label.className = 'comp-group-label';
      label.textContent = group.label;
      moduleList.append(label);
      group.items.forEach(item => {
        const button = document.createElement('button');
        button.type = 'button';
        button.dataset.compItem = item.id;
        if (item.id === currentItem.id) button.classList.add('is-active');
        const name = document.createElement('span');
        name.textContent = item.name;
        button.append(name);
        moduleList.append(button);
      });
    });
    refreshIcons();
  }

  $('[data-comp-menu]').addEventListener('click', () => {
    renderModuleList();
    $('[data-sheet-backdrop]').hidden = false;
    $('[data-comp-module]').hidden = false;
  });
  moduleList.addEventListener('click', event => {
    const button = event.target.closest('[data-comp-item]');
    if (!button) return;
    GROUPS.forEach(g => g.items.forEach(i => { if (i.id === button.dataset.compItem) currentItem = i; }));
    closeSheets();
    renderContent();
  });
  $('[data-comp-back]').addEventListener('click', () => { window.location.href = 'm03.html'; });
  $$('[data-sheet-close]').forEach(b => b.addEventListener('click', closeSheets));
  $('[data-sheet-backdrop]').addEventListener('click', closeSheets);

  renderContent();
})();
