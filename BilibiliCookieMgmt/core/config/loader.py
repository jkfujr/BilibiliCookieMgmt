from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from pathlib import Path
import os
import argparse
import json
import logging
import secrets
import yaml

DEFAULT_CONFIG_PATH = "data/config.json"
LEGACY_CONFIG_PATH = "config.yaml"
logger = logging.getLogger(__name__)


@dataclass
class ApiTokenConfig:
    enable: bool = False
    token: str = ""


@dataclass
class StorageConfig:
    cookie_dir: str = "./data/cookie"


@dataclass
class GotifyConfig:
    enable: bool = False
    url: str = ""
    token: str = ""
    priority: int = 5
    title: str = "BilibiliCookieMgmt"


@dataclass
class SchedulerItemConfig:
    enable: bool = False
    interval_seconds: int = 43200
    scan_interval_seconds: int = 21600


@dataclass
class SchedulerIntervalConfig:
    interval_seconds: int = 43200


@dataclass
class SchedulerConfig:
    cookie_check: SchedulerItemConfig = field(default_factory=SchedulerItemConfig)
    cookie_refresh: SchedulerItemConfig = field(default_factory=lambda: SchedulerItemConfig(enable=False, interval_seconds=86400))
    bili_ticket_refresh: SchedulerIntervalConfig = field(default_factory=lambda: SchedulerIntervalConfig(interval_seconds=43200))
    risk_control_check: SchedulerIntervalConfig = field(default_factory=lambda: SchedulerIntervalConfig(interval_seconds=3600))


@dataclass
class BiliConfig:
    bili_ticket_enabled: bool = False
    risk_control_enabled: bool = False


@dataclass
class AppConfig:
    host: str = "0.0.0.0"
    port: int = 18000
    api_token: ApiTokenConfig = field(default_factory=ApiTokenConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    gotify: GotifyConfig = field(default_factory=GotifyConfig)
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)
    bili: BiliConfig = field(default_factory=BiliConfig)
    config_path: str = DEFAULT_CONFIG_PATH


def _ensure_dirs(cfg: AppConfig) -> None:
    os.makedirs(cfg.storage.cookie_dir, exist_ok=True)


def config_to_dict(cfg: AppConfig) -> Dict[str, Any]:
    return {
        "HOST": cfg.host,
        "PORT": cfg.port,
        "API_TOKEN": {
            "enable": cfg.api_token.enable,
            "token": cfg.api_token.token,
        },
        "STORAGE": {
            "cookie_dir": cfg.storage.cookie_dir,
        },
        "GOTIFY": {
            "enable": cfg.gotify.enable,
            "url": cfg.gotify.url,
            "token": cfg.gotify.token,
            "priority": cfg.gotify.priority,
            "title": cfg.gotify.title,
        },
        "SCHEDULER": {
            "COOKIE_CHECK": {
                "enable": cfg.scheduler.cookie_check.enable,
                "interval_seconds": cfg.scheduler.cookie_check.interval_seconds,
            },
            "COOKIE_REFRESH": {
                "enable": cfg.scheduler.cookie_refresh.enable,
                "interval_seconds": cfg.scheduler.cookie_refresh.interval_seconds,
                "scan_interval_seconds": cfg.scheduler.cookie_refresh.scan_interval_seconds,
            },
            "BILI_TICKET_REFRESH": {
                "interval_seconds": cfg.scheduler.bili_ticket_refresh.interval_seconds,
            },
            "RISK_CONTROL_CHECK": {
                "interval_seconds": cfg.scheduler.risk_control_check.interval_seconds,
            },
        },
        "BILI": {
            "bili_ticket_enabled": cfg.bili.bili_ticket_enabled,
            "risk_control_enabled": cfg.bili.risk_control_enabled,
        },
    }


def save_config_file(cfg: AppConfig, config_path: str | Path | None = None) -> None:
    _write_config_data(Path(config_path or cfg.config_path), config_to_dict(cfg))


