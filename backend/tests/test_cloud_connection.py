import pytest
from app.cloud_sync.connection import connection_candidates, connect_with_fallback, validate_cloud_base_url


def test_connection_candidates_prioritize_lan_and_encode_session():
    candidates = connection_candidates("https://cloud.example/api", "s/id", ["192.168.1.2:8583"])
    assert candidates[0].transport == "lan" and candidates[0].url.endswith("s%2Fid")
    assert candidates[-1].transport == "relay"
    assert candidates[-1].url == "wss://cloud.example/v1/relay/connect/s%2Fid"


def test_connection_fallback_tries_next_candidate():
    candidates = connection_candidates("http://127.0.0.1:8583", "s1", ["127.0.0.1:1"])
    attempts = []
    def connect(candidate, timeout):
        attempts.append(candidate.transport)
        if candidate.transport == "lan": raise OSError("unreachable")
        return "connected"
    assert connect_with_fallback(candidates, connect) == ("connected", candidates[-1])
    assert attempts == ["lan", "relay"]


def test_connection_rejects_invalid_base_url():
    with pytest.raises(ValueError):
        connection_candidates("file:///tmp", "s1")
    with pytest.raises(ValueError, match="private or local"):
        connection_candidates("https://cloud.example", "s1", ["8.8.8.8:443"])


def test_cloud_base_url_requires_tls_for_remote_hosts():
    assert validate_cloud_base_url("http://127.0.0.1:8583/") == "http://127.0.0.1:8583"
    assert validate_cloud_base_url("https://cloud.example.test/") == "https://cloud.example.test"
    for value in ("http://cloud.example.test", "https://user:pass@cloud.example.test", "https://cloud.example.test/?token=x"):
        with pytest.raises(ValueError):
            validate_cloud_base_url(value)
