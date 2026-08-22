"""Small SQLite owner for Interaction Fabric state.

The Milestone 6 runtime remains the authoritative classroom runtime.  Fabric
uses its own schema and connection so adding the glasses/agent vertical slice
does not replace or subtly change that runtime's persistence model.
"""

from __future__ import annotations

import sqlite3
from importlib.resources import files
from pathlib import Path
from types import TracebackType

from .fabric_persistence import FabricPersistenceMixin


class SQLiteFabricRepository(FabricPersistenceMixin):
    """Own one SQLite connection and apply only packaged Fabric migrations."""

    def __init__(self, database_path: str | Path) -> None:
        self._connection = sqlite3.connect(Path(database_path), timeout=5.0)
        try:
            self._connection.row_factory = sqlite3.Row
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._connection.execute("PRAGMA journal_mode = WAL")
            self._connection.execute("PRAGMA synchronous = FULL")
            self._apply_migrations()
        except BaseException:
            try:
                self._connection.rollback()
            finally:
                self._connection.close()
            raise

    def __enter__(self) -> SQLiteFabricRepository:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._connection.close()

    def _apply_migrations(self) -> None:
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS fabric_schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        applied = {
            int(row[0])
            for row in self._connection.execute(
                "SELECT version FROM fabric_schema_migrations"
            ).fetchall()
        }
        migration_root = files("cit_runtime").joinpath("migrations")
        migrations = sorted(
            (
                migration
                for migration in migration_root.iterdir()
                if migration.name.endswith("_interaction_fabric.sql")
            ),
            key=lambda migration: migration.name,
        )
        if not migrations:
            raise RuntimeError("No Interaction Fabric migration is packaged")
        for migration in migrations:
            version_text, _, _ = migration.name.partition("_")
            version = int(version_text)
            if version in applied:
                continue
            name = migration.name.replace("'", "''")
            script = migration.read_text(encoding="utf-8")
            self._connection.executescript(
                f"""
                BEGIN IMMEDIATE;
                {script}
                INSERT INTO fabric_schema_migrations (version, name)
                VALUES ({version}, '{name}');
                COMMIT;
                """
            )
