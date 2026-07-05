"""画面抓取方案测试脚本。

对比多种后台截图方案的性能和效果，帮助选择最佳方案：
1. BitBlt + GetDC          — 客户区 DC，软件渲染游戏首选
2. BitBlt + GetWindowDC    — 完整窗口 DC（含标题栏）
3. PrintWindow             — DX 游戏备用方案
4. PIL ImageGrab           — 屏幕截图（受遮挡影响）
5. mss                     — 高速屏幕截图库（需 pip install mss）

用法：
    python test_capture.py

游戏需处于软件渲染模式（QQ三国启动器设置）。
"""

import logging
import os
import sys
import time
import ctypes

import win32gui
import win32ui
import win32con
import win32api
from PIL import Image, ImageGrab

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# 输出目录
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "capture_test")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 排除本项目窗口
_SELF_KEYWORDS = ["挂机脚本", "配置控制台", "画面预览", "按键测试", "QQ三国Bot", "capture"]


def find_game_window(title_keyword: str = "QQ三国") -> int:
    """查找游戏窗口句柄。"""
    hwnd = win32gui.FindWindow(None, title_keyword)
    if hwnd:
        return hwnd

    found = [0]

    def _enum(h, _):
        if win32gui.IsWindowVisible(h):
            t = win32gui.GetWindowText(h)
            if t and not any(kw in t for kw in _SELF_KEYWORDS) and title_keyword in t:
                found[0] = h
                return False
        return True

    win32gui.EnumWindows(_enum, None)
    return found[0]


# ---------------------------------------------------------------------------
# 方案 1：BitBlt + GetDC（客户区）
# ---------------------------------------------------------------------------

def capture_bitblt_getdc(hwnd: int) -> Image.Image:
    """BitBlt + GetDC：只截客户区，不含标题栏边框。"""
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
    img = Image.frombuffer("RGB", (bmp_info["bmWidth"], bmp_info["bmHeight"]),
                           bmp_bits, "raw", "BGRX", 0, 1)

    save_dc.DeleteDC()
    mfc_dc.DeleteDC()
    win32gui.ReleaseDC(hwnd, hwnd_dc)
    win32gui.DeleteObject(bmp.GetHandle())
    return img


# ---------------------------------------------------------------------------
# 方案 2：BitBlt + GetWindowDC（完整窗口含标题栏）
# ---------------------------------------------------------------------------

def capture_bitblt_windowdc(hwnd: int) -> Image.Image:
    """BitBlt + GetWindowDC：截完整窗口（含标题栏边框）。"""
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
    img = Image.frombuffer("RGB", (bmp_info["bmWidth"], bmp_info["bmHeight"]),
                           bmp_bits, "raw", "BGRX", 0, 1)

    save_dc.DeleteDC()
    mfc_dc.DeleteDC()
    win32gui.ReleaseDC(hwnd, hwnd_dc)
    win32gui.DeleteObject(bmp.GetHandle())
    return img


# ---------------------------------------------------------------------------
# 方案 3：PrintWindow（DX 游戏备用）
# ---------------------------------------------------------------------------

def capture_printwindow(hwnd: int) -> Image.Image:
    """PrintWindow：后台截图，对 DX 游戏可能有效。

    使用 ctypes 调用 user32.PrintWindow（pywin32 的 win32gui 无此属性）。
    """
    _, _, w, h = win32gui.GetClientRect(hwnd)
    if w <= 0 or h <= 0:
        return Image.new("RGB", (1, 1))

    hwnd_dc = win32gui.GetWindowDC(hwnd)
    mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
    save_dc = mfc_dc.CreateCompatibleDC()

    bmp = win32ui.CreateBitmap()
    bmp.CreateCompatibleBitmap(mfc_dc, w, h)
    save_dc.SelectObject(bmp)

    # PW_CLIENTONLY = 1, PW_RENDERFULLCONTENT = 2
    hdc = save_dc.GetSafeHdc()
    result = ctypes.windll.user32.PrintWindow(hwnd, hdc, 0x00000001)
    if result == 0:
        result = ctypes.windll.user32.PrintWindow(hwnd, hdc, 0x00000002)

    bmp_info = bmp.GetInfo()
    bmp_bits = bmp.GetBitmapBits(True)
    img = Image.frombuffer("RGB", (bmp_info["bmWidth"], bmp_info["bmHeight"]),
                           bmp_bits, "raw", "BGRX", 0, 1)

    save_dc.DeleteDC()
    mfc_dc.DeleteDC()
    win32gui.ReleaseDC(hwnd, hwnd_dc)
    win32gui.DeleteObject(bmp.GetHandle())
    return img


