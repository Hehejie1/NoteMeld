from __future__ import annotations

import json
from typing import Any


def _json_block(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def build_note_style_instruction(template: dict[str, Any]) -> str:
    output_formats = template.get("output_formats") or ["markdown"]
    needs_markdown = "markdown" in output_formats
    needs_html = "html" in output_formats

    strategy = "先生成 HTML"
    if needs_html and needs_markdown:
        strategy += "；后端会由 HTML 转 Markdown，同时保存两份结果。模型只返回 HTML"
    elif needs_markdown:
        strategy += "；后端会由 HTML 转 Markdown。模型只返回 HTML"
    else:
        strategy += "，只返回 HTML"

    return f"""
## 笔记风格模板协议

模板名称：{template.get("name", "")}
模板简介：{template.get("description", "")}

### 输出策略
{strategy}

### skeleton_html
```html
{template.get("skeleton_html", "")}
```

### style_constraints
```json
{_json_block(template.get("style_constraints", {}))}
```

### rule_config
```json
{_json_block(template.get("rule_config", {}))}
```

### example_content
```json
{_json_block(template.get("example_content", {}))}
```

### 强制要求
- 骨架模板是 HTML 一等格式，必须优先保留主要 DOM 结构、class 和 data 属性。
- CSS selector 对应的局部约束必须作用到对应节点。
- 标题必须根据内容生成，禁止把模板名、风格名或通用词直接当成最终标题。
- 如果 skeleton 里出现 `<h1>`，它只代表结构占位；最终标题必须替换成内容摘要标题，不要直接使用模板名。
- 禁止输出 script、内联事件和危险链接。
- 如果需要 Markdown，必须先形成稳定 HTML 结构；模型仍只返回 HTML，后端负责转换为 Markdown。
""".strip()
