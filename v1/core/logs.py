import os, logging, shutil

from logging.handlers import TimedRotatingFileHandler

class DiskSpaceCheckHandler(TimedRotatingFileHandler):
    """检查硬盘空间"""
    
    def __init__(self, filename, when='h', interval=1, backupCount=0, encoding=None, 
                 delay=False, utc=False, atTime=None, min_free_space_mb=100):
        """
        初始化处理器, 增加最小可用空间参数
        :param min_free_space_mb: 最小可用空间(MB)
        """
        super().__init__(filename, when, interval, backupCount, encoding, delay, utc, atTime)
        self.min_free_space_mb = min_free_space_mb
        self.emit_failed = False
    
    def emit(self, record):
        """
        发出日志记录前检查硬盘空间
        """
        try:
            if self.emit_failed:
                free_space = self._get_free_space()
                if free_space < self.min_free_space_mb:
                    return
                self.emit_failed = False
                
            super().emit(record)
        except OSError as e:
            if e.errno == 28:
                if not self.emit_failed:
                    self.emit_failed = True
                    print(f"警告: 硬盘空间不足, 日志写入暂停 - {e}")
                    console = logging.StreamHandler()
                    console.setLevel(logging.WARNING)
                    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
                    console.setFormatter(formatter)
                    record.levelno = logging.WARNING
                    record.levelname = 'WARNING'
                    record.msg = f"硬盘空间不足, 日志写入暂停: {e}"
                    console.emit(record)
            else:
                print(f"日志写入错误: {e}")
        except Exception as e:
            print(f"日志处理异常: {e}")
    
    def _get_free_space(self):
        """获取日志文件所在硬盘的可用空间(MB)"""
        try:
            if self.baseFilename:
                disk = os.path.dirname(os.path.abspath(self.baseFilename))
                return self._get_disk_usage_mb(disk)
            return 0
        except Exception:
            return 0
    
    def _get_disk_usage_mb(self, path):
        """获取指定路径的硬盘可用空间(MB), 兼容 PyPy"""
        return _get_disk_usage_mb(path)

def _get_disk_usage_mb(path):
    """获取指定路径的硬盘可用空间(MB), 兼容 PyPy"""
    try:
        import platform
        system = platform.system().lower()
        
        if system == 'windows':
            import ctypes
            free_bytes = ctypes.c_ulonglong(0)
            ctypes.windll.kernel32.GetDiskFreeSpaceExW(
                ctypes.c_wchar_p(path),
                ctypes.pointer(free_bytes),
                None,
                None
            )
            return free_bytes.value / (1024 * 1024)
        else:
            # Unix/Linux 系统使用 statvfs
            import os
            statvfs = os.statvfs(path)
            free_bytes = statvfs.f_frsize * statvfs.f_bavail
            return free_bytes / (1024 * 1024)
    except Exception:
        # 最后的回退: 返回一个安全的默认值
        return 1000  # 假设有 1GB 可用空间

def log():
    """
    初始化日志记录器, 仅配置文件处理器, 记录 DEBUG 及以上级别的日志。
    增加硬盘空间检查功能。
    """
    logger = logging.getLogger()
    if logger.hasHandlers():
        return logger

    logger.setLevel(logging.DEBUG)

    script_directory = os.path.dirname(os.path.abspath(__file__))
    log_directory = os.path.abspath(os.path.join(script_directory, '..', 'logs'))
    
    if not os.path.exists(log_directory):
        try:
            os.makedirs(log_directory)
        except Exception as e:
            print(f"[日志] 创建日志目录 {log_directory} 失败: {e}")
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.DEBUG)
            formatter = logging.Formatter("%(asctime)s [%(levelname)s] - %(message)s")
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)
            return logger

    default_log_file_name = "BCK"
    log_file_path = os.path.join(log_directory, default_log_file_name)

    try:
        # 使用兼容的硬盘空间检查方法
        free_space_mb = _get_disk_usage_mb(log_directory)
        if free_space_mb < 100:
            print(f"[警告] 日志目录所在硬盘空间不足: {free_space_mb:.2f}MB")
    except Exception as e:
        print(f"[警告] 检查硬盘空间失败: {e}")

    file_handler = DiskSpaceCheckHandler(
        log_file_path,
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
        min_free_space_mb=50
    )
    file_handler.suffix = "%Y-%m-%d.log"
    file_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(processName)s - %(message)s"
    )
    file_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger

def log_print(message, level="INFO"):
    """
    记录日志并输出到控制台。

    参数:
    - message (str): 需要记录的消息内容。
    - level (str): 日志等级, 默认为 'INFO'。可以设置为 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'。
    """
    logger = logging.getLogger()
    
    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)

    try:
        logger.log(level, message)
    except Exception as e:
        print(f"日志写入失败: {e}")
    
    level_name = logging.getLevelName(level)
    prefix = f"{level_name}:     "
    print(prefix + message)
