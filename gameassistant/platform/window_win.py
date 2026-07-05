"""Windows 平台窗口操作实现。

基于 win32gui + pydirectinput 实现游戏窗口获取和按键模拟。
使用 pydirectinput（SendInput + scancode）发送按键，兼容 DirectInput 游戏。

依赖：
- pydirectinput（pip install pydirectinput）
- pywin32（pip install pywin32）
"""

import ctypes
import logging
import time
from typing import Optional

import pydirectinput
import win32gui

from gameassistant.platform.window_base import WindowController

pydirectinput.FAILSAFE = False

logger = logging.getLogger(__name__)
user32 = ctypes.windll.user32

# ---------------------------------------------------------------------------
# VK -> pydirectinput key name 映射
# ---------------------------------------------------------------------------
_VK_TO_NAME: dict[int, str] = {
    0x30: "0", 0x31: "1", 0x32: "2", 0x33: "3", 0x34: "4",
    0x35: "5", 0x36: "6", 0x37: "7", 0x38: "8", 0x39: "9",
    0x41: "a", 0x42: "b", 0x43: "c", 0x44: "d", 0x45: "e",
    0x46: "f", 0x47: "g", 0x48: "h", 0x49: "i", 0x4A: "j",
    0x4B: "k", 0x4C: "l", 0x4D: "m", 0x4E: "n", 0x4F: "o",
    0x50: "p", 0x51: "q", 0x52: "r", 0x53: "s", 0x54: "t",
    0x55: "u", 0x56: "v", 0x57: "w", 0x58: "x", 0x59: "y",
    0x5A: "z",
    0x20: "space", 0x0D: "enter", 0x09: "tab", 0x1B: "escape",
    0x10: "shift", 0x11: "ctrl", 0x12: "alt",
    0x70: "f1", 0x71: "f2", 0x72: "f3", 0x73: "f4", 0x74: "f5",
    0x75: "f6", 0x76: "f7", 0x77: "f8", 0x78: "f9", 0x79: "f10",
    0x7a: "f11", 0x7b: "f12",
    # 方向键
    0x25: "left", 0x26: "up", 0x27: "right", 0x28: "down",
}

# VK -> hardware scancode (Set 1) for PostMessage mode
_VK_TO_SCAN: dict[int, int] = {
    0x30: 0x0B, 0x31: 0x02, 0x32: 0x03, 0x33: 0x04, 0x34: 0x05,
    0x35: 0x06, 0x36: 0x07, 0x37: 0x08, 0x38: 0x09, 0x39: 0x0A,
    0x41: 0x1E, 0x42: 0x30, 0x43: 0x2E, 0x44: 0x20, 0x45: 0x12,
    0x46: 0x21, 0x47: 0x22, 0x48: 0x23, 0x49: 0x17, 0x4A: 0x24,
    0x4B: 0x25, 0x4C: 0x26, 0x4D: 0x32, 0x4E: 0x31, 0x4F: 0x18,
    0x50: 0x19, 0x51: 0x10, 0x52: 0x13, 0x53: 0x1F, 0x54: 0x14,
    0x55: 0x16, 0x56: 0x2F, 0x57: 0x11, 0x58: 0x2D, 0x59: 0x15,
    0x5A: 0x2C,
    0x20: 0x39, 0x0D: 0x1C, 0x09: 0x0F, 0x1B: 0x01,
    0x70: 0x3B, 0x71: 0x3C, 0x72: 0x3D, 0x73: 0x3E, 0x74: 0x3F,
    0x75: 0x40, 0x76: 0x41, 0x77: 0x42, 0x78: 0x43, 0x79: 0x44,
    0x7A: 0x57, 0x7B: 0x58,
    # 方向键（扩展键，scancode 带 E0 前缀）
    0x25: 0x4B, 0x26: 0x48, 0x27: 0x4D, 0x28: 0x50,
}

# 扩展键集合（方向键等需要 E0 前缀的键）
_EXTENDED_KEYS: set[int] = {0x25, 0x26, 0x27, 0x28}


