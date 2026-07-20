from __future__ import annotations

import aiosqlite


version = 1
name = "create_task_tables"


async def upgrade(connection: aiosqlite.Connection) -> None:
    """创建任务与任务项存储。"""
    statements = (
        """
        CREATE TABLE tasks (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            source TEXT NOT NULL,
            status TEXT NOT NULL,
            parent_task_id TEXT,
            payload_json TEXT NOT NULL DEFAULT '{}',
            total INTEGER NOT NULL DEFAULT 0,
            succeeded INTEGER NOT NULL DEFAULT 0,
            invalid INTEGER NOT NULL DEFAULT 0,
            failed INTEGER NOT NULL DEFAULT 0,
            skipped INTEGER NOT NULL DEFAULT 0,
            cancelled INTEGER NOT NULL DEFAULT 0,
            revision INTEGER NOT NULL DEFAULT 0,
            cancel_requested INTEGER NOT NULL DEFAULT 0,
            error_message TEXT,
            created_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (parent_task_id) REFERENCES tasks(id) ON DELETE SET NULL
        )
        """,
        """
        CREATE TABLE task_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            position INTEGER NOT NULL,
            line_number INTEGER,
            subject_id TEXT,
            status TEXT NOT NULL,
            input_json TEXT NOT NULL DEFAULT '{}',
            secret_payload BLOB,
            result_json TEXT NOT NULL DEFAULT '{}',
            revision INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
            UNIQUE (task_id, position)
        )
        """,
        "CREATE INDEX ix_tasks_history ON tasks(created_at DESC)",
        "CREATE INDEX ix_tasks_status_history ON tasks(status, created_at DESC)",
        "CREATE INDEX ix_tasks_type_history ON tasks(type, created_at DESC)",
        "CREATE INDEX ix_tasks_source_history ON tasks(source, created_at DESC)",
        "CREATE UNIQUE INDEX ux_tasks_retry_parent ON tasks(parent_task_id) WHERE parent_task_id IS NOT NULL",
        "CREATE INDEX ix_task_items_claim ON task_items(task_id, status, position)",
        "CREATE INDEX ix_task_items_revision ON task_items(task_id, revision)",
    )
    for statement in statements:
        await connection.execute(statement)
