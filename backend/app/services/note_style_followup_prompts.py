from __future__ import annotations


def build_followup_prompts(
    replication_score: dict[str, object] | None, router: dict[str, object] | None = None
) -> list[dict[str, str]]:
    overall_score = int((replication_score or {}).get("overall_score") or 0)
    doc_type = str((router or {}).get("doc_type") or "document")

    prompts = [
        {
            "label": "更像原图布局",
            "prompt": "保持当前内容不变，让整体布局更接近原图，优先保留栏结构、模块顺序和标题区比例。",
        },
        {
            "label": "更像原图配色",
            "prompt": "保持当前结构不变，让颜色、标题条和卡片视觉更接近原图。",
        },
        {
            "label": "保留标题层级",
            "prompt": "保持整体样式不变，优先保留原图的标题层级、分节顺序和列表结构。",
        },
        {
            "label": "只调整顶部区域",
            "prompt": "只调整顶部标题区和 header 模块，其余结构保持不变。",
        },
    ]
    if doc_type in {"poster", "slide"}:
        prompts.append(
            {
                "label": "强化视觉主次",
                "prompt": "强化主视觉和次级信息层级，让标题、主卖点和按钮区更接近参考图。",
            }
        )
    if overall_score < 75:
        prompts.append(
            {
                "label": "提升整体相似度",
                "prompt": "在不改动核心文案的前提下，同时优化布局、色彩和模块关系，让结果更像参考模板。",
            }
        )
    return prompts
