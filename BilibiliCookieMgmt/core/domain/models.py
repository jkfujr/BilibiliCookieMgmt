from __future__ import annotations

"""
Cookie 状态、刷新状态、管理信息结构
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, Any
from datetime import datetime


class CookieStatus(str, Enum):
    VALID = "valid"
    INVALID = "invalid"
    EXPIRED = "expired"
    UNKNOWN = "unknown"


class RefreshStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    PENDING = "pending"
    NOT_NEEDED = "not_needed"


@dataclass
class ManagedInfo:
    """Cookie 管理信息"""
    DedeUserID: str
    update_time: datetime
    last_check_time: Optional[datetime] = None
    last_refresh_time: Optional[datetime] = None
    refresh_status: RefreshStatus = RefreshStatus.NOT_NEEDED
    error_message: Optional[str] = None
    header_string: Optional[str] = None
    is_enabled: bool = True
    status: CookieStatus = CookieStatus.UNKNOWN
    username: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "DedeUserID": self.DedeUserID,
            "update_time": self.update_time.isoformat(),
            "last_check_time": self.last_check_time.isoformat() if self.last_check_time else None,
            "last_refresh_time": self.last_refresh_time.isoformat() if self.last_refresh_time else None,
            "refresh_status": self.refresh_status.value,
            "error_message": self.error_message,
            "header_string": self.header_string,
            "is_enabled": self.is_enabled,
            "status": self.status.value,
            "username": self.username,
        }