from __future__ import annotations

"""
设置服务: 读取、保存并应用运行配置。
"""

from dataclasses import replace
from typing import Any, Dict

from fastapi import FastAPI

from ..config import AppConfig, build_config, config_to_dict, save_config_file
from ..config.loader import SchedulerConfig
from ..infrastructure.notifications import GotifyNotificationService, NoopNotificationService
from ..scheduler import AppScheduler


def build_notification_service(cfg: AppConfig):
    if cfg.gotify.enable and cfg.gotify.url and cfg.gotify.token:
        return GotifyNotificationService(
            url=cfg.gotify.url,
            token=cfg.gotify.token,
            default_title=cfg.gotify.title,
            default_priority=cfg.gotify.priority,
        )
    return NoopNotificationService()


class SettingsService:
    def __init__(self, app: FastAPI):
        self.app = app

    def get_settings(self) -> Dict[str, Any]:
        return self._settings_view(self.app.state.config)

    async def update_settings(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        current = self.app.state.config
        data = self._payload_to_config_data(payload, current)
        next_config = build_config(data, current.config_path)
        save_config_file(next_config)

        restart_required = self._restart_required(current, next_config)
        restart_scheduler = self._scheduler_changed(current, next_config)
        gotify_changed = config_to_dict(current)["GOTIFY"] != config_to_dict(next_config)["GOTIFY"]
        await self._apply_runtime_config(current, next_config, restart_scheduler, gotify_changed)

        return {
            "settings": self._settings_view(next_config),
            "restart_required": restart_required,
            "message": "已保存，部分设置需重启后生效" if restart_required else "设置已保存并生效",
        }

    def _settings_view(self, cfg: AppConfig) -> Dict[str, Any]:
        data = config_to_dict(cfg)
        data["API_TOKEN"]["token"] = self._secret_view(cfg.api_token.token)
        data["GOTIFY"]["token"] = self._secret_view(cfg.gotify.token)
        return data

    @staticmethod
    def _secret_view(value: str) -> Dict[str, Any]:
        return {
            "configured": bool(value),
            "masked": "****" if value else "",
        }

    def _payload_to_config_data(self, payload: Dict[str, Any], current: AppConfig) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("设置内容必须是对象")

        base = config_to_dict(current)
        base["HOST"] = self._string(payload, "HOST", current.host)
        base["PORT"] = self._positive_int(payload, "PORT", current.port)

        api_token = self._dict(payload, "API_TOKEN")
        base["API_TOKEN"]["enable"] = self._bool(api_token, "enable", current.api_token.enable)
        base["API_TOKEN"]["token"] = self._secret_value(api_token, "token", current.api_token.token)

        storage = self._dict(payload, "STORAGE")
        base["STORAGE"]["cookie_dir"] = self._string(storage, "cookie_dir", current.storage.cookie_dir)

        gotify = self._dict(payload, "GOTIFY")
        base["GOTIFY"]["enable"] = self._bool(gotify, "enable", current.gotify.enable)
        base["GOTIFY"]["url"] = self._string(gotify, "url", current.gotify.url)
        base["GOTIFY"]["token"] = self._secret_value(gotify, "token", current.gotify.token)
        base["GOTIFY"]["priority"] = self._int(gotify, "priority", current.gotify.priority)
        base["GOTIFY"]["title"] = self._string(gotify, "title", current.gotify.title)

        scheduler = self._dict(payload, "SCHEDULER")
        self._merge_scheduler(base["SCHEDULER"], scheduler, current.scheduler)

        bili = self._dict(payload, "BILI")
        base["BILI"]["bili_ticket_enabled"] = self._bool(bili, "bili_ticket_enabled", current.bili.bili_ticket_enabled)
        base["BILI"]["risk_control_enabled"] = self._bool(bili, "risk_control_enabled", current.bili.risk_control_enabled)
        return base

    def _merge_scheduler(self, target: Dict[str, Any], payload: Dict[str, Any], current: SchedulerConfig) -> None:
        cookie_check = self._dict(payload, "COOKIE_CHECK")
        target["COOKIE_CHECK"]["enable"] = self._bool(cookie_check, "enable", current.cookie_check.enable)
        target["COOKIE_CHECK"]["interval_seconds"] = self._positive_int(cookie_check, "interval_seconds", current.cookie_check.interval_seconds)

        cookie_refresh = self._dict(payload, "COOKIE_REFRESH")
        target["COOKIE_REFRESH"]["enable"] = self._bool(cookie_refresh, "enable", current.cookie_refresh.enable)
        target["COOKIE_REFRESH"]["interval_seconds"] = self._positive_int(cookie_refresh, "interval_seconds", current.cookie_refresh.interval_seconds)
        target["COOKIE_REFRESH"]["scan_interval_seconds"] = self._positive_int(cookie_refresh, "scan_interval_seconds", current.cookie_refresh.scan_interval_seconds)

        ticket_refresh = self._dict(payload, "BILI_TICKET_REFRESH")
        target["BILI_TICKET_REFRESH"]["enable"] = self._bool(ticket_refresh, "enable", current.bili_ticket_refresh.enable)
        target["BILI_TICKET_REFRESH"]["interval_seconds"] = self._positive_int(ticket_refresh, "interval_seconds", current.bili_ticket_refresh.interval_seconds)

        risk_check = self._dict(payload, "RISK_CONTROL_CHECK")
        target["RISK_CONTROL_CHECK"]["interval_seconds"] = self._positive_int(risk_check, "interval_seconds", current.risk_control_check.interval_seconds)

    async def _apply_runtime_config(
        self,
        current: AppConfig,
        next_config: AppConfig,
        restart_scheduler: bool,
        gotify_changed: bool,
    ) -> None:
        current.host = next_config.host
        current.port = next_config.port
        current.storage = replace(next_config.storage)
        current.config_path = next_config.config_path
        current.api_token = replace(next_config.api_token)
        current.gotify = replace(next_config.gotify)
        current.scheduler = self._copy_scheduler(next_config.scheduler)
        current.bili = replace(next_config.bili)

        service = self.app.state.cookie_service
        service.config = current
        service.repo.bili_ticket_enabled = current.bili.bili_ticket_enabled

        if gotify_changed:
            old_notification = getattr(self.app.state, "notification", None)
            service.notification = build_notification_service(current)
            self.app.state.notification = service.notification
            if old_notification is not None and old_notification is not service.notification and hasattr(old_notification, "aclose"):
                await old_notification.aclose()

        if restart_scheduler:
            old_scheduler = getattr(self.app.state, "scheduler", None)
            if old_scheduler is not None:
                await old_scheduler.stop()
            scheduler = AppScheduler(service=service, config=current)
            await scheduler.start(self.app)

    @staticmethod
    def _copy_scheduler(scheduler: SchedulerConfig) -> SchedulerConfig:
        return SchedulerConfig(
            cookie_check=replace(scheduler.cookie_check),
            cookie_refresh=replace(scheduler.cookie_refresh),
            bili_ticket_refresh=replace(scheduler.bili_ticket_refresh),
            risk_control_check=replace(scheduler.risk_control_check),
        )

    @staticmethod
    def _restart_required(current: AppConfig, next_config: AppConfig) -> bool:
        return (
            current.host != next_config.host
            or current.port != next_config.port
            or current.storage.cookie_dir != next_config.storage.cookie_dir
        )

    @staticmethod
    def _scheduler_changed(current: AppConfig, next_config: AppConfig) -> bool:
        current_data = config_to_dict(current)
        next_data = config_to_dict(next_config)
        return current_data["SCHEDULER"] != next_data["SCHEDULER"] or current_data["BILI"] != next_data["BILI"]

    @staticmethod
    def _dict(data: Dict[str, Any], key: str) -> Dict[str, Any]:
        value = data.get(key, {})
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError(f"{key} 必须是对象")
        return value

    @staticmethod
    def _bool(data: Dict[str, Any], key: str, default: bool) -> bool:
        value = data.get(key, default)
        if not isinstance(value, bool):
            raise ValueError(f"{key} 必须是布尔值")
        return value

    @staticmethod
    def _int(data: Dict[str, Any], key: str, default: int) -> int:
        value = data.get(key, default)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{key} 必须是整数")
        return value

    def _positive_int(self, data: Dict[str, Any], key: str, default: int) -> int:
        value = self._int(data, key, default)
        if value <= 0:
            raise ValueError(f"{key} 必须是正整数")
        return value

    @staticmethod
    def _string(data: Dict[str, Any], key: str, default: str) -> str:
        value = data.get(key, default)
        if not isinstance(value, str):
            raise ValueError(f"{key} 必须是字符串")
        return value

    @staticmethod
    def _secret_value(data: Dict[str, Any], key: str, current: str) -> str:
        value = data.get(key)
        if value is None:
            return current
        if not isinstance(value, dict):
            raise ValueError(f"{key} 必须是对象")
        if "value" not in value:
            return current
        next_value = value["value"]
        if not isinstance(next_value, str):
            raise ValueError(f"{key}.value 必须是字符串")
        return next_value
