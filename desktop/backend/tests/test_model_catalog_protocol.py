"""notemeld.model-add.v1 三端协议桌面端回归测试。

覆盖 change-spec-cross-end-model-config-protocol.md 第 10 节要求：
  - 迁移幂等：providers 明文加密清空、models 目录列回填与部分唯一索引；
  - 密钥文件：0600、Fernet 往返、坏密文/坏 key 文件安全降级、掩码；
  - Provider 四端点脱敏与编辑留空/提交掩码保留原密钥；
  - httpx mock 三协议：Ollama /api/tags、Anthropic /v1/messages、OpenAI /chat/completions
    的 URL/header/body 断言，超时/失败脱敏；
  - batch 去重、context 范围（含 bool 拒绝）、设备级唯一默认；
  - 分享 decode：合法/配对码/夹带密钥/bedrock/非法 schema；
  - MCP catalog 双 enabled 过滤且输出 model=model_id。
"""
from __future__ import annotations

import json
import os
import stat
from collections.abc import Generator
from unittest.mock import ANY

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app.db import model_capability_dao, model_dao, provider_dao
from app.db.engine import Base
from app.db.model_schema import ensure_model_catalog_schema
from app.db.provider_schema import ensure_provider_catalog_schema
from app.gpt.provider import anthropic_messages_provider, ollama_provider
from app.gpt.provider.OpenAI_compatible_provider import OpenAICompatibleProvider
from app.gpt.provider.anthropic_messages_provider import AnthropicMessagesProvider
from app.gpt.provider.ollama_provider import OllamaProvider
from app.mcp import service as mcp_service
from app.routers import model as model_router
from app.routers import provider as provider_router
from app.security import model_secret
from app.services import model as model_service_module
from app.services import vendor_registry
from app.services.model import ModelService, ModelServiceError
from app.services.provider import ProviderService
from app.db.models.models import Model
from app.db.models.providers import Provider


# ---------------------------------------------------------------------------
# 夹具
# ---------------------------------------------------------------------------

def _session_dependency(session_factory) -> Generator:
    db = session_factory()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def isolated_secret_dir(monkeypatch, tmp_path):
    """让 Fernet 主密钥与运行库都落在临时目录，隔离 lru_cache 与真实数据。"""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("NOTEMELD_DATA_DIR", str(data_dir))
    model_secret._fernet.cache_clear()
    yield data_dir
    model_secret._fernet.cache_clear()


