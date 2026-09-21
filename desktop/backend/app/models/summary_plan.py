from dataclasses import dataclass, field


def build_default_render_contract(output_type: str) -> dict:
    if output_type == "export_outline":
        return {
            "format": "structured_json",
            "target": "pptx",
            "max_slides": 12,
            "slide_schema": {
                "title": "string",
                "main_point": "string",
                "supporting_evidence": "list",
                "quote": "string",
                "suggested_visual_timestamp": "float",
            },
        }
    if output_type == "wiki_page":
        return {
            "format": "markdown",
            "sections": [
                "summary",
                "source_metadata",
                "key_claims",
                "concepts",
                "entities",
                "evidence",
                "related_pages",
            ],
            "backlink_required": True,
            "entity_link_required": True,
        }
    return {
        "format": "markdown",
        "sections": [
            "title",
            "overview",
            "toc",
            "chapters",
            "key_points",
            "visual_notes",
            "audience_feedback",
            "ai_summary",
        ],
        "timestamp_required": True,
        "screenshot_marker_required": True,
        "evidence_required": False,
    }


@dataclass
class SummaryPlan:
    input_id: str
    output_type: str
    strategy: str
    chunk_policy: dict = field(default_factory=dict)
    context_policy: dict = field(default_factory=dict)
    vision_policy: dict = field(default_factory=dict)
    render_contract: dict = field(default_factory=dict)
    checkpoint_policy: dict = field(default_factory=dict)
    wiki_policy: dict = field(default_factory=dict)
