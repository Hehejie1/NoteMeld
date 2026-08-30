from pathlib import Path
from fastapi.testclient import TestClient
from cloud.app import create_app
from cloud.config import CloudSettings


def test_device_connectivity_candidates_are_validated_and_returned(tmp_path: Path):
    with TestClient(create_app(CloudSettings(tmp_path / "data", "admin", "admin-password-123"))) as http:
        token = http.post("/v1/auth/login", json={"username": "admin", "password": "admin-password-123"}).json()["data"]["token"]
        headers = {"Authorization": f"Bearer {token}"}
        response = http.post("/v1/devices/register", headers=headers, json={"device_id": "desktop-001", "platform": "desktop", "display_name": "Mac", "lan_endpoints": ["192.168.1.20:8583"]})
        assert response.status_code == 200
        devices = http.get("/v1/devices", headers=headers).json()["data"]
        assert devices[0]["connectivity"]["lan_endpoints"] == ["192.168.1.20:8583"]
        assert devices[0]["online"] is True
        assert http.post("/v1/devices/register", headers=headers, json={"device_id": "desktop-002", "platform": "desktop", "display_name": "Bad", "lan_endpoints": ["8.8.8.8:8583"]}).status_code == 422
        assert http.post("/v1/devices/desktop-001/heartbeat", headers=headers, json={"lan_endpoints": ["192.168.1.21:8583"]}).status_code == 200
