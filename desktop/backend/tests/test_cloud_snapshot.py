from pathlib import Path
import pytest
from app.cloud_sync.snapshot import SnapshotError, build_import_snapshot


def test_snapshot_excludes_local_only_and_symlink_files(tmp_path: Path):
    (tmp_path / "notes").mkdir(); (tmp_path / "notes" / "readme.md").write_text("hello")
    (tmp_path / ".env.local").write_text("TOKEN=secret"); (tmp_path / "plugins").mkdir(); (tmp_path / "plugins" / "x.py").write_text("secret")
    outside = tmp_path.parent / "outside.txt"; outside.write_text("outside"); (tmp_path / "link.txt").symlink_to(outside)
    payload = build_import_snapshot(request_id="r1", source_session_id="s1", source_device_id="desktop-1", workspace_root=tmp_path)
    assert [item["path"] for item in payload["files"]] == ["notes/readme.md"]
    assert payload["files"][0]["size"] == 5 and payload["files"][0]["mime_type"] == "text/markdown"


def test_snapshot_enforces_limits(tmp_path: Path):
    (tmp_path / "a.txt").write_text("12345")
    with pytest.raises(SnapshotError, match="byte limit"):
        build_import_snapshot(request_id="r1", source_session_id="s1", source_device_id="desktop-1", workspace_root=tmp_path, max_bytes=4)
    with pytest.raises(SnapshotError, match="file limit"):
        build_import_snapshot(request_id="r1", source_session_id="s1", source_device_id="desktop-1", workspace_root=tmp_path, max_files=0)


def test_snapshot_rejects_symlink_root(tmp_path: Path):
    link = tmp_path / "root-link"; link.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(SnapshotError, match="non-symlink"):
        build_import_snapshot(request_id="r1", source_session_id="s1", source_device_id="desktop-1", workspace_root=link)
