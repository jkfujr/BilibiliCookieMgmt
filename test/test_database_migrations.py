from __future__ import annotations

import asyncio
import sqlite3
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "BilibiliCookieMgmt"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.config.loader import resolve_app_root
from core.database import Database, MigrationError, load_or_create_fernet, migrate_database


class DatabaseMigrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "data.db"

    async def asyncTearDown(self) -> None:
        self.temp_dir.cleanup()

    async def test_fresh_database_migrates_once(self) -> None:
        database = Database(self.database_path)
        await migrate_database(database)
        await migrate_database(database)

        cursor = await database.connection.execute(
            "SELECT version, name FROM schema_migrations ORDER BY version"
        )
        self.assertEqual([tuple(row) for row in await cursor.fetchall()], [(1, "create_task_tables")])
        tables = await database.connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
        table_names = {row["name"] for row in await tables.fetchall()}
        self.assertIn("tasks", table_names)
        self.assertIn("task_items", table_names)
        self.assertNotIn("accounts", table_names)
        self.assertFalse(self.database_path.with_name("data.db.bak").exists())
        await database.close()

    async def test_nonempty_database_is_backed_up_before_migration(self) -> None:
        connection = sqlite3.connect(self.database_path)
        connection.execute("CREATE TABLE legacy_marker(value TEXT)")
        connection.execute("INSERT INTO legacy_marker(value) VALUES ('保留')")
        connection.commit()
        connection.close()

        database = Database(self.database_path)
        await migrate_database(database)
        await database.close()

        backup_path = self.database_path.with_name("data.db.bak")
        self.assertTrue(backup_path.exists())
        backup = sqlite3.connect(backup_path)
        try:
            value = backup.execute("SELECT value FROM legacy_marker").fetchone()[0]
            migration_table = backup.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'"
            ).fetchone()
        finally:
            backup.close()
        self.assertEqual(value, "保留")
        self.assertIsNone(migration_table)

    async def test_failed_migration_rolls_back_and_is_not_recorded(self) -> None:
        async def upgrade_one(connection):
            await connection.execute("CREATE TABLE first_table(id INTEGER PRIMARY KEY)")

        async def upgrade_two(connection):
            await connection.execute("CREATE TABLE rolled_back(id INTEGER PRIMARY KEY)")
            raise RuntimeError("boom")

        migrations = (
            types.SimpleNamespace(version=1, name="first", upgrade=upgrade_one),
            types.SimpleNamespace(version=2, name="second", upgrade=upgrade_two),
        )
        database = Database(self.database_path)

        with self.assertRaisesRegex(MigrationError, "v2 second"):
            await migrate_database(database, migrations)

        cursor = await database.connection.execute("SELECT version FROM schema_migrations")
        self.assertEqual([row["version"] for row in await cursor.fetchall()], [1])
        table = await database.connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'rolled_back'"
        )
        self.assertIsNone(await table.fetchone())
        await database.close()

    async def test_unknown_newer_version_is_rejected(self) -> None:
        database = Database(self.database_path)
        await migrate_database(database)
        await database.connection.execute(
            "INSERT INTO schema_migrations(version, name) VALUES (99, 'future')"
        )
        await database.connection.commit()

        with self.assertRaisesRegex(MigrationError, "高于当前程序"):
            await migrate_database(database)
        await database.close()

    async def test_duplicate_registry_version_is_rejected_before_opening_database(self) -> None:
        async def upgrade(connection):
            return None

        migrations = (
            types.SimpleNamespace(version=1, name="first", upgrade=upgrade),
            types.SimpleNamespace(version=1, name="duplicate", upgrade=upgrade),
        )
        database = Database(self.database_path)

        with self.assertRaisesRegex(MigrationError, "严格递增"):
            await migrate_database(database, migrations)

        self.assertFalse(self.database_path.exists())

    async def test_backup_failure_prevents_pending_migration(self) -> None:
        connection = sqlite3.connect(self.database_path)
        connection.execute("CREATE TABLE legacy_marker(value TEXT)")
        connection.commit()
        connection.close()
        database = Database(self.database_path)

        with patch(
            "core.database.migrator._backup_database",
            new=AsyncMock(side_effect=OSError("磁盘已满")),
        ):
            with self.assertRaisesRegex(MigrationError, "备份失败"):
                await migrate_database(database)

        table = await database.connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'tasks'"
        )
        self.assertIsNone(await table.fetchone())
        await database.close()

    async def test_restart_continues_from_last_successful_version(self) -> None:
        should_fail = True

        async def upgrade_one(connection):
            await connection.execute("CREATE TABLE first_table(id INTEGER PRIMARY KEY)")

        async def upgrade_two(connection):
            nonlocal should_fail
            if should_fail:
                raise RuntimeError("首次失败")
            await connection.execute("CREATE TABLE second_table(id INTEGER PRIMARY KEY)")

        migrations = (
            types.SimpleNamespace(version=1, name="first", upgrade=upgrade_one),
            types.SimpleNamespace(version=2, name="second", upgrade=upgrade_two),
        )
        database = Database(self.database_path)

        with self.assertRaises(MigrationError):
            await migrate_database(database, migrations)
        should_fail = False
        await migrate_database(database, migrations)

        cursor = await database.connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        )
        self.assertEqual([row["version"] for row in await cursor.fetchall()], [1, 2])
        await database.close()

    async def test_concurrent_migration_starts_are_idempotent(self) -> None:
        first = Database(self.database_path)
        second = Database(self.database_path)
        await asyncio.gather(migrate_database(first), migrate_database(second))

        cursor = await first.connection.execute("SELECT COUNT(*) AS count FROM schema_migrations")
        self.assertEqual((await cursor.fetchone())["count"], 1)
        await first.close()
        await second.close()

    async def test_concurrent_nonempty_database_keeps_pre_migration_backup(self) -> None:
        connection = sqlite3.connect(self.database_path)
        connection.execute("CREATE TABLE legacy_marker(value TEXT)")
        connection.execute("INSERT INTO legacy_marker(value) VALUES ('并发前')")
        connection.commit()
        connection.close()
        first = Database(self.database_path)
        second = Database(self.database_path)

        await asyncio.gather(migrate_database(first), migrate_database(second))

        backup = sqlite3.connect(self.database_path.with_name("data.db.bak"))
        try:
            value = backup.execute("SELECT value FROM legacy_marker").fetchone()[0]
            migration_table = backup.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'"
            ).fetchone()
        finally:
            backup.close()
        self.assertEqual(value, "并发前")
        self.assertIsNone(migration_table)
        await first.close()
        await second.close()


