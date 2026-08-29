from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('admin','user')), disabled INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS tokens (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), digest TEXT NOT NULL UNIQUE,
  expires_at INTEGER, revoked_at INTEGER, created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS devices (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), public_key TEXT,
  platform TEXT NOT NULL, display_name TEXT NOT NULL, revoked_at INTEGER, created_at INTEGER NOT NULL
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
  title TEXT NOT NULL, workspace_id TEXT NOT NULL, status TEXT NOT NULL,
  next_sequence INTEGER NOT NULL DEFAULT 1, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS commands (
  id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id), request_id TEXT NOT NULL,
  payload_hash TEXT NOT NULL, sequence INTEGER NOT NULL, input_text TEXT NOT NULL,
  status TEXT NOT NULL, created_at INTEGER NOT NULL, UNIQUE(session_id, request_id),
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
