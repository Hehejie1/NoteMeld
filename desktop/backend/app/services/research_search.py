from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any, Protocol
from urllib.parse import quote

import httpx
from pydantic import BaseModel, Field

from app.models.learning_canvas import LearningSource
from app.services.research_search_config import ResearchSearchConfigManager


class ResearchProvider(Protocol):
    name: str

    def search(self, query: str, limit: int) -> list[LearningSource]: ...


class ResearchSearchError(BaseModel):
    provider: str
    code: str
    message: str


class ResearchSearchBundle(BaseModel):
    sources: list[LearningSource] = Field(default_factory=list)
    errors: list[ResearchSearchError] = Field(default_factory=list)


def _default_client(timeout: float = 15.0) -> httpx.Client:
    return httpx.Client(
        timeout=timeout,
        headers={"User-Agent": "NoteMeld/0.0.4 research-search"},
        follow_redirects=True,
    )


class ArxivSearchProvider:
    name = "arxiv"
    endpoint = "https://export.arxiv.org/api/query"
    _ns = {"atom": "http://www.w3.org/2005/Atom"}

    def __init__(self, client: httpx.Client | None = None):
        self.client = client or _default_client()

    def search(self, query: str, limit: int = 5) -> list[LearningSource]:
        response = self.client.get(
            self.endpoint,
            params={"search_query": f"all:{query}", "start": 0, "max_results": limit},
        )
        response.raise_for_status()
        root = ET.fromstring(response.text)
        sources: list[LearningSource] = []
        for entry in root.findall("atom:entry", self._ns)[:limit]:
            url = self._text(entry, "atom:id")
            arxiv_id = url.rstrip("/").rsplit("/", 1)[-1]
            version_match = re.search(r"(v\d+)$", arxiv_id)
            authors = [
                (author.findtext("atom:name", default="", namespaces=self._ns) or "").strip()
                for author in entry.findall("atom:author", self._ns)
            ]
            sources.append(
                LearningSource(
                    id=f"arxiv:{arxiv_id}",
                    source_type="academic",
                    provider=self.name,
                    title=" ".join(self._text(entry, "atom:title").split()),
                    url=url,
                    snippet=" ".join(self._text(entry, "atom:summary").split()),
                    published_at=self._text(entry, "atom:published") or None,
                    authors=[name for name in authors if name],
                    version=version_match.group(1) if version_match else None,
                )
            )
        return sources

    def _text(self, entry: ET.Element, path: str) -> str:
        return (entry.findtext(path, default="", namespaces=self._ns) or "").strip()


class GitHubSearchProvider:
    name = "github"
    endpoint = "https://api.github.com/search/repositories"

    def __init__(self, token: str = "", client: httpx.Client | None = None):
        self.token = token
        self.client = client or _default_client()

    def search(self, query: str, limit: int = 5) -> list[LearningSource]:
        headers = {"Accept": "application/vnd.github+json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        response = self.client.get(
            self.endpoint,
            params={"q": query, "per_page": limit, "sort": "stars"},
            headers=headers,
        )
        response.raise_for_status()
        items = response.json().get("items") or []
        sources: list[LearningSource] = []
        for item in items[:limit]:
            repository = str(item.get("full_name") or "").strip()
            if not repository:
                continue
            license_payload = item.get("license") or {}
            sources.append(
                LearningSource(
                    id=f"github:{repository}",
                    source_type="github",
                    provider=self.name,
                    title=repository,
                    url=item.get("html_url"),
                    snippet=str(item.get("description") or ""),
                    published_at=item.get("updated_at"),
                    repository=repository,
                    default_branch=item.get("default_branch"),
                    stars=item.get("stargazers_count"),
                    license=license_payload.get("spdx_id"),
                )
            )
        return sources