# ---------------------------------------------------------------------------
# 方案 4：PIL ImageGrab（屏幕截图，需窗口可见）
# ---------------------------------------------------------------------------

def capture_imagegrab(hwnd: int) -> Image.Image:
    """PIL ImageGrab：截取客户区在屏幕上的区域。"""
    _, _, w, h = win32gui.GetClientRect(hwnd)
    if w <= 0 or h <= 0:
        return Image.new("RGB", (1, 1))
    x, y = win32gui.ClientToScreen(hwnd, (0, 0))
    return ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True)


# ---------------------------------------------------------------------------
# 方案 5：mss（高速屏幕截图，需 pip install mss）
# ---------------------------------------------------------------------------

def capture_mss(hwnd: int, sct=None) -> Image.Image:
    """mss：高速屏幕截图，截取客户区在屏幕上的区域。"""
    _, _, w, h = win32gui.GetClientRect(hwnd)
    if w <= 0 or h <= 0:
        return Image.new("RGB", (1, 1))
    x, y = win32gui.ClientToScreen(hwnd, (0, 0))
    monitor = {"top": y, "left": x, "width": w, "height": h}
    shot = sct.grab(monitor)
    return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")


# ---------------------------------------------------------------------------
# 黑屏检测
# ---------------------------------------------------------------------------

