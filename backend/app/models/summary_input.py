from dataclasses import dataclass, field
from typing import Optional

from app.models.transcriber_model import TranscriptSegment


@dataclass
class InputInspection:
    input_type: str
    source_url: Optional[str] = None
    platform: Optional[str] = None
    page_type: Optional[str] = None
    detected_media: list[dict] = field(default_factory=list)
    supported_media: list[dict] = field(default_factory=list)
    recommended_collectors: list[str] = field(default_factory=list)
    confidence: float = 0.0


@dataclass
class PageContext:
    title: str
    description: Optional[str] = None
    author: Optional[str] = None
    publish_time: Optional[str] = None
    url: str = ""
    site_name: Optional[str] = None
    page_type: str = "unknown"
    topic: Optional[str] = None
    headings: list[dict] = field(default_factory=list)
    main_text_summary: Optional[str] = None
    key_points: list[str] = field(default_factory=list)
    links: list[dict] = field(default_factory=list)
    detected_media: list[dict] = field(default_factory=list)
    raw_text_path: Optional[str] = None
    confidence: float = 0.0


@dataclass
class TranscriptContext:
    language: str
    full_text: str
    segments: list[TranscriptSegment] = field(default_factory=list)
    duration: Optional[float] = None
    chunk_summary: list[dict] = field(default_factory=list)
    key_moments: list[dict] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    concepts: list[str] = field(default_factory=list)
    quality: dict = field(default_factory=dict)


@dataclass
class VisionFrame:
    timestamp: float
    image_url: str
    summary: str
    detected_text: Optional[str] = None
    visual_type: str = "unknown"
    importance: float = 0.0


@dataclass
class VisionContext:
    mode: str = "disabled"
    frames: list[VisionFrame] = field(default_factory=list)
    storyboard_summary: Optional[str] = None
    visual_entities: list[str] = field(default_factory=list)
    visual_concepts: list[str] = field(default_factory=list)


@dataclass
class SocialComment:
    author: Optional[str] = None
    content: str = ""
    like_count: Optional[int] = None
    reply_count: Optional[int] = None
    replies: list["SocialComment"] = field(default_factory=list)


@dataclass
class SocialContext:
    like_count: Optional[int] = None
    comment_count: Optional[int] = None
    share_count: Optional[int] = None
    favorite_count: Optional[int] = None
    comments_summary: Optional[str] = None
    sentiment: Optional[str] = None
    controversy_points: list[str] = field(default_factory=list)
    audience_questions: list[str] = field(default_factory=list)
    useful_supplements: list[str] = field(default_factory=list)
    comments: list[SocialComment] = field(default_factory=list)
    confidence: float = 0.0


@dataclass
class DocumentContext:
    title: str
    parser_name: str
    page_count: int
    text: str
    resource_type: str = "document"
    source_url: Optional[str] = None
    parser_backend: Optional[str] = None
    fallback_used: bool = False
    evidence_count: int = 0
    chunk_count: int = 0
    raw_json_path: Optional[str] = None
    quality: dict = field(default_factory=dict)
    pages: list[dict] = field(default_factory=list)


@dataclass
class MetaContext:
    resource_type: str
    platform: Optional[str] = None
    video_id: Optional[str] = None
    duration: Optional[float] = None
    language: Optional[str] = None
    model_name: Optional[str] = None
    provider_id: Optional[str] = None
    raw: dict = field(default_factory=dict)


@dataclass
class ContextBlock:
    source_type: str
    role: str
    content: str
    weight: float
    confidence: float
    include_policy: str = "always"


@dataclass
class WeightedContextPack:
    input_id: str
    primary_sources: list[str] = field(default_factory=list)
    auxiliary_sources: list[str] = field(default_factory=list)
    source_weights: dict[str, float] = field(default_factory=dict)
    context_blocks: list[ContextBlock] = field(default_factory=list)
    token_budget: dict = field(default_factory=dict)


@dataclass
class SummaryInput:
    input_id: str
    input_type: str
    source_url: Optional[str]
    platform: Optional[str]
    title: Optional[str]
    user_goal: Optional[str]
    user_options: dict
    page_context: Optional[PageContext]
    transcript_context: Optional[TranscriptContext]
    vision_context: Optional[VisionContext]
    social_context: Optional[SocialContext]
    meta_context: MetaContext
    document_context: Optional[DocumentContext] = None
