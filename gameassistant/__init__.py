"""GameAssistant - 游戏辅助（挂机）程序核心包。

提供配置管理、任务队列模型、平台窗口操作、Bot 引擎和 Qt 工作线程。
"""

__version__ = "2.0.0"

from gameassistant.config import BotConfig, VK_MAP, VK_REVERSE_MAP, name_to_vk, vk_to_name
from gameassistant.models.tasks import TaskEvent, Task, TaskQueue

# 懒加载 Windows 平台模块（避免在没有 pywin32/pydirectinput 的环境中导入失败）
__all__ = [
    "BotConfig", "VK_MAP", "VK_REVERSE_MAP", "name_to_vk", "vk_to_name",
    "TaskEvent", "Task", "TaskQueue",
    "SanguoBot", "BotState",
]


def __getattr__(name):
    if name == "SanguoBot":
        from gameassistant.bot.core import SanguoBot as _mod
        return _mod
    if name == "BotState":
        from gameassistant.bot.core import BotState as _mod
        return _mod
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