class RuntimePathTests(unittest.TestCase):
    def test_source_mode_uses_backend_root(self) -> None:
        module = Path("C:/project/BilibiliCookieMgmt/core/config/loader.py")
        self.assertEqual(resolve_app_root(module, frozen=False), Path("C:/project/BilibiliCookieMgmt"))

    def test_frozen_mode_uses_executable_directory(self) -> None:
        executable = Path("C:/apps/BilibiliCookieMgmt/app.exe")
        self.assertEqual(
            resolve_app_root("C:/Temp/_MEI123/core/config/loader.py", frozen=True, executable=executable),
            executable.parent,
        )


class EncryptionKeyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.database_path = self.root / "data.db"
        self.key_path = self.root / "data.key"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_generated_key_is_reused_without_overwrite(self) -> None:
        first = load_or_create_fernet(self.key_path, self.database_path)
        key_bytes = self.key_path.read_bytes()
        second = load_or_create_fernet(self.key_path, self.database_path)

        token = first.encrypt(b"payload")
        self.assertEqual(second.decrypt(token), b"payload")
        self.assertEqual(self.key_path.read_bytes(), key_bytes)

    def test_existing_database_without_key_is_rejected(self) -> None:
        self.database_path.write_bytes(b"existing")

        with self.assertRaisesRegex(RuntimeError, "缺少加密密钥"):
            load_or_create_fernet(self.key_path, self.database_path)

    def test_invalid_existing_key_is_rejected(self) -> None:
        self.key_path.write_text("invalid-key", encoding="ascii")

        with self.assertRaisesRegex(RuntimeError, "无法读取数据加密密钥"):
            load_or_create_fernet(self.key_path, self.database_path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
