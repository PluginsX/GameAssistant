"""GUI 画面截图工具。

提供 BitBlt + GetDC 和 BitBlt + WindowDC 两种截图方案。
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


# 截图方法注册表
CAPTURE_METHODS = {
    "BitBlt+GetDC（客户区）": capture_getdc,
    "BitBlt+WindowDC（完整窗口）": capture_windowdc,
}
