import os
from typing import Optional

from .factories import ConfigFactoryBuilder
from .configs import AppConfig


class ConfigManager:
    _instance: Optional['ConfigManager'] = None
    _config: Optional[AppConfig] = None
    
    def __new__(cls) -> 'ConfigManager':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def initialize(self, config_path: Optional[str] = None) -> None:
        if config_path is None:
            config_path = os.path.join(os.getcwd(), "config.yaml")
        
        factory = ConfigFactoryBuilder.create_default_factory(config_path)
        self._config = factory.create(AppConfig)
    
    @property
    def config(self) -> AppConfig:
        if self._config is None:
            raise RuntimeError("配置管理器未初始化, 请先调用 initialize()")
        return self._config
    
    def reload(self, config_path: Optional[str] = None) -> None:
        self.initialize(config_path)


def get_config_manager() -> ConfigManager:
    return ConfigManager()


def get_config() -> AppConfig:
    return get_config_manager().config