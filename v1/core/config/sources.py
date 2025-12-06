import os, yaml
from abc import ABC, abstractmethod
from typing import Dict, Any


class ConfigSource(ABC):
    @abstractmethod
    def load(self) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    def exists(self) -> bool:
        pass


class YamlFileSource(ConfigSource):
    def __init__(self, file_path: str):
        self.file_path = file_path
    
    def load(self) -> Dict[str, Any]:
        if not self.exists():
            raise FileNotFoundError(f"配置文件不存在: {self.file_path}")
        
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            raise RuntimeError(f"加载配置文件失败: {e}")
    
    def exists(self) -> bool:
        return os.path.exists(self.file_path)


class EnvironmentSource(ConfigSource):
    def __init__(self, prefix: str = "BILI_"):
        self.prefix = prefix
    
    def load(self) -> Dict[str, Any]:
        config = {}
        for key, value in os.environ.items():
            if key.startswith(self.prefix):
                config_key = key[len(self.prefix):].lower()
                config[config_key] = value
        return config
    
    def exists(self) -> bool:
        return any(key.startswith(self.prefix) for key in os.environ)


class DefaultSource(ConfigSource):
    def __init__(self, defaults: Dict[str, Any]):
        self.defaults = defaults
    
    def load(self) -> Dict[str, Any]:
        return self.defaults.copy()
    
    def exists(self) -> bool:
        return True