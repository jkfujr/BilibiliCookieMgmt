from __future__ import annotations

"""
调度器包: 包含后台周期任务(健康检查、刷新占位)。
"""

from .tasks import AppScheduler

__all__ = ["AppScheduler"]
