from __future__ import annotations

import pytest

from app.agent_host.workspace_adapter import WorkspaceAdapterError, list_directory, read_file


def test_workspace_adapter_reads_only_safe_product_workspace(monkeypatch, tmp_path):
    monkeypatch.setenv("NOTEMELD_DATA_DIR", str(tmp_path))
    root = tmp_path / "note_results" / "workspaces" / "conv-1"
    root.mkdir(parents=True)
    (root / "note.md").write_text("hello", encoding="utf-8")

    assert list_directory("conv-1")["entries"][0]["name"] == "note.md"
    assert read_file("conv-1", "note.md")["content"] == "hello"
    with pytest.raises(WorkspaceAdapterError):
        read_file("conv-1", "../secret")
