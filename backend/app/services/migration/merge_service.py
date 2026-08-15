from __future__ import annotations

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
        current_conn = sqlite3.connect(self.current_db_path)
        source_conn = sqlite3.connect(source_path)
        try:
            for table_name in self._shared_tables(current_conn, source_conn):
                columns = self._shared_columns(current_conn, source_conn, table_name)
                if not columns:
                    continue
                primary_keys = self._primary_keys(current_conn, table_name)
                table_summary = {"inserted": 0, "overwritten": 0, "skipped": 0}

                for row in self._read_rows(source_conn, table_name, columns):
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
