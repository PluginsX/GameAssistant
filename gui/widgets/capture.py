"""GUI 画面截图工具。

提供多种截图方案：
  1. BitBlt + GetDC       — 客户区截图（窗口需可见）
  2. BitBlt + WindowDC    — 完整窗口截图（窗口需可见）
  3. PrintWindow          — 后台渲染，窗口被遮挡也能截取纯净内容
"""

import ctypes
from PIL import Image

from gui.utils.dpi import dpi_unaware_context

# 延迟导入以避免循环依赖
_win32gui = None
_win32ui = None
_win32con = None


def _get_win32():
    global _win32gui, _win32ui, _win32con
    if _win32gui is None:
        import win32gui as wg
        import win32ui as wu
        import win32con as wc
        _win32gui, _win32ui, _win32con = wg, wu, wc
    return _win32gui, _win32ui, _win32con


def capture_getdc(hwnd: int) -> Image.Image:
    """BitBlt + GetDC：只截客户区。"""
    win32gui, win32ui, win32con = _get_win32()
    with dpi_unaware_context():
        _, _, w, h = win32gui.GetClientRect(hwnd)
        if w <= 0 or h <= 0:
            return Image.new("RGB", (1, 1))
        hwnd_dc = win32gui.GetDC(hwnd)
        mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
        save_dc = mfc_dc.CreateCompatibleDC()
        bmp = win32ui.CreateBitmap()
        bmp.CreateCompatibleBitmap(mfc_dc, w, h)
        save_dc.SelectObject(bmp)
        save_dc.BitBlt((0, 0), (w, h), mfc_dc, (0, 0), win32con.SRCCOPY)
        bmp_info = bmp.GetInfo()
        bmp_bits = bmp.GetBitmapBits(True)
        save_dc.DeleteDC()
        mfc_dc.DeleteDC()
        win32gui.ReleaseDC(hwnd, hwnd_dc)
        win32gui.DeleteObject(bmp.GetHandle())

    return Image.frombuffer(
        "RGB", (bmp_info["bmWidth"], bmp_info["bmHeight"]),
        bmp_bits, "raw", "BGRX", 0, 1
    )


def capture_windowdc(hwnd: int) -> Image.Image:
    """BitBlt + GetWindowDC：截完整窗口（含非客户区）。"""
    win32gui, win32ui, win32con = _get_win32()
    with dpi_unaware_context():
        l, t, r, b = win32gui.GetWindowRect(hwnd)
        w, h = r - l, b - t
        if w <= 0 or h <= 0:
            return Image.new("RGB", (1, 1))
        hwnd_dc = win32gui.GetWindowDC(hwnd)
        mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
        save_dc = mfc_dc.CreateCompatibleDC()
        bmp = win32ui.CreateBitmap()
        bmp.CreateCompatibleBitmap(mfc_dc, w, h)
        save_dc.SelectObject(bmp)
        save_dc.BitBlt((0, 0), (w, h), mfc_dc, (0, 0), win32con.SRCCOPY)
        bmp_info = bmp.GetInfo()
        bmp_bits = bmp.GetBitmapBits(True)
        save_dc.DeleteDC()
        mfc_dc.DeleteDC()
        win32gui.ReleaseDC(hwnd, hwnd_dc)
        win32gui.DeleteObject(bmp.GetHandle())

    return Image.frombuffer(
        "RGB", (bmp_info["bmWidth"], bmp_info["bmHeight"]),
        bmp_bits, "raw", "BGRX", 0, 1
    )


def capture_printwindow(hwnd: int) -> Image.Image:
    """PrintWindow（无标志）：屏幕分辨率截图。

    以 windows 当前屏幕分辨率截取窗口内容。
    窗口被完全遮挡时可能截到空白或其它窗口内容，但画面清晰。
    """
    return _capture_printwindow_ex(hwnd, 0)


def capture_printwindow_full(hwnd: int) -> Image.Image:
    """PrintWindow + PW_RENDERFULLCONTENT：后台完整渲染。

    即使窗口被遮挡也能获取窗口自身的完整渲染内容，
    但部分游戏会以内部渲染分辨率输出，可能导致画面模糊。
    """
    return _capture_printwindow_ex(hwnd, 2)


def _capture_printwindow_ex(hwnd: int, flags: int) -> Image.Image:
    """PrintWindow 通用实现。"""
    win32gui, win32ui, win32con = _get_win32()
    with dpi_unaware_context():
        l, t, r, b = win32gui.GetWindowRect(hwnd)
        w, h = r - l, b - t
        if w <= 0 or h <= 0:
            return Image.new("RGB", (1, 1))
        hwnd_dc = win32gui.GetWindowDC(hwnd)
        mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
        save_dc = mfc_dc.CreateCompatibleDC()
        bmp = win32ui.CreateBitmap()
        bmp.CreateCompatibleBitmap(mfc_dc, w, h)
        save_dc.SelectObject(bmp)

        ctypes.windll.user32.PrintWindow(hwnd, save_dc.GetSafeHdc(), flags)

        bmp_info = bmp.GetInfo()
        bmp_bits = bmp.GetBitmapBits(True)
        save_dc.DeleteDC()
        mfc_dc.DeleteDC()
        win32gui.ReleaseDC(hwnd, hwnd_dc)
        win32gui.DeleteObject(bmp.GetHandle())

    return Image.frombuffer(
        "RGB", (bmp_info["bmWidth"], bmp_info["bmHeight"]),
        bmp_bits, "raw", "BGRX", 0, 1
    )


# 截图方法注册表
CAPTURE_METHODS = {
    "PrintWindow（屏幕分辨率）": capture_printwindow,
    "PrintWindow+全内容（渲染分辨率）": capture_printwindow_full,
    "BitBlt+GetDC（客户区）": capture_getdc,
    "BitBlt+WindowDC（完整窗口）": capture_windowdc,
}
