"""Portable official link-to-Note capability.

The plugin owns URL routing and the capability contract.  All product state,
progress and Note persistence remain in the host supplied ports.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Protocol
from urllib.parse import urlparse


class LinkNoteHost(Protocol):
    def generate_video(self, *, task_id: str, video_url: str, platform: str, options: dict[str, Any]) -> Any:
        ...

    def generate_web(self, *, task_id: str, web_url: str, options: dict[str, Any]) -> Any:
        ...


class LinkNoteError(ValueError):
    """Stable, safe error exposed by the capability."""

    code = "invalid_link"


class UnsupportedLinkError(LinkNoteError):
    code = "unsupported_link"


@dataclass(frozen=True)
class LinkRoute:
    platform: str
    kind: str


SUPPORTED_PLATFORMS = (
    "youtube",
    "bilibili",
    "tiktok",
    "kuaishou",
    "douyin",
    "wechat_channels",
    "local",
)

URL_PATTERNS = {
    "youtube": re.compile(r"^(https?://)?(www\.)?(youtube\.com/watch\?v=|youtu\.be/)[\w\-]+"),
    "bilibili": re.compile(r"^(https?://)?(www\.)?bilibili\.com/video/[a-zA-Z0-9]+"),
    "kuaishou": re.compile(r"kuaishou"),
    "douyin": re.compile(r"douyin"),
    "wechat_channels": re.compile(r"channels\.weixin\.qq\.com/finder-preview/pages/feed"),
}


def validate_link(url: str, platform: str) -> str:
    """Validate the frozen N01 input contract and return a normalized URL."""
    value = str(url or "").strip()
    if not value:
        raise LinkNoteError("link is required")
    if platform == "local":
        return value
    if platform not in SUPPORTED_PLATFORMS:
        raise UnsupportedLinkError("link platform is not supported")
    if platform == "tiktok":
        return value
    if platform == "bilibili" and "b23.tv" in value:
        return value
    pattern = URL_PATTERNS.get(platform)
    if pattern is None or not pattern.search(value):
        raise LinkNoteError("link format is invalid for the selected platform")
    return value


def route_link(url: str, platform: str, *, force_web_fallback: bool = False) -> LinkRoute:
    value = str(url or "").strip()
    if not value:
        raise LinkNoteError("link is required")
    if force_web_fallback or platform == "web_link":
        if urlparse(value).scheme not in {"http", "https"}:
            raise LinkNoteError("web link must use http or https")
        return LinkRoute("web_link", "web")
    validate_link(value, platform)
    return LinkRoute(platform, "video")


class OfficialLinkNotePlugin:
    """Stateless capability implementation backed by host operation ports."""

    capability_id = "official-link-note:create"

    def __init__(self, host: LinkNoteHost):
        self.host = host

    @classmethod
    def descriptor(cls) -> dict[str, Any]:
        return {
            "id": cls.capability_id,
            "name": "Official link to Note",
            "description": "将受支持的视频或网页链接加工为可追溯 Note。",
            "input_schema": {
                "type": "object",
                "required": ["url", "platform"],
                "properties": {
                    "url": {"type": "string", "minLength": 1},
                    "platform": {"type": "string", "minLength": 1},
                    "force_web_fallback": {"type": "boolean"},
                    "options": {"type": "object"},
                },
            },
            "output_schema": {"type": "object"},
            "portable": True,
        }

    def execute(
        self,
        *,
        task_id: str,
        url: str,
        platform: str,
        options: dict[str, Any] | None = None,
        force_web_fallback: bool = False,
    ) -> Any:
        route = route_link(url, platform, force_web_fallback=force_web_fallback)
        request_options = dict(options or {})
        if route.kind == "web":
            return self.host.generate_web(task_id=task_id, web_url=url, options=request_options)
        return self.host.generate_video(
            task_id=task_id,
            video_url=url,
            platform=route.platform,
            options=request_options,
        )


__all__ = [
    "LinkNoteError",
    "LinkNoteHost",
    "LinkRoute",
    "OfficialLinkNotePlugin",
    "SUPPORTED_PLATFORMS",
    "UnsupportedLinkError",
    "URL_PATTERNS",
    "validate_link",
    "route_link",
]
