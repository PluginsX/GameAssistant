"""窗口控制器抽象接口。

定义平台无关的窗口操作接口，便于单元测试 mock 和多平台扩展。
"""

import time
from abc import ABC, abstractmethod
from typing import Optional


class WindowController(ABC):
    """窗口操作抽象基类。

    所有平台实现必须继承此类并实现所有抽象方法。
    """

    # ------------------------------------------------------------------
    # 窗口管理
    # ------------------------------------------------------------------

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
    def capture_window(self, hwnd: int):
        """截取窗口画面，返回 PIL Image。"""
        ...

    # ------------------------------------------------------------------
    # 单一按键操作
    # ------------------------------------------------------------------

    @abstractmethod
    def send_key(self, hwnd: int, vk_code: int, mode: str = "foreground") -> None:
        """发送单一按键（按下+松开）。"""
        ...

    @abstractmethod
    def send_key_down(self, hwnd: int, vk_code: int, mode: str = "foreground") -> None:
        """单一按键按下（不松开）。"""
        ...

    @abstractmethod
    def send_key_up(self, hwnd: int, vk_code: int, mode: str = "foreground") -> None:
        """单一按键松开。"""
        ...

    # ------------------------------------------------------------------
    # 复合按键操作（基于单一按键方法组合）
    # ------------------------------------------------------------------

    def send_keys(self, hwnd: int, vk_codes: list[int], mode: str = "foreground") -> None:
        """发送复合按键：按顺序按下所有键，再反向松开。

        适用于组合键 click，如 Ctrl+Shift+A：
            按下 Ctrl → 按下 Shift → 按下 A → 松开 A → 松开 Shift → 松开 Ctrl

        Args:
            hwnd: 目标窗口句柄。
            vk_codes: 虚拟键码列表，按顺序按下（最多 3 个键）。
            mode: 输入模式，同 send_key_down/up。
        """
        if not vk_codes:
            return
        for vk in vk_codes:
            self.send_key_down(hwnd, vk, mode=mode)
        time.sleep(0.02)
        for vk in reversed(vk_codes):
            self.send_key_up(hwnd, vk, mode=mode)

    def send_keys_down(self, hwnd: int, vk_codes: list[int], mode: str = "foreground") -> None:
        """按下复合按键群：按顺序按下所有键（不松开）。

        Args:
            hwnd: 目标窗口句柄。
            vk_codes: 虚拟键码列表，按顺序按下。
            mode: 输入模式，同 send_key_down。
        """
        for vk in vk_codes:
            self.send_key_down(hwnd, vk, mode=mode)

    def send_keys_up(self, hwnd: int, vk_codes: list[int], mode: str = "foreground") -> None:
        """松开复合按键群：反向松开所有键。

        Args:
            hwnd: 目标窗口句柄。
            vk_codes: 虚拟键码列表，按反向松开。
            mode: 输入模式，同 send_key_up。
        """
        for vk in reversed(vk_codes):
            self.send_key_up(hwnd, vk, mode=mode)
