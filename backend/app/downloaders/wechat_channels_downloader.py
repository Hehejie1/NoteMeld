import os
import re
import subprocess
import uuid
from dataclasses import dataclass
from typing import Any, Optional, Union
from urllib.parse import parse_qs, urlparse

import requests

from app.downloaders.base import Downloader
from app.enmus.note_enums import DownloadQuality
from app.models.audio_model import AudioDownloadResult
from app.services.cookie_manager import CookieConfigManager
from app.utils.path_helper import get_data_dir
from app.utils.video_helper import save_cover_to_static


WECHAT_CHANNELS_API = "https://channels.weixin.qq.com/finder-preview/api/feed/get_feed_info"
WECHAT_CHANNELS_PAGE_URL = "https://channels.weixin.qq.com/finder-preview/pages/feed"


@dataclass(frozen=True)
class WeChatChannelsFeedRequest:
    general_token: str
    export_id: str
    referer: str


@dataclass(frozen=True)
class WeChatChannelsFeedMetadata:
    video_id: str
    title: str
    cover_url: Optional[str]
    author: str
    duration: float


def _unwrap_feed_info(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    feed_info = data.get("feedInfo") if isinstance(data, dict) else None
    if not isinstance(feed_info, dict):
        raise ValueError("视频号接口返回缺少 feedInfo")
    return feed_info


def _first_text(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z._-]+", "_", value).strip("._")
    return cleaned or uuid.uuid4().hex


def _guess_image_extension(url: str, content_type: str) -> str:
    normalized = (content_type or "").split(";")[0].strip().lower()
    if normalized == "image/png":
        return ".png"
    if normalized == "image/webp":
        return ".webp"
    if normalized in {"image/jpg", "image/jpeg"}:
        return ".jpg"

    path = urlparse(url).path.lower()
    if path.endswith(".png"):
        return ".png"
    if path.endswith(".webp"):
        return ".webp"
    if path.endswith(".jpg") or path.endswith(".jpeg"):
        return ".jpg"
    return ".jpg"


def extract_feed_request(video_url: str) -> WeChatChannelsFeedRequest:
    parsed = urlparse(video_url)
    query = parse_qs(parsed.query)
    token = _first_text(*(query.get("token") or []))
    export_id = _first_text(*(query.get("exportId") or []), *(query.get("eid") or []))
    if not token:
        raise ValueError("视频号链接缺少 token，请重新复制完整分享链接")
    if not export_id:
        raise ValueError("视频号链接缺少 exportId/eid，请重新复制完整分享链接")
    return WeChatChannelsFeedRequest(
        general_token=token,
        export_id=export_id,
        referer=video_url,
    )


def select_video_url(payload: dict[str, Any]) -> str:
    feed_info = _unwrap_feed_info(payload)
    direct_url = _first_text(feed_info.get("videoUrl"))
    h265_url = _first_text((feed_info.get("h265VideoInfo") or {}).get("videoUrl"))
    h264_url = _first_text((feed_info.get("h264VideoInfo") or {}).get("videoUrl"))
    video_url = _first_text(direct_url, h265_url, h264_url)
    if not video_url:
        raise ValueError("视频号接口返回缺少可下载视频地址")
    return video_url


def extract_feed_metadata(payload: dict[str, Any]) -> WeChatChannelsFeedMetadata:
    feed_info = _unwrap_feed_info(payload)
    description = _first_text(
        feed_info.get("description"),
        feed_info.get("title"),
        feed_info.get("desc"),
    )
    author = _first_text(
        feed_info.get("nickname"),
        (feed_info.get("authorInfo") or {}).get("nickname"),
    )
    title = description or author or "视频号视频"
    video_id = _first_text(
        feed_info.get("feedId"),
        feed_info.get("objectId"),
        feed_info.get("id"),
    )
    duration = feed_info.get("duration") or feed_info.get("mediaDuration") or 0
    try:
        duration_value = float(duration)
    except (TypeError, ValueError):
        duration_value = 0
    return WeChatChannelsFeedMetadata(
        video_id=video_id or uuid.uuid4().hex,
        title=title,
        cover_url=_first_text(feed_info.get("coverUrl")) or None,
        author=author,
        duration=duration_value,
    )


class WeChatChannelsDownloader(Downloader):
    def __init__(self):
        super().__init__()
        self.cookie_manager = CookieConfigManager()

    def _build_headers(self, referer: str) -> dict[str, str]:
        cookie = self.cookie_manager.get("wechat_channels")
        if not cookie:
            raise ValueError("未设置视频号 Cookie，请先在下载器设置中保存 Cookie")
        return {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "application/json",
            "Cookie": cookie,
            "Origin": "https://channels.weixin.qq.com",
            "Pragma": "no-cache",
            "Referer": referer,
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/148.0.0.0 Safari/537.36"
            ),
        }

    def fetch_feed_info(self, video_url: str) -> dict[str, Any]:
        feed_request = extract_feed_request(video_url)
        response = requests.post(
            WECHAT_CHANNELS_API,
            params={
                "_rid": uuid.uuid4().hex,
                "_pageUrl": WECHAT_CHANNELS_PAGE_URL,
            },
            headers=self._build_headers(feed_request.referer),
            json={
                "baseReq": {"generalToken": feed_request.general_token},
                "exportId": feed_request.export_id,
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        _unwrap_feed_info(payload)
        return payload

    def _download_mp4(self, source_url: str, target_path: str, referer: str) -> str:
        if os.path.exists(target_path):
            return target_path
        headers = self._build_headers(referer)
        with requests.get(source_url, headers=headers, stream=True, timeout=60) as response:
            response.raise_for_status()
            with open(target_path, "wb") as output:
                for chunk in response.iter_content(1024 * 1024):
                    if chunk:
                        output.write(chunk)
        return target_path

    def _cache_cover_locally(self, cover_url: Optional[str], output_dir: str, referer: str, file_id: str) -> Optional[str]:
        if not cover_url:
            return None

        headers = self._build_headers(referer)
        response = requests.get(cover_url, headers=headers, timeout=30)
        response.raise_for_status()
        if not response.content:
            return None

        extension = _guess_image_extension(cover_url, response.headers.get("Content-Type", ""))
        local_cover_path = os.path.join(output_dir, f"{file_id}_cover{extension}")
        with open(local_cover_path, "wb") as output:
            output.write(response.content)
        return save_cover_to_static(local_cover_path)

    @staticmethod
    def _convert_to_mp3(video_path: str, audio_path: str) -> str:
        if os.path.exists(audio_path):
            return audio_path
        subprocess.run(
            ["ffmpeg", "-y", "-i", video_path, "-vn", "-acodec", "libmp3lame", audio_path],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return audio_path

    def download_video(
        self,
        video_url: str,
        output_dir: Union[str, None] = None,
    ) -> str:
        payload = self.fetch_feed_info(video_url)
        metadata = extract_feed_metadata(payload)
        media_url = select_video_url(payload)
        output_dir = output_dir or get_data_dir() or self.cache_data
        os.makedirs(output_dir, exist_ok=True)
        video_path = os.path.join(output_dir, f"{_safe_filename(metadata.video_id)}.mp4")
        return self._download_mp4(media_url, video_path, video_url)

    def download(
        self,
        video_url: str,
        output_dir: Union[str, None] = None,
        quality: DownloadQuality = "fast",
        need_video: Optional[bool] = False,
        skip_download: bool = False,
    ) -> AudioDownloadResult:
        payload = self.fetch_feed_info(video_url)
        metadata = extract_feed_metadata(payload)
        media_url = select_video_url(payload)
        output_dir = output_dir or get_data_dir() or self.cache_data
        os.makedirs(output_dir, exist_ok=True)
        file_id = _safe_filename(metadata.video_id)
        video_path = os.path.join(output_dir, f"{file_id}.mp4")
        audio_path = os.path.join(output_dir, f"{file_id}.mp3")
        cover_url = self._cache_cover_locally(metadata.cover_url, output_dir, video_url, file_id)

        if not skip_download:
            self._download_mp4(media_url, video_path, video_url)
            self._convert_to_mp3(video_path, audio_path)

        return AudioDownloadResult(
            file_path=audio_path,
            title=metadata.title,
            duration=metadata.duration,
            cover_url=cover_url,
            platform="wechat_channels",
            video_id=metadata.video_id,
            raw_info={
                "author": metadata.author,
                "source_video_url": media_url,
                "original_cover_url": metadata.cover_url,
                "quality": str(quality),
            },
            video_path=video_path if need_video or os.path.exists(video_path) else None,
        )
