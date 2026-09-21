from __future__ import annotations

import importlib.util
from pathlib import Path
import sqlite3

import pytest


SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "release" / "verify_first_batch_security_audit.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("verify_first_batch_security_audit", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeRedis:
    def __init__(self, values=None, ttls=None, types=None):
        self.values = values or {b"notemeld:relay:online:session:host": b"connection-id"}
        self.ttls = ttls or {key: 60 for key in self.values}
        self.types = types or {key: b"string" for key in self.values}
        self.closed = False

    def ping(self):
        return True

    def scan_iter(self, match=None, count=None):
        assert match == "notemeld:relay:*"
        assert count == 100
        return iter(self.values)

    def type(self, key):
        return self.types[key]

    def ttl(self, key):
        return self.ttls[key]

    def get(self, key):
        return self.values[key]

    def close(self):
        self.closed = True


def cloud_database(path: Path) -> None:
    with sqlite3.connect(path) as cx:
        cx.execute("CREATE TABLE sessions (id TEXT PRIMARY KEY, kind TEXT NOT NULL)")
        cx.execute("CREATE TABLE commands (id TEXT PRIMARY KEY, session_id TEXT NOT NULL)")
        cx.execute("CREATE TABLE events (id TEXT PRIMARY KEY, session_id TEXT NOT NULL)")
        cx.execute(
            "CREATE TABLE relay_cursors (session_id TEXT NOT NULL, sender_device_id TEXT NOT NULL, "
            "last_sequence INTEGER NOT NULL, updated_at INTEGER NOT NULL, PRIMARY KEY(session_id,sender_device_id))"
        )
        cx.execute("INSERT INTO sessions VALUES ('session','device_remote')")
        cx.execute("INSERT INTO relay_cursors VALUES ('session','host',2,1)")
        cx.execute("INSERT INTO relay_cursors VALUES ('session','controller',2,1)")


def needles():
    return {
        "challenge": "challenge-value-123",
        "account_token": "account-token-value-123",
        "device_token": "device-token-value-123",
        "session_key": "session-key-value-123",
        "provider_key": "provider-key-value-123",
    }


def test_security_audit_scans_cloud_database_logs_and_ephemeral_redis_without_exposing_values(tmp_path):
    tool = load_tool()
    database = tmp_path / "cloud.db"
    cloud_database(database)
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "cloud.log").write_text("relay connected; frame body omitted\n", encoding="utf-8")
    fake = FakeRedis()

    result = tool.run(
        database,
        [logs],
        "rediss://redis.example.test/0",
        needles(),
        session_id="session",
        redis_factory=lambda _url: fake,
    )

    assert result["release_checks"] == {"e_01_cloud_storage_logs_redis": "PASS"}
    assert result["database"]["quick_check"] == "ok"
    assert result["database"]["relay_cursor_columns"] == [
        "session_id",
        "sender_device_id",
        "last_sequence",
        "updated_at",
    ]
    assert result["database"]["session_relay_cursors"] == 2
    assert result["database"]["session_commands"] == 0
    assert result["database"]["session_events"] == 0
    assert result["logs"]["files"] == 1
    assert result["redis"] == {"keys": 1, "ephemeral_presence_keys": 1}
    assert fake.closed is True
    serialized = repr(result)
    assert all(value not in serialized for value in needles().values())
    assert set(result["needle_sha256"]) == set(needles())


@pytest.mark.parametrize("surface", ["database", "wal", "log"])
def test_security_audit_fails_closed_when_a_sensitive_value_is_found_on_disk(tmp_path, surface):
    tool = load_tool()
    database = tmp_path / "cloud.db"
    cloud_database(database)
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "cloud.log").write_text("safe", encoding="utf-8")
    if surface == "database":
        with sqlite3.connect(database) as cx:
            cx.execute("CREATE TABLE forbidden(value TEXT)")
            cx.execute("INSERT INTO forbidden VALUES (?)", (needles()["challenge"],))
    elif surface == "wal":
        Path(f"{database}-wal").write_text(needles()["session_key"], encoding="utf-8")
    else:
        (logs / "cloud.log").write_bytes(b"x" * (1024 * 1024 - 5) + needles()["device_token"].encode())

    with pytest.raises(tool.AuditError, match="sensitive audit needle") as error:
        tool.run(database, [logs], "rediss://redis.example.test/0", needles(), session_id="session", redis_factory=lambda _url: FakeRedis())
    assert all(value not in str(error.value) for value in needles().values())


def test_security_audit_rejects_persistent_or_sensitive_relay_redis_keys(tmp_path):
    tool = load_tool()
    database = tmp_path / "cloud.db"
    cloud_database(database)
    log = tmp_path / "cloud.log"
    log.write_text("safe", encoding="utf-8")
    persistent = FakeRedis(
        values={b"notemeld:relay:payload:session": needles()["challenge"].encode()},
        ttls={b"notemeld:relay:payload:session": -1},
    )

    with pytest.raises(tool.AuditError, match="unexpected Redis relay key"):
        tool.run(database, [log], "rediss://redis.example.test/0", needles(), session_id="session", redis_factory=lambda _url: persistent)
    assert persistent.closed is True


def test_security_audit_rejects_cloud_command_rows_for_device_remote_session(tmp_path):
    tool = load_tool()
    database = tmp_path / "cloud.db"
    cloud_database(database)
    with sqlite3.connect(database) as cx:
        cx.execute("INSERT INTO commands VALUES ('forbidden-command','session')")
    log = tmp_path / "cloud.log"
    log.write_text("safe", encoding="utf-8")

    with pytest.raises(tool.AuditError, match="forbidden Cloud command/event rows"):
        tool.run(
            database,
            [log],
            "rediss://redis.example.test/0",
            needles(),
            session_id="session",
            redis_factory=lambda _url: FakeRedis(),
        )


def test_security_audit_requires_complete_nontrivial_needles_and_secure_redis_url(tmp_path):
    tool = load_tool()
    database = tmp_path / "cloud.db"
    cloud_database(database)
    log = tmp_path / "cloud.log"
    log.write_text("safe", encoding="utf-8")

    incomplete = needles()
    incomplete.pop("session_key")
    with pytest.raises(tool.AuditError, match="needle labels"):
        tool.run(database, [log], "rediss://redis.example.test/0", incomplete, session_id="session", redis_factory=lambda _url: FakeRedis())
    with pytest.raises(tool.AuditError, match="rediss"):
        tool.run(database, [log], "redis://redis.example.test/0", needles(), session_id="session", redis_factory=lambda _url: FakeRedis())
    compressed = tmp_path / "cloud.log.gz"
    compressed.write_bytes(b"not-a-real-gzip")
    with pytest.raises(tool.AuditError, match="decompressed"):
        tool.run(database, [compressed], "rediss://redis.example.test/0", needles(), session_id="session", redis_factory=lambda _url: FakeRedis())
