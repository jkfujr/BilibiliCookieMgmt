from __future__ import annotations

from . import v0001_create_task_tables


MIGRATIONS = (v0001_create_task_tables,)

__all__ = ["MIGRATIONS"]
