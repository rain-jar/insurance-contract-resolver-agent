from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .storage import StoredDocument


SCHEMA_VERSION = 1

MIGRATION_1 = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at_utc TEXT NOT NULL
);

CREATE TABLE stacks (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);

CREATE TABLE documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stack_id TEXT NOT NULL REFERENCES stacks(id) ON DELETE CASCADE,
    display_name TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    byte_size INTEGER NOT NULL CHECK (byte_size > 0),
    sha256 TEXT NOT NULL,
    UNIQUE (stack_id, display_name)
);

CREATE TABLE analyses (
    id TEXT PRIMARY KEY,
    stack_id TEXT NOT NULL REFERENCES stacks(id) ON DELETE CASCADE,
    question TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED')),
    result_json TEXT,
    error_type TEXT,
    error_message TEXT,
    created_at_utc TEXT NOT NULL,
    started_at_utc TEXT,
    completed_at_utc TEXT
);

CREATE INDEX analyses_stack_id_index ON analyses(stack_id);
"""


class SQLiteRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.migrate()
        self.database_path.chmod(0o600)

    def migrate(self) -> None:
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations "
                "(version INTEGER PRIMARY KEY, applied_at_utc TEXT NOT NULL)"
            )
            applied = {
                row["version"]
                for row in connection.execute("SELECT version FROM schema_migrations")
            }
            if 1 not in applied:
                connection.executescript(MIGRATION_1)
                connection.execute(
                    "INSERT INTO schema_migrations(version, applied_at_utc) VALUES (?, ?)",
                    (1, _now()),
                )
            version = connection.execute(
                "SELECT MAX(version) AS version FROM schema_migrations"
            ).fetchone()["version"]
            if version != SCHEMA_VERSION:
                raise RuntimeError(f"Unsupported database schema version: {version}")

    def create_stack(
        self,
        stack_id: str,
        title: str,
        documents: list[StoredDocument],
    ) -> dict[str, Any]:
        created_at = _now()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO stacks(id, title, created_at_utc) VALUES (?, ?, ?)",
                (stack_id, title, created_at),
            )
            connection.executemany(
                "INSERT INTO documents"
                "(stack_id, display_name, relative_path, byte_size, sha256) "
                "VALUES (?, ?, ?, ?, ?)",
                [
                    (
                        stack_id,
                        item.display_name,
                        item.relative_path,
                        item.byte_size,
                        item.sha256,
                    )
                    for item in documents
                ],
            )
        result = self.get_stack(stack_id)
        if result is None:
            raise RuntimeError("The stored contract stack could not be reloaded.")
        return result

    def get_stack(self, stack_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            stack = connection.execute(
                "SELECT id, title, created_at_utc FROM stacks WHERE id = ?",
                (stack_id,),
            ).fetchone()
            if stack is None:
                return None
            documents = connection.execute(
                "SELECT display_name, relative_path, byte_size, sha256 "
                "FROM documents WHERE stack_id = ? ORDER BY id",
                (stack_id,),
            ).fetchall()
        return {**dict(stack), "documents": [dict(item) for item in documents]}

    def list_stacks(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT stacks.id, stacks.title, stacks.created_at_utc, "
                "COUNT(documents.id) AS document_count "
                "FROM stacks LEFT JOIN documents ON documents.stack_id = stacks.id "
                "GROUP BY stacks.id ORDER BY stacks.created_at_utc DESC"
            ).fetchall()
        return [dict(row) for row in rows]

    def list_expired_stack_ids(self, cutoff_utc: str) -> list[str]:
        """Return stacks whose latest persisted activity predates the cutoff."""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT stacks.id FROM stacks "
                "LEFT JOIN analyses ON analyses.stack_id = stacks.id "
                "GROUP BY stacks.id "
                "HAVING MAX(COALESCE(analyses.completed_at_utc, "
                "analyses.started_at_utc, analyses.created_at_utc, "
                "stacks.created_at_utc)) < ?",
                (cutoff_utc,),
            ).fetchall()
        return [row["id"] for row in rows]

    def delete_stack(self, stack_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM stacks WHERE id = ?", (stack_id,))
        return cursor.rowcount > 0

    def health(self) -> dict[str, Any]:
        with self._connect() as connection:
            connection.execute("SELECT 1").fetchone()
            version = connection.execute(
                "SELECT MAX(version) AS version FROM schema_migrations"
            ).fetchone()["version"]
        return {"database": "ok", "schema_version": version}

    def fail_interrupted_analyses(self) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE analyses SET status = 'FAILED', "
                "error_type = 'InterruptedAnalysis', "
                "error_message = 'Analysis interrupted by application restart.', "
                "completed_at_utc = ? WHERE status IN ('PENDING', 'RUNNING')",
                (_now(),),
            )
        return cursor.rowcount

    def create_analysis(self, analysis_id: str, stack_id: str, question: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO analyses"
                "(id, stack_id, question, status, created_at_utc) "
                "VALUES (?, ?, ?, 'PENDING', ?)",
                (analysis_id, stack_id, question, _now()),
            )

    def mark_analysis_running(self, analysis_id: str) -> None:
        self._update_analysis(
            analysis_id,
            "status = 'RUNNING', started_at_utc = ?",
            (_now(),),
        )

    def complete_analysis(self, analysis_id: str, result: dict[str, Any]) -> None:
        self._update_analysis(
            analysis_id,
            "status = 'COMPLETED', result_json = ?, completed_at_utc = ?",
            (json.dumps(result, separators=(",", ":")), _now()),
        )

    def fail_analysis(
        self,
        analysis_id: str,
        error: Exception,
        *,
        public_message: str | None = None,
    ) -> None:
        self._update_analysis(
            analysis_id,
            "status = 'FAILED', error_type = ?, error_message = ?, completed_at_utc = ?",
            (type(error).__name__, public_message or str(error), _now()),
        )

    def get_analysis(self, analysis_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id, stack_id, question, status, result_json, error_type, "
                "error_message, created_at_utc, started_at_utc, completed_at_utc "
                "FROM analyses WHERE id = ?",
                (analysis_id,),
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        serialized = result.pop("result_json")
        result["result"] = json.loads(serialized) if serialized else None
        return result

    def list_analyses(self, stack_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, stack_id, question, status, error_type, error_message, "
                "created_at_utc, started_at_utc, completed_at_utc "
                "FROM analyses WHERE stack_id = ? ORDER BY created_at_utc DESC",
                (stack_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def _update_analysis(
        self, analysis_id: str, assignments: str, parameters: tuple[Any, ...]
    ) -> None:
        with self._connect() as connection:
            cursor = connection.execute(
                f"UPDATE analyses SET {assignments} WHERE id = ?",
                (*parameters, analysis_id),
            )
        if cursor.rowcount != 1:
            raise KeyError(f"Unknown analysis: {analysis_id}")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection


def _now() -> str:
    return datetime.now(UTC).isoformat()