class SearxngSearchProvider:
    name = "searxng"

    def __init__(self, endpoint: str, client: httpx.Client | None = None):
        self.endpoint = endpoint.rstrip("/")
        self.client = client or _default_client()

    def search(self, query: str, limit: int = 5) -> list[LearningSource]:
        response = self.client.get(
            f"{self.endpoint}/search",
            params={"q": query, "format": "json"},
        )
        response.raise_for_status()
        return [
            LearningSource(
                id=f"web:searxng:{index}:{abs(hash(item.get('url') or ''))}",
                source_type="web",
                provider=self.name,
                title=str(item.get("title") or item.get("url") or ""),
                url=item.get("url"),
                snippet=str(item.get("content") or ""),
                published_at=item.get("publishedDate"),
            )
            for index, item in enumerate((response.json().get("results") or [])[:limit])
            if item.get("url")
        ]


class TavilySearchProvider:
    name = "tavily"
    endpoint = "https://api.tavily.com/search"

    def __init__(self, api_key: str, client: httpx.Client | None = None):
        self.api_key = api_key
        self.client = client or _default_client()

    def search(self, query: str, limit: int = 5) -> list[LearningSource]:
        response = self.client.post(
            self.endpoint,
            json={"api_key": self.api_key, "query": query, "max_results": limit},
        )
        response.raise_for_status()
        return [
            LearningSource(
                id=f"web:tavily:{index}:{abs(hash(item.get('url') or ''))}",
                source_type="web",
                provider=self.name,
                title=str(item.get("title") or item.get("url") or ""),
                url=item.get("url"),
                snippet=str(item.get("content") or ""),
                published_at=item.get("published_date"),
            )
            for index, item in enumerate((response.json().get("results") or [])[:limit])
            if item.get("url")
        ]


class ResearchSearchService:
    def __init__(self, providers: dict[str, list[ResearchProvider]] | None = None):
        self.providers = providers or {}

    def search(self, query: str, scopes: list[str], limit: int = 5) -> ResearchSearchBundle:
        bundle = ResearchSearchBundle()
        seen: set[str] = set()
        for scope in scopes:
            for provider in self.providers.get(scope, []):
                try:
                    results = provider.search(query, limit)
                    for source in results:
                        key = source.url or source.id
                        if key in seen:
                            continue
                        seen.add(key)
                        bundle.sources.append(source)
                except (httpx.TimeoutException, httpx.ConnectError) as exc:
                    bundle.errors.append(
                        ResearchSearchError(
                            provider=provider.name,
                            code="provider_down",
                            message=str(exc),
                        )
                    )
                except httpx.HTTPStatusError as exc:
                    code = "auth_error" if exc.response.status_code in {401, 403} else "provider_error"
                    bundle.errors.append(
                        ResearchSearchError(
                            provider=provider.name,
                            code=code,
                            message=f"HTTP {exc.response.status_code}",
                        )
                    )
                except Exception as exc:
                    bundle.errors.append(
                        ResearchSearchError(
                            provider=provider.name,
                            code="provider_error",
                            message=str(exc),
                        )
                    )
        return bundle


def build_research_search_service(
    manager: ResearchSearchConfigManager | None = None,
) -> ResearchSearchService:
    config = (manager or ResearchSearchConfigManager()).get_config()
    timeout = max(5.0, min(float(config.get("timeout_seconds") or 15), 30.0))
    providers: dict[str, list[ResearchProvider]] = {
        "academic": [ArxivSearchProvider(client=_default_client(timeout))],
        "github": [
            GitHubSearchProvider(
                token=str(config.get("github_token") or ""),
                client=_default_client(timeout),
            )
        ],
    }
    web_provider = str(config.get("web_provider") or "disabled")
    if web_provider == "searxng" and config.get("searxng_endpoint"):
        providers["web"] = [
            SearxngSearchProvider(
                str(config["searxng_endpoint"]), client=_default_client(timeout)
            )
        ]
    elif web_provider == "tavily" and config.get("tavily_api_key"):
        providers["web"] = [
            TavilySearchProvider(
                str(config["tavily_api_key"]), client=_default_client(timeout)
            )
        ]
    return ResearchSearchService(providers=providers)

