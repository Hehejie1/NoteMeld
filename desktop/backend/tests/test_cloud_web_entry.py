from pathlib import Path

from fastapi.testclient import TestClient

from cloud.app import create_app
from cloud.config import CloudSettings


def test_cloud_root_serves_login_page_and_static_assets(tmp_path):
    settings = CloudSettings(tmp_path / "data", "admin", "admin-password-123")
    with TestClient(create_app(settings)) as client:
        root = client.get("/", follow_redirects=False)
        assert root.status_code == 307
        assert root.headers["location"] == "/cloud/login"

        page = client.get(root.headers["location"])
        source_dist = Path(__file__).resolve().parents[3] / "desktop" / "frontend" / "dist-cloud-web"
        if source_dist.is_dir():
            assert page.status_code == 200
            # Cloud Web is a production SPA entry; route content is rendered
            # client-side, so the server response must expose the built entry
            # and its hashed asset references rather than prototype HTML.
            assert "NoteMeld Cloud" in page.text
            assert "<script type=\"module\" crossorigin src=\"/assets/" in page.text
            assert any(source_dist.joinpath("assets").iterdir())
        else:
            assert page.status_code == 404
