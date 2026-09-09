from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import unquote, urlparse

import httpx


MAX_RELEASE_BYTES = 64 * 1024 * 1024
MAX_REDIRECTS = 3
RELEASE_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)
ALLOWED_HOSTS = {
    "github.com", "api.github.com", "objects.githubusercontent.com", "githubusercontent.com",
    "gitee.com", "api.gitee.com", "gitee.com.cn",
}


class ReleaseResolverError(ValueError):
    pass


@dataclass(frozen=True)
class ReleaseArtifact:
    plugin_id: str
    version: str
    url: str
    content: bytes
    provider: str


def _https_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ReleaseResolverError("release URL must use HTTPS")
    if parsed.hostname.lower() not in ALLOWED_HOSTS:
        raise ReleaseResolverError("release host is not allowlisted")
    return value


def _provider_url(source_url: str) -> tuple[str, str]:
    source_url = _https_url(source_url)
    host = urlparse(source_url).hostname.lower()
    return ("github" if "github" in host else "gitee"), source_url


class ReleaseResolver:
    def __init__(self, client: httpx.Client | None = None, *, max_bytes: int = MAX_RELEASE_BYTES):
        self.client = client
        self.max_bytes = max_bytes

    def _request(self, url: str) -> tuple[str, bytes, str]:
        current = _https_url(url)
        owns_client = self.client is None
        client = self.client or httpx.Client(timeout=RELEASE_TIMEOUT, follow_redirects=False)
        try:
            for _ in range(MAX_REDIRECTS + 1):
                response = client.get(current)
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location:
                        raise ReleaseResolverError("redirect missing location")
                    current = _https_url(str(httpx.URL(current).join(location)))
                    continue
                if response.status_code >= 400:
                    raise ReleaseResolverError(f"release download failed: HTTP {response.status_code}")
                declared = response.headers.get("content-length")
                if declared and int(declared) > self.max_bytes:
                    raise ReleaseResolverError("release exceeds maximum size")
                content = response.content
                if len(content) > self.max_bytes:
                    raise ReleaseResolverError("release exceeds maximum size")
                return current, content, response.headers.get("content-type", "")
            raise ReleaseResolverError("too many redirects")
        finally:
            if owns_client:
                client.close()

    def resolve(self, source_url: str, *, plugin_id: str = "", version: str = "") -> ReleaseArtifact:
        provider, url = _provider_url(source_url)
        parsed = urlparse(url)
        if "/releases/tag/" in parsed.path:
            parts = [unquote(part) for part in parsed.path.split("/") if part]
            try:
                owner, repo, tag = parts[0], parts[1], parts[parts.index("releases") + 2]
            except (IndexError, ValueError) as exc:
                raise ReleaseResolverError("invalid release page URL") from exc
            api_host = "api.github.com" if provider == "github" else "gitee.com"
            api_path = f"/repos/{owner}/{repo}/releases/tags/{tag}" if provider == "github" else f"/api/v5/repos/{owner}/{repo}/releases/tags/{tag}"
            _, metadata, _ = self._request(f"https://{api_host}{api_path}")
            try:
                assets = json.loads(metadata.decode("utf-8")).get("assets", [])
                asset_url = next((item.get("browser_download_url") or item.get("download_url") for item in assets if str(item.get("name", "")).lower().endswith(".zip")), None)
            except (UnicodeDecodeError, json.JSONDecodeError, AttributeError) as exc:
                raise ReleaseResolverError("invalid release metadata") from exc
            if not asset_url:
                raise ReleaseResolverError("release has no ZIP asset")
            url = _https_url(asset_url)
        final_url, content, content_type = self._request(url)
        if not content:
            raise ReleaseResolverError("empty release artifact")
        if not (final_url.lower().endswith(".zip") or "zip" in content_type.lower()):
            raise ReleaseResolverError("release artifact must be a ZIP package")
        return ReleaseArtifact(plugin_id=plugin_id, version=version, url=final_url, content=content, provider=provider)

    @staticmethod
    def parse_release_payload(source_url: str, payload: bytes) -> dict:
        _provider_url(source_url)
        try:
            value = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ReleaseResolverError("invalid release metadata") from exc
        if not isinstance(value, dict):
            raise ReleaseResolverError("invalid release metadata")
        return value
