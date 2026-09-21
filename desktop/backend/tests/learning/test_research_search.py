from __future__ import annotations

import json

import httpx

from app.services.research_search import (
    ArxivSearchProvider,
    GitHubSearchProvider,
    ResearchSearchService,
)
from app.services.research_search_config import ResearchSearchConfigManager


def test_config_masks_secrets_and_empty_updates_preserve_them(tmp_path) -> None:
    path = tmp_path / "research_search.json"
    manager = ResearchSearchConfigManager(path=path)
    manager.update_config(
        {
            "enabled_scopes": ["academic", "github"],
            "tavily_api_key": "tvly-secret",
            "github_token": "gh-secret",
        }
    )

    public = manager.get_public_config()
    assert public["tavily_api_key_set"] is True
    assert public["github_token_set"] is True
    assert "tvly-secret" not in json.dumps(public)
    assert "gh-secret" not in json.dumps(public)

    manager.update_config({"tavily_api_key": "", "github_token": ""})
    stored = manager.get_config()
    assert stored["tavily_api_key"] == "tvly-secret"
    assert stored["github_token"] == "gh-secret"


def test_learning_scopes_always_include_academic_and_github(tmp_path) -> None:
    manager = ResearchSearchConfigManager(path=tmp_path / "research_search.json")
    manager.update_config({"enabled_scopes": []})

    assert manager.get_learning_scopes() == ["academic", "github"]
    assert manager.get_learning_scopes(["academic"]) == ["academic", "github"]


def test_learning_scopes_add_web_only_when_provider_is_usable(tmp_path) -> None:
    manager = ResearchSearchConfigManager(path=tmp_path / "research_search.json")

    manager.update_config({"web_provider": "searxng", "searxng_endpoint": ""})
    assert manager.get_learning_scopes(["web"]) == ["academic", "github"]

    manager.update_config(
        {
            "web_provider": "searxng",
            "searxng_endpoint": "https://search.example.com",
        }
    )
    assert manager.get_learning_scopes() == ["academic", "github", "web"]

    tavily_manager = ResearchSearchConfigManager(
        path=tmp_path / "research_search_tavily.json"
    )
    tavily_manager.update_config(
        {"web_provider": "tavily", "tavily_api_key": "tvly-secret"}
    )
    assert tavily_manager.get_learning_scopes() == ["academic", "github", "web"]


def test_learning_scopes_reject_invalid_searxng_endpoint(tmp_path) -> None:
    manager = ResearchSearchConfigManager(path=tmp_path / "research_search.json")
    manager.update_config(
        {"web_provider": "searxng", "searxng_endpoint": "search-without-scheme"}
    )

    assert manager.get_learning_scopes() == ["academic", "github"]


def test_arxiv_provider_preserves_paper_metadata() -> None:
    payload = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <id>https://arxiv.org/abs/2608.01234v2</id>
        <updated>2026-08-10T00:00:00Z</updated>
        <published>2026-08-01T00:00:00Z</published>
        <title>  Learning Agents  </title>
        <summary> Evidence based learning. </summary>
        <author><name>Alice</name></author>
        <author><name>Bob</name></author>
      </entry>
    </feed>"""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "export.arxiv.org"
        return httpx.Response(200, text=payload)

    provider = ArxivSearchProvider(
        client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    sources = provider.search("learning agents", limit=5)

    assert len(sources) == 1
    source = sources[0]
    assert source.id == "arxiv:2608.01234v2"
    assert source.source_type == "academic"
    assert source.authors == ["Alice", "Bob"]
    assert source.published_at == "2026-08-01T00:00:00Z"
    assert source.version == "v2"


def test_github_provider_preserves_repository_metadata() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer gh-token"
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": 42,
                        "full_name": "org/project",
                        "html_url": "https://github.com/org/project",
                        "description": "Official implementation",
                        "stargazers_count": 123,
                        "default_branch": "main",
                        "updated_at": "2026-08-09T00:00:00Z",
                        "license": {"spdx_id": "Apache-2.0"},
                    }
                ]
            },
        )

    provider = GitHubSearchProvider(
        token="gh-token",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    sources = provider.search("project", limit=5)

    assert len(sources) == 1
    source = sources[0]
    assert source.id == "github:org/project"
    assert source.source_type == "github"
    assert source.repository == "org/project"
    assert source.default_branch == "main"
    assert source.stars == 123
    assert source.license == "Apache-2.0"


class _GoodProvider:
    name = "good"

    def search(self, query: str, limit: int):
        from app.models.learning_canvas import LearningSource

        return [
            LearningSource(
                id="web:good",
                source_type="web",
                provider="good",
                title=query,
                url="https://example.com/good",
            )
        ]


class _FailingProvider:
    name = "failing"

    def search(self, query: str, limit: int):
        raise httpx.TimeoutException("timed out")


def test_search_service_keeps_partial_success_and_typed_error() -> None:
    service = ResearchSearchService(
        providers={"web": [_GoodProvider()], "github": [_FailingProvider()]}
    )

    bundle = service.search("agent learning", scopes=["web", "github"], limit=5)

    assert [source.id for source in bundle.sources] == ["web:good"]
    assert len(bundle.errors) == 1
    assert bundle.errors[0].provider == "failing"
    assert bundle.errors[0].code == "provider_down"
    assert "timed out" in bundle.errors[0].message
