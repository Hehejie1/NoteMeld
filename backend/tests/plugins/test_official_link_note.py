from __future__ import annotations

import importlib.util
import hashlib
import json
import sys
import zipfile
from pathlib import Path

import pytest


SOURCE = Path(__file__).resolve().parents[3] / "plugins" / "official-link-note" / "src" / "official_link_note.py"
spec = importlib.util.spec_from_file_location("official_link_note_fixture", SOURCE)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class Host:
    def __init__(self):
        self.calls = []

    def generate_video(self, **kwargs):
        self.calls.append(("video", kwargs))
        return kwargs

    def generate_web(self, **kwargs):
        self.calls.append(("web", kwargs))
        return kwargs


def test_plugin_routes_every_n01_platform_through_host_port():
    host = Host()
    plugin = module.OfficialLinkNotePlugin(host)
    urls = {
        "youtube": "https://www.youtube.com/watch?v=abc123",
        "bilibili": "https://www.bilibili.com/video/BV123",
        "tiktok": "https://www.tiktok.com/@demo/video/123",
        "kuaishou": "https://www.kuaishou.com/short-video/abc",
        "douyin": "https://www.douyin.com/video/123",
        "wechat_channels": "https://channels.weixin.qq.com/finder-preview/pages/feed?feed_id=1",
        "local": "/tmp/example.mp4",
    }
    for platform in module.SUPPORTED_PLATFORMS:
        plugin.execute(task_id="t", url=urls[platform], platform=platform, options={})
    assert [kind for kind, _ in host.calls] == ["video"] * len(module.SUPPORTED_PLATFORMS)


def test_plugin_routes_web_fallback_without_application_state_access():
    host = Host()
    result = module.OfficialLinkNotePlugin(host).execute(
        task_id="t", url="https://example.test/page", platform="youtube", force_web_fallback=True
    )
    assert host.calls[0][0] == "web"
    assert result["web_url"] == "https://example.test/page"


@pytest.mark.parametrize("platform", ["", "unknown"])
def test_plugin_rejects_unknown_platforms(platform):
    with pytest.raises(module.UnsupportedLinkError):
        module.route_link("https://example.test/item", platform)


def test_plugin_manifest_has_stable_capability_contract():
    descriptor = module.OfficialLinkNotePlugin.descriptor()
    assert descriptor["id"] == "official-link-note:create"
    assert descriptor["portable"] is True
    assert descriptor["input_schema"]["required"] == ["url", "platform"]


def test_plugin_owns_n01_url_validation():
    assert module.validate_link("https://www.youtube.com/watch?v=abc", "youtube")
    with pytest.raises(module.LinkNoteError):
        module.validate_link("https://example.test/not-youtube", "youtube")


def test_local_release_fixture_matches_manifest_and_index():
    root = SOURCE.parents[1]
    manifest = json.loads((root / "manifest.json").read_text())
    index = json.loads((root / "package-index.json").read_text())
    assert manifest["package"] == index
    assert (root / "release-fixture" / "official-link-note-1.0.0.zip").exists()
    with zipfile.ZipFile(root / "release-fixture" / "official-link-note-1.0.0.zip") as archive:
        assert set(archive.namelist()) == {"manifest.json", "package-index.json", "README.md", "src/official_link_note.py"}
        for item in index["files"]:
            payload = archive.read(item["path"])
            assert len(payload) == item["size"]
            assert "sha256:" + hashlib.sha256(payload).hexdigest() == item["sha256"]