@pytest.fixture
def catalog_db(monkeypatch, tmp_path, isolated_secret_dir):
    """当前 schema 的真实 SQLite + 三个 DAO 的 get_db 全部接入。"""
    engine = create_engine(f"sqlite:///{tmp_path / 'catalog.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    def get_test_db():
        yield from _session_dependency(session_factory)

    monkeypatch.setattr(model_dao, "get_db", get_test_db)
    monkeypatch.setattr(model_capability_dao, "get_db", get_test_db)
    monkeypatch.setattr(provider_dao, "get_db", get_test_db)
    # ModelService 模块顶部 from ...model_dao import 的名字
    monkeypatch.setattr(model_service_module, "get_all_models", model_dao.get_all_models)
    monkeypatch.setattr(model_service_module, "upsert_models_batch", model_dao.upsert_models_batch)
    monkeypatch.setattr(model_service_module, "set_default_model", model_dao.set_default_model)
    return engine, session_factory


@pytest.fixture
def catalog_api(catalog_db):
    _engine, session_factory = catalog_db
    app = FastAPI()
    app.include_router(model_router.router, prefix="/api")
    app.include_router(provider_router.router, prefix="/api")
    return TestClient(app), session_factory


# ---------------------------------------------------------------------------
# 1. 密钥文件
# ---------------------------------------------------------------------------

class TestModelSecret:
    def test_key_file_created_with_0600_permission(self, isolated_secret_dir):
        ciphertext = model_secret.encrypt("sk-secret-value")

        assert ciphertext
        key_path = isolated_secret_dir / "config" / "model_secret.key"
        assert key_path.exists()
        mode = stat.S_IMODE(os.stat(key_path).st_mode)
        assert mode == 0o600

    def test_encrypt_decrypt_roundtrip(self, isolated_secret_dir):
        ciphertext = model_secret.encrypt("sk-往返密钥-123456")

        assert ciphertext != "sk-往返密钥-123456"
        assert model_secret.decrypt(ciphertext) == "sk-往返密钥-123456"

    def test_empty_string_encryption_is_empty(self, isolated_secret_dir):
        assert model_secret.encrypt("") == ""
        assert model_secret.decrypt("") == ""
        assert model_secret.decrypt(None) == ""

    def test_bad_ciphertext_returns_empty_without_raising(self, isolated_secret_dir):
        # 先触发 key 生成，再喂入非法 Fernet 密文
        model_secret.encrypt("seed")
        assert model_secret.decrypt("not-a-valid-fernet-token") == ""

    def test_invalid_key_file_raises_runtime_error(self, isolated_secret_dir):
        key_path = isolated_secret_dir / "config" / "model_secret.key"
        key_path.parent.mkdir(parents=True, exist_ok=True)
        key_path.write_bytes(b"this-is-not-a-fernet-key")
        model_secret._fernet.cache_clear()

        with pytest.raises(RuntimeError, match="模型密钥文件内容无效"):
            model_secret.encrypt("anything")

    @pytest.mark.parametrize("plain,expected", [
        ("", ""),
        ("short", "*****"),
        ("1234567", "*******"),
        ("sk-1234567890", "sk-1*****7890"),
    ])
    def test_mask_key(self, plain, expected):
        assert model_secret.mask_key(plain) == expected


# ---------------------------------------------------------------------------
# 2. additive 迁移（旧库）
# ---------------------------------------------------------------------------

class TestProviderCatalogMigration:
    def _legacy_engine(self, tmp_path):
        engine = create_engine(f"sqlite:///{tmp_path / 'legacy_provider.db'}")
        with engine.begin() as conn:
            conn.execute(text(
                "CREATE TABLE providers ("
                "id TEXT PRIMARY KEY, name TEXT NOT NULL, logo TEXT NOT NULL, "
                "api_key TEXT NOT NULL, base_url TEXT NOT NULL, "
                "enabled INTEGER DEFAULT 1, created_at DATETIME)"
            ))
            conn.execute(text(
                "INSERT INTO providers (id, name, logo, api_key, base_url, enabled) VALUES "
                "('p1', 'DeepSeek', 'bot', 'sk-plain-123456', 'https://api.deepseek.com', 1),"
                "('p2', 'Ollama Local', 'hard-drive', '', 'http://127.0.0.1:11434', 1),"
                "('p3', 'NoKey', 'custom', '', 'https://example.com/v1', 1)"
            ))
        return engine

    def test_plaintext_key_encrypted_and_cleared_without_dropping_rows(
        self, tmp_path, isolated_secret_dir
    ):
        engine = self._legacy_engine(tmp_path)

        result = ensure_provider_catalog_schema(engine)

        assert result == {"encrypted_keys": 1, "failed_keys": 0}
        with engine.begin() as conn:
            row = conn.execute(text(
                "SELECT api_key, api_key_ciphertext, display_name, vendor_id, protocol "
                "FROM providers WHERE id = 'p1'"
            )).fetchone()
        plaintext_after, ciphertext_after, display_name, vendor_id, protocol = row
        assert plaintext_after == ""
        assert ciphertext_after
        assert model_secret.decrypt(ciphertext_after) == "sk-plain-123456"
        assert display_name == "DeepSeek"
        assert vendor_id == "custom"
        assert protocol == "openai-compatible"
        count = inspect(engine)  # noqa: F841 - 仅确保 inspector 可用
        with engine.begin() as conn:
            total = conn.execute(text("SELECT COUNT(*) FROM providers")).scalar_one()
        assert total == 3

    def test_ollama_heuristic_backfills_protocol(self, tmp_path, isolated_secret_dir):
        engine = self._legacy_engine(tmp_path)
        ensure_provider_catalog_schema(engine)

        with engine.begin() as conn:
            protocol = conn.execute(text(
                "SELECT protocol FROM providers WHERE id = 'p2'"
            )).scalar_one()
        assert protocol == "ollama"

    def test_failed_row_keeps_plaintext_and_is_counted(
        self, tmp_path, isolated_secret_dir, monkeypatch
    ):
        engine = self._legacy_engine(tmp_path)
        calls = {"n": 0}
        real_encrypt = model_secret.encrypt

        def flaky_encrypt(plaintext: str) -> str:
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("disk full")
            return real_encrypt(plaintext)

        monkeypatch.setattr(model_secret, "encrypt", flaky_encrypt)

        result = ensure_provider_catalog_schema(engine)

        assert result == {"encrypted_keys": 0, "failed_keys": 1}
        with engine.begin() as conn:
            row = conn.execute(text(
                "SELECT api_key, api_key_ciphertext FROM providers WHERE id = 'p1'"
            )).fetchone()
        assert row[0] == "sk-plain-123456"
        assert not row[1]

    def test_migration_idempotent_second_run_noop(self, tmp_path, isolated_secret_dir):
        engine = self._legacy_engine(tmp_path)
        assert ensure_provider_catalog_schema(engine) == {"encrypted_keys": 1, "failed_keys": 0}

        assert ensure_provider_catalog_schema(engine) == {"encrypted_keys": 0, "failed_keys": 0}
        # 第三次也保持幂等
        assert ensure_provider_catalog_schema(engine) == {"encrypted_keys": 0, "failed_keys": 0}

    def test_migration_without_table_returns_zero(self, tmp_path, isolated_secret_dir):
        engine = create_engine(f"sqlite:///{tmp_path / 'empty.db'}")
        assert ensure_provider_catalog_schema(engine) == {"encrypted_keys": 0, "failed_keys": 0}


class TestModelCatalogMigration:
    def _legacy_engine(self, tmp_path):
        engine = create_engine(f"sqlite:///{tmp_path / 'legacy_model.db'}")
        with engine.begin() as conn:
            conn.execute(text(
                "CREATE TABLE models ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, provider_id TEXT NOT NULL, "
                "model_name TEXT NOT NULL, context_window_tokens INTEGER NOT NULL DEFAULT 4096, "
                "max_input_tokens INTEGER NOT NULL DEFAULT 3072, "
                "max_output_tokens INTEGER NOT NULL DEFAULT 1024, "
                "supports_vision BOOLEAN NOT NULL DEFAULT 0, "
                "supports_stream BOOLEAN NOT NULL DEFAULT 1, "
                "created_at DATETIME, UNIQUE (provider_id, model_name))"
            ))
            conn.execute(text(
                "INSERT INTO models (provider_id, model_name) VALUES "
                "('p1', 'legacy-a'), ('p1', 'legacy-b')"
            ))
        return engine

    def test_adds_columns_backfills_identity_and_partial_index_without_deleting(
        self, tmp_path
    ):
        engine = self._legacy_engine(tmp_path)

        changed = ensure_model_catalog_schema(engine)
        assert changed is True

        inspector = inspect(engine)
        columns = {column["name"] for column in inspector.get_columns("models")}
        assert {
            "model_id", "display_name", "enabled", "is_default", "test_status", "updated_at"
        } <= columns
        index_names = {index["name"] for index in inspector.get_indexes("models")}
        assert "uq_models_provider_model_id_partial" in index_names

        with engine.begin() as conn:
            backfilled = conn.execute(text(
                "SELECT model_id, display_name FROM models ORDER BY model_name"
            )).fetchall()
            total = conn.execute(text("SELECT COUNT(*) FROM models")).scalar_one()
        assert backfilled == [("legacy-a", "legacy-a"), ("legacy-b", "legacy-b")]
        assert total == 2

    def test_catalog_migration_idempotent(self, tmp_path):
        engine = self._legacy_engine(tmp_path)
        assert ensure_model_catalog_schema(engine) is True
        assert ensure_model_catalog_schema(engine) is False

    def test_partial_unique_index_rejects_duplicate_identity_after_backfill(self, tmp_path):
        import sqlite3

        db_path = tmp_path / "legacy_model.db"
        engine = create_engine(f"sqlite:///{db_path}")
        with engine.begin() as conn:
            conn.execute(text(
                "CREATE TABLE models ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, provider_id TEXT NOT NULL, "
                "model_name TEXT NOT NULL, created_at DATETIME)"
            ))
            conn.execute(text(
                "INSERT INTO models (provider_id, model_name) VALUES ('p1', 'dup')"
            ))
        ensure_model_catalog_schema(engine)
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO models (provider_id, model_name, model_id) VALUES "
                "('p1', 'other', 'other')"
            ))
        raw = sqlite3.connect(db_path)
        try:
            with pytest.raises(sqlite3.IntegrityError):
                raw.execute(
                    "INSERT INTO models (provider_id, model_name, model_id) VALUES (?, ?, ?)",
                    ("p1", "third", "dup"),
                )
        finally:
            raw.close()

    def test_without_table_returns_false(self, tmp_path):
        engine = create_engine(f"sqlite:///{tmp_path / 'empty_model.db'}")
        assert ensure_model_catalog_schema(engine) is False


