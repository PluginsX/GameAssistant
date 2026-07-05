"""窗口控制器抽象接口。

定义平台无关的窗口操作接口，便于单元测试 mock 和多平台扩展。
"""

from abc import ABC, abstractmethod


class WindowController(ABC):
    """窗口操作抽象基类。

    所有平台实现必须继承此类并实现所有抽象方法。
    """

    @abstractmethod
    def get_hwnd(self, window_title: str) -> int:
        """按窗口标题获取窗口句柄。"""
        ...

    @abstractmethod
    def list_windows(self, window_title: str = "") -> list[tuple[int, str]]:
        """枚举所有可见窗口。"""
        ...

    @abstractmethod
    def set_foreground(self, hwnd: int) -> bool:
        """激活窗口到前台。"""
        ...

    @abstractmethod
    def is_minimized(self, hwnd: int) -> bool:
        """检测窗口是否处于最小化状态。"""
        ...

    @abstractmethod
    def send_key(self, hwnd: int, vk_code: int, mode: str = "foreground") -> None:
        """发送按键（按下+松开）。"""
        ...

    @abstractmethod
    def send_key_down(self, hwnd: int, vk_code: int, mode: str = "foreground") -> None:
        """按键按下（不松开）。"""
        ...

    @abstractmethod
    def send_key_up(self, hwnd: int, vk_code: int, mode: str = "foreground") -> None:
        """按键松开。"""
        ...

    @abstractmethod
    def capture_window(self, hwnd: int):
        """截取窗口画面，返回 PIL Image。"""
        ...
