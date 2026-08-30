from pathlib import Path
import pytest
from app.cloud_sync.token_store import EncryptedTokenStore, TokenStoreError


def test_encrypted_token_store_round_trip_and_permissions(tmp_path: Path):
    path = tmp_path / "token.json"
    store = EncryptedTokenStore(path, b"k" * 32)
    store.save("nmt_secret")
    assert store.load() == "nmt_secret"
    assert "nmt_secret" not in path.read_text()
    assert path.stat().st_mode & 0o077 == 0
    store.clear()
    assert store.load() is None


def test_encrypted_token_store_rejects_wrong_key_and_key_size(tmp_path: Path):
    with pytest.raises(TokenStoreError):
        EncryptedTokenStore(tmp_path / "token", b"short")
    path = tmp_path / "token"; EncryptedTokenStore(path, b"a" * 32).save("nmt_secret")
    with pytest.raises(TokenStoreError):
        EncryptedTokenStore(path, b"b" * 32).load()
