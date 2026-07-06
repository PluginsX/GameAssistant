"""GUI 初始化工具。

提供 DPI 感知切换与 win32gui Monkey Patch（不受缩放污染的坐标获取）。
"""

import ctypes
import ctypes.wintypes
import json
import os
import sys
from contextlib import contextmanager


@contextmanager
def dpi_unaware_context():
    """临时切换当前线程为 DPI 无感知，避免高缩放时 BitBlt 抓出大量黑边的问题。"""
    old_ctx = None
    if sys.platform == "win32":
        try:
            user32 = ctypes.windll.user32
            if hasattr(user32, 'SetThreadDpiAwarenessContext'):
                old_ctx = user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-1))
        except Exception:
            pass
    try:
        yield
    finally:
        if old_ctx and sys.platform == "win32":
            try:
                ctypes.windll.user32.SetThreadDpiAwarenessContext(old_ctx)
            except Exception:
                pass


def _get_config_path() -> str:
    """获取 config.json 的绝对路径（项目根目录下）。"""
    if getattr(sys, "frozen", False):
        project_root = os.path.dirname(sys.executable)
    else:
        utils_dir = os.path.dirname(os.path.abspath(__file__))
        gui_dir = os.path.dirname(utils_dir)
        project_root = os.path.dirname(gui_dir)
    return os.path.join(project_root, "config.json")


def setup_dpi_scaling() -> bool:
    """在 Qt 加载前根据 config.json 配置 DPI 缩放。

    Returns:
        是否启用了 DPI 缩放。
    """
    enable_dpi = True
    if sys.platform == "win32":
        try:
            config_path = _get_config_path()
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    if "auto_dpi_scale" in cfg:
                        enable_dpi = bool(cfg["auto_dpi_scale"])
        except Exception:
            pass

        if enable_dpi:
            os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
            os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
        else:
            os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
            os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "0"
            try:
                ctypes.windll.user32.SetProcessDpiAwarenessContext(-1)
            except AttributeError:
                try:
                    ctypes.windll.shcore.SetProcessDpiAwareness(0)
                except Exception:
                    pass
    return enable_dpi


def install_win32gui_patches() -> None:
    """安装 win32gui Monkey Patch，确保 BitBlt 获取不受 DPI 缩放的物理坐标。"""
    import win32gui

    _orig_GetClientRect = win32gui.GetClientRect
    _orig_GetWindowRect = win32gui.GetWindowRect

    def _patched_GetClientRect(hwnd):
        with dpi_unaware_context():
            return _orig_GetClientRect(hwnd)

    def _patched_GetWindowRect(hwnd):
        with dpi_unaware_context():
            return _orig_GetWindowRect(hwnd)

    win32gui.GetClientRect = _patched_GetClientRect
    win32gui.GetWindowRect = _patched_GetWindowRect


def is_admin() -> bool:
    """检测当前进程是否以管理员权限运行。"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False
