import re
from typing import Optional
from urllib.parse import urlparse

from app.models.summary_input import InputInspection
from app.validators.video_url_validator import is_supported_video_url


class SourceInspector:
    VIDEO_EXTENSIONS = (".mp4", ".mov", ".mkv", ".webm", ".avi")
    AUDIO_EXTENSIONS = (".mp3", ".wav", ".m4a", ".aac", ".flac")

    def inspect(self, raw_input: str) -> InputInspection:
        value = (raw_input or "").strip()
        extracted_url = self._extract_first_url(value)
        target = extracted_url or value

        if target.startswith("/uploads/") and target.lower().endswith(self.VIDEO_EXTENSIONS):
            return InputInspection(
                input_type="uploaded_video",
                source_url=target,
                recommended_collectors=["transcript", "vision"],
                confidence=0.95,
            )

        if target.lower().endswith(self.VIDEO_EXTENSIONS):
            return InputInspection(
                input_type="local_media",
                source_url=target,
                recommended_collectors=["transcript", "vision"],
                confidence=0.9,
            )

        if target.lower().endswith(self.AUDIO_EXTENSIONS):
            return InputInspection(
                input_type="local_media",
                source_url=target,
                recommended_collectors=["transcript"],
                confidence=0.9,
            )

        parsed = urlparse(target)
        if parsed.scheme in ("http", "https"):
            platform = self._detect_platform(target)
            if platform and is_supported_video_url(target):
                return InputInspection(
                    input_type="video_link",
                    source_url=target,
                    platform=platform,
                    page_type="video_page",
                    detected_media=[{"type": "video", "url": target, "platform": platform}],
                    supported_media=[{"type": "video", "url": target, "platform": platform}],
                    recommended_collectors=["page", "transcript", "vision"],
                    confidence=0.93,
                )
            return InputInspection(
                input_type="web_link",
                source_url=target,
                page_type="unknown",
                recommended_collectors=["page"],
                confidence=0.75,
            )

        return InputInspection(
            input_type="unknown",
            source_url=target or None,
            recommended_collectors=[],
            confidence=0.0,
        )

    def _extract_first_url(self, value: str) -> Optional[str]:
        match = re.search(r"https?://[^\s]+", value)
        return match.group(0) if match else None

    def _detect_platform(self, url: str) -> Optional[str]:
        lowered = url.lower()
        if "bilibili.com" in lowered or "b23.tv" in lowered:
            return "bilibili"
        if "youtube.com" in lowered or "youtu.be" in lowered:
            return "youtube"
        if "douyin.com" in lowered:
            return "douyin"
        if "kuaishou.com" in lowered:
            return "kuaishou"
        return None
