from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from pathlib import Path
import argparse
import json
import logging
import secrets
import sys
import yaml


def resolve_app_root(
    module_file: str | Path = __file__,
    *,
    frozen: bool | None = None,
    executable: str | Path | None = None,
) -> Path:
    """解析持久数据根目录，冻结程序使用可执行文件所在目录。"""
    is_frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    if is_frozen:
        return Path(executable or sys.executable).resolve().parent
    return Path(module_file).resolve().parents[2]


APP_ROOT = resolve_app_root()
DEFAULT_CONFIG_FILE = APP_ROOT / "data" / "config.json"
DEFAULT_COOKIE_DIR = APP_ROOT / "data" / "cookie"
LEGACY_CONFIG_FILE = APP_ROOT / "config.yaml"
DEFAULT_CONFIG_PATH = DEFAULT_CONFIG_FILE.as_posix()
logger = logging.getLogger(__name__)


@dataclass
class ApiTokenConfig:
    enable: bool = False
    token: str = ""


@dataclass
class StorageConfig:
    cookie_dir: str = DEFAULT_COOKIE_DIR.as_posix()


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
class TasksConfig:
    history_retention_days: Optional[int] = 30


@dataclass
class AppConfig:
    host: str = "0.0.0.0"
    port: int = 18000
    api_token: ApiTokenConfig = field(default_factory=ApiTokenConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    gotify: GotifyConfig = field(default_factory=GotifyConfig)
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)
    bili: BiliConfig = field(default_factory=BiliConfig)
    tasks: TasksConfig = field(default_factory=TasksConfig)
    config_path: str = DEFAULT_CONFIG_PATH
    database_path: str = (DEFAULT_CONFIG_FILE.parent / "data.db").as_posix()
    encryption_key_path: str = (DEFAULT_CONFIG_FILE.parent / "data.key").as_posix()


def _ensure_dirs(cfg: AppConfig) -> None:
    Path(cfg.storage.cookie_dir).mkdir(parents=True, exist_ok=True)


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
        "TASKS": {
            "history_retention_days": cfg.tasks.history_retention_days,
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
            "cookie_dir": DEFAULT_COOKIE_DIR.as_posix(),
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
        "TASKS": {
            "history_retention_days": 30,
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
    tasks_cfg = data.get("TASKS", {})
    if tasks_cfg is None:
        tasks_cfg = {}
    if not isinstance(tasks_cfg, dict):
        raise ValueError("TASKS 必须是对象")
    retention_days = tasks_cfg.get("history_retention_days", 30)
    if retention_days is not None:
        if isinstance(retention_days, bool) or not isinstance(retention_days, int) or retention_days <= 0:
            raise ValueError("TASKS.history_retention_days 必须是正整数或 null")

    resolved_config_path = Path(config_path).resolve()
    data_dir = resolved_config_path.parent

    return AppConfig(
        host=str(data.get("HOST", "0.0.0.0")),
        port=int(data.get("PORT", 18000)),
        api_token=ApiTokenConfig(
            enable=bool(api_token_cfg.get("enable", False)),
            token=str(api_token_cfg.get("token", "")),
        ),
        storage=StorageConfig(
            cookie_dir=str(storage_cfg.get("cookie_dir", DEFAULT_COOKIE_DIR.as_posix())),
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
        tasks=TasksConfig(history_retention_days=retention_days),
        config_path=resolved_config_path.as_posix(),
        database_path=(data_dir / "data.db").as_posix(),
        encryption_key_path=(data_dir / "data.key").as_posix(),
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

    explicit_config = config_path is not None
    config_file = Path(config_path) if explicit_config else DEFAULT_CONFIG_FILE

    if config_file.suffix.lower() != ".json":
        raise ValueError("仅支持 JSON 配置文件，请使用 data/config.json")

    if explicit_config:
        if not config_file.exists():
            raise FileNotFoundError(f"未找到配置文件: {config_file}")
        cfg = build_config(_read_json_config(config_file), config_file)
        _ensure_dirs(cfg)
        return cfg

    if config_file.exists():
        cfg = build_config(_read_json_config(config_file), config_file)
        _ensure_dirs(cfg)
        return cfg

    if LEGACY_CONFIG_FILE.exists():
        data = _read_legacy_yaml_config(LEGACY_CONFIG_FILE)
        cfg = build_config(data, config_file)
        save_config_file(cfg, config_file)
        _ensure_dirs(cfg)
        logger.warning(f"已迁移旧配置到: {cfg.config_path}")
        return cfg

    token = _generate_api_token()
    data = _build_default_config_data(token)
    _write_config_data(config_file, data)
    cfg = build_config(data, config_file)
    _ensure_dirs(cfg)
    logger.warning(f"已生成默认配置: {cfg.config_path}")
    logger.warning(f"初始 API Token: {token}")
    return cfg