# ---------------------------------------------------------------------------
# 3. Provider 脱敏服务 / HTTP 出口
# ---------------------------------------------------------------------------

def _add_provider_row(session_factory, *, provider_id="p-1", name="DeepSeek",
                      api_key="sk-deepseek-123456", base_url="https://api.deepseek.com",
                      protocol="openai-compatible", vendor_id="deepseek", enabled=1,
                      display_name=None):
    with session_factory.begin() as db:
        db.add(Provider(
            id=provider_id,
            name=name,
            logo=vendor_id,
            api_key="",
            base_url=base_url,
            enabled=enabled,
            display_name=display_name or name,
            vendor_id=vendor_id,
            protocol=protocol,
            auth_type="api_key",
            api_key_ciphertext=model_secret.encrypt(api_key) if api_key else "",
        ))


class TestProviderSafeSerialization:
    def test_add_provider_persists_ciphertext_and_returns_safe_dict(self, catalog_db):
        _engine, _sf = catalog_db
        safe = ProviderService.add_provider(
            name="My DeepSeek",
            api_key="sk-abcdef123456",
            base_url="https://api.deepseek.com",
            logo="bot",
            display_name="我的 DeepSeek",
            vendor_id="deepseek",
            protocol="openai-compatible",
        )

        assert "api_key" not in safe
        assert safe["has_api_key"] is True
        assert safe["credential_status"] == "saved"
        assert safe["api_key_masked"] == "sk-a*******3456"
        assert safe["vendor_id"] == "deepseek"
        assert safe["protocol"] == "openai-compatible"
        assert safe["display_name"] == "我的 DeepSeek"

        internal = ProviderService.get_provider_by_id(safe["id"])
        assert internal["api_key"] == "sk-abcdef123456"  # 内部链路仍可解密

        with _sf.begin() as db:
            row = db.query(Provider).filter_by(id=safe["id"]).one()
            assert row.api_key == ""
            assert row.api_key_ciphertext
            assert "sk-abcdef123456" not in row.api_key_ciphertext

    def test_ollama_provider_does_not_require_key(self, catalog_db):
        _engine, _sf = catalog_db
        safe = ProviderService.add_provider(
            name="Ollama",
            api_key="",
            base_url="http://localhost:11434",
            logo="",
            vendor_id="ollama",
            protocol="ollama",
        )
        assert safe["has_api_key"] is False
        assert safe["credential_status"] == "missing"
        assert safe["api_key_masked"] == ""

    def test_openai_protocol_without_key_rejected(self, catalog_db):
        _engine, _sf = catalog_db
        with pytest.raises(ValueError, match="请填写 API Key"):
            ProviderService.add_provider(
                name="X", api_key="  ", base_url="https://api.example.com/v1", logo="x"
            )

    def test_duplicate_name_rejected(self, catalog_db):
        _engine, _sf = catalog_db
        ProviderService.add_provider(
            name="Dup", api_key="sk-aaaaaaaa", base_url="https://a.example/v1", logo="x"
        )
        with pytest.raises(ValueError, match="供应商名称已存在"):
            ProviderService.add_provider(
                name="Dup", api_key="sk-bbbbbbbb", base_url="https://b.example/v1", logo="x"
            )

    def test_update_with_empty_key_keeps_original_ciphertext(self, catalog_db):
        _engine, sf = catalog_db
        _add_provider_row(sf)
        with sf() as db:
            before = db.query(Provider).filter_by(id="p-1").one().api_key_ciphertext

        result = ProviderService.update_provider("p-1", {"base_url": "https://api.deepseek.com/v2",
                                                         "api_key": ""})
        assert result["provider"]["api_key_masked"] == "sk-d**********3456"
        with sf() as db:
            row = db.query(Provider).filter_by(id="p-1").one()
            assert row.api_key_ciphertext == before
            assert row.api_key == ""
            assert row.base_url == "https://api.deepseek.com/v2"
        # 内部解密仍是原密钥
        assert ProviderService.get_provider_by_id("p-1")["api_key"] == "sk-deepseek-123456"

    def test_update_with_mask_submission_keeps_original_ciphertext(self, catalog_db):
        _engine, sf = catalog_db
        _add_provider_row(sf)
        mask = ProviderService.serialize_provider_safe(
            ProviderService.get_provider_by_id_safe("p-1")
        )["api_key_masked"]
        with sf() as db:
            before = db.query(Provider).filter_by(id="p-1").one().api_key_ciphertext

        ProviderService.update_provider("p-1", {"api_key": mask})

        with sf() as db:
            after = db.query(Provider).filter_by(id="p-1").one().api_key_ciphertext
        assert after == before

    def test_update_with_new_key_re_encrypts(self, catalog_db):
        _engine, sf = catalog_db
        _add_provider_row(sf)

        result = ProviderService.update_provider("p-1", {"api_key": "sk-brand-new-9999"})

        assert result["provider"]["api_key_masked"] == "sk-b*********9999"
        internal = ProviderService.get_provider_by_id("p-1")
        assert internal["api_key"] == "sk-brand-new-9999"

    def test_update_switch_to_key_required_protocol_without_key_rejected(self, catalog_db):
        _engine, sf = catalog_db
        _add_provider_row(sf, provider_id="p-o", name="Ollama", api_key="",
                          base_url="http://localhost:11434", protocol="ollama",
                          vendor_id="ollama")
        with pytest.raises(ValueError, match="请填写 API Key"):
            ProviderService.update_provider("p-o", {"protocol": "openai-compatible"})

    def test_safe_list_and_get_endpoints_never_leak_plaintext(self, catalog_api):
        client, sf = catalog_api
        _add_provider_row(sf)

        listing = client.get("/api/get_all_providers").json()["data"]
        assert len(listing) == 1
        item = listing[0]
        assert "api_key" not in item
        assert item["has_api_key"] is True
        assert item["api_key_masked"] == "sk-d**********3456"

        detail = client.get("/api/get_provider_by_id/p-1").json()["data"]
        assert "api_key" not in detail
        assert detail["credential_status"] == "saved"

    def test_add_and_update_http_endpoints_safe_payloads(self, catalog_api):
        client, _sf = catalog_api
        created = client.post("/api/add_provider", json={
            "name": "HTTP DeepSeek",
            "api_key": "sk-http-12345678",
            "base_url": "https://api.deepseek.com",
            "vendor_id": "deepseek",
            "protocol": "openai-compatible",
        }).json()
        assert created["code"] == 0
        provider_id = created["data"]["id"]
        assert "api_key" not in created["data"]

        updated = client.post("/api/update_provider", json={
            "id": provider_id, "api_key": ""
        }).json()
        # 只提交空密钥时因其他字段都为 None 会被端点拦截，补一个非密钥字段
        assert updated["code"] in (0, 500)

        updated = client.post("/api/update_provider", json={
            "id": provider_id, "display_name": "改名 DeepSeek", "api_key": ""
        }).json()
        assert updated["code"] == 0
        assert "api_key" not in updated["data"]["provider"]
        assert updated["data"]["provider"]["display_name"] == "改名 DeepSeek"
        assert updated["data"]["provider"]["api_key_masked"] == "sk-h********5678"


