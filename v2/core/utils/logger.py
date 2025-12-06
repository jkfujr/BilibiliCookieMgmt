import os
import logging
import time
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

# 基础配置
LOG_DIR = Path("logs")
LOG_FILENAME = "BCK.log"
LOG_FORMAT = "%(asctime)s - %(levelname)s - [%(module)s] - %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

def setup_logging():
    """
    配置日志系统:
    - 确保 logs 目录存在
    - 配置控制台输出
    - 配置按天轮转的文件输出 (保留30天)
    - 轮转文件名格式: BCK20250101.log
    """
    if not LOG_DIR.exists():
        LOG_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # 清除现有的 handlers (避免重复添加)
    if logger.hasHandlers():
        logger.handlers.clear()

    # 1. 控制台 Handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # 2. 文件 Handler (按天轮转)
    log_file_path = LOG_DIR / LOG_FILENAME
    
    # when='midnight' 表示每天午夜轮转
    # interval=1 表示每1天
    # backupCount=30 表示保留30个备份
    file_handler = TimedRotatingFileHandler(
        filename=str(log_file_path),
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8"
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(console_formatter)
    
    # 自定义 namer 和 rotator 以满足 "BCK{YYYYMMDD}.log" 的命名需求
    # 默认命名是 BCK.log.YYYY-MM-DD
    
    def custom_namer(default_name):
        # default_name 类似 logs/BCK.log.2025-01-01
        # 我们需要将其转换为 logs/BCK20250101.log
        base_filename = os.path.basename(default_name) # BCK.log.2025-01-01
        parts = base_filename.split('.')
        # parts: ['BCK', 'log', '2025-01-01']
        if len(parts) >= 3:
            date_part = parts[-1] # 2025-01-01
            # 去掉日期中的横杠
            date_compact = date_part.replace('-', '')
            new_name = f"BCK{date_compact}.log"
            return os.path.join(os.path.dirname(default_name), new_name)
        return default_name

    file_handler.namer = custom_namer
    
    # suffix 决定了 TimedRotatingFileHandler 生成的临时后缀格式
    # 默认是 %Y-%m-%d
    file_handler.suffix = "%Y-%m-%d"

    logger.addHandler(file_handler)
    
    logging.info("日志系统初始化完成")
