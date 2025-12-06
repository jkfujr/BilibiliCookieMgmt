import os
import json
import random
import threading
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from core.logs import log

logger = log()


@dataclass
class CachedCookie:
    """缓存的Cookie数据结构"""
    dede_user_id: str
    cookie_data: Dict[str, Any]
    is_valid: bool
    is_enabled: bool
    update_time: int
    
    def to_simple_format(self) -> str:
        """转换为简化格式的cookie字符串"""
        try:
            cookie_info = self.cookie_data.get("cookie_info", {})
            cookies = cookie_info.get("cookies", [])
            
            if not cookies:
                logger.error(f"[缓存] 用户 {self.dede_user_id} 没有cookie数据")
                raise ValueError("Cookie数据为空")
            
            cookie_dict = {cookie["name"]: cookie["value"] for cookie in cookies}
            required_keys = ["DedeUserID", "DedeUserID__ckMd5", "SESSDATA", "bili_jct", "buvid3", "buvid4"]
            return "".join([f"{key}={cookie_dict.get(key, '')};" for key in required_keys])
        except (KeyError, TypeError, ValueError) as e:
            logger.error(f"[缓存] 生成简化格式失败: {e}, 数据结构: {self.cookie_data}")
            raise


class CookieCacheManager:
    """Cookie缓存管理器 - 单例模式"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
            
        self._cache: Dict[str, CachedCookie] = {}
        self._cache_lock = threading.RLock()
        self._initialized = True
        logger.info("[缓存] Cookie缓存管理器初始化完成")
    
    def get_cookie_folder(self) -> str:
        """获取Cookie文件夹路径"""
        try:
            from core.config.manager import get_config
            app_config = get_config()
            return app_config.cookie.folder
        except RuntimeError:
            return os.path.join("data", "cookie")
    
    def _load_cookie_from_file(self, dede_user_id: str) -> Optional[CachedCookie]:
        """从文件加载单个cookie"""
        cookie_folder = self.get_cookie_folder()
        file_path = os.path.join(cookie_folder, f"{dede_user_id}.json")
        
        if not os.path.exists(file_path):
            return None
            
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                file_content = file.read().strip()
                if not file_content:
                    return None
                    
                cookie_data = json.loads(file_content)

                if "_cookiemgmt" not in cookie_data:
                    logger.warning(f"[缓存] 用户 {dede_user_id} 使用旧格式, 跳过缓存")
                    return None
                
                mgmt_data = cookie_data["_cookiemgmt"]
                is_valid = mgmt_data.get("cookie_valid", False)
                is_enabled = mgmt_data.get("enabled", True)
                update_time = mgmt_data.get("update_time", 0)
                
                return CachedCookie(
                    dede_user_id=dede_user_id,
                    cookie_data=cookie_data,
                    is_valid=is_valid,
                    is_enabled=is_enabled,
                    update_time=update_time
                )
                
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"[缓存] 加载用户 {dede_user_id} 失败: {e}")
            return None
    
    def load_all_cookies(self) -> None:
        """加载所有cookie到缓存"""
        cookie_folder = self.get_cookie_folder()
        
        if not os.path.exists(cookie_folder):
            logger.warning(f"[缓存] Cookie文件夹不存在: {cookie_folder}")
            return
        
        with self._cache_lock:
            self._cache.clear()
            loaded_count = 0
            valid_count = 0
            
            for filename in os.listdir(cookie_folder):
                if not filename.endswith(".json"):
                    continue
                    
                dede_user_id = filename.replace(".json", "")
                cached_cookie = self._load_cookie_from_file(dede_user_id)
                
                if cached_cookie:
                    self._cache[dede_user_id] = cached_cookie
                    loaded_count += 1
                    if cached_cookie.is_valid and cached_cookie.is_enabled:
                        valid_count += 1
            
            logger.info(f"[缓存] 加载完成: 总数 {loaded_count}, 有效 {valid_count}")
    
    def get_valid_cookies(self) -> List[CachedCookie]:
        """获取所有有效且启用的cookie"""
        with self._cache_lock:
            if not self._cache:
                logger.info("[缓存] 首次访问, 开始加载所有cookie")
                self.load_all_cookies()
            
            return [
                cookie for cookie in self._cache.values()
                if cookie.is_valid and cookie.is_enabled
            ]
    
    def get_random_cookie(self) -> Optional[CachedCookie]:
        """随机获取一个有效cookie"""
        valid_cookies = self.get_valid_cookies()
        
        if not valid_cookies:
            logger.warning("[缓存] 没有可用的有效cookie")
            return None
        
        chosen = random.choice(valid_cookies)
        logger.debug(f"[缓存] 随机选择用户 {chosen.dede_user_id}")
        return chosen
    
    def get_cookie(self, dede_user_id: str) -> Optional[CachedCookie]:
        """获取指定用户的cookie"""
        with self._cache_lock:
            if dede_user_id in self._cache:
                return self._cache[dede_user_id]

            cached_cookie = self._load_cookie_from_file(dede_user_id)
            if cached_cookie:
                self._cache[dede_user_id] = cached_cookie
                logger.debug(f"[缓存] 从文件加载用户 {dede_user_id}")
            
            return cached_cookie
    
    def update_cookie(self, dede_user_id: str) -> None:
        """更新指定用户的cookie缓存"""
        with self._cache_lock:
            cached_cookie = self._load_cookie_from_file(dede_user_id)
            
            if cached_cookie:
                self._cache[dede_user_id] = cached_cookie
                logger.info(f"[缓存] 更新用户 {dede_user_id} 缓存成功")
            else:
                if dede_user_id in self._cache:
                    del self._cache[dede_user_id]
                    logger.info(f"[缓存] 移除用户 {dede_user_id} 缓存")
    
    def remove_cookie(self, dede_user_id: str) -> None:
        """从缓存中移除指定用户的cookie"""
        with self._cache_lock:
            if dede_user_id in self._cache:
                del self._cache[dede_user_id]
                logger.info(f"[缓存] 移除用户 {dede_user_id} 缓存")
    
    def get_cache_stats(self) -> Dict[str, int]:
        """获取缓存统计信息"""
        with self._cache_lock:
            total = len(self._cache)
            valid = sum(1 for c in self._cache.values() if c.is_valid and c.is_enabled)
            invalid = sum(1 for c in self._cache.values() if not c.is_valid)
            disabled = sum(1 for c in self._cache.values() if not c.is_enabled)
            
            return {
                "total": total,
                "valid": valid,
                "invalid": invalid,
                "disabled": disabled
            }
    
    def clear_cache(self) -> None:
        """清空所有缓存"""
        with self._cache_lock:
            self._cache.clear()
            logger.info("[缓存] 清空所有缓存")


cache_manager = CookieCacheManager()


def get_cache_manager() -> CookieCacheManager:
    """获取缓存管理器实例"""
    return cache_manager