def _write_config_data(config_path: str | Path, data: Dict[str, Any]) -> None:
    path = Path(config_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _read_json_config(config_path: str | Path) -> Dict[str, Any]:
    with Path(config_path).open("r", encoding="utf-8") as f:
        data = json.load(f) or {}
    if not isinstance(data, dict):
        raise ValueError("配置文件根节点必须是对象")
    return data


def _read_legacy_yaml_config(config_path: str | Path) -> Dict[str, Any]:
    with Path(config_path).open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError("旧配置文件根节点必须是对象")
    return data


def _generate_api_token() -> str:
    return secrets.token_urlsafe(32)


def _build_default_config_data(token: str) -> Dict[str, Any]:
    return {
        "HOST": "0.0.0.0",
        "PORT": 18000,
        "API_TOKEN": {
            "enable": True,
            "token": token,
        },
        "STORAGE": {
            "cookie_dir": "./data/cookie",
        },
        "GOTIFY": {
            "enable": False,
            "url": "http://HOST:PORT",
            "token": "",
            "priority": 5,
            "title": "BilibiliCookieMgmt",
        },
        "SCHEDULER": {
            "COOKIE_CHECK": {
                "enable": True,
                "interval_seconds": 600,
            },
            "COOKIE_REFRESH": {
                "enable": True,
                "interval_seconds": 2592000,
                "scan_interval_seconds": 21600,
            },
            "BILI_TICKET_REFRESH": {
                "interval_seconds": 43200,
            },
            "RISK_CONTROL_CHECK": {
                "interval_seconds": 3600,
            },
        },
        "BILI": {
            "bili_ticket_enabled": False,
            "risk_control_enabled": False,
        },
    }


def build_config(data: Dict[str, Any], config_path: str | Path = DEFAULT_CONFIG_PATH) -> AppConfig:
    api_token_cfg = data.get("API_TOKEN", {})
    storage_cfg = data.get("STORAGE", {})
    gotify_cfg = data.get("GOTIFY", {})
    scheduler_cfg = data.get("SCHEDULER", {})
    check_cfg_src = scheduler_cfg.get("COOKIE_CHECK", {}) if scheduler_cfg else {}
    refresh_cfg_src = scheduler_cfg.get("COOKIE_REFRESH", {}) if scheduler_cfg else {}
    ticket_refresh_cfg_src = scheduler_cfg.get("BILI_TICKET_REFRESH", {}) if scheduler_cfg else {}
    risk_check_cfg_src = scheduler_cfg.get("RISK_CONTROL_CHECK", {}) if scheduler_cfg else {}
    bili_cfg = data.get("BILI", {})

    return AppConfig(
        host=str(data.get("HOST", "0.0.0.0")),
        port=int(data.get("PORT", 18000)),
        api_token=ApiTokenConfig(
            enable=bool(api_token_cfg.get("enable", False)),
            token=str(api_token_cfg.get("token", "")),
        ),
        storage=StorageConfig(
            cookie_dir=str(storage_cfg.get("cookie_dir", "./data/cookie")),
        ),
        gotify=GotifyConfig(
            enable=bool(gotify_cfg.get("enable", False)),
            url=str(gotify_cfg.get("url", "")),
            token=str(gotify_cfg.get("token", "")),
            priority=int(gotify_cfg.get("priority", 5)),
            title=str(gotify_cfg.get("title", "BilibiliCookieMgmt")),
        ),
        scheduler=SchedulerConfig(
            cookie_check=SchedulerItemConfig(
                enable=bool(check_cfg_src.get("enable", False)),
                interval_seconds=int(check_cfg_src.get("interval_seconds", 600)),
            ),
            cookie_refresh=SchedulerItemConfig(
                enable=bool(refresh_cfg_src.get("enable", False)),
                interval_seconds=int(refresh_cfg_src.get("interval_seconds", 86400)),
                scan_interval_seconds=int(refresh_cfg_src.get("scan_interval_seconds", 21600)),
            ),
            bili_ticket_refresh=SchedulerIntervalConfig(
                interval_seconds=int(ticket_refresh_cfg_src.get("interval_seconds", 43200)),
            ),
            risk_control_check=SchedulerIntervalConfig(
                interval_seconds=int(risk_check_cfg_src.get("interval_seconds", 3600)),
            ),
        ),
        bili=BiliConfig(
            bili_ticket_enabled=bool(bili_cfg.get("bili_ticket_enabled", False)),
            risk_control_enabled=bool(bili_cfg.get("risk_control_enabled", False)),
        ),
        config_path=Path(config_path).as_posix(),
    )


def load_config(config_path: Optional[str] = None) -> AppConfig:
    """
    加载配置
    """
    # 优先使用命令行参数指定的配置文件
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("-c", "--config", help="配置文件路径")
    args, _ = parser.parse_known_args()

    if args.config:
        config_path = args.config

    using_default_path = config_path is None
    if config_path is None:
        config_path = DEFAULT_CONFIG_PATH

    config_file = Path(config_path)
    if config_file.suffix.lower() != ".json":
        raise ValueError("仅支持 JSON 配置文件，请使用 data/config.json")

    if using_default_path and not config_file.exists() and Path(LEGACY_CONFIG_PATH).exists():
        data = _read_legacy_yaml_config(LEGACY_CONFIG_PATH)
        cfg = build_config(data, config_file)
        save_config_file(cfg, config_file)
        _ensure_dirs(cfg)
        return cfg

    if using_default_path and not config_file.exists():
        token = _generate_api_token()
        data = _build_default_config_data(token)
        _write_config_data(config_file, data)
        cfg = build_config(data, config_file)
        _ensure_dirs(cfg)
        logger.warning(f"已生成默认配置: {cfg.config_path}")
        logger.warning(f"初始 API Token: {token}")
        return cfg

    if not config_file.exists():
        msg = f"未找到配置文件: {config_path}"
        if os.path.exists("config.example.json"):
            msg += "。检测到 config.example.json，可参考该文件创建配置。"
        raise FileNotFoundError(msg)

    cfg = build_config(_read_json_config(config_file), config_file)
    _ensure_dirs(cfg)
    return cfg
