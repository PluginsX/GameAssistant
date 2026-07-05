"""Bot 工作线程子包。

提供 BotWorker 将 SanguoBot 包装为 QThread 运行。
（懒加载以避免在没有 pywin32/pydirectinput 的环境中导入失败）
"""

__all__ = ["BotWorker", "QtLogHandler"]


def __getattr__(name):
    if name in ("BotWorker", "QtLogHandler"):
        from gameassistant.worker.qt_worker import BotWorker, QtLogHandler
        return BotWorker if name == "BotWorker" else QtLogHandler
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
