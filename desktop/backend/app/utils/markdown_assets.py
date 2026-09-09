import json
import hashlib
import logging
import mimetypes
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlparse

import httpx

from app.utils.storage_paths import static_dir


logger = logging.getLogger(__name__)
MARKDOWN_IMAGE_PATTERN = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
HTML_IMAGE_PATTERN = re.compile(r'(<img\b[^>]*\bsrc=["\'])([^"\']+)(["\'][^>]*>)', re.IGNORECASE)


@dataclass
class MarkdownAssetEntry:
    original_url: str
    localized_url: str
    status: str
    error: str = ""


@dataclass
class MarkdownAssetLocalizationResult:
    markdown: Optional[str]
    assets: list[MarkdownAssetEntry]


def _is_remote_image_url(url: str) -> bool:
    parsed = urlparse((url or "").strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _extract_markdown_image_url(inner: str) -> tuple[str, str, str]:
    raw = (inner or "").strip()
    if not raw:
        return "", "", ""
    if raw.startswith("<") and ">" in raw:
        closing = raw.index(">")
        url = raw[1:closing].strip()
        return url, raw[:closing + 1], raw[closing + 1:]
    parts = raw.split(maxsplit=1)
    url = parts[0].strip()
    suffix = raw[len(url):]
    return url, url, suffix


def _pick_extension(url: str, content_type: str) -> str:
    mime_type = (content_type or "").split(";", 1)[0].strip().lower()
    guessed = mimetypes.guess_extension(mime_type) if mime_type.startswith("image/") else None
    if guessed:
        return guessed
    path_suffix = Path(urlparse(url).path).suffix.strip()
    if path_suffix:
        return path_suffix if path_suffix.startswith(".") else f".{path_suffix}"
    return ".jpg"


def download_remote_image_to_static(
    task_id: str,
    url: str,
    *,
    source_url: Optional[str] = None,
    static_root: Optional[Path] = None,
    client_cls=httpx.Client,
) -> str:
    headers = {
        "User-Agent": "NoteMeld-MarkdownAssets/1.0",
        "Referer": (source_url or url).strip(),
    }
    with client_cls(timeout=15.0, follow_redirects=True) as client:
        response = client.get(url, headers=headers)
        response.raise_for_status()
    content_type = response.headers.get("content-type", "")
    if not content_type.lower().startswith("image/"):
        raise ValueError(f"remote asset is not an image: {content_type or 'unknown'}")
    asset_root = (static_root or static_dir()) / "note_assets"
    asset_root.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    extension = _pick_extension(url, content_type)
    file_name = f"{task_id}_{digest}{extension}"
    target_path = asset_root / file_name
    target_path.write_bytes(response.content)
    return f"/static/note_assets/{file_name}"


def localize_remote_markdown_images(
    task_id: str,
    markdown: Optional[str],
    *,
    source_url: Optional[str] = None,
    downloader: Optional[Callable[..., str]] = None,
) -> MarkdownAssetLocalizationResult:
    if markdown is None:
        return MarkdownAssetLocalizationResult(markdown=None, assets=[])
    if "http://" not in markdown and "https://" not in markdown and "<img" not in markdown.lower():
        return MarkdownAssetLocalizationResult(markdown=markdown, assets=[])

    download = downloader or download_remote_image_to_static
    replacements: dict[str, str] = {}
    entries: dict[str, MarkdownAssetEntry] = {}

    def resolve(url: str) -> str:
        clean = (url or "").strip()
        if not _is_remote_image_url(clean):
            return clean
        if clean in replacements:
            return replacements[clean]
        try:
            replacements[clean] = download(task_id, clean, source_url=source_url)
            entries[clean] = MarkdownAssetEntry(
                original_url=clean,
                localized_url=replacements[clean],
                status="localized",
                error="",
            )
        except Exception as exc:
            logger.warning("Failed to localize markdown image task_id=%s url=%s error=%s", task_id, clean, exc)
            replacements[clean] = clean
            entries[clean] = MarkdownAssetEntry(
                original_url=clean,
                localized_url=clean,
                status="failed",
                error=str(exc),
            )
        return replacements[clean]

    def replace_markdown(match: re.Match) -> str:
        inner = match.group(1)
        url, original_token, suffix = _extract_markdown_image_url(inner)
        localized = resolve(url)
        if localized == url or not original_token:
            return match.group(0)
        updated_inner = inner.replace(original_token, localized if original_token == url else f"<{localized}>", 1)
        return match.group(0).replace(inner, updated_inner, 1)

    localized_markdown = MARKDOWN_IMAGE_PATTERN.sub(replace_markdown, markdown)

    def replace_html(match: re.Match) -> str:
        prefix, url, suffix = match.groups()
        localized = resolve(url)
        return f"{prefix}{localized}{suffix}"

    final_markdown = HTML_IMAGE_PATTERN.sub(replace_html, localized_markdown)
    return MarkdownAssetLocalizationResult(markdown=final_markdown, assets=list(entries.values()))


def write_markdown_assets_sidecar(output_dir: Path, task_id: str, assets: list[MarkdownAssetEntry]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = [asdict(item) for item in assets]
    (output_dir / f"{task_id}_markdown_assets.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
