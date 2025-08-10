from typing import Dict, Any
from abc import ABC


class BaseConfig(ABC):
    def __init__(self, data: Dict[str, Any]):
        self._data = data
    
    def get(self, key: str, default: Any = None) -> Any:
        keys = key.split('.')
        value = self._data
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value
    
    def __getitem__(self, key: str) -> Any:
        return self.get(key)


class CookieConfig(BaseConfig):
    @property
    def check_enabled(self) -> bool:
        return self.get("COOKIE_CHECK.enable", False)
    
    @property
    def check_interval(self) -> int:
        return self.get("COOKIE_CHECK.check_intlval", 3600)
    
    @property
    def refresh_enabled(self) -> bool:
        return self.get("COOKIE_REFRESH.enable", False)
    
    @property
    def refresh_interval(self) -> int:
        return self.get("COOKIE_REFRESH.refresh_intlval", 86400)
    
    @property
    def folder(self) -> str:
        return self.get("COOKIE_FOLDER", "data/cookie")


class PushConfig(BaseConfig):
    @property
    def gotify_enabled(self) -> bool:
        return self.get("PUSH.GOTIFY.enable", False)
    
    @property
    def gotify_url(self) -> str:
        return self.get("PUSH.GOTIFY.url", "")
    
    @property
    def gotify_token(self) -> str:
        return self.get("PUSH.GOTIFY.token", "")
    
    def get_gotify_config(self) -> Dict[str, Any]:
        return {
            "enable": self.gotify_enabled,
            "url": self.gotify_url,
            "token": self.gotify_token
        }


class ServerConfig(BaseConfig):
    @property
    def host(self) -> str:
        return self.get("HOST", "127.0.0.1")
    
    @property
    def port(self) -> int:
        return self.get("PORT", 8080)
    
    @property
    def api_token(self) -> str:
        return self.get("API_TOKEN", "")


class AppConfig(BaseConfig):
    def __init__(self, data: Dict[str, Any]):
        super().__init__(data)
        self._cookie_config = CookieConfig(data)
        self._push_config = PushConfig(data)
        self._server_config = ServerConfig(data)
    
    @property
    def cookie(self) -> CookieConfig:
        return self._cookie_config
    
    @property
    def push(self) -> PushConfig:
        return self._push_config
    
    @property
    def server(self) -> ServerConfig:
        return self._server_config