"""项目路径工具模块。

统一管理项目根目录、配置文件路径等，
支持 PyInstaller 打包后的运行环境。
"""

import os
import sys


def get_project_root() -> str:
    """获取项目根目录。

    优先级：
    1. 打包后：exe 所在目录（用户可编辑配置文件）
    2. 开发时：项目根目录
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    gameassistant_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(gameassistant_dir)


def get_config_path() -> str:
    """获取 config.json 的完整路径。"""
    return os.path.join(get_project_root(), "config.json")


def get_task_config_path() -> str:
    """获取 TaskConfig.json 的完整路径。"""
    return os.path.join(get_project_root(), "TaskConfig.json")
