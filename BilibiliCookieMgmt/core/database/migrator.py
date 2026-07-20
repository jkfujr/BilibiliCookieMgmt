from __future__ import annotations

import os
from pathlib import Path
from types import ModuleType
from typing import Iterable

import aiosqlite

from .connection import Database
from .migrations import MIGRATIONS


class MigrationError(RuntimeError):
    pass


def _validate_registry(migrations: Iterable[ModuleType]) -> tuple[ModuleType, ...]:
    registered = tuple(migrations)
    versions = [int(item.version) for item in registered]
    if versions != sorted(versions) or len(versions) != len(set(versions)):
        raise MigrationError("数据库迁移版本必须严格递增且不得重复")
    return registered


async def _create_schema_migrations(connection: aiosqlite.Connection) -> None:
    await connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


async def _schema_migrations_exists(connection: aiosqlite.Connection) -> bool:
    cursor = await connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'"
    )
    return await cursor.fetchone() is not None


async def _applied_versions(connection: aiosqlite.Connection) -> set[int]:
    if not await _schema_migrations_exists(connection):
        return set()
    cursor = await connection.execute("SELECT version FROM schema_migrations ORDER BY version")
    rows = await cursor.fetchall()
    return {int(row["version"]) for row in rows}


async def _backup_database(path: Path) -> None:
    backup_path = path.with_name(f"{path.name}.bak")
    temp_path = backup_path.with_suffix(f"{backup_path.suffix}.tmp")
    if temp_path.exists():
        temp_path.unlink()

    source: aiosqlite.Connection | None = None
    backup: aiosqlite.Connection | None = None
    try:
        try:
            source = await aiosqlite.connect(path.as_posix())
            backup = await aiosqlite.connect(temp_path.as_posix())
            await source.backup(backup)
            await backup.commit()
        finally:
            if backup is not None:
                await backup.close()
            if source is not None:
                await source.close()
        os.replace(temp_path, backup_path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


async def migrate_database(database: Database, migrations: Iterable[ModuleType] = MIGRATIONS) -> None:
    registered = _validate_registry(migrations)
    existed_with_data = database.path.exists() and database.path.stat().st_size > 0
    connection = await database.open()
    known_versions = {int(item.version) for item in registered}
    target_version = max(known_versions, default=0)
    pending: list[ModuleType] = []
    applied: set[int] = set()
    migration: ModuleType | None = None

    try:
        await connection.execute("BEGIN IMMEDIATE")
        applied = await _applied_versions(connection)
        unknown = applied - known_versions
        current_version = max(applied, default=0)
        if unknown:
            raise MigrationError(
                f"数据库版本高于当前程序: 当前 {current_version}, 目标 {target_version}, "
                f"无法识别 {sorted(unknown)}"
            )

        pending = [item for item in registered if int(item.version) not in applied]
        if pending and existed_with_data:
            try:
                await _backup_database(database.path)
            except Exception as exc:
                raise MigrationError(
                    f"数据库迁移前备份失败: 当前 {current_version}, 目标 {target_version}: {exc}"
                ) from exc

        await _create_schema_migrations(connection)
        if not pending:
            await connection.commit()
        else:
            migration = pending.pop(0)
            await migration.upgrade(connection)
            await connection.execute(
                "INSERT INTO schema_migrations(version, name) VALUES (?, ?)",
                (int(migration.version), str(migration.name)),
            )
            await connection.commit()
    except MigrationError:
        await connection.rollback()
        raise
    except Exception as exc:
        await connection.rollback()
        migration_label = f"v{migration.version} {migration.name}" if migration else "初始化迁移表"
        raise MigrationError(
            f"数据库迁移失败: 当前 {max(applied, default=0)}, "
            f"目标 {target_version}, 失败迁移 {migration_label}: {exc}"
        ) from exc

    for migration in pending:
        current: set[int] = set()
        try:
            await connection.execute("BEGIN IMMEDIATE")
            current = await _applied_versions(connection)
            unknown = current - known_versions
            if unknown:
                raise MigrationError(
                    f"数据库版本高于当前程序: 当前 {max(current)}, 目标 {target_version}, "
                    f"无法识别 {sorted(unknown)}"
                )
            if int(migration.version) in current:
                await connection.rollback()
                continue
            await migration.upgrade(connection)
            await connection.execute(
                "INSERT INTO schema_migrations(version, name) VALUES (?, ?)",
                (int(migration.version), str(migration.name)),
            )
            await connection.commit()
        except MigrationError:
            await connection.rollback()
            raise
        except Exception as exc:
            await connection.rollback()
            raise MigrationError(
                f"数据库迁移失败: 当前 {max(current, default=0)}, "
                f"目标 {target_version}, 失败迁移 v{migration.version} {migration.name}: {exc}"
            ) from exc

    final_versions = await _applied_versions(connection)
    if final_versions != known_versions:
        raise MigrationError(
            f"数据库未达到目标版本: 当前 {sorted(final_versions)}, 目标 {sorted(known_versions)}"
        )
