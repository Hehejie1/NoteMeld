from __future__ import annotations

import pathlib
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))


def test_catalog_prefers_exact_rule_over_later_family_rule():
    from app.services.model_runtime_catalog import resolve_model_runtime_defaults

    defaults = resolve_model_runtime_defaults(" DEEPSEEK-CHAT ")

    assert defaults.model_name == "deepseek-chat"
    assert defaults.context_window_tokens == 65536
    assert defaults.supports_vision is False
    assert defaults.supports_stream is True
    assert defaults.source == "catalog"
    assert defaults.matched_rule == "deepseek-chat"


def test_catalog_matches_deepseek_r1_family_in_catalog_order():
    from app.services.model_runtime_catalog import resolve_model_runtime_defaults

    defaults = resolve_model_runtime_defaults("deepseek-r1:7b")

    assert defaults.context_window_tokens == 131072
    assert defaults.supports_vision is False
    assert defaults.supports_stream is True
    assert defaults.source == "catalog"
    assert defaults.matched_rule == "deepseek-r1:*"


def test_catalog_marks_qwen_vl_family_as_vision_capable():
    from app.services.model_runtime_catalog import resolve_model_runtime_defaults

    defaults = resolve_model_runtime_defaults(" QWEN2.5VL:7B ")

    assert defaults.model_name == "qwen2.5vl:7b"
    assert defaults.context_window_tokens == 32768
    assert defaults.supports_vision is True
    assert defaults.supports_stream is True
    assert defaults.source == "catalog"
    assert defaults.matched_rule == "qwen2.5vl:*"


def test_catalog_returns_safe_fallback_for_unknown_model():
    from app.services.model_runtime_catalog import resolve_model_runtime_defaults

    defaults = resolve_model_runtime_defaults(" company/custom-model ")

    assert defaults.model_name == "company/custom-model"
    assert defaults.context_window_tokens == 4096
    assert defaults.supports_vision is False
    assert defaults.supports_stream is True
    assert defaults.source == "fallback"
    assert defaults.matched_rule is None


def test_catalog_falls_back_when_catalog_json_is_invalid(monkeypatch, tmp_path, caplog):
    from app.services import model_runtime_catalog

    invalid_catalog = tmp_path / "model_runtime_catalog.json"
    invalid_catalog.write_text("{ invalid json", encoding="utf-8")
    monkeypatch.setattr(model_runtime_catalog, "_CATALOG_PATH", invalid_catalog)
    model_runtime_catalog._load_catalog.cache_clear()
    try:
        defaults = model_runtime_catalog.resolve_model_runtime_defaults("deepseek-r1:7b")

        assert defaults.context_window_tokens == 4096
        assert defaults.supports_vision is False
        assert defaults.supports_stream is True
        assert defaults.source == "fallback"
        assert "model runtime catalog" in caplog.text.lower()
    finally:
        model_runtime_catalog._load_catalog.cache_clear()


def test_catalog_falls_back_when_catalog_json_has_invalid_schema(monkeypatch, tmp_path, caplog):
    from app.services import model_runtime_catalog

    invalid_catalog = tmp_path / "model_runtime_catalog.json"
    invalid_catalog.write_text('{"version": 1, "fallback": [], "models": []}', encoding="utf-8")
    monkeypatch.setattr(model_runtime_catalog, "_CATALOG_PATH", invalid_catalog)
    model_runtime_catalog._load_catalog.cache_clear()
    try:
        defaults = model_runtime_catalog.resolve_model_runtime_defaults("deepseek-r1:7b")

        assert defaults.context_window_tokens == 4096
        assert defaults.supports_vision is False
        assert defaults.supports_stream is True
        assert defaults.source == "fallback"
        assert "model runtime catalog" in caplog.text.lower()
    finally:
        model_runtime_catalog._load_catalog.cache_clear()


