from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agent_host.capabilities import InvalidCapabilityArguments, NoteMeldCapabilityRegistry


def _invoke(registry, name, arguments):
    return asyncio.run(registry.invoke(
        name,
        arguments,
        "call-1",
        SimpleNamespace(session_id="session-1", turn_id="turn-1"),
        lambda _event: None,
    ))


def test_conversion_capabilities_are_explicitly_discoverable():
    registry = NoteMeldCapabilityRegistry()
    requested = ["document:to_markdown", "image:ocr", "video:fetch", "audio:extract", "audio:transcribe", "video:frames"]
    names = [item["name"] for item in registry.describe(requested)]
    assert names == requested
    assert registry.get_tool("image:ascii") is None


def test_mcp_exposes_the_same_atomic_capability_family():
    from app.mcp.service import TOOL_DEFINITIONS

    names = {item["name"] for item in TOOL_DEFINITIONS}
    assert {
        "notemeld_document_to_markdown", "notemeld_image_ocr", "notemeld_video_fetch",
        "notemeld_audio_extract", "notemeld_audio_transcribe", "notemeld_video_frames",
    }.issubset(names)


def test_document_conversion_returns_artifact_without_note_write(monkeypatch):
    expected = {
        "schema_version": "conversion-artifact.v1",
        "request_id": "request-1",
        "status": "completed",
        "artifact": {"kind": "markdown", "content": "# Imported"},
    }
    monkeypatch.setattr("app.agent_host.capabilities.convert_document_to_markdown", lambda **_kwargs: expected)
    result = _invoke(
        NoteMeldCapabilityRegistry(),
        "document:to_markdown",
        {"file_url": "/api/note/uploads/file-1.pdf", "file_name": "file.pdf", "request_id": "request-1"},
    )
    assert result is expected
    assert result["artifact"]["kind"] == "markdown"


def test_image_ocr_preserves_positioned_lines(monkeypatch):
    expected = {
        "schema_version": "conversion-artifact.v1",
        "request_id": "request-2",
        "status": "completed",
        "artifact": {"kind": "ocr", "metadata": {"lines": [{"text": "你好", "bbox": [1, 2, 30, 12]}]}},
    }
    monkeypatch.setattr("app.agent_host.capabilities.extract_image_ocr", lambda **_kwargs: expected)
    result = _invoke(
        NoteMeldCapabilityRegistry(),
        "image:ocr",
        {"file_url": "/api/note/uploads/file-2.png", "file_name": "file.png", "request_id": "request-2"},
    )
    assert result["artifact"]["metadata"]["lines"][0]["bbox"] == [1, 2, 30, 12]


def test_conversion_capabilities_require_uploaded_file_arguments():
    registry = NoteMeldCapabilityRegistry()
    with pytest.raises(InvalidCapabilityArguments):
        _invoke(registry, "document:to_markdown", {"file_name": "file.pdf"})
    with pytest.raises(InvalidCapabilityArguments):
        _invoke(registry, "image:ocr", {"file_url": "/uploads/file.png"})


@pytest.mark.parametrize(
    ("capability", "function_name", "arguments"),
    [
        ("video:fetch", "fetch_video_media", {"source_url": "https://example.com/video"}),
        ("audio:extract", "extract_audio", {"source_url": "https://example.com/video"}),
        ("audio:transcribe", "transcribe_audio", {"source_url": "https://example.com/video"}),
        ("video:frames", "extract_video_frames", {"source_url": "https://example.com/video"}),
    ],
)
def test_media_atomic_capabilities_return_tool_artifacts(monkeypatch, capability, function_name, arguments):
    expected = {"schema_version": "conversion-artifact.v1", "request_id": "call-1", "status": "completed", "artifact": {"kind": "media"}}
    monkeypatch.setattr(f"app.agent_host.capabilities.{function_name}", lambda **_kwargs: expected)
    result = _invoke(NoteMeldCapabilityRegistry(), capability, arguments)
    assert result is expected


def test_document_plugin_jsonl_smoke_when_built(tmp_path, monkeypatch):
    binary = Path(__file__).parents[4] / "notemeld-plugins" / "plugins" / "official-document-to-markdown" / "target" / "debug" / "notemeld-document-to-markdown"
    if not binary.is_file():
        pytest.skip("document plugin binary is not built")
    input_path = tmp_path / "table.csv"
    input_path.write_text("name,value\nalpha,1\n", encoding="utf-8")
    monkeypatch.setattr("app.services.document_conversion_plugin.resolve_uploaded_file_path", lambda _url: input_path)
    result = __import__("app.services.document_conversion_plugin", fromlist=["convert_document_to_markdown"]).convert_document_to_markdown(
        file_url="/api/note/uploads/table.csv",
        file_name="table.csv",
        request_id="plugin-smoke",
    )
    assert result["status"] == "completed"
    assert result["artifact"]["format"] == "csv"
    assert "alpha" in result["artifact"]["content"]
