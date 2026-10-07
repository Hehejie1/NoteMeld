from __future__ import annotations

import hashlib
import re
import sqlite3
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY, username TEXT NOT NULL, email TEXT, display_name TEXT, avatar TEXT, password_hash TEXT NOT NULL,
  email_verified_at INTEGER, last_login_at INTEGER,
  role TEXT NOT NULL CHECK(role IN ('admin','user')), disabled INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS organizations (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS organization_members (
  organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK(role IN ('owner','admin','member')),
  created_at INTEGER NOT NULL,
  PRIMARY KEY(organization_id, user_id)
);
CREATE TABLE IF NOT EXISTS organization_preferences (
  organization_id TEXT PRIMARY KEY REFERENCES organizations(id) ON DELETE CASCADE,
  preferences_json TEXT NOT NULL DEFAULT '{}', updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS organization_memories (
  id TEXT PRIMARY KEY, organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  content TEXT NOT NULL, source TEXT NOT NULL DEFAULT 'admin', created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS tokens (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), digest TEXT NOT NULL UNIQUE,
  expires_at INTEGER, revoked_at INTEGER, audience TEXT NOT NULL DEFAULT 'cloud-api', scopes_json TEXT NOT NULL DEFAULT '["*"]',
  device_id TEXT REFERENCES devices(id), created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS devices (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), public_key TEXT,
  platform TEXT NOT NULL, display_name TEXT NOT NULL, connectivity_json TEXT NOT NULL DEFAULT '{}', revoked_at INTEGER, last_seen_at INTEGER, created_at INTEGER NOT NULL
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
  auth_mode TEXT NOT NULL DEFAULT 'default',
  created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS session_archives (
  user_id TEXT NOT NULL REFERENCES users(id), session_id TEXT NOT NULL REFERENCES sessions(id),
  device_id TEXT, archived_at INTEGER NOT NULL, PRIMARY KEY(user_id, session_id, device_id)
);
CREATE TABLE IF NOT EXISTS commands (
  id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id), request_id TEXT NOT NULL,
  payload_hash TEXT NOT NULL, sequence INTEGER NOT NULL, input_text TEXT NOT NULL, attachments_json TEXT NOT NULL DEFAULT '[]', options_json TEXT NOT NULL DEFAULT '{}',
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
CREATE TABLE IF NOT EXISTS files (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
  session_id TEXT REFERENCES sessions(id), workspace_id TEXT NOT NULL,
  name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
  mime TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('image','document','text','other')),
  path TEXT NOT NULL, sha256 TEXT NOT NULL, size INTEGER NOT NULL,
  created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS file_chunks (
  id TEXT PRIMARY KEY, file_id TEXT NOT NULL REFERENCES files(id) ON DELETE CASCADE,
  ordinal INTEGER NOT NULL, content TEXT NOT NULL,
  token_count INTEGER NOT NULL DEFAULT 0,
  UNIQUE(file_id, ordinal)
);
CREATE TABLE IF NOT EXISTS providers (
  id TEXT PRIMARY KEY, organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  display_name TEXT NOT NULL, vendor_id TEXT NOT NULL DEFAULT 'custom',
  protocol TEXT NOT NULL CHECK(protocol IN ('openai-compatible','anthropic-messages','ollama')),
  base_url TEXT NOT NULL, auth_type TEXT NOT NULL DEFAULT 'bearer',
  api_key_ciphertext TEXT, created_by TEXT NOT NULL REFERENCES users(id),
  created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
  UNIQUE(organization_id, display_name)
);
CREATE TABLE IF NOT EXISTS models (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), name TEXT NOT NULL,
  provider TEXT NOT NULL, model TEXT NOT NULL, base_url TEXT,
  api_key_ciphertext TEXT, enabled INTEGER NOT NULL DEFAULT 1, is_default INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
  organization_id TEXT REFERENCES organizations(id), provider_id TEXT REFERENCES providers(id) ON DELETE CASCADE,
  display_name TEXT, context_window INTEGER NOT NULL DEFAULT 128000,
  modalities TEXT NOT NULL DEFAULT 'text', test_status TEXT NOT NULL DEFAULT 'unknown', model_id TEXT
);
CREATE TABLE IF NOT EXISTS model_usage_records (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  command_id TEXT NOT NULL REFERENCES commands(id) ON DELETE CASCADE,
  model_id TEXT, provider TEXT, model TEXT NOT NULL,
  prompt_tokens INTEGER NOT NULL DEFAULT 0, completion_tokens INTEGER NOT NULL DEFAULT 0,
  total_tokens INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL
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
CREATE TABLE IF NOT EXISTS login_attempts (
  key TEXT PRIMARY KEY, window_started INTEGER NOT NULL, failed_count INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS user_preferences (
  user_id TEXT PRIMARY KEY REFERENCES users(id), preferences_json TEXT NOT NULL DEFAULT '{}', updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS config_sync_state (
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  workspace_id TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 0,
  updated_at INTEGER NOT NULL,
  PRIMARY KEY(user_id, workspace_id)
);
CREATE TABLE IF NOT EXISTS config_sync_items (
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  workspace_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  item_key TEXT NOT NULL,
  value_json TEXT,
  revision INTEGER NOT NULL,
  deleted INTEGER NOT NULL DEFAULT 0,
  updated_at INTEGER NOT NULL,
  PRIMARY KEY(user_id, workspace_id, kind, item_key)
);
CREATE TABLE IF NOT EXISTS config_sync_idempotency (
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  workspace_id TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  request_hash TEXT NOT NULL,
  response_json TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  PRIMARY KEY(user_id, workspace_id, idempotency_key)
);
CREATE TABLE IF NOT EXISTS verification_codes (
  id TEXT PRIMARY KEY, email TEXT NOT NULL, purpose TEXT NOT NULL,
  code_hash TEXT NOT NULL, expires_at INTEGER NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
  used_at INTEGER, created_at INTEGER NOT NULL, request_ip TEXT
);
CREATE TABLE IF NOT EXISTS access_requests (
  id TEXT PRIMARY KEY, email TEXT NOT NULL, display_name TEXT NOT NULL,
  reason TEXT NOT NULL, password_hash TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('pending','approved','rejected','expired')),
  reviewed_by TEXT, reviewed_at INTEGER, created_at INTEGER NOT NULL, expires_at INTEGER
);
CREATE TABLE IF NOT EXISTS invitations (
  id TEXT PRIMARY KEY, email TEXT NOT NULL, display_name TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('user')),
  token_hash TEXT NOT NULL UNIQUE, status TEXT NOT NULL CHECK(status IN ('pending','accepted','revoked','expired')),
  created_by TEXT NOT NULL REFERENCES users(id), created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL, accepted_at INTEGER
);
CREATE TABLE IF NOT EXISTS workspaces (
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, id TEXT NOT NULL,
  display_name TEXT NOT NULL, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
  PRIMARY KEY(user_id, id)
);
CREATE TABLE IF NOT EXISTS workspace_backups (
  user_id TEXT NOT NULL, workspace_id TEXT NOT NULL, id TEXT NOT NULL,
  archive_path TEXT NOT NULL, bytes INTEGER NOT NULL, created_at INTEGER NOT NULL,
  PRIMARY KEY(user_id, id),
  FOREIGN KEY(user_id, workspace_id) REFERENCES workspaces(user_id, id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_commands_session_status_sequence ON commands(session_id, status, sequence);
CREATE INDEX IF NOT EXISTS idx_events_session_sequence ON events(session_id, sequence);
CREATE INDEX IF NOT EXISTS idx_tokens_user_active ON tokens(user_id, revoked_at, expires_at);
CREATE INDEX IF NOT EXISTS idx_verification_codes_email ON verification_codes(email, purpose, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_access_requests_status ON access_requests(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_invitations_email_status ON invitations(email, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_devices_user_active ON devices(user_id, revoked_at);
CREATE INDEX IF NOT EXISTS idx_sessions_user_updated ON sessions(user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_audits_created ON audits(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_workspaces_user_updated ON workspaces(user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_model_usage_user_created ON model_usage_records(user_id, created_at DESC);
-- 两级目录（providers/models）的索引在 _migrate_catalog 建列后创建，避免旧库启动失败。
CREATE INDEX IF NOT EXISTS idx_workspace_backups_workspace_created ON workspace_backups(user_id, workspace_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_config_sync_items_revision ON config_sync_items(user_id, workspace_id, revision);
"""


class CloudDB:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, isolation_level=None, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
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
            user_columns = {row[1] for row in connection.execute("PRAGMA table_info(users)").fetchall()}
            if "email" not in user_columns:
                connection.execute("ALTER TABLE users ADD COLUMN email TEXT")
            if "display_name" not in user_columns:
                connection.execute("ALTER TABLE users ADD COLUMN display_name TEXT")
            if "avatar" not in user_columns:
                connection.execute("ALTER TABLE users ADD COLUMN avatar TEXT")
            if "email_verified_at" not in user_columns:
                connection.execute("ALTER TABLE users ADD COLUMN email_verified_at INTEGER")
            if "last_login_at" not in user_columns:
                connection.execute("ALTER TABLE users ADD COLUMN last_login_at INTEGER")
            connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email) WHERE email IS NOT NULL")
            columns = {row[1] for row in connection.execute("PRAGMA table_info(sessions)").fetchall()}
            if "copied_from" not in columns:
                connection.execute("ALTER TABLE sessions ADD COLUMN copied_from TEXT")
            if "authority_epoch" not in columns:
                connection.execute("ALTER TABLE sessions ADD COLUMN authority_epoch INTEGER NOT NULL DEFAULT 1")
            if "lease_owner" not in columns:
                connection.execute("ALTER TABLE sessions ADD COLUMN lease_owner TEXT")
            if "lease_expires_at" not in columns:
                connection.execute("ALTER TABLE sessions ADD COLUMN lease_expires_at INTEGER")
            if "auth_mode" not in columns:
                connection.execute("ALTER TABLE sessions ADD COLUMN auth_mode TEXT NOT NULL DEFAULT 'default'")
            token_columns = {row[1] for row in connection.execute("PRAGMA table_info(tokens)").fetchall()}
            if "audience" not in token_columns:
                connection.execute("ALTER TABLE tokens ADD COLUMN audience TEXT NOT NULL DEFAULT 'cloud-api'")
            if "scopes_json" not in token_columns:
                connection.execute("ALTER TABLE tokens ADD COLUMN scopes_json TEXT NOT NULL DEFAULT '[\"*\"]'")
            if "device_id" not in token_columns:
                connection.execute("ALTER TABLE tokens ADD COLUMN device_id TEXT")
            device_columns = {row[1] for row in connection.execute("PRAGMA table_info(devices)").fetchall()}
            if "last_seen_at" not in device_columns:
                connection.execute("ALTER TABLE devices ADD COLUMN last_seen_at INTEGER")
            if "connectivity_json" not in device_columns:
                connection.execute("ALTER TABLE devices ADD COLUMN connectivity_json TEXT NOT NULL DEFAULT '{}'")
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
            if "attachments_json" not in command_columns:
                connection.execute("ALTER TABLE commands ADD COLUMN attachments_json TEXT NOT NULL DEFAULT '[]'")
            if "options_json" not in command_columns:
                connection.execute("ALTER TABLE commands ADD COLUMN options_json TEXT NOT NULL DEFAULT '{}'")
            if "lease_owner" not in command_columns:
                connection.execute("ALTER TABLE commands ADD COLUMN lease_owner TEXT")
            if "lease_expires_at" not in command_columns:
                connection.execute("ALTER TABLE commands ADD COLUMN lease_expires_at INTEGER")
            if "attempt_count" not in command_columns:
                connection.execute("ALTER TABLE commands ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 0")
            now = int(__import__("time").time())
            connection.execute("INSERT OR IGNORE INTO organizations(id,name,created_at,updated_at) VALUES('default','Default organization',?,?)", (now, now))
            connection.execute("INSERT OR IGNORE INTO organization_members(organization_id,user_id,role,created_at) SELECT 'default',id,CASE WHEN role='admin' THEN 'owner' ELSE 'member' END,? FROM users", (now,))

            self._migrate_catalog(connection, now)

    def _migrate_catalog(self, connection: sqlite3.Connection, now: int) -> None:
        """两级目录（providers/models）幂等迁移与回填。"""
        model_columns = {row[1] for row in connection.execute("PRAGMA table_info(models)").fetchall()}
        model_additions = {
            "organization_id": "TEXT",
            "provider_id": "TEXT",
            "display_name": "TEXT",
            "context_window": "INTEGER NOT NULL DEFAULT 128000",
            "modalities": "TEXT NOT NULL DEFAULT 'text'",
            "test_status": "TEXT NOT NULL DEFAULT 'unknown'",
            "model_id": "TEXT",
        }
        for column, declaration in model_additions.items():
            if column not in model_columns:
                connection.execute(f"ALTER TABLE models ADD COLUMN {column} {declaration}")

        # 此时 providers 表与 models 新列已就绪，再补建 catalog 索引。
        connection.execute("CREATE INDEX IF NOT EXISTS idx_providers_organization ON providers(organization_id)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_models_catalog ON models(organization_id, provider_id)")

        legacy_rows = connection.execute(
            "SELECT * FROM models WHERE provider_id IS NULL ORDER BY created_at ASC, id ASC"
        ).fetchall()
        if not legacy_rows:
            return

        user_orgs = {
            row[1]: row[0]
            for row in connection.execute("SELECT organization_id,user_id FROM organization_members").fetchall()
        }
        # 旧 provider 字符串 → (vendor_id, protocol)；未知项一律 custom/openai-compatible
        legacy_protocol_map = {
            "openai": ("openai", "openai-compatible"),
            "openai-compatible": ("custom", "openai-compatible"),
            "deepseek": ("deepseek", "openai-compatible"),
            "volcengine": ("volcengine-ark", "openai-compatible"),
            "anthropic": ("anthropic", "anthropic-messages"),
            "ollama": ("ollama", "ollama"),
        }

        # 按 (organization_id, vendor_id, protocol, base_url) 聚合旧行
        grouped: dict[tuple, list[sqlite3.Row]] = {}
        for row in legacy_rows:
            org_id = user_orgs.get(row["user_id"], "default")
            vendor_id, protocol = legacy_protocol_map.get(
                str(row["provider"] or "").strip(), ("custom", "openai-compatible")
            )
            base_url = re.sub(r"/+$", "", str(row["base_url"] or "").strip())
            grouped.setdefault((org_id, vendor_id, protocol, base_url), []).append(row)

        used_names: dict[str, set[str]] = {}

        for (org_id, vendor_id, protocol, base_url), rows in grouped.items():
            # 旧行的 name 是厂商/连接名（model 才是模型名）
            display_name = (
                str(rows[0]["name"] or "").strip()
                or str(rows[0]["provider"] or "Provider").strip()
            )
            name_set = used_names.setdefault(org_id, {
                str(r[0])
                for r in connection.execute(
                    "SELECT display_name FROM providers WHERE organization_id=?", (org_id,)
                ).fetchall()
            })
            if display_name in name_set:
                suffix = base_url.rsplit("/", 1)[-1] if base_url else "custom"
                candidate = f"{display_name} ({suffix})"
                counter = 2
                while candidate in name_set:
                    candidate = f"{display_name} ({suffix} {counter})"
                    counter += 1
                display_name = candidate
            name_set.add(display_name)

            digest = hashlib.sha1(
                f"{org_id}|{display_name}|{base_url}".encode("utf-8")
            ).hexdigest()[:16]
            provider_id = f"prov_{digest}"
            auth_type = "none" if protocol == "ollama" else "bearer"
            # 凭据取该组最早一条 ciphertext
            connection.execute(
                "INSERT OR IGNORE INTO providers"
                "(id,organization_id,display_name,vendor_id,protocol,base_url,auth_type,"
                "api_key_ciphertext,created_by,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (provider_id, org_id, display_name, vendor_id, protocol, base_url, auth_type,
                 rows[0]["api_key_ciphertext"], rows[0]["user_id"], rows[0]["created_at"], now),
            )
            # INSERT 被 UNIQUE(organization_id,display_name) 忽略时，取回已存在的 provider id
            resolved = connection.execute(
                "SELECT id FROM providers WHERE organization_id=? AND display_name=?",
                (org_id, display_name),
            ).fetchone()
            provider_id = resolved[0]
            for row in rows:
                connection.execute(
                    "UPDATE models SET organization_id=?, provider_id=?, display_name=COALESCE(display_name,?), "
                    "model_id=COALESCE(model_id,?), context_window=COALESCE(context_window,128000), "
                    "modalities=COALESCE(modalities,'text'), test_status=COALESCE(test_status,'unknown'), "
                    "updated_at=? WHERE id=? AND provider_id IS NULL",
                    (org_id, provider_id, row["model"], row["model"], now, row["id"]),
                )

        # 每组织至多一个 is_default：保留 created_at 最早的默认行，其余清除
        default_rows = connection.execute(
            "SELECT id,organization_id FROM models WHERE is_default=1 AND organization_id IS NOT NULL "
            "ORDER BY organization_id ASC, created_at ASC, id ASC"
        ).fetchall()
        seen_orgs: set[str] = set()
        for row in default_rows:
            if row[1] in seen_orgs:
                connection.execute("UPDATE models SET is_default=0 WHERE id=?", (row[0],))
            else:
                seen_orgs.add(row[1])
