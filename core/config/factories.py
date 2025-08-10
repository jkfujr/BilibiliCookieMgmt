from typing import Dict, Any, List, Type, TypeVar

from .sources import ConfigSource, YamlFileSource, EnvironmentSource, DefaultSource
from .configs import BaseConfig

T = TypeVar('T', bound=BaseConfig)


class ConfigFactory:
    def __init__(self):
        self._sources: List[ConfigSource] = []
        self._merged_data: Dict[str, Any] = {}
    
    def add_source(self, source: ConfigSource) -> 'ConfigFactory':
        self._sources.append(source)
        return self
    
    def _merge_configs(self) -> Dict[str, Any]:
        merged = {}
        for source in self._sources:
            if source.exists():
                data = source.load()
                self._deep_merge(merged, data)
        return merged
    
    def _deep_merge(self, target: Dict[str, Any], source: Dict[str, Any]):
        for key, value in source.items():
            if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                self._deep_merge(target[key], value)
            else:
                target[key] = value
    
    def create(self, config_class: Type[T]) -> T:
        if not self._merged_data:
            self._merged_data = self._merge_configs()
        return config_class(self._merged_data)


class ConfigFactoryBuilder:
    @staticmethod
    def create_default_factory(config_path: str = "config.yaml") -> ConfigFactory:
        defaults = {
            "HOST": "127.0.0.1",
            "PORT": 8080,
            "API_TOKEN": "",
            "COOKIE_CHECK": {"enable": False, "check_intlval": 3600},
            "COOKIE_REFRESH": {"enable": False, "refresh_intlval": 86400},
            "PUSH": {
                "GOTIFY": {"enable": False, "url": "", "token": ""}
            }
        }
        
        return (ConfigFactory()
                .add_source(DefaultSource(defaults))
                .add_source(YamlFileSource(config_path))
                .add_source(EnvironmentSource()))
    
    @staticmethod
    def create_cookie_factory(config_path: str = "config.yaml") -> ConfigFactory:
        return ConfigFactoryBuilder.create_default_factory(config_path)
    
    @staticmethod
    def create_push_factory(config_path: str = "config.yaml") -> ConfigFactory:
        return ConfigFactoryBuilder.create_default_factory(config_path)
    
    @staticmethod
    def create_server_factory(config_path: str = "config.yaml") -> ConfigFactory:
        return ConfigFactoryBuilder.create_default_factory(config_path)