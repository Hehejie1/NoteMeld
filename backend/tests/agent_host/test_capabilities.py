from __future__ import annotations

import asyncio

from app.agent_host.capabilities import NoteMeldCapabilityRegistry


def test_capability_registry_exposes_only_bounded_read_tools():
    registry = NoteMeldCapabilityRegistry()
    names = [item["name"] for item in registry.describe([])]
    assert names == ["wiki:search", "note:search", "note:read"]
    assert registry.get_tool("note:delete") is None


def test_wiki_search_capability_uses_existing_service(monkeypatch):
    registry = NoteMeldCapabilityRegistry()
    monkeypatch.setattr(
        "app.agent_host.capabilities.WikiSearch.search",
        lambda self, query, limit: [{"title": query, "limit": limit}],
    )
    progress = []

    result = asyncio.run(registry.invoke(
        "wiki:search",
        {"query": "agent", "limit": 2},
        "call-1",
        object(),
        lambda event: progress.append(event),
    ))

    assert result == [{"title": "agent", "limit": 2}]
    assert progress[-1]["progress"] == 1.0