def is_black_image(img: Image.Image) -> bool:
    """检测图像是否几乎全黑（中心区域多点采样）。

    采样策略：中心 + 四角 + 边缘中点共 9 个点，避免标题栏等空白区域干扰。
    超过 80% 的采样点为黑色即判定为黑屏。

    Args:
        img: PIL 图像。

    Returns:
        全黑（或几乎全黑）返回 True。
    """
    import numpy as np
    arr = np.array(img)
    h, w = arr.shape[:2]

    # 9 点采样：中心 + 四角 + 四边中点
    sample_points = [
        (h // 2, w // 2),           # 中心
        (h // 4, w // 4),           # 左上
        (h // 4, 3 * w // 4),       # 右上
        (3 * h // 4, w // 4),       # 左下
        (3 * h // 4, 3 * w // 4),   # 右下
        (h // 2, w // 4),           # 左中
        (h // 2, 3 * w // 4),       # 右中
        (h // 4, w // 2),           # 上中
        (3 * h // 4, w // 2),       # 下中
    ]

    black_count = 0
    for py, px in sample_points:
        py = max(0, min(py, h - 1))
        px = max(0, min(px, w - 1))
        pixel = arr[py, px]
        # RGB 三通道总和 < 30 视为黑色
        if sum(pixel[:3]) < 30:
            black_count += 1

    return black_count / len(sample_points) > 0.8


# ---------------------------------------------------------------------------
# 性能测试
# ---------------------------------------------------------------------------

def benchmark(name: str, func, hwnd: int, rounds: int = 10, **kwargs):
    """对指定截图方案进行性能测试。

    Returns:
        (avg_ms, min_ms, max_ms, is_black, sample_img)
    """
    times = []
    sample = None
    black = True

    # 预热 1 次
    try:
        func(hwnd, **kwargs) if kwargs else func(hwnd)
    except Exception as e:
        logger.error("[%s] 预热失败: %s", name, e)
        return (0, 0, 0, True, None)

    for i in range(rounds):
        t0 = time.perf_counter()
        try:
            img = func(hwnd, **kwargs) if kwargs else func(hwnd)
        except Exception as e:
            logger.error("[%s] 第 %d 次失败: %s", name, i + 1, e)
            continue
        t1 = time.perf_counter()
        times.append((t1 - t0) * 1000)
        if i == 0:
            sample = img
            black = is_black_image(img)

    if not times:
        return (0, 0, 0, True, None)

    avg = sum(times) / len(times)
    mn = min(times)
    mx = max(times)
    logger.info("[%s] %d 次: 平均 %.1fms | 最小 %.1fms | 最大 %.1fms | 黑屏=%s",
                name, len(times), avg, mn, mx, black)
    return (avg, mn, mx, black, sample)


def main():
    print("=" * 60)
    print("  QQ三国 画面抓取方案测试")
    print("=" * 60)

    # 查找游戏窗口
    hwnd = find_game_window("QQ三国")
    if not hwnd:
        print("\n未找到 QQ三国 窗口！请确认游戏已启动。")
        print("\n当前可见窗口列表（输入关键词过滤，回车显示全部）：")
        keyword = input("> ").strip()

        results = []
        def _list_enum(h, _):
            if win32gui.IsWindowVisible(h):
                t = win32gui.GetWindowText(h)
                if t and not any(kw in t for kw in _SELF_KEYWORDS):
                    if not keyword or keyword in t:
                        results.append((h, t))
            return True
        win32gui.EnumWindows(_list_enum, None)
        results.sort(key=lambda x: x[1].lower())

        if not results:
            print("没有找到任何可见窗口")
            return

        print("\n可见窗口列表：")
        for i, (h, t) in enumerate(results):
            print(f"  [{i}] hwnd={h}  {t}")

        choice = input("\n选择窗口编号（回车退出）: ").strip()
        if not choice:
            return
        try:
            hwnd = results[int(choice)][0]
        except (ValueError, IndexError):
            print("选择无效")
            return

    print(f"\n目标窗口句柄: {hwnd}")
    print(f"窗口标题: {win32gui.GetWindowText(hwnd)}")
    rect = win32gui.GetWindowRect(hwnd)
    _, _, cw, ch = win32gui.GetClientRect(hwnd)
    print(f"窗口矩形: {rect}")
    print(f"客户区尺寸: {cw}x{ch}")
    print(f"是否最小化: {win32gui.IsIconic(hwnd)}")

    if win32gui.IsIconic(hwnd):
        print("\n窗口已最小化，正在恢复...")
        win32gui.ShowWindow(hwnd, 9)  # SW_RESTORE
        time.sleep(1)

    print("\n" + "=" * 60)
    print("  开始性能测试（每个方案 10 次）")
    print("=" * 60)

    results = {}

    # 方案 1
    results["BitBlt+GetDC"] = benchmark("BitBlt+GetDC", capture_bitblt_getdc, hwnd)

    # 方案 2
    results["BitBlt+WindowDC"] = benchmark("BitBlt+WindowDC", capture_bitblt_windowdc, hwnd)

    # 方案 3
    results["PrintWindow"] = benchmark("PrintWindow", capture_printwindow, hwnd)

    # 方案 4
    results["ImageGrab"] = benchmark("ImageGrab", capture_imagegrab, hwnd)

    # 方案 5（mss，可选）
    try:
        import mss
        with mss.mss() as sct:
            results["mss"] = benchmark("mss", capture_mss, hwnd, sct=sct)
    except ImportError:
        print("\n[mss] 未安装，跳过（pip install mss 可启用）")
        results["mss"] = (0, 0, 0, True, None)

    # 保存截图样本
    print("\n" + "=" * 60)
    print("  保存截图样本")
    print("=" * 60)

    for name, (avg, mn, mx, black, sample) in results.items():
        if sample is not None:
            safe_name = name.replace("+", "_")
            path = os.path.join(OUTPUT_DIR, f"{safe_name}.png")
            sample.save(path)
            print(f"  {name:20s} → {path}  尺寸={sample.size}  黑屏={black}")

    # 汇总
    print("\n" + "=" * 60)
    print("  测试汇总")
    print("=" * 60)
    print(f"{'方案':<22} {'平均(ms)':<10} {'最小(ms)':<10} {'最大(ms)':<10} {'黑屏':<6} {'推荐'}")
    print("-" * 80)

    for name, (avg, mn, mx, black, sample) in results.items():
        recommend = ""
        if avg > 0 and not black:
            if avg < 20:
                recommend = "★★★ 优秀"
            elif avg < 50:
                recommend = "★★ 可用"
            else:
                recommend = "★ 较慢"
        elif black:
            recommend = "✗ 不可用（黑屏）"
        print(f"{name:<22} {avg:<10.1f} {mn:<10.1f} {mx:<10.1f} {str(black):<6} {recommend}")

    print(f"\n截图已保存到: {OUTPUT_DIR}")
    print("请打开图片查看哪个方案截取的画面正确且不含标题栏。")


if __name__ == "__main__":
    main()
