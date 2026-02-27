from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path
import os
import argparse
import yaml


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
    interval_seconds: int = 600


@dataclass
class SchedulerConfig:
    cookie_check: SchedulerItemConfig = field(default_factory=SchedulerItemConfig)
    cookie_refresh: SchedulerItemConfig = field(default_factory=lambda: SchedulerItemConfig(enable=False, interval_seconds=86400))


@dataclass
class AppConfig:
    host: str = "0.0.0.0"
    port: int = 18000
    api_token: ApiTokenConfig = field(default_factory=ApiTokenConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    gotify: GotifyConfig = field(default_factory=GotifyConfig)
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)


def _ensure_dirs(cfg: AppConfig) -> None:
    os.makedirs(cfg.storage.cookie_dir, exist_ok=True)


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

    if config_path is None:
        config_path = "config.yaml"

    if not os.path.exists(config_path):
        msg = f"未找到配置文件: {config_path}"
        if os.path.exists("config.example.yaml"):
            msg += "。检测到 config.example.yaml，请将其复制为 config.yaml 并根据需要修改配置。"
        raise FileNotFoundError(msg)

    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    api_token_cfg = data.get("API_TOKEN", {})
    storage_cfg = data.get("STORAGE", {})
    gotify_cfg = data.get("GOTIFY", {})
    scheduler_cfg = data.get("SCHEDULER", {})
    check_cfg_src = scheduler_cfg.get("COOKIE_CHECK", {}) if scheduler_cfg else {}
    refresh_cfg_src = scheduler_cfg.get("COOKIE_REFRESH", {}) if scheduler_cfg else {}

    cfg = AppConfig(
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
            ),
        ),
    )

    _ensure_dirs(cfg)
    return cfg