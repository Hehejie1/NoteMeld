from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from app.utils.storage_paths import database_path


class MigrationMergeService:
    def __init__(self, current_db_path: str | Path | None = None):
        self.current_db_path = Path(current_db_path or database_path())

    def merge_database(self, import_db_path: str | Path) -> dict[str, dict[str, int]]:
        source_path = Path(import_db_path)
        if not source_path.exists():
            raise FileNotFoundError(f"import database missing: {source_path}")

        summary: dict[str, dict[str, int]] = {}
        whiteboard_id_map: dict[str, str] = {}
        card_id_map: dict[str, str] = {}
        relation_id_map: dict[str, str] = {}
        current_conn = sqlite3.connect(self.current_db_path)
        source_conn = sqlite3.connect(source_path)
        try:
            current_conn.execute("PRAGMA foreign_keys=ON")
            source_conn.execute("PRAGMA foreign_keys=ON")
            for table_name in self._shared_tables(current_conn, source_conn):
                columns = self._shared_columns(current_conn, source_conn, table_name)
                if not columns:
                    continue
                primary_keys = self._primary_keys(current_conn, table_name)
                table_summary = {"inserted": 0, "overwritten": 0, "skipped": 0}

                for source_row in self._read_rows(source_conn, table_name, columns):
                    row, skip = self._map_whiteboard_row(
                        current_conn,
                        table_name,
                        source_row,
                        whiteboard_id_map=whiteboard_id_map,
                        card_id_map=card_id_map,
                        relation_id_map=relation_id_map,
                    )
                    if skip:
                        table_summary["skipped"] += 1
                        continue
                    if primary_keys:
                        existed = self._pk_exists(current_conn, table_name, primary_keys, row)
                        if existed:
                            self._update_row(current_conn, table_name, columns, primary_keys, row)
                            table_summary["overwritten"] += 1
                        else:
                            self._insert_row(current_conn, table_name, columns, row)
                            table_summary["inserted"] += 1
                        continue

                    if self._row_exists(current_conn, table_name, columns, row):
                        table_summary["skipped"] += 1
                        continue
                    self._insert_row(current_conn, table_name, columns, row)
                    table_summary["inserted"] += 1

                if any(table_summary.values()):
                    summary[table_name] = table_summary

            current_conn.commit()
            return summary
        finally:
            source_conn.close()
            current_conn.close()

    def _map_whiteboard_row(
        self,
        conn: sqlite3.Connection,
        table_name: str,
        source_row: dict,
        *,
        whiteboard_id_map: dict[str, str],
        card_id_map: dict[str, str],
        relation_id_map: dict[str, str],
    ) -> tuple[dict, bool]:
        row = dict(source_row)
        if table_name == "whiteboards" and {"id", "conversation_id"} <= row.keys():
            source_id = str(row["id"])
            owner_id = str(row["conversation_id"])
            legacy_canvas_id = row.get("legacy_canvas_id")
            legacy_binding = None
            if legacy_canvas_id is not None:
                legacy_binding = conn.execute(
                    "SELECT id, conversation_id FROM whiteboards "
                    "WHERE legacy_canvas_id IS ? LIMIT 1",
                    (legacy_canvas_id,),
                ).fetchone()

            if legacy_binding is not None and str(legacy_binding[1]) == owner_id:
                target_id = str(legacy_binding[0])
            else:
                target_id = self._ownership_aware_id(
                    conn,
                    table_name="whiteboards",
                    id_column="id",
                    source_id=source_id,
                    owner_column="conversation_id",
                    owner_id=owner_id,
                    prefix="wb_import",
                )
                if legacy_binding is not None:
                    row["legacy_canvas_id"] = None
            whiteboard_id_map[source_id] = target_id
            row["id"] = target_id
            return row, False

        if table_name == "whiteboard_cards" and {"id", "whiteboard_id"} <= row.keys():
            source_id = str(row["id"])
            target_board_id = whiteboard_id_map.get(
                str(row["whiteboard_id"]),
                str(row["whiteboard_id"]),
            )
            target_id = self._ownership_aware_id(
                conn,
                table_name="whiteboard_cards",
                id_column="id",
                source_id=source_id,
                owner_column="whiteboard_id",
                owner_id=target_board_id,
                prefix="card_import",
            )
            card_id_map[source_id] = target_id
            row["id"] = target_id
            row["whiteboard_id"] = target_board_id
            if row.get("card_type") == "whiteboard" and row.get("content_json"):
                try:
                    content = json.loads(row["content_json"])
                except (TypeError, ValueError):
                    content = None
                if isinstance(content, dict):
                    child_id = content.get("child_whiteboard_id")
                    if child_id in whiteboard_id_map:
                        content["child_whiteboard_id"] = whiteboard_id_map[child_id]
                        row["content_json"] = json.dumps(
                            content,
                            ensure_ascii=False,
                            separators=(",", ":"),
                            sort_keys=True,
                        )
            return row, False

        if table_name == "whiteboard_relations" and {
            "id",
            "whiteboard_id",
            "source_card_id",
            "target_card_id",
        } <= row.keys():
            source_id = str(row["id"])
            target_board_id = whiteboard_id_map.get(
                str(row["whiteboard_id"]),
                str(row["whiteboard_id"]),
            )
            target_id = self._ownership_aware_id(
                conn,
                table_name="whiteboard_relations",
                id_column="id",
                source_id=source_id,
                owner_column="whiteboard_id",
                owner_id=target_board_id,
                prefix="rel_import",
            )
            relation_id_map[source_id] = target_id
            row["id"] = target_id
            row["whiteboard_id"] = target_board_id
            row["source_card_id"] = card_id_map.get(
                str(row["source_card_id"]),
                str(row["source_card_id"]),
            )
            row["target_card_id"] = card_id_map.get(
                str(row["target_card_id"]),
                str(row["target_card_id"]),
            )
            if not self._relation_endpoints_belong_to_board(conn, row):
                return row, True
            return row, False

        if table_name == "whiteboard_note_links" and {
            "whiteboard_id",
            "note_task_id",
        } <= row.keys():
            row["whiteboard_id"] = whiteboard_id_map.get(
                str(row["whiteboard_id"]),
                str(row["whiteboard_id"]),
            )
            existing = conn.execute(
                "SELECT whiteboard_id FROM whiteboard_note_links "
                "WHERE note_task_id IS ? LIMIT 1",
                (row["note_task_id"],),
            ).fetchone()
            if existing is not None and existing[0] != row["whiteboard_id"]:
                return row, True
            return row, False

        return row, False

    def _ownership_aware_id(
        self,
        conn: sqlite3.Connection,
        *,
        table_name: str,
        id_column: str,
        source_id: str,
        owner_column: str,
        owner_id: str,
        prefix: str,
    ) -> str:
        existing = conn.execute(
            f"SELECT {self._ident(owner_column)} FROM {self._ident(table_name)} "
            f"WHERE {self._ident(id_column)} IS ? LIMIT 1",
            (source_id,),
        ).fetchone()
        if existing is None or str(existing[0]) == owner_id:
            return source_id

        for salt in range(100):
            digest = hashlib.sha256(
                f"{table_name}:{source_id}:{owner_id}:{salt}".encode("utf-8")
            ).hexdigest()[:20]
            candidate = f"{prefix}_{digest}"
            candidate_owner = conn.execute(
                f"SELECT {self._ident(owner_column)} FROM {self._ident(table_name)} "
                f"WHERE {self._ident(id_column)} IS ? LIMIT 1",
                (candidate,),
            ).fetchone()
            if candidate_owner is None or str(candidate_owner[0]) == owner_id:
                return candidate
        raise RuntimeError(f"unable to allocate migration id for {table_name}")

    @staticmethod
    def _relation_endpoints_belong_to_board(
        conn: sqlite3.Connection,
        row: dict,
    ) -> bool:
        owners = conn.execute(
            "SELECT id, whiteboard_id FROM whiteboard_cards WHERE id IN (?, ?)",
            (row["source_card_id"], row["target_card_id"]),
        ).fetchall()
        return (
            len(owners) == 2
            and row["source_card_id"] != row["target_card_id"]
            and all(owner[1] == row["whiteboard_id"] for owner in owners)
        )

    def _shared_tables(self, current_conn: sqlite3.Connection, source_conn: sqlite3.Connection) -> list[str]:
        current_tables = set(self._table_names(current_conn))
        shared_tables = [
            name for name in self._table_names(source_conn) if name in current_tables
        ]
        preferred_order = (
            "conversations",
            "conversation_messages",
            "note_documents",
            "whiteboards",
            "whiteboard_cards",
            "whiteboard_relations",
            "whiteboard_note_links",
        )
        preferred = [name for name in preferred_order if name in shared_tables]
        preferred_set = set(preferred)
        return preferred + [name for name in shared_tables if name not in preferred_set]

    def _table_names(self, conn: sqlite3.Connection) -> list[str]:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        return [row[0] for row in rows if row and row[0]]

    def _shared_columns(self, current_conn: sqlite3.Connection, source_conn: sqlite3.Connection, table_name: str) -> list[str]:
        current_columns = {row[1] for row in current_conn.execute(f"PRAGMA table_info({self._ident(table_name)})").fetchall()}
        return [
            row[1]
            for row in source_conn.execute(f"PRAGMA table_info({self._ident(table_name)})").fetchall()
            if row[1] in current_columns
        ]

    def _primary_keys(self, conn: sqlite3.Connection, table_name: str) -> list[str]:
        rows = conn.execute(f"PRAGMA table_info({self._ident(table_name)})").fetchall()
        ordered = sorted((row for row in rows if row[5]), key=lambda row: row[5])
        return [row[1] for row in ordered]

    def _read_rows(self, conn: sqlite3.Connection, table_name: str, columns: list[str]) -> list[dict]:
        sql = f"SELECT {', '.join(self._ident(column) for column in columns)} FROM {self._ident(table_name)}"
        cursor = conn.execute(sql)
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def _pk_exists(self, conn: sqlite3.Connection, table_name: str, primary_keys: list[str], row: dict) -> bool:
        where = " AND ".join(f"{self._ident(column)} IS ?" for column in primary_keys)
        params = [row.get(column) for column in primary_keys]
        found = conn.execute(f"SELECT 1 FROM {self._ident(table_name)} WHERE {where} LIMIT 1", params).fetchone()
        return found is not None

    def _row_exists(self, conn: sqlite3.Connection, table_name: str, columns: list[str], row: dict) -> bool:
        where = " AND ".join(f"{self._ident(column)} IS ?" for column in columns)
        params = [row.get(column) for column in columns]
        found = conn.execute(f"SELECT 1 FROM {self._ident(table_name)} WHERE {where} LIMIT 1", params).fetchone()
        return found is not None

    def _update_row(
        self,
        conn: sqlite3.Connection,
        table_name: str,
        columns: list[str],
        primary_keys: list[str],
        row: dict,
    ) -> None:
        update_columns = [column for column in columns if column not in primary_keys]
        if not update_columns:
            return
        assignments = ", ".join(f"{self._ident(column)} = ?" for column in update_columns)
        where = " AND ".join(f"{self._ident(column)} IS ?" for column in primary_keys)
        conn.execute(
            f"UPDATE {self._ident(table_name)} SET {assignments} WHERE {where}",
            [row.get(column) for column in update_columns] + [row.get(column) for column in primary_keys],
        )

    def _insert_row(self, conn: sqlite3.Connection, table_name: str, columns: list[str], row: dict) -> None:
        placeholders = ", ".join("?" for _ in columns)
        column_sql = ", ".join(self._ident(column) for column in columns)
        conn.execute(
            f"INSERT INTO {self._ident(table_name)} ({column_sql}) VALUES ({placeholders})",
            [row.get(column) for column in columns],
        )

    def _ident(self, value: str) -> str:
        return f'"{str(value).replace(chr(34), chr(34) * 2)}"'