class Win32WindowController(WindowController):
    """Windows 平台窗口控制器实现。"""

    def get_hwnd(self, window_title: str) -> int:
        """按窗口标题获取窗口句柄。

        Args:
            window_title: 窗口标题（精确匹配优先，失败则模糊匹配）。

        Returns:
            窗口句柄 hwnd，找不到返回 0。
        """
        hwnd = win32gui.FindWindow(None, window_title)
        if hwnd:
            logger.info("找到窗口 '%s'，句柄: %s", window_title, hwnd)
            return hwnd

        found_hwnd = 0
        _self_keywords = ["挂机脚本", "配置控制台", "画面预览", "按键测试"]

        def _enum_handler(hwnd, _):
            nonlocal found_hwnd
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if any(kw in title for kw in _self_keywords):
                    return True
                if window_title in title:
                    found_hwnd = hwnd
                    return False
            return True

        win32gui.EnumWindows(_enum_handler, None)
        if found_hwnd:
            logger.info("找到窗口(模糊匹配)句柄: %s", found_hwnd)
        else:
            logger.warning("未找到标题包含 '%s' 的窗口", window_title)
        return found_hwnd

    def list_windows(self, window_title: str = "") -> list[tuple[int, str]]:
        """枚举所有可见窗口，返回 (hwnd, title) 列表。

        Args:
            window_title: 可选，按标题关键词过滤（模糊匹配）。空字符串返回所有可见窗口。

        Returns:
            列表，每项为 (hwnd, title) 元组，按标题排序。
        """
        results: list[tuple[int, str]] = []
        _self_keywords = ["挂机脚本", "配置控制台", "画面预览", "按键测试", "QQ三国Bot"]

        def _enum_handler(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if title and not any(kw in title for kw in _self_keywords):
                    if not window_title or window_title in title:
                        results.append((hwnd, title))
            return True

        win32gui.EnumWindows(_enum_handler, None)
        results.sort(key=lambda x: x[1].lower())
        return results

    def set_foreground(self, hwnd: int) -> bool:
        """激活窗口到前台。

        Args:
            hwnd: 窗口句柄。

        Returns:
            成功激活返回 True。
        """
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        time.sleep(0.1)

        result = user32.SetForegroundWindow(hwnd)
        if not result:
            # 备选方案：AttachThreadInput
            fg_hwnd = user32.GetForegroundWindow()
            if fg_hwnd:
                fg_tid = user32.GetWindowThreadProcessId(fg_hwnd, None)
                cur_tid = ctypes.windll.kernel32.GetCurrentThreadId()
                ctypes.windll.user32.AttachThreadInput(fg_tid, cur_tid, True)
                user32.SetForegroundWindow(hwnd)
                ctypes.windll.user32.AttachThreadInput(fg_tid, cur_tid, False)
        time.sleep(0.15)

        actual_fg = user32.GetForegroundWindow()
        return actual_fg == hwnd

    def is_minimized(self, hwnd: int) -> bool:
        """检测窗口是否处于最小化状态。"""
        return win32gui.IsIconic(hwnd)

    # ------------------------------------------------------------------
    # 按键发送
    # ------------------------------------------------------------------

    def send_key(self, hwnd: int, vk_code: int, mode: str = "foreground") -> None:
        """发送按键。

        Args:
            hwnd: 目标窗口句柄。
            vk_code: 虚拟键码，如 0x31 表示 '1' 键。
            mode: 输入模式：
                "foreground" — 激活窗口到前台后用 pydirectinput 发送（已验证有效）
                "postmsg"    — 用 PostMessage 后台发送（不打扰用户，但游戏可能不响应）
                "focus"      — 快速切焦点：激活游戏->发键->切回原窗口
        """
        if mode == "postmsg":
            self._send_key_postmsg(hwnd, vk_code)
        elif mode == "focus":
            self._send_key_focus(hwnd, vk_code)
        else:
            self._send_key_foreground(hwnd, vk_code)

    def send_key_down(self, hwnd: int, vk_code: int, mode: str = "foreground") -> None:
        """按键按下（不松开，用于按住场景）。"""
        if mode == "postmsg":
            self._send_key_down_postmsg(hwnd, vk_code)
        else:
            prev_hwnd: Optional[int] = None
            if mode == "focus":
                prev_hwnd = user32.GetForegroundWindow()
            self.set_foreground(hwnd)
            key_name = _VK_TO_NAME.get(vk_code)
            if key_name:
                logger.debug("按下: %s (0x%02X)", key_name, vk_code)
                pydirectinput.keyDown(key_name)
            if mode == "focus" and prev_hwnd and prev_hwnd != hwnd:
                time.sleep(0.05)
                user32.SetForegroundWindow(prev_hwnd)

    def send_key_up(self, hwnd: int, vk_code: int, mode: str = "foreground") -> None:
        """按键松开。"""
        if mode == "postmsg":
            self._send_key_up_postmsg(hwnd, vk_code)
        else:
            prev_hwnd: Optional[int] = None
            if mode == "focus":
                prev_hwnd = user32.GetForegroundWindow()
            self.set_foreground(hwnd)
            key_name = _VK_TO_NAME.get(vk_code)
            if key_name:
                logger.debug("松开: %s (0x%02X)", key_name, vk_code)
                pydirectinput.keyUp(key_name)
            if mode == "focus" and prev_hwnd and prev_hwnd != hwnd:
                time.sleep(0.05)
                user32.SetForegroundWindow(prev_hwnd)

    def capture_window(self, hwnd: int):
        """截图功能占位（当前返回 1x1 占位图，实际截图由 GUI 模块提供）。"""
        from PIL import Image
        return Image.new("RGB", (1, 1))

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------

    def _send_key_foreground(self, hwnd: int, vk_code: int) -> None:
        """前台模式：激活游戏窗口后用 pydirectinput 发送。"""
        self.set_foreground(hwnd)
        self._press_vk(vk_code)

    def _send_key_focus(self, hwnd: int, vk_code: int) -> None:
        """快速切焦点模式：保存当前前台->激活游戏->发键->切回。"""
        prev_hwnd = user32.GetForegroundWindow()
        self.set_foreground(hwnd)
        self._press_vk(vk_code)
        time.sleep(0.05)
        if prev_hwnd and prev_hwnd != hwnd:
            user32.SetForegroundWindow(prev_hwnd)
            time.sleep(0.05)

    def _send_key_postmsg(self, hwnd: int, vk_code: int) -> None:
        """后台模式：用 PostMessage 发送 WM_KEYDOWN/WM_KEYUP。"""
        scan = _VK_TO_SCAN.get(vk_code, vk_code)
        lparam_down = (scan << 16) | 1
        lparam_up = (scan << 16) | 0xC0000001

        WM_KEYDOWN = 0x0100
        WM_KEYUP = 0x0101

        win32gui.PostMessage(hwnd, WM_KEYDOWN, vk_code, lparam_down)
        time.sleep(0.05)
        win32gui.PostMessage(hwnd, WM_KEYUP, vk_code, lparam_up)
        logger.debug("PostMessage 按键: 0x%02X (scan=0x%02X)", vk_code, scan)

    def _send_key_down_postmsg(self, hwnd: int, vk_code: int) -> None:
        """按键按下（PostMessage 模式）。"""
        scan = _VK_TO_SCAN.get(vk_code, vk_code)
        is_extended = vk_code in _EXTENDED_KEYS
        lparam = (scan << 16) | (0x10000 if is_extended else 0) | 1
        win32gui.PostMessage(hwnd, 0x0100, vk_code, lparam)
        logger.debug("PostMessage 按下: 0x%02X", vk_code)

    def _send_key_up_postmsg(self, hwnd: int, vk_code: int) -> None:
        """按键松开（PostMessage 模式）。"""
        scan = _VK_TO_SCAN.get(vk_code, vk_code)
        is_extended = vk_code in _EXTENDED_KEYS
        lparam = (scan << 16) | (0x10000 if is_extended else 0) | 0xC0000001
        win32gui.PostMessage(hwnd, 0x0101, vk_code, lparam)
        logger.debug("PostMessage 松开: 0x%02X", vk_code)

    def _press_vk(self, vk_code: int) -> None:
        """用 pydirectinput 发送按键（按下+松开）。"""
        key_name = _VK_TO_NAME.get(vk_code)
        if key_name:
            logger.debug("发送按键: %s (0x%02X)", key_name, vk_code)
            pydirectinput.press(key_name)
        else:
            logger.warning("不支持的按键: 0x%02X", vk_code)


# ---------------------------------------------------------------------------
# 模块级便捷函数（保持与旧 window.py 兼容）
# ---------------------------------------------------------------------------
_default_controller = Win32WindowController()

get_hwnd = _default_controller.get_hwnd
list_windows = _default_controller.list_windows
set_foreground = _default_controller.set_foreground
is_minimized = _default_controller.is_minimized
send_key = _default_controller.send_key
send_key_down = _default_controller.send_key_down
send_key_up = _default_controller.send_key_up
capture_window = _default_controller.capture_window
send_key_foreground = _default_controller._send_key_foreground
send_key_focus = _default_controller._send_key_focus
send_key_postmsg = _default_controller._send_key_postmsg
