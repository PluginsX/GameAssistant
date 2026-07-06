"""日志配置模块。

集中管理文件日志输出，确保日志统一写入项目 log 目录。
"""

import logging
import os
import sys
from datetime import datetime


def get_log_dir() -> str:
    """获取日志目录路径（项目根目录下的 log 文件夹）。"""
    if getattr(sys, "frozen", False):
        project_root = os.path.dirname(sys.executable)
    else:
        utils_dir = os.path.dirname(os.path.abspath(__file__))
        gui_dir = os.path.dirname(utils_dir)
        project_root = os.path.dirname(gui_dir)
    log_dir = os.path.join(project_root, "log")
    os.makedirs(log_dir, exist_ok=True)
    return log_dir


def setup_file_logger(level: int = logging.INFO) -> str:
    """初始化文件日志处理器，添加到 root logger。

    日志文件按日期命名，保存在项目 log 目录下。

    Args:
        level: 日志级别，默认 INFO。

    Returns:
        日志文件的完整路径。
    """
    log_dir = get_log_dir()
    date_str = datetime.now().strftime("%Y%m%d")
    log_file = os.path.join(log_dir, f"{date_str}.log")

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    for handler in root_logger.handlers:
        if isinstance(handler, logging.FileHandler):
            if os.path.abspath(handler.baseFilename) == os.path.abspath(log_file):
                return log_file

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(level)
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    return log_file
