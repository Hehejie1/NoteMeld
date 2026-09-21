import sys


def test_bundled_fixture_discovers_workspace_packages_plugin_root(tmp_path, monkeypatch):
    from app.services import official_link_note_host as host

    fixture = tmp_path / "packages" / "notemeld-plugins" / "plugins" / "official-link-note" / "release-fixture" / "official-link-note-1.0.0.zip"
    fixture.parent.mkdir(parents=True)
    fixture.write_bytes(b"fixture")
    monkeypatch.setattr(host, "project_root", lambda: tmp_path / "NoteMeld")
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)

    assert host._bundled_fixture() == fixture


def test_document_converter_discovers_workspace_packages_plugin_root(tmp_path, monkeypatch):
    from app.services import document_conversion_plugin as converter

    plugin_root = tmp_path / "packages" / "notemeld-plugins" / "plugins" / "official-document-to-markdown"
    plugin_root.mkdir(parents=True)
    monkeypatch.setattr(converter.Path, "resolve", lambda _path: tmp_path / "NoteMeld" / "desktop" / "backend" / "app" / "services" / "document_conversion_plugin.py")
    monkeypatch.delenv("NOTEMELD_PLUGINS_DIR", raising=False)

    assert converter._plugin_root() == plugin_root