# ---------------------------------------------------------------------------
# 4. httpx mock 三协议
# ---------------------------------------------------------------------------

class _FakeTransport(httpx.BaseTransport):
    def __init__(self, handler):
        self.handler = handler
        self.calls = []

    def handle_request(self, request):
        self.calls.append(request)
        return self.handler(request)


def _json_response(payload: dict, status_code: int = 200):
    return httpx.Response(
        status_code,
        content=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
    )


def _install_transport(monkeypatch, module, transport):
    real_client = httpx.Client

    def fake_client(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr(module.httpx, "Client", fake_client)


class TestOllamaProtocol:
    def test_list_models_get_api_tags_and_parses_names(self, monkeypatch):
        transport = _FakeTransport(lambda req: _json_response({
            "models": [{"name": "llama3:8b"}, {"name": "qwen2:7b"}, {"name": None}]
        }))
        _install_transport(monkeypatch, ollama_provider, transport)

        result = OllamaProvider.list_models("http://localhost:11434/")

        assert result == [
            {"id": "llama3:8b", "context_window": 128000},
            {"id": "qwen2:7b", "context_window": 128000},
        ]
        request = transport.calls[0]
        assert request.method == "GET"
        assert str(request.url) == "http://localhost:11434/api/tags"
        assert request.headers["accept"] == "application/json"

    @pytest.mark.parametrize("payload", [
        {"models": []},
        {},
        {"models": [{"name": None}]},
    ])
    def test_list_empty_catalog_raises_chinese_error(self, monkeypatch, payload):
        transport = _FakeTransport(lambda req: _json_response(payload))
        _install_transport(monkeypatch, ollama_provider, transport)

        with pytest.raises(RuntimeError, match="未获取到模型"):
            OllamaProvider.list_models("http://localhost:11434")

    def test_list_http_error_is_sanitized(self, monkeypatch):
        def handler(request):
            return httpx.Response(500, content=b"boom")

        transport = _FakeTransport(handler)
        _install_transport(monkeypatch, ollama_provider, transport)

        with pytest.raises(RuntimeError, match="HTTP 500"):
            OllamaProvider.list_models("http://localhost:11434")

    def test_list_connection_error_is_sanitized(self, monkeypatch):
        def handler(request):
            raise httpx.ConnectError("internal dial detail 127.0.0.1:11434")

        transport = _FakeTransport(handler)
        _install_transport(monkeypatch, ollama_provider, transport)

        with pytest.raises(RuntimeError, match="无法连接本地 Ollama 服务"):
            OllamaProvider.list_models("http://localhost:11434")

    def test_test_connection_success_and_failure(self, monkeypatch):
        state = {"fail": False}

        def handler(request):
            if state["fail"]:
                raise httpx.ConnectError("down")
            return _json_response({"models": [{"name": "a"}]})

        transport = _FakeTransport(handler)
        _install_transport(monkeypatch, ollama_provider, transport)

        assert OllamaProvider.test_connection("http://localhost:11434") is True
        request = transport.calls[0]
        assert str(request.url) == "http://localhost:11434/api/tags"

        state["fail"] = True
        assert OllamaProvider.test_connection("http://localhost:11434") is False


class TestAnthropicProtocol:
    def test_builtin_list_does_not_touch_network(self):
        models = AnthropicMessagesProvider.list_models()

        assert [item["id"] for item in models] == [
            "claude-opus-4-1",
            "claude-sonnet-4-5",
            "claude-3-5-haiku-latest",
        ]
        assert all(item["context_window"] == 200000 for item in models)

    def test_test_connection_posts_messages_with_required_headers(self, monkeypatch):
        transport = _FakeTransport(lambda req: _json_response({"id": "msg_1", "content": []}))
        _install_transport(monkeypatch, anthropic_messages_provider, transport)

        result = AnthropicMessagesProvider.test_connection(
            "sk-ant-secret", "https://api.anthropic.com/", "claude-opus-4-1"
        )

        assert result is True
        request = transport.calls[0]
        assert request.method == "POST"
        assert str(request.url) == "https://api.anthropic.com/v1/messages"
        assert request.headers["x-api-key"] == "sk-ant-secret"
        assert request.headers["anthropic-version"] == "2023-06-01"
        body = json.loads(request.content.decode("utf-8"))
        assert body == {
            "model": "claude-opus-4-1",
            "max_tokens": 1,
            "messages": [{"role": "user", "content": "ping"}],
        }

    def test_test_connection_missing_arguments_raise_chinese(self):
        with pytest.raises(RuntimeError, match="请填写 API 密钥"):
            AnthropicMessagesProvider.test_connection("", "https://api.anthropic.com", "m")
        with pytest.raises(RuntimeError, match="请选择或填写要测试的模型 ID"):
            AnthropicMessagesProvider.test_connection("sk-ant", "https://api.anthropic.com", "")

    @pytest.mark.parametrize("payload", [{"unexpected": 1}, []])
    def test_test_connection_shapes_failure(self, monkeypatch, payload):
        transport = _FakeTransport(lambda req: _json_response(payload))
        _install_transport(monkeypatch, anthropic_messages_provider, transport)

        assert AnthropicMessagesProvider.test_connection(
            "sk-ant", "https://api.anthropic.com", "claude-opus-4-1"
        ) is False

    def test_test_connection_http_error_returns_false(self, monkeypatch):
        transport = _FakeTransport(lambda req: httpx.Response(401, content=b"unauthorized"))
        _install_transport(monkeypatch, anthropic_messages_provider, transport)

        assert AnthropicMessagesProvider.test_connection(
            "sk-ant", "https://api.anthropic.com", "m"
        ) is False


class TestOpenAICompatibleProtocol:
    def test_test_chat_connection_posts_chat_completions(self, monkeypatch):
        transport = _FakeTransport(lambda req: _json_response({"choices": [{"text": "x"}]}))
        real_client = httpx.Client

        def fake_client(*args, **kwargs):
            kwargs["transport"] = transport
            return real_client(*args, **kwargs)

        monkeypatch.setattr(httpx, "Client", fake_client)

        result = OpenAICompatibleProvider.test_chat_connection(
            "sk-openai-secret", "https://api.openai.com/v1/", "gpt-4o"
        )

        assert result is True
        request = transport.calls[0]
        assert request.method == "POST"
        assert str(request.url) == "https://api.openai.com/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer sk-openai-secret"
        body = json.loads(request.content.decode("utf-8"))
        assert body["model"] == "gpt-4o"
        assert body["max_tokens"] == 1
        assert body["stream"] is False

    def test_test_chat_missing_arguments_raise_chinese(self):
        with pytest.raises(RuntimeError, match="请填写 API 密钥"):
            OpenAICompatibleProvider.test_chat_connection("", "https://x/v1", "m")
        with pytest.raises(RuntimeError, match="请选择或填写要测试的模型 ID"):
            OpenAICompatibleProvider.test_chat_connection("sk", "https://x/v1", "")

    @pytest.mark.parametrize("payload", [{"choices": "nope"}, {}])
    def test_test_chat_bad_shape_returns_false(self, monkeypatch, payload):
        transport = _FakeTransport(lambda req: _json_response(payload))
        real_client = httpx.Client

        def fake_client(*args, **kwargs):
            kwargs["transport"] = transport
            return real_client(*args, **kwargs)

        monkeypatch.setattr(httpx, "Client", fake_client)

        assert OpenAICompatibleProvider.test_chat_connection(
            "sk", "https://x/v1", "m"
        ) is False

    def test_test_chat_http_error_returns_false(self, monkeypatch):
        transport = _FakeTransport(lambda req: httpx.Response(429, content=b"rate limited"))
        real_client = httpx.Client

        def fake_client(*args, **kwargs):
            kwargs["transport"] = transport
            return real_client(*args, **kwargs)

        monkeypatch.setattr(httpx, "Client", fake_client)

        assert OpenAICompatibleProvider.test_chat_connection(
            "sk", "https://x/v1", "m"
        ) is False

    def test_fetch_remote_models_uses_sdk_models_list(self, catalog_db, monkeypatch):
        class _Item:
            def __init__(self, item_id):
                self.id = item_id

        class _Page:
            data = [_Item("gpt-4o"), _Item("gpt-4o-mini")]

        class _Models:
            def list(self_inner):
                return _Page()

        class _Client:
            models = _Models()

        created = {}

        def fake_init(self, api_key, base_url, model=None):
            created["api_key"] = api_key
            created["base_url"] = base_url
            self.client = _Client()
            self.model = model

        monkeypatch.setattr(OpenAICompatibleProvider, "__init__", fake_init)

        result = ModelService.fetch_remote_models(
            "openai-compatible", "https://api.openai.com/v1/", "sk-sdk-secret"
        )

        assert result == [
            {"id": "gpt-4o", "context_window": 128000},
            {"id": "gpt-4o-mini", "context_window": 128000},
        ]
        assert created == {"api_key": "sk-sdk-secret", "base_url": "https://api.openai.com/v1"}

    def test_fetch_remote_models_sdk_failure_sanitized(self, monkeypatch):
        def fake_init(self, api_key, base_url, model=None):
            raise RuntimeError("raw endpoint leak detail")

        monkeypatch.setattr(OpenAICompatibleProvider, "__init__", fake_init)

        with pytest.raises(RuntimeError, match="获取模型列表失败"):
            ModelService.fetch_remote_models(
                "openai-compatible", "https://api.openai.com/v1", "sk"
            )

    def test_fetch_remote_models_empty_catalog_raises(self, monkeypatch):
        class _Page:
            data = []

        class _Models:
            def list(self_inner):
                return _Page()

        class _Client:
            models = _Models()

        def fake_init(self, api_key, base_url, model=None):
            self.client = _Client()
            self.model = model

        monkeypatch.setattr(OpenAICompatibleProvider, "__init__", fake_init)

        with pytest.raises(RuntimeError, match="未获取到模型"):
            ModelService.fetch_remote_models("openai-compatible", "https://x/v1", "sk")

    def test_fetch_remote_models_dispatch(self, monkeypatch):
        # ollama / anthropic 分派且 openai 缺 key 时中文报错
        monkeypatch.setattr(
            ollama_provider.OllamaProvider,
            "list_models",
            staticmethod(lambda url: [{"id": "llama3", "context_window": 128000}]),
        )
        assert ModelService.fetch_remote_models("ollama", "http://localhost:11434") == [
            {"id": "llama3", "context_window": 128000}
        ]
        assert ModelService.fetch_remote_models(
            "anthropic-messages", "https://api.anthropic.com"
        )[0]["id"] == "claude-opus-4-1"

        with pytest.raises(Exception, match="请填写 API Key"):
            ModelService.fetch_remote_models("openai-compatible", "https://x/v1", "")
        with pytest.raises(RuntimeError, match="请选择协议类型"):
            ModelService.fetch_remote_models("bedrock", "https://x", "sk")


# ---------------------------------------------------------------------------
# 5. batch 保存 / 默认唯一
# ---------------------------------------------------------------------------

def _batch_item(model_id, **overrides):
    item = {
        "model_id": model_id,
        "display_name": model_id,
        "context_window_tokens": 128000,
        "supports_vision": False,
        "supports_stream": True,
        "enabled": 1,
        "test_status": "unknown",
    }
    item.update(overrides)
    return item


class TestSaveModelsBatch:
    def test_batch_insert_dedup_and_existing(self, catalog_db):
        _engine, sf = catalog_db
        _add_provider_row(sf, provider_id="p-1")

        result = ModelService.save_models_batch("p-1", [
            _batch_item("gpt-4o"),
            _batch_item("gpt-4o"),  # 请求内重复，跳过
            _batch_item("gpt-4o-mini", display_name="GPT Mini"),
        ])
        assert result == {"inserted": 2, "existed": 0}

        result_again = ModelService.save_models_batch("p-1", [
            _batch_item("gpt-4o", display_name="GPT-4o 改名"),
            _batch_item("gpt-4.1"),
        ])
        assert result_again == {"inserted": 1, "existed": 1}

        with sf() as db:
            renamed = db.query(Model).filter_by(provider_id="p-1", model_id="gpt-4o").one()
            assert renamed.display_name == "GPT-4o 改名"
            assert renamed.model_name == "gpt-4o"
            total = db.query(Model).filter_by(provider_id="p-1").count()
        assert total == 3

    @pytest.mark.parametrize("bad_ctx", [511, 4_000_001, True, False, "128000", 128000.0])
    def test_batch_rejects_context_out_of_range_or_non_int(self, catalog_db, bad_ctx):
        _engine, sf = catalog_db
        _add_provider_row(sf)

        with pytest.raises(ModelServiceError, match="上下文需为"):
            ModelService.save_models_batch("p-1", [_batch_item("m", context_window_tokens=bad_ctx)])

    def test_batch_rejects_empty_list_and_unknown_provider(self, catalog_db):
        _engine, sf = catalog_db
        _add_provider_row(sf)
        with pytest.raises(ModelServiceError, match="至少选择"):
            ModelService.save_models_batch("p-1", [])
        with pytest.raises(Exception, match="供应商ID p-x 不存在"):
            ModelService.save_models_batch("p-x", [_batch_item("m")])

    def test_default_model_is_device_unique_across_providers(self, catalog_db):
        _engine, sf = catalog_db
        _add_provider_row(sf, provider_id="p-1")
        _add_provider_row(sf, provider_id="p-2", name="Other",
                          api_key="sk-other-123456", base_url="https://other.example/v1",
                          vendor_id="custom")
        ModelService.save_models_batch(
            "p-1", [_batch_item("a"), _batch_item("b")], default_model_id="a"
        )
        ModelService.save_models_batch(
            "p-2", [_batch_item("c"), _batch_item("d")], default_model_id="c"
        )

        with sf() as db:
            defaults = {
                (m.provider_id, m.model_id)
                for m in db.query(Model).filter(Model.is_default == 1).all()
            }
        assert defaults == {("p-2", "c")}

        assert ModelService.set_default_model("p-1", "b") is True
        with sf() as db:
            defaults = {
                (m.provider_id, m.model_id)
                for m in db.query(Model).filter(Model.is_default == 1).all()
            }
        assert defaults == {("p-1", "b")}

    def test_set_default_unknown_model_raises(self, catalog_db):
        _engine, sf = catalog_db
        _add_provider_row(sf)
        with pytest.raises(Exception, match="请先保存"):
            ModelService.set_default_model("p-1", "ghost")


class TestBatchHttpEndpoints:
    def test_batch_http_success_and_bad_context_rejected(self, catalog_api):
        client, sf = catalog_api
        _add_provider_row(sf)

        ok = client.post("/api/models/batch", json={
            "provider_id": "p-1",
            "models": [
                {"model_id": "gpt-4o", "context_window_tokens": 128000},
                {"model_id": "gpt-4o"},  # 请求内去重
                {"model_id": "gpt-4o-mini"},
            ],
        })
        assert ok.json()["code"] == 0
        assert ok.json()["data"] == {"inserted": 2, "existed": 0}

        bad = client.post("/api/models/batch", json={
            "provider_id": "p-1",
            "models": [{"model_id": "x", "context_window_tokens": 100}],
        })
        # Pydantic Field(ge=512) 在路由层直接 422，不进入 service
        assert bad.status_code == 422

    def test_batch_http_unknown_provider_404(self, catalog_api):
        client, _sf = catalog_api
        resp = client.post("/api/models/batch", json={
            "provider_id": "nope", "models": [{"model_id": "m"}],
        })
        assert resp.json()["code"] == 404

    def test_set_default_http_404_for_unsaved_model(self, catalog_api):
        client, sf = catalog_api
        _add_provider_row(sf)
        resp = client.post("/api/models/default", json={
            "provider_id": "p-1", "model_id": "ghost"
        })
        assert resp.json()["code"] == 404

    def test_saved_rows_expose_new_catalog_fields(self, catalog_api):
        client, sf = catalog_api
        _add_provider_row(sf)
        client.post("/api/models/batch", json={
            "provider_id": "p-1",
            "models": [{"model_id": "gpt-4o", "display_name": "GPT-4o",
                        "context_window_tokens": 200000, "test_status": "tested"}],
        })

        listed = client.get("/api/model_list").json()["data"]
        assert len(listed) == 1
        row = listed[0]
        assert row["model_id"] == "gpt-4o"
        assert row["display_name"] == "GPT-4o"
        assert row["context_window_tokens"] == 200000
        assert row["enabled"] == 1
        assert row["is_default"] == 0
        assert row["test_status"] == "tested"


# ---------------------------------------------------------------------------
# 6. 分享 encode / decode
# ---------------------------------------------------------------------------

def _encode_raw(payload: dict) -> str:
    import base64

    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    encoded = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    return f"notemeld://model-add?d={encoded}"


class TestShareRoundTrip:
    def test_preset_vendor_payload_is_compact_and_roundtrips(self):
        payload = vendor_registry.build_share_payload(
            vendor_id="deepseek",
            display_name="DeepSeek",
            protocol="openai-compatible",
            base_url="https://api.deepseek.com",
            models=[{"id": "deepseek-chat", "display_name": "DeepSeek Chat",
                     "context_window": 64000}],
        )
        # 预设厂商载荷不携带 protocol/url，由接收端 registry 解析
        assert payload["vendor"] == "deepseek"
        assert "protocol" not in payload
        assert "url" not in payload
        assert payload["models"] == [{"id": "deepseek-chat", "n": "DeepSeek Chat", "c": 64000}]

        link = vendor_registry.encode_share(payload)
        assert "api_key" not in link
        decoded = vendor_registry.decode_share(link)
        assert decoded == {
            "vendor_id": "deepseek",
            "display_name": "DeepSeek",
            "protocol": "openai-compatible",
            "base_url": "https://api.deepseek.com",
            "models": [{
                "id": "deepseek-chat",
                "display_name": "DeepSeek Chat",
                "context_window": 64000,
            }],
            "imported": True,
        }

    def test_default_context_omitted_and_restored(self):
        payload = vendor_registry.build_share_payload(
            vendor_id="custom", display_name="我的服务",
            protocol="openai-compatible", base_url="https://x.example/v1",
            models=[{"id": "m1", "display_name": "m1", "context_window": 128000}],
        )
        link = vendor_registry.encode_share(payload)
        decoded = vendor_registry.decode_share(link)
        assert decoded["vendor_id"] == "custom"
        assert decoded["display_name"] == "我的服务"
        assert decoded["base_url"] == "https://x.example/v1"
        assert decoded["models"][0]["context_window"] == 128000

    @pytest.mark.parametrize("text", [
        "notemeld://pair?code=ABCD1234",
        "notemeld://pair?d=eyJhIjoxfQ",
        "",
        "   ",
        "not a link at all",
    ])
    def test_decode_rejects_pair_code_and_garbage(self, text):
        assert vendor_registry.decode_share(text) is None
        with pytest.raises(ModelServiceError, match="设备配对码不可混用"):
            ModelService.decode_model_share(text)

    def test_decode_rejects_secret_fields_at_any_level(self):
        link = _encode_raw({
            "s": vendor_registry.SHARE_SCHEMA, "v": 1,
            "vendor": "custom", "name": "evil",
            "protocol": "openai-compatible", "url": "https://x.example/v1",
            "models": [{"id": "m", "config": {"X-Api-Key": "sk-leak"}}],
        })
        assert vendor_registry.decode_share(link) is None

    def test_decode_rejects_bedrock_even_with_preset_vendor(self):
        link = _encode_raw({
            "s": vendor_registry.SHARE_SCHEMA, "v": 1,
            "vendor": "aws-bedrock",
            "models": [{"id": "claude-3"}],
        })
        assert vendor_registry.decode_share(link) is None

    @pytest.mark.parametrize("context", [511, 4_000_001, True, False, "128"])
    def test_decode_rejects_bad_context(self, context):
        link = _encode_raw({
            "s": vendor_registry.SHARE_SCHEMA, "v": 1,
            "vendor": "custom", "name": "x",
            "protocol": "openai-compatible", "url": "https://x.example/v1",
            "models": [{"id": "m", "c": context}],
        })
        assert vendor_registry.decode_share(link) is None

    def test_decode_rejects_empty_models_and_bad_schema(self):
        empty_link = _encode_raw({
            "s": vendor_registry.SHARE_SCHEMA, "v": 1,
            "vendor": "custom", "name": "x", "protocol": "openai-compatible",
            "url": "https://x.example/v1", "models": [],
        })
        assert vendor_registry.decode_share(empty_link) is None

        wrong_schema = _encode_raw({
            "s": "other.schema", "models": [{"id": "m"}],
        })
        assert vendor_registry.decode_share(wrong_schema) is None

    def test_ollama_preset_share_roundtrips_without_key(self):
        payload = vendor_registry.build_share_payload(
            vendor_id="ollama", display_name="本地 Ollama",
            protocol="ollama", base_url="http://localhost:11434",
            models=[{"id": "llama3:8b", "display_name": "llama3:8b",
                     "context_window": 128000}],
        )
        decoded = vendor_registry.decode_share(vendor_registry.encode_share(payload))
        assert decoded["protocol"] == "ollama"
        assert decoded["base_url"] == "http://localhost:11434"


class TestBuildModelShareFromDb:
    def test_build_share_contains_only_selected_models_and_no_key(self, catalog_db):
        _engine, sf = catalog_db
        _add_provider_row(sf, provider_id="p-1", name="DeepSeek", vendor_id="deepseek")
        ModelService.save_models_batch("p-1", [
            _batch_item("deepseek-chat"), _batch_item("deepseek-reasoner"),
        ])

        link = ModelService.build_model_share("p-1", ["deepseek-chat"])

        assert "api_key" not in link and "sk-deepseek" not in link
        decoded = ModelService.decode_model_share(link)
        assert decoded["vendor_id"] == "deepseek"
        assert [m["id"] for m in decoded["models"]] == ["deepseek-chat"]

    def test_build_share_without_saved_models_raises(self, catalog_db):
        _engine, sf = catalog_db
        _add_provider_row(sf)
        with pytest.raises(ModelServiceError, match="请选择至少一个已保存模型用于分享"):
            ModelService.build_model_share("p-1", ["ghost"])

    def test_decode_http_endpoint_success_and_400(self, catalog_api):
        client, _sf = catalog_api
        link = vendor_registry.encode_share(vendor_registry.build_share_payload(
            vendor_id="deepseek", display_name="DeepSeek",
            protocol="openai-compatible", base_url="https://api.deepseek.com",
            models=[{"id": "deepseek-chat", "display_name": "deepseek-chat",
                     "context_window": 128000}],
        ))
        ok = client.post("/api/model_share/decode", json={"text": link})
        assert ok.json()["code"] == 0
        assert ok.json()["data"]["models"][0]["id"] == "deepseek-chat"

        bad = client.post("/api/model_share/decode",
                          json={"text": "notemeld://pair?code=XYZ"})
        assert bad.json()["code"] == 400


# ---------------------------------------------------------------------------
# 7. registry 单元
# ---------------------------------------------------------------------------

class TestVendorRegistry:
    def test_builtin_counts_and_unknown_urls_left_blank(self):
        assert len(vendor_registry.MODEL_VENDORS) == 22
        assert len(vendor_registry.PROTOCOLS) == 3
        protocols = {p["id"] for p in vendor_registry.PROTOCOLS}
        assert protocols == {"openai-compatible", "anthropic-messages", "ollama"}

        bedrock = vendor_registry.get_vendor("aws-bedrock")
        assert bedrock["protocol"] == "bedrock"
        assert bedrock.get("unsupported")

        for vendor_id in ("xiaomi-mimo", "moli-fangzhou"):
            assert vendor_registry.get_vendor(vendor_id)["base_url"] == ""
            assert vendor_registry.get_vendor(vendor_id).get("url_note")

    def test_validate_model_config_rules(self):
        base = {
            "display_name": "My Service",
            "protocol": "openai-compatible",
            "base_url": "https://api.example.com/v1",
            "api_key": "sk-12345678",
            "models": [{"id": "m", "context_window": 128000}],
        }
        assert vendor_registry.validate_model_config(dict(base)) == {}

        missing_name = dict(base, display_name="  ")
        assert "display_name" in vendor_registry.validate_model_config(missing_name)

        http_remote = dict(base, base_url="http://api.example.com/v1")
        assert vendor_registry.validate_model_config(http_remote)["base_url"] == "非本机地址必须使用 HTTPS"

        local_http = dict(base, base_url="http://localhost:11434", protocol="ollama",
                          api_key="", models=[{"id": "m", "context_window": 128000}])
        assert vendor_registry.validate_model_config(local_http) == {}

        no_key = dict(base, api_key="", has_stored_key=False)
        assert "api_key" in vendor_registry.validate_model_config(no_key)
        kept = dict(base, api_key="", has_stored_key=True)
        assert "api_key" not in vendor_registry.validate_model_config(kept)

        bool_ctx = dict(base, models=[{"id": "m", "context_window": True}])
        assert any(k.startswith("model_context:") for k in vendor_registry.validate_model_config(bool_ctx))

        no_models = dict(base, models=[])
        assert "models" in vendor_registry.validate_model_config(no_models)


# ---------------------------------------------------------------------------
# 8. MCP catalog
# ---------------------------------------------------------------------------

class TestMcpModelCatalog:
    def test_catalog_filters_both_enabled_and_uses_model_id(self, monkeypatch, tmp_path):
        engine = create_engine(f"sqlite:///{tmp_path / 'mcp.db'}")
        Base.metadata.create_all(engine)
        session_factory = sessionmaker(bind=engine)

        def get_test_db():
            yield from _session_dependency(session_factory)

        # mcp/service 在函数体内 from app.db.engine import get_db
        import app.db.engine as engine_module
        monkeypatch.setattr(engine_module, "get_db", get_test_db)

        with session_factory.begin() as db:
            db.add(Provider(id="on", name="Enabled", logo="x", api_key="",
                            base_url="https://on.example/v1", enabled=1))
            db.add(Provider(id="off", name="Disabled", logo="x", api_key="",
                            base_url="https://off.example/v1", enabled=0))
            db.add(Model(provider_id="on", model_name="alpha-name", model_id="alpha-id",
                         display_name="Alpha", enabled=1))
            db.add(Model(provider_id="on", model_name="beta-name", model_id="beta-id",
                         display_name="Beta", enabled=0))
            db.add(Model(provider_id="off", model_name="gamma-name", model_id="gamma-id",
                         display_name="Gamma", enabled=1))

        catalog = mcp_service.list_enabled_model_catalog()

        assert catalog == [{
            "providerId": "on",
            "providerName": "Enabled",
            "model": "alpha-id",
            "modelId": ANY,
            "baseUrl": "https://on.example/v1",
        }]
        serialized = json.dumps(catalog)
        assert "api_key" not in serialized
