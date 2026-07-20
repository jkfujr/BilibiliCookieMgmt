from __future__ import annotations

from pathlib import Path

import aiosqlite


class Database:
    """SQLite 连接生命周期与基础 PRAGMA。"""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.connection: aiosqlite.Connection | None = None

    async def open(self) -> aiosqlite.Connection:
        if self.connection is not None:
            return self.connection

        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = await aiosqlite.connect(self.path.as_posix(), timeout=30)
        connection.row_factory = aiosqlite.Row
        await connection.execute("PRAGMA foreign_keys = ON")
        await connection.execute("PRAGMA journal_mode = WAL")
        await connection.execute("PRAGMA busy_timeout = 30000")
        await connection.execute("PRAGMA secure_delete = ON")
        self.connection = connection
        return connection

    async def close(self) -> None:
        if self.connection is None:
            return
        await self.connection.close()
        self.connection = None
