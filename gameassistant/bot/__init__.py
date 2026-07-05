"""Bot 引擎子包。

提供 SanguoBot 主控制器和状态机实现。
（懒加载以避免在没有 pywin32/pydirectinput 的环境中导入失败）
"""

__all__ = ["SanguoBot", "BotState"]


def __getattr__(name):
    if name in ("SanguoBot", "BotState"):
        from gameassistant.bot.core import SanguoBot, BotState
        return SanguoBot if name == "SanguoBot" else BotState
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
