# NoteMeld · galaxy 组件契约

状态：8 个高频基础组件的**实现契约**。本文件定义统一的 HTML 结构、属性、状态与可访问性，任何端（Web/桌面 React、Vue、Android、iOS、鸿蒙）都应映射到同一契约，可用各自原生技术实现。

灵感来源 [uiverse-io/galaxy](https://github.com/uiverse-io/galaxy)：只吸收**交互动效与“手感”**，不复制其硬编码颜色、固定尺寸或非语义结构。这是补齐“直接生成组件基础能力差”的核心层。

## 0. 分层与文件

```text
③ 业务组件    ChatTurn / ReasonPanel / WorkspaceTree / Terminal / ApprovalCard
② galaxy 层   本文件：8 个高频基础组件（统一、可组合、可访问）
① 基础 token  tokens.css：颜色/间距/圆角/尺寸/动效；primitives.css：原始形态
```

| 文件 | 职责 |
|---|---|
| `tokens.css` | 全部设计变量（含组件级：switch、card shadow、tooltip、spring） |
| `galaxy.css` | 8 组件的交互增强（纯 CSS，全部 var() 引用） |
| `galaxy.js` | 仅补 CSS 做不到的行为：aria-checked 同步、程序化 `NmGalaxy.init()` |
| `index.html` | 可操作的组件展示与对照 |

### 0.1 通用规则

- **不写死颜色/尺寸**：所有可视值必须来自 `--nm-*` 变量，保证明暗主题与品牌可切换。
- **语义元素**：动作用 `<button>`，开关/勾选是 `<input type="checkbox">`，字段用 `<label><input></label>`。
- **焦点可见**：所有可交互元素必须有 `:focus-visible` 环。
- **可中断/可降级**：动画在 `prefers-reduced-motion: reduce` 下即时完成。
- **禁用**：`disabled` 时禁止交互、降低对比度并改 `cursor`。

## 1. Button（按钮）

**结构**：`<button class="nm-button">`，图标与文字作为直接子元素。

**属性**：

| 属性 | 取值 | 说明 |
|---|---|---|
| `data-variant` | `primary` `secondary` `ghost` `dashed` `link` `danger` | 视觉变体 |
| `data-size` | `sm` `md(默认)` `lg` | 尺寸（接 control-height token） |
| `disabled` | 布尔 | 禁用 |

**交互**：hover 时光泽从左扫到右（仅实心 primary/danger）；active 下沉 1px 并轻微缩放；图标/文字层级高于光泽层。

**A11y**：真实 `<button>` 天然支持 Enter/Space；`:focus-visible` 显示环；禁用项不可聚焦（原生）。图标-only 按钮必须加 `aria-label`（见 Icon Button）。

## 2. Icon Button（图标按钮）

**结构**：`<button class="nm-icon-button" aria-label="…">图标</button>`。

**交互**：hover 显示浅底；active 用 spring 曲线缩放到 .88 并回弹。

**A11y**：**必须**有 `aria-label`；支持 `disabled`；`:focus-visible` 环。

## 3. Input / Field（输入字段）

**结构**：`<label class="nm-field"><input></label>`（内部可含图标，输入框 `border:0`）。

| 属性 | 说明 |
|---|---|
| `data-invalid="true"` | 错误态：红描边 + 红色聚焦光晕 |
| 内部 `<input aria-invalid>` | 与错误态配合 |

**交互**：focus-within 描边转强调色并出现 3px 柔和光晕。

**A11y**：必须有用 `<label>` 或 visually-hidden 文本提供的可访问名；占位符不能替代标签。

## 4. Switch（开关）

**结构（固定）**：

```html
<label class="nm-switch">
  <input type="checkbox" class="nm-switch-input">
  <span class="nm-switch-track"><span class="nm-switch-thumb"></span></span>
  <span>标签文字</span>
</label>
```

| 属性 | 说明 |
|---|---|
| 内部 input `checked` | 开/关唯一事实源 |
| `data-size="sm"`（在 label 上） | 小尺寸 |
| input `disabled` | 禁用 |

**交互**：checked 时轨道变色、拇指用 spring 曲线平移。

**A11y**：视觉上隐藏原生 input，但保留可聚焦；`:focus-visible` 环落在轨道；Space 切换；`galaxy.js` 把 `checked` 同步到 `aria-checked`。点标签/轨道都触发原生 input，无重复触发。

## 5. Checkbox（复选框）

**结构**：

```html
<label class="nm-checkbox">
  <input type="checkbox" class="nm-checkbox-input">
  <span class="nm-checkbox-box"><svg><!-- check 图标 --></svg></span>
  <span>标签</span>
</label>
```

**交互**：checked 时方框填充强调色，对勾 svg 以 spring 从 .4 pop 到 1。

**A11y**：原生 input 隐藏但可聚焦；`:focus-visible` 环；Space 勾选；`aria-checked` 同步；支持 `disabled`。

## 6. Card（卡片）

**结构**：`<div class="nm-card">…</div>`。

| 属性 | 说明 |
|---|---|
| `data-interactive="true"` | 可交互：hover 抬升、阴影加深 |
| `tabindex="0"` | 可交互卡片要可聚焦（键盘可达） |

**交互**：仅 `data-interactive` 卡片 hover 上浮 2px、active 回落；普通卡片不抬升。

**A11y**：纯展示卡片不带交互；若整卡可点，优先用 `<a>`/`<button>` 包裹或提供键盘操作，不能只靠 hover。

## 7. Tooltip（工具提示）

**结构**：

```html
<span class="nm-tooltip-wrapper">
  <button>触发</button>
  <span class="nm-tooltip" role="tooltip">提示文字</span>
</span>
```

| 属性 | 说明 |
|---|---|
| `data-placement` | 上方（默认）/ `bottom` |

**交互**：hover 或 focus-within 时淡入并从 4px 位移归位；带小箭头。**纯 CSS，无需 JS**。

**A11y**：用 `focus-within` 保证键盘聚焦也显示；tooltip 不可承载关键信息（hover 不可达场景），关键内容应常驻。

## 8. Loader（加载器）

三种形态，均需 `role="status"` + `aria-label`：

| 类 | 形态 |
|---|---|
| `.nm-loader-spin` | 圆环旋转（700ms 线性） |
| `.nm-loader-dots`（含 3 个 `<span>`） | 三点弹跳（错开 0.15s） |
| `.nm-loader-bar` | 不定进度条（滑块往返） |

**A11y**：装饰性加载器对 AT 用 `aria-hidden`；表达区域状态用 `role="status"`；`role="progressbar"` 的确定进度应带 `aria-valuenow`（不定进度可省略）。

## 9. 程序化接口（galaxy.js）

```js
// 动态插入组件后，绑定 aria 同步：
window.NmGalaxy.init(rootElement);
```

- 初始化幂等（以 `data-nmGalaxyReady` 标记）。
- 不改写 DOM 结构、不拦截事件；键盘交互完全依赖原生控件。

## 10. 验收清单

- [ ] 所有颜色/尺寸来自 token，切到 dark 主题无残留硬编码色。
- [ ] 仅键盘（Tab/Enter/Space/Esc）可操作全部组件并看到焦点环。
- [ ] Switch/Checkbox 的点击、Space、label 点击都只切换一次。
- [ ] disabled 项不可操作、不可聚焦。
- [ ] 开启系统“减少动态效果”后所有动画即时完成、状态正确。
- [ ] 图标按钮均有 `aria-label`；字段有可访问名；loader 有正确 role。
- [ ] 业务组件（ChatTurn 等）只在本层基础上组合，不重复造交互底层。
