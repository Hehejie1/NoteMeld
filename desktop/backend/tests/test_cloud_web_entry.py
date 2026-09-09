from fastapi.testclient import TestClient

from cloud.app import create_app
from cloud.config import CloudSettings


def test_cloud_root_serves_login_page_and_static_assets(tmp_path):
    settings = CloudSettings(tmp_path / "data", "admin", "admin-password-123")
    with TestClient(create_app(settings)) as client:
        root = client.get("/", follow_redirects=False)
        assert root.status_code == 307
        assert root.headers["location"] == "/cloud/pages/cloud/c01.html"

        page = client.get(root.headers["location"])
        assert page.status_code == 200
        assert "登录 NoteMeld 云端" in page.text

        asset = client.get("/cloud/assets/cloud.css")
        assert asset.status_code == 200
        assert "cloud-page" in asset.text
