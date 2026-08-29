from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY, username TEXT NOT NULL, password_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('admin','user')), disabled INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS tokens (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), digest TEXT NOT NULL UNIQUE,
  expires_at INTEGER, revoked_at INTEGER, audience TEXT NOT NULL DEFAULT 'cloud-api', scopes_json TEXT NOT NULL DEFAULT '["*"]', created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS devices (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), public_key TEXT,
  platform TEXT NOT NULL, display_name TEXT NOT NULL, revoked_at INTEGER, last_seen_at INTEGER, created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS pairings (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), code_hash TEXT NOT NULL UNIQUE,
  expires_at INTEGER NOT NULL, status TEXT NOT NULL, device_id TEXT, created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS grants (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), controller_device_id TEXT NOT NULL,
  host_device_id TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('standard','super_admin')),
  scopes_json TEXT NOT NULL, workspace_refs_json TEXT NOT NULL, expires_at INTEGER,
  revoked_at INTEGER, created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), kind TEXT NOT NULL,
  title TEXT NOT NULL, workspace_id TEXT NOT NULL, status TEXT NOT NULL, copied_from TEXT,
  next_sequence INTEGER NOT NULL DEFAULT 1, next_event_sequence INTEGER NOT NULL DEFAULT 1, authority_epoch INTEGER NOT NULL DEFAULT 1, model_id TEXT,
  lease_owner TEXT, lease_expires_at INTEGER,
  created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS session_archives (
  user_id TEXT NOT NULL REFERENCES users(id), session_id TEXT NOT NULL REFERENCES sessions(id),
  device_id TEXT, archived_at INTEGER NOT NULL, PRIMARY KEY(user_id, session_id, device_id)
);
CREATE TABLE IF NOT EXISTS commands (
  id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id), request_id TEXT NOT NULL,
  payload_hash TEXT NOT NULL, sequence INTEGER NOT NULL, input_text TEXT NOT NULL,
  status TEXT NOT NULL, lease_owner TEXT, lease_expires_at INTEGER, attempt_count INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL, UNIQUE(session_id, request_id),
  UNIQUE(session_id, sequence)
);
CREATE TABLE IF NOT EXISTS events (
  id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id), sequence INTEGER NOT NULL,
  event_type TEXT NOT NULL, payload_json TEXT NOT NULL, created_at INTEGER NOT NULL,
  UNIQUE(session_id, sequence)
);
CREATE TABLE IF NOT EXISTS audits (
  id TEXT PRIMARY KEY, actor_user_id TEXT, action TEXT NOT NULL, resource_id TEXT,
  metadata_json TEXT NOT NULL, created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS share_tokens (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), session_id TEXT NOT NULL REFERENCES sessions(id),
  token_digest TEXT NOT NULL UNIQUE, role TEXT NOT NULL CHECK(role IN ('viewer','standard','super_admin')),
  scopes_json TEXT NOT NULL, expires_at INTEGER, revoked_at INTEGER, created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS session_payloads (
  session_id TEXT PRIMARY KEY REFERENCES sessions(id), payload_json TEXT NOT NULL,
  created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS session_import_requests (
  user_id TEXT NOT NULL REFERENCES users(id), request_id TEXT NOT NULL,
  payload_hash TEXT NOT NULL, session_id TEXT NOT NULL REFERENCES sessions(id),
  created_at INTEGER NOT NULL, PRIMARY KEY(user_id, request_id)
);
CREATE TABLE IF NOT EXISTS models (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), name TEXT NOT NULL,
  provider TEXT NOT NULL, model TEXT NOT NULL, base_url TEXT,
  api_key_ciphertext TEXT, enabled INTEGER NOT NULL DEFAULT 1, is_default INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS approvals (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), session_id TEXT NOT NULL REFERENCES sessions(id),
  command_id TEXT, tool_name TEXT NOT NULL, arguments_json TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('pending','approved','rejected','expired')),
  requested_by TEXT NOT NULL, resolved_by TEXT, resolution_note TEXT, created_at INTEGER NOT NULL, resolved_at INTEGER,
  UNIQUE(session_id, command_id, tool_name, arguments_json)
);
CREATE TABLE IF NOT EXISTS relay_cursors (
  session_id TEXT NOT NULL REFERENCES sessions(id), sender_device_id TEXT NOT NULL,
  last_sequence INTEGER NOT NULL DEFAULT 0, updated_at INTEGER NOT NULL,
  PRIMARY KEY(session_id, sender_device_id)
);
"""


class CloudDB:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, isolation_level=None, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=2000")
        return connection

    def init(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            users_sql = connection.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='users'").fetchone()[0]
            if "username TEXT NOT NULL UNIQUE" in users_sql:
                connection.execute("PRAGMA foreign_keys=OFF")
                connection.execute("BEGIN")
                connection.execute("CREATE TABLE users_v2 (id TEXT PRIMARY KEY, username TEXT NOT NULL, password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('admin','user')), disabled INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL)")
                connection.execute("INSERT INTO users_v2 SELECT id,username,password_hash,role,disabled,created_at FROM users")
                connection.execute("DROP TABLE users")
                connection.execute("ALTER TABLE users_v2 RENAME TO users")
                connection.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
                connection.execute("COMMIT")
                connection.execute("PRAGMA foreign_keys=ON")
            columns = {row[1] for row in connection.execute("PRAGMA table_info(sessions)").fetchall()}
            if "copied_from" not in columns:
                connection.execute("ALTER TABLE sessions ADD COLUMN copied_from TEXT")
            if "authority_epoch" not in columns:
                connection.execute("ALTER TABLE sessions ADD COLUMN authority_epoch INTEGER NOT NULL DEFAULT 1")
            if "lease_owner" not in columns:
                connection.execute("ALTER TABLE sessions ADD COLUMN lease_owner TEXT")
            if "lease_expires_at" not in columns:
                connection.execute("ALTER TABLE sessions ADD COLUMN lease_expires_at INTEGER")
            token_columns = {row[1] for row in connection.execute("PRAGMA table_info(tokens)").fetchall()}
            if "audience" not in token_columns:
                connection.execute("ALTER TABLE tokens ADD COLUMN audience TEXT NOT NULL DEFAULT 'cloud-api'")
            if "scopes_json" not in token_columns:
                connection.execute("ALTER TABLE tokens ADD COLUMN scopes_json TEXT NOT NULL DEFAULT '[\"*\"]'")
            device_columns = {row[1] for row in connection.execute("PRAGMA table_info(devices)").fetchall()}
            if "last_seen_at" not in device_columns:
                connection.execute("ALTER TABLE devices ADD COLUMN last_seen_at INTEGER")
            archive_columns = {row[1] for row in connection.execute("PRAGMA table_info(session_archives)").fetchall()}
            if "device_id" not in archive_columns:
                connection.execute("PRAGMA foreign_keys=OFF")
                connection.execute("BEGIN")
                connection.execute("CREATE TABLE session_archives_v2 (user_id TEXT NOT NULL REFERENCES users(id), session_id TEXT NOT NULL REFERENCES sessions(id), device_id TEXT, archived_at INTEGER NOT NULL, PRIMARY KEY(user_id, session_id, device_id))")
                connection.execute("INSERT INTO session_archives_v2(user_id,session_id,device_id,archived_at) SELECT user_id,session_id,NULL,archived_at FROM session_archives")
                connection.execute("DROP TABLE session_archives")
                connection.execute("ALTER TABLE session_archives_v2 RENAME TO session_archives")
                connection.execute("COMMIT")
                connection.execute("PRAGMA foreign_keys=ON")
            if "next_event_sequence" not in columns:
                connection.execute("ALTER TABLE sessions ADD COLUMN next_event_sequence INTEGER NOT NULL DEFAULT 1")
            if "model_id" not in columns:
                connection.execute("ALTER TABLE sessions ADD COLUMN model_id TEXT")
            command_columns = {row[1] for row in connection.execute("PRAGMA table_info(commands)").fetchall()}
            if "lease_owner" not in command_columns:
                connection.execute("ALTER TABLE commands ADD COLUMN lease_owner TEXT")
            if "lease_expires_at" not in command_columns:
                connection.execute("ALTER TABLE commands ADD COLUMN lease_expires_at INTEGER")
            if "attempt_count" not in command_columns:
                connection.execute("ALTER TABLE commands ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 0")
