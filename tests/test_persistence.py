import sqlite3
from pathlib import Path

from contract_stack.persistence import MIGRATION_1, SQLiteRepository


def test_version_one_database_migrates_existing_stacks_to_local_owner(
    tmp_path: Path,
) -> None:
    database = tmp_path / "app.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.executescript(MIGRATION_1)
        connection.execute(
            "INSERT INTO schema_migrations(version, applied_at_utc) VALUES (1, ?)",
            ("2026-01-01T00:00:00+00:00",),
        )
        connection.execute(
            "INSERT INTO stacks(id, title, created_at_utc) VALUES (?, ?, ?)",
            ("existing-stack", "Existing policy", "2026-01-01T00:00:00+00:00"),
        )

    repository = SQLiteRepository(database)

    assert repository.health()["schema_version"] == 2
    assert repository.get_stack("existing-stack", owner_id="local") is not None
    assert repository.get_stack("existing-stack", owner_id="another-reviewer") is None

