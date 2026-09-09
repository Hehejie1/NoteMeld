from __future__ import annotations

from html.parser import HTMLParser
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator


OutputFormat = Literal["html", "markdown"]

DEFAULT_STYLE_CONSTRAINTS: dict[str, Any] = {
    "global": {
        "tone": "",
        "sentence": "",
        "visual": "",
        "forbidden": [],
    }
}
DEFAULT_RULE_CONFIG: dict[str, Any] = {"global": {}}
DEFAULT_EXAMPLE_CONTENT: dict[str, str] = {"html": "", "markdown": ""}
DEFAULT_OUTPUT_FORMATS: list[OutputFormat] = ["markdown"]


class _TagCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[tuple[str, dict[str, str]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append((tag, {key: value or "" for key, value in attrs}))


def copy_default(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: copy_default(item) for key, item in value.items()}
    if isinstance(value, list):
        return [copy_default(item) for item in value]
    return value


def normalize_output_formats(values: list[str] | None) -> list[OutputFormat]:
    requested = values or DEFAULT_OUTPUT_FORMATS
    allowed = {"html", "markdown"}
    unique = [value for value in ["html", "markdown"] if value in requested and value in allowed]
    return unique or DEFAULT_OUTPUT_FORMATS.copy()


def _selector_matches(selector: str, tags: list[tuple[str, dict[str, str]]]) -> bool:
    selector = selector.strip()
    if not selector or selector == "global":
        return True
    if selector.startswith("."):
        class_name = selector[1:]
        return any(class_name in attrs.get("class", "").split() for _, attrs in tags)
    if selector.startswith("#"):
        element_id = selector[1:]
        return any(attrs.get("id") == element_id for _, attrs in tags)
    if ">" in selector:
        selector = selector.split(">")[-1].strip()
    if "." in selector:
        tag, class_name = selector.split(".", 1)
        return any(
            item_tag == tag and class_name in attrs.get("class", "").split()
            for item_tag, attrs in tags
        )
    return any(item_tag == selector for item_tag, _ in tags)


def selector_warnings(skeleton_html: str, *constraint_maps: dict[str, Any]) -> list[str]:
    parser = _TagCollector()
    parser.feed(skeleton_html or "")
    warnings: list[str] = []
    for constraint_map in constraint_maps:
        for selector in constraint_map.keys():
            if selector != "global" and not _selector_matches(selector, parser.tags):
                warnings.append(f"selector '{selector}' does not match skeleton_html")
    return warnings


class NoteStylePayload(BaseModel):
    name: str = Field(..., min_length=1, max_length=20)
    description: str = Field("", max_length=500)
    skeleton_html: str = Field(..., min_length=1)
    style_constraints: dict[str, Any] = Field(
        default_factory=lambda: copy_default(DEFAULT_STYLE_CONSTRAINTS)
    )
    rule_config: dict[str, Any] = Field(default_factory=lambda: copy_default(DEFAULT_RULE_CONFIG))
    example_content: dict[str, str] = Field(
        default_factory=lambda: copy_default(DEFAULT_EXAMPLE_CONTENT)
    )
    output_formats: list[OutputFormat] = Field(default_factory=lambda: DEFAULT_OUTPUT_FORMATS.copy())

    @field_validator("name")
    @classmethod
    def trim_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("模板标题不能为空")
        return value

    @field_validator("description")
    @classmethod
    def trim_description(cls, value: str) -> str:
        return (value or "").strip()

    @field_validator("style_constraints")
    @classmethod
    def validate_style_constraints(cls, value: dict[str, Any]) -> dict[str, Any]:
        if "global" not in value:
            raise ValueError("风格约束必须包含 global")
        return value

    @field_validator("rule_config")
    @classmethod
    def validate_rule_config(cls, value: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ValueError("规则配置必须是对象")
        return value

    @field_validator("output_formats")
    @classmethod
    def validate_output_formats(cls, value: list[str]) -> list[OutputFormat]:
        return normalize_output_formats(value)


class NoteStyleRecord(NoteStylePayload):
    id: str
    builtin: bool = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    selector_warnings: list[str] = Field(default_factory=list)
