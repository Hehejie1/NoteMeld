from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Protocol

from app.models.multisource_summary import WebSearchResult
from app.utils.storage_paths import note_output_dir


class WebSearchProvider(Protocol):
    def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        ...


class DisabledWebSearchProvider:
    def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        return []


def get_web_search_provider() -> WebSearchProvider | None:
    provider_name = (os.getenv("NOTEMELD_WEB_SEARCH_PROVIDER", "") or "").strip().lower()
    if not provider_name:
        return None
    if provider_name in {"disabled", "none"}:
        return None
    raise ValueError(f"Unsupported Web Search provider: {provider_name}")


class WebSearchCollector:
    def __init__(self, provider: WebSearchProvider | None = None, output_dir: Path | None = None):
        self.provider = provider
        self.output_dir = output_dir or note_output_dir()

    def collect(
        self,
        *,
        task_id: str,
        source_url: str,
        title: str,
        platform: str,
        description: str | None,
    ) -> WebSearchResult:
        cache_path = self.output_dir / f"{task_id}_web_search.json"
        cached = self._read_cache(cache_path)
        if cached:
            return cached
        if self.provider is None:
            return WebSearchResult(source="web_search", status="skipped", error="web search provider not configured")

        query = self._build_query(source_url=source_url, title=title, platform=platform, description=description)
        try:
            sources = self.provider.search(query, limit=5)
        except Exception as exc:
            return WebSearchResult(source="web_search", status="failed", error=str(exc))

        normalized = self._normalize_sources(sources)
        content = self._format_sources(normalized)
        result = WebSearchResult(
            source="web_search",
            status="done" if normalized else "skipped",
            content=content,
            confidence=0.7 if normalized else 0.0,
            sources=normalized,
            artifacts={"query": query},
        )
        self._write_cache(cache_path, result)
        return result

    def _build_query(self, *, source_url: str, title: str, platform: str, description: str | None) -> str:
        parts = [title.strip(), platform.strip(), source_url.strip()]
        if description:
            parts.append(description.strip()[:120])
        return " ".join(part for part in parts if part)

    def _normalize_sources(self, sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        seen_urls: set[str] = set()
        for item in sources:
            url = str(item.get("url") or "").strip()
            title = str(item.get("title") or "").strip()
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            normalized.append(
                {
                    "title": title or url,
                    "url": url,
                    "snippet": str(item.get("snippet") or item.get("summary") or "").strip(),
                    "published_at": item.get("published_at"),
                    "confidence": float(item.get("confidence") or 0.5),
                }
            )
        return normalized[:5]

    def _format_sources(self, sources: list[dict[str, Any]]) -> str:
        lines = []
        for index, source in enumerate(sources, start=1):
            lines.append(
                f"{index}. {source['title']}\n"
                f"URL: {source['url']}\n"
                f"Summary: {source.get('snippet') or ''}\n"
                f"Confidence: {source.get('confidence', 0.0)}"
            )
        return "\n\n".join(lines)

    def _read_cache(self, cache_path: Path) -> WebSearchResult | None:
        if not cache_path.exists():
            return None
        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            return WebSearchResult(**payload)
        except Exception:
            return None

    def _write_cache(self, cache_path: Path, result: WebSearchResult) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(result.__dict__, ensure_ascii=False, indent=2), encoding="utf-8")
