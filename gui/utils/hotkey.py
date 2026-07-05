"""全局热键管理器。

基于 keyboard 库实现启动/停止切换热键，
通过 Qt 信号将触发事件安全转发到 GUI 主线程。
"""

from PyQt5.QtCore import QObject, pyqtSignal

try:
    import keyboard
    _HAS_KEYBOARD = True
except ImportError:
    _HAS_KEYBOARD = False


class HotkeyManager(QObject):
    """全局热键管理器。

    封装 keyboard 库的 add_hotkey / clear_all_hotkeys，
    通过 Qt 信号通知 GUI 主线程热键触发。
    """

    hotkey_triggered = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._hooked = False
        self._current_hotkey: str | None = None

    def set_hotkey(self, hotkey: str) -> None:
        """注册全局热键（自动注销之前的）。

        Args:
            hotkey: keyboard 库格式的热键字符串（如 "f12"）。
        """
        self.unhook()
        if not hotkey or not _HAS_KEYBOARD:
            return
        try:
            keyboard.add_hotkey(hotkey, self._on_hotkey)
            self._current_hotkey = hotkey
            self._hooked = True
        except Exception:
            self._hooked = False

    def unhook(self) -> None:
        """注销所有热键。"""
        if self._hooked and _HAS_KEYBOARD:
            try:
                keyboard.clear_all_hotkeys()
            except Exception:
                pass
        self._hooked = False
        self._current_hotkey = None

    def _on_hotkey(self):
        """热键触发时的内部回调，发射 Qt 信号到 GUI 线程。"""
        self.hotkey_triggered.emit()

    @property
    def is_hooked(self) -> bool:
        return self._hooked

    @property
    def current_hotkey(self) -> str | None:
        return self._current_hotkey


def has_keyboard() -> bool:
    """检测 keyboard 库是否可用。"""
    return _HAS_KEYBOARD