def test_catalog_falls_back_when_context_window_is_zero_or_negative(monkeypatch, tmp_path, caplog):
    from app.services import model_runtime_catalog

    invalid_catalog = tmp_path / "model_runtime_catalog.json"
    invalid_catalog.write_text(
        """
        {
          "version": 1,
          "fallback": {"context_window_tokens": 0, "supports_vision": false, "supports_stream": true},
          "models": [
            {"match": "deepseek-r1:*", "context_window_tokens": -1, "supports_vision": false, "supports_stream": true}
          ]
        }
        """,
        encoding="utf-8",
    )
    monkeypatch.setattr(model_runtime_catalog, "_CATALOG_PATH", invalid_catalog)
    model_runtime_catalog._load_catalog.cache_clear()
    try:
        defaults = model_runtime_catalog.resolve_model_runtime_defaults("deepseek-r1:7b")

        assert defaults.context_window_tokens == 4096
        assert defaults.supports_vision is False
        assert defaults.supports_stream is True
        assert defaults.source == "fallback"
        assert "model runtime catalog" in caplog.text.lower()
    finally:
        model_runtime_catalog._load_catalog.cache_clear()


def test_catalog_falls_back_when_version_is_boolean(monkeypatch, tmp_path, caplog):
    from app.services import model_runtime_catalog

    invalid_catalog = tmp_path / "model_runtime_catalog.json"
    invalid_catalog.write_text(
        """
        {
          "version": true,
          "fallback": {"context_window_tokens": 8192, "supports_vision": true, "supports_stream": false},
          "models": []
        }
        """,
        encoding="utf-8",
    )
    monkeypatch.setattr(model_runtime_catalog, "_CATALOG_PATH", invalid_catalog)
    model_runtime_catalog._load_catalog.cache_clear()
    try:
        defaults = model_runtime_catalog.resolve_model_runtime_defaults("deepseek-r1:7b")

        assert defaults.context_window_tokens == 4096
        assert defaults.supports_vision is False
        assert defaults.supports_stream is True
        assert defaults.source == "fallback"
        assert "model runtime catalog" in caplog.text.lower()
    finally:
        model_runtime_catalog._load_catalog.cache_clear()


def test_defaults_api_returns_wrapper_and_normalized_catalog_result():
    from app.routers import model

    app = FastAPI()
    app.include_router(model.router, prefix="/api")
    response = TestClient(app).post("/api/models/defaults", json={"model_name": "DeepSeek-R1:7B"})

    assert response.status_code == 200
    assert response.json() == {
        "code": 0,
        "msg": "获取模型默认配置成功",
        "data": {
            "model_name": "deepseek-r1:7b",
            "context_window_tokens": 131072,
            "supports_vision": False,
            "supports_stream": True,
            "source": "catalog",
            "matched_rule": "deepseek-r1:*",
        },
    }


def test_defaults_api_rejects_blank_model_name_with_wrapper_code_400():
    from app.routers import model

    app = FastAPI()
    app.include_router(model.router, prefix="/api")
    response = TestClient(app).post("/api/models/defaults", json={"model_name": "   "})

    assert response.status_code == 200
    assert response.json()["code"] == 400
    assert response.json()["data"] is None


def test_defaults_api_rejects_missing_model_name_with_wrapper_code_400():
    from app.routers import model

    app = FastAPI()
    app.include_router(model.router, prefix="/api")
    response = TestClient(app).post("/api/models/defaults", json={})

    assert response.status_code == 200
    assert response.json()["code"] == 400
    assert response.json()["data"] is None


def test_defaults_api_rejects_null_model_name_with_wrapper_code_400():
    from app.routers import model

    app = FastAPI()
    app.include_router(model.router, prefix="/api")
    response = TestClient(app).post("/api/models/defaults", json={"model_name": None})

    assert response.status_code == 200
    assert response.json()["code"] == 400
    assert response.json()["data"] is None


def test_defaults_api_rejects_non_string_model_name_with_wrapper_code_400():
    from app.routers import model

    app = FastAPI()
    app.include_router(model.router, prefix="/api")
    response = TestClient(app).post("/api/models/defaults", json={"model_name": 4096})

    assert response.status_code == 200
    assert response.json()["code"] == 400
    assert response.json()["data"] is None
