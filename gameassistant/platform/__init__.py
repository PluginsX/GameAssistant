"""平台抽象层子包。

提供 Windows 窗口操作和按键模拟的封装，
通过 WindowController 接口实现平台无关性。
"""

from gameassistant.platform.window_base import WindowController

# 懒加载 Windows 实现（需要 pywin32 + pydirectinput）
__all__ = ["WindowController", "Win32WindowController", "window_controller"]


def __getattr__(name):
    if name == "Win32WindowController":
        from gameassistant.platform.window_win import Win32WindowController
        return Win32WindowController
    if name == "window_controller":
        from gameassistant.platform.window_win import Win32WindowController
        return Win32WindowController()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
