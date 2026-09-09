from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


CardType = Literal["markdown", "web", "file", "whiteboard"]
RelationType = Literal[
    "related",
    "supports",
    "challenges",
    "depends_on",
    "contains",
    "custom",
]
LineType = Literal["bezier", "straight", "smoothstep"]
RelationDirection = Literal["none", "forward", "backward", "both"]
RelationStyleColor = Literal["default", "muted", "accent", "positive", "warning", "danger"]
RelationStyleWidth = Literal["thin", "medium", "thick"]
RelationStylePattern = Literal["solid", "dashed", "dotted"]

SafeId = Annotated[
    str,
    Field(
        min_length=1,
        max_length=200,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    ),
]
FiniteCoordinate = Annotated[float, Field(allow_inf_nan=False)]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _validate_http_url(value: str, field_name: str) -> str:
    normalized = value.strip()
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{field_name} must use http or https")
    return normalized


def _validate_card_content(card_type: CardType, content: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(content, dict):
        raise ValueError("card content must be an object")

    allowed_keys: dict[CardType, set[str]] = {
        "markdown": {"markdown"},
        "web": {"url", "preview_title", "preview_image", "media_type"},
        "file": {"upload_id"},
        "whiteboard": {"child_whiteboard_id"},
    }
    unknown = set(content) - allowed_keys[card_type]
    if unknown:
        raise ValueError(f"unsupported {card_type} content keys: {sorted(unknown)}")

    if card_type == "markdown":
        markdown = content.get("markdown")
        if not isinstance(markdown, str) or not markdown.strip():
            raise ValueError("markdown content must be non-empty")
        if len(markdown) > 100_000:
            raise ValueError("markdown content exceeds 100000 characters")
        return {"markdown": markdown}

    if card_type == "web":
        url = content.get("url")
        if not isinstance(url, str):
            raise ValueError("web content requires url")
        normalized: dict[str, Any] = {"url": _validate_http_url(url, "url")}
        for key in ("preview_title", "media_type"):
            value = content.get(key)
            if value is not None:
                if not isinstance(value, str) or len(value) > 500:
                    raise ValueError(f"{key} must be a string no longer than 500 characters")
                normalized[key] = value
        preview_image = content.get("preview_image")
        if preview_image is not None:
            if not isinstance(preview_image, str) or len(preview_image) > 2_000:
                raise ValueError("preview_image must be a bounded URL")
            normalized["preview_image"] = _validate_http_url(preview_image, "preview_image")
        return normalized

    key = "upload_id" if card_type == "file" else "child_whiteboard_id"
    value = content.get(key)
    if not isinstance(value, str):
        raise ValueError(f"{card_type} content requires {key}")
    value = value.strip()
    if not value or len(value) > 200:
        raise ValueError(f"{key} must be non-empty and no longer than 200 characters")
    if not value[0].isalnum() or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._:-" for character in value):
        raise ValueError(f"{key} contains unsafe characters")
    return {key: value}


class WhiteboardSourceRef(_StrictModel):
    source_id: Annotated[str, Field(min_length=1, max_length=200)]
    source_type: Annotated[str, Field(min_length=1, max_length=100)]
    title: Annotated[str, Field(min_length=1, max_length=500)]
    url: Annotated[str, Field(max_length=2_000)] | None = None
    task_id: SafeId | None = None

    @field_validator("source_id", "source_type", "title", "task_id")
    @classmethod
    def strip_bounded_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("source fields must not be blank")
        if any(ord(character) < 32 for character in normalized):
            raise ValueError("source fields must not contain control characters")
        return normalized

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _validate_http_url(value, "source url")


class WhiteboardPosition(_StrictModel):
    x: FiniteCoordinate
    y: FiniteCoordinate


class WhiteboardSize(_StrictModel):
    width: Annotated[float, Field(ge=220, le=960, allow_inf_nan=False)]
    height: Annotated[float, Field(ge=120, le=720, allow_inf_nan=False)]


class WhiteboardViewport(_StrictModel):
    x: FiniteCoordinate = 0
    y: FiniteCoordinate = 0
    zoom: Annotated[float, Field(ge=0.1, le=2.5, allow_inf_nan=False)] = 1


class WhiteboardCard(_StrictModel):
    id: SafeId
    type: CardType
    title: Annotated[str, Field(min_length=1, max_length=200)]
    description: Annotated[str, Field(max_length=2_000)] = ""
    content: dict[str, Any]
    source_refs: list[WhiteboardSourceRef] = Field(default_factory=list, max_length=20)
    position: WhiteboardPosition
    size: WhiteboardSize
    z_index: int = 0
    collapsed: bool = True

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("card title must not be blank")
        return normalized

    @model_validator(mode="after")
    def validate_content_for_type(self):
        self.content = _validate_card_content(self.type, self.content)
        return self


WhiteboardCardCreate = WhiteboardCard


class WhiteboardRelationStyle(_StrictModel):
    color: RelationStyleColor | None = None
    width: RelationStyleWidth | None = None
    pattern: RelationStylePattern | None = None


class WhiteboardRelation(_StrictModel):
    id: SafeId
    source_card_id: SafeId
    target_card_id: SafeId
    relation_type: RelationType = "related"
    label: Annotated[str, Field(max_length=160)] = ""
    description: Annotated[str, Field(max_length=2_000)] = ""
    line_type: LineType = "bezier"
    direction: RelationDirection = "forward"
    source_refs: list[WhiteboardSourceRef] = Field(default_factory=list, max_length=20)
    style: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_relation(self):
        if self.source_card_id == self.target_card_id:
            raise ValueError("relation endpoints must be different")
        parsed_style = WhiteboardRelationStyle.model_validate(self.style)
        self.style = parsed_style.model_dump(exclude_none=True)
        return self


class WhiteboardNoteLink(_StrictModel):
    note_task_id: SafeId
    published_revision: Annotated[int, Field(ge=1)]
    published_at: datetime | None = None
    updated_at: datetime | None = None


class WhiteboardSummary(_StrictModel):
    id: SafeId
    conversation_id: SafeId
    title: str
    description: str
    schema_version: int
    revision: int
    legacy_canvas_id: str | None = None
    status: Literal["active", "archived"]
    updated_at: datetime | None = None


class WhiteboardSnapshot(_StrictModel):
    id: SafeId
    conversation_id: SafeId
    title: str
    description: str
    schema_version: int
    revision: int
    viewport: WhiteboardViewport
    cards: list[WhiteboardCard]
    relations: list[WhiteboardRelation]
    note_link: WhiteboardNoteLink | None
    legacy_canvas_id: str | None


class WhiteboardCardPatch(_StrictModel):
    type: CardType | None = None
    title: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    description: Annotated[str, Field(max_length=2_000)] | None = None
    content: dict[str, Any] | None = None
    source_refs: list[WhiteboardSourceRef] | None = Field(default=None, max_length=20)
    z_index: int | None = None
    collapsed: bool | None = None

    @model_validator(mode="after")
    def validate_patch(self):
        if not self.model_fields_set:
            raise ValueError("card patch must not be empty")
        if "type" in self.model_fields_set and "content" not in self.model_fields_set:
            raise ValueError("card type changes require new content")
        if self.type is not None and self.content is not None:
            self.content = _validate_card_content(self.type, self.content)
        if self.title is not None:
            self.title = self.title.strip()
            if not self.title:
                raise ValueError("card title must not be blank")
        return self


class WhiteboardRelationPatch(_StrictModel):
    source_card_id: SafeId | None = None
    target_card_id: SafeId | None = None
    relation_type: RelationType | None = None
    label: Annotated[str, Field(max_length=160)] | None = None
    description: Annotated[str, Field(max_length=2_000)] | None = None
    line_type: LineType | None = None
    direction: RelationDirection | None = None
    source_refs: list[WhiteboardSourceRef] | None = Field(default=None, max_length=20)
    style: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_patch(self):
        if not self.model_fields_set:
            raise ValueError("relation patch must not be empty")
        if self.style is not None:
            parsed_style = WhiteboardRelationStyle.model_validate(self.style)
            self.style = parsed_style.model_dump(exclude_none=True)
        return self


class CardCreateOp(_StrictModel):
    op: Literal["card.create"]
    card: WhiteboardCardCreate


class CardUpdateOp(_StrictModel):
    op: Literal["card.update"]
    card_id: SafeId
    patch: WhiteboardCardPatch


class CardDeleteOp(_StrictModel):
    op: Literal["card.delete"]
    card_id: SafeId


class CardMoveResizeItem(_StrictModel):
    card_id: SafeId
    position: WhiteboardPosition | None = None
    size: WhiteboardSize | None = None

    @model_validator(mode="after")
    def validate_change(self):
        if self.position is None and self.size is None:
            raise ValueError("move/resize item requires position or size")
        return self


class CardMoveResizeOp(_StrictModel):
    op: Literal["card.move_resize"]
    items: list[CardMoveResizeItem] = Field(min_length=1, max_length=500)


class RelationCreateOp(_StrictModel):
    op: Literal["relation.create"]
    relation: WhiteboardRelation


class RelationUpdateOp(_StrictModel):
    op: Literal["relation.update"]
    relation_id: SafeId
    patch: WhiteboardRelationPatch


class RelationDeleteOp(_StrictModel):
    op: Literal["relation.delete"]
    relation_id: SafeId


class ViewportUpdateOp(_StrictModel):
    op: Literal["viewport.update"]
    x: FiniteCoordinate
    y: FiniteCoordinate
    zoom: Annotated[float, Field(ge=0.1, le=2.5, allow_inf_nan=False)]

    def as_viewport(self) -> WhiteboardViewport:
        return WhiteboardViewport(x=self.x, y=self.y, zoom=self.zoom)


WhiteboardOperation = Annotated[
    CardCreateOp
    | CardUpdateOp
    | CardDeleteOp
    | CardMoveResizeOp
    | RelationCreateOp
    | RelationUpdateOp
    | RelationDeleteOp
    | ViewportUpdateOp,
    Field(discriminator="op"),
]


class WhiteboardMutationResult(_StrictModel):
    revision: Annotated[int, Field(ge=2)]
    cards: list[WhiteboardCard] = Field(default_factory=list)
    relations: list[WhiteboardRelation] = Field(default_factory=list)
    deleted_card_ids: list[SafeId] = Field(default_factory=list)
    deleted_relation_ids: list[SafeId] = Field(default_factory=list)
    viewport: WhiteboardViewport | None = None
