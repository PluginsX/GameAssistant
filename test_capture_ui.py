"""画面抓取实时预览测试工具。"""

import os
import ctypes
import sys

# =================================================================================
# 【核心修复 1】：强制关闭 DPI 缩放（必须放在整个文件最顶部！）
# PyQt 默认将进程设为 DPI 感知，导致 GetClientRect 返回物理像素尺寸，
# 而 BitBlt 抓取的是游戏实际渲染尺寸（逻辑像素），产生黑边。
# =================================================================================
if sys.platform == "win32":
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "0"
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(-1)
    except AttributeError:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(0)
        except Exception:
            pass


import logging
import time

import win32gui
import win32ui
import win32con
from PIL import Image
from PyQt5.QtCore import Qt, QTimer, QRect
from PyQt5.QtGui import QImage, QPixmap, QFont, QPainter, QPen, QColor
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSlider, QComboBox, QSizePolicy
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

_SELF_KEYWORDS = ["挂机脚本", "配置控制台", "画面预览", "按键测试", "QQ三国Bot", "capture"]


def find_game_window(title_keyword: str = "QQ三国") -> int:
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
# 截图方案
# ---------------------------------------------------------------------------

def capture_getdc(hwnd: int) -> Image.Image:
    """BitBlt + GetDC：只截客户区。"""
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


def capture_windowdc(hwnd: int) -> Image.Image:
    """BitBlt + GetWindowDC：截完整窗口。"""
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


CAPTURE_METHODS = {
    "BitBlt+GetDC（客户区）": capture_getdc,
    "BitBlt+WindowDC（完整窗口）": capture_windowdc,
}


# ---------------------------------------------------------------------------
# 自定义预览控件
# ---------------------------------------------------------------------------

class PreviewWidget(QWidget):
    """等比例居中、不裁剪的实时画面预览控件。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(400, 300)
        self.setStyleSheet("PreviewWidget { background: #0A0E17; }")

        self._qimage = QImage()
        self._error_text = None

    def set_image(self, qimage: QImage):
        self._qimage = qimage
        self._error_text = None
        self.update()

    def set_error(self, message: str):
        self._qimage = QImage()
        self._error_text = message
        self.update()

    def current_image(self) -> QImage:
        return self._qimage

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        rect = self.rect()
        painter.fillRect(rect, QColor("#0A0E17"))

        if self._error_text:
            painter.setPen(QPen(QColor("#FF6666")))
            painter.drawText(rect, Qt.AlignCenter, self._error_text)
            return

        if not self._qimage.isNull():
            img_w = self._qimage.width()
            img_h = self._qimage.height()
            view_w = rect.width()
            view_h = rect.height()

            # Aspect-Fit：等比居中不裁剪
            scale = min(view_w / img_w, view_h / img_h)
            new_w = int(img_w * scale)
            new_h = int(img_h * scale)

            x = (view_w - new_w) // 2
            y = (view_h - new_h) // 2

            target_rect = QRect(x, y, new_w, new_h)
            painter.drawImage(target_rect, self._qimage)

            # 虚线外框确认实际边界
            painter.setPen(QPen(QColor("#334155"), 1, Qt.DashLine))
            painter.drawRect(target_rect)


# ---------------------------------------------------------------------------
# 实时预览窗口
# ---------------------------------------------------------------------------

STYLE_SHEET = """
QWidget { background: #0F172A; color: #CBD5E1; font-size: 13px; }
QLabel { color: #CBD5E1; }
QLabel#title { color: #00D9A3; font-size: 15px; font-weight: 600; }
QLabel#fps { color: #00D9A3; font-size: 14px; font-weight: 600; }
QLabel#info { color: #94A3B8; font-size: 11px; }
QComboBox, QSlider { background: #1E293B; border: 1px solid #334155; border-radius: 5px; padding: 4px 8px; }
QComboBox:hover, QSlider:hover { border-color: #0EA5E9; }
QComboBox::drop-down { border: none; width: 20px; }
QPushButton { background: #1E293B; border: 1px solid #334155; border-radius: 6px; padding: 8px 20px; font-weight: 500; }
QPushButton:hover { background: #334155; border-color: #0EA5E9; }
QPushButton#startBtn { background: #00D9A3; color: #0F172A; border: none; font-weight: 600; }
QPushButton#stopBtn { background: #EF4444; color: #F1F5F9; border: none; font-weight: 600; }
QSlider::groove:horizontal { height: 6px; background: #334155; border-radius: 3px; }
QSlider::handle:horizontal { width: 18px; height: 18px; margin: -6px 0; background: #00D9A3; border-radius: 9px; }
QSlider::sub-page:horizontal { background: #00D9A3; border-radius: 3px; }
"""

class CapturePreviewWindow(QWidget):
    def __init__(self, hwnd: int):
        super().__init__()
        self.hwnd = hwnd
        self.setWindowTitle("画面抓取预览 - QQ三国")
        self.resize(900, 650)
        self.setStyleSheet(STYLE_SHEET)

        self._capturing = False
        self._method_name = "BitBlt+GetDC（客户区）"
        self._fps = 30
        self._frame_count = 0
        self._fps_timer_start = time.time()
        self._actual_fps = 0.0
        self._last_capture_ms = 0.0

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)

        self._build_ui()
        self._update_info_label()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        ctrl_row = QHBoxLayout()
        title_label = QLabel("画面抓取预览")
        title_label.setObjectName("title")
        ctrl_row.addWidget(title_label)
        ctrl_row.addSpacing(20)

        ctrl_row.addWidget(QLabel("截图方案:"))
        self._method_combo = QComboBox()
        self._method_combo.addItems(list(CAPTURE_METHODS.keys()))
        self._method_combo.setCurrentText(self._method_name)
        self._method_combo.currentTextChanged.connect(self._on_method_changed)
        self._method_combo.setFixedWidth(220)
        ctrl_row.addWidget(self._method_combo)
        ctrl_row.addSpacing(10)

        ctrl_row.addWidget(QLabel("FPS:"))
        self._fps_slider = QSlider(Qt.Horizontal)
        self._fps_slider.setRange(1, 60)
        self._fps_slider.setValue(self._fps)
        self._fps_slider.setFixedWidth(150)
        self._fps_slider.valueChanged.connect(self._on_fps_changed)
        ctrl_row.addWidget(self._fps_slider)

        self._fps_value_label = QLabel(f"{self._fps}")
        self._fps_value_label.setFixedWidth(30)
        self._fps_value_label.setStyleSheet("color: #00D9A3; font-weight: 600;")
        ctrl_row.addWidget(self._fps_value_label)
        ctrl_row.addStretch()

        self._fps_label = QLabel("实际: 0.0 FPS")
        self._fps_label.setObjectName("fps")
        ctrl_row.addWidget(self._fps_label)
        layout.addLayout(ctrl_row)

        btn_row = QHBoxLayout()
        self._start_btn = QPushButton("开始预览")
        self._start_btn.setObjectName("startBtn")
        self._start_btn.clicked.connect(self._on_start)
        btn_row.addWidget(self._start_btn)

        self._stop_btn = QPushButton("停止预览")
        self._stop_btn.setObjectName("stopBtn")
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._on_stop)
        btn_row.addWidget(self._stop_btn)

        self._save_btn = QPushButton("保存当前帧")
        self._save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(self._save_btn)
        btn_row.addStretch()

        self._ms_label = QLabel("单帧: 0.0 ms")
        self._ms_label.setStyleSheet("color: #0EA5E9; font-size: 12px;")
        btn_row.addWidget(self._ms_label)
        layout.addLayout(btn_row)

        self._preview = PreviewWidget()
        layout.addWidget(self._preview, 1)

        info_row = QHBoxLayout()
        self._info_label = QLabel("")
        self._info_label.setObjectName("info")
        info_row.addWidget(self._info_label)
        info_row.addStretch()
        self._status_label = QLabel("就绪")
        self._status_label.setObjectName("info")
        info_row.addWidget(self._status_label)
        layout.addLayout(info_row)

    def _update_info_label(self):
        title = win32gui.GetWindowText(self.hwnd)
        _, _, cw, ch = win32gui.GetClientRect(self.hwnd)
        self._info_label.setText(f"窗口: {title}  |  hwnd: {self.hwnd}  |  客户区: {cw}x{ch}")

    def _on_method_changed(self, text: str):
        self._method_name = text

    def _on_fps_changed(self, value: int):
        self._fps = value
        self._fps_value_label.setText(f"{value}")
        if self._capturing:
            self._timer.setInterval(int(1000 / value))

    def _on_start(self):
        if win32gui.IsIconic(self.hwnd):
            win32gui.ShowWindow(self.hwnd, 9)
            time.sleep(0.5)

        self._capturing = True
        self._frame_count = 0
        self._fps_timer_start = time.time()
        self._timer.start(int(1000 / self._fps))
        self._start_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._status_label.setText("预览中...")

    def _on_stop(self):
        self._capturing = False
        self._timer.stop()
        self._start_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._status_label.setText("已停止")

    def _on_save(self):
        qimg = self._preview.current_image()
        if qimg is None or qimg.isNull():
            return
        save_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "capture_test")
        os.makedirs(save_dir, exist_ok=True)
        path = os.path.join(save_dir, f"preview_{int(time.time())}.png")
        QPixmap.fromImage(qimg).save(path)
        self._status_label.setText(f"已保存: {path}")

    def _on_tick(self):
        if not self._capturing:
            return

        if win32gui.IsIconic(self.hwnd):
            win32gui.ShowWindow(self.hwnd, 9)
            time.sleep(0.3)

        method = CAPTURE_METHODS.get(self._method_name, capture_getdc)
        t0 = time.perf_counter()
        try:
            img = method(self.hwnd)
        except Exception as e:
            self._preview.set_error(f"截图失败: {e}")
            return
        self._last_capture_ms = (time.perf_counter() - t0) * 1000

        self._update_info_label()
        _, _, cw, ch = win32gui.GetClientRect(self.hwnd)
        if img.size == (1, 1) or cw <= 0 or ch <= 0:
            self._preview.set_error("窗口客户区为 0x0，请确保游戏窗口未最小化")
            return

        try:
            if img.mode != "RGB":
                img = img.convert("RGB")

            img_data = img.tobytes("raw", "RGB")
            qimg = QImage(img_data, img.width, img.height, img.width * 3, QImage.Format_RGB888)

            # 深拷贝，避免 img_data 生命周期结束后野指针导致闪退
            self._preview.set_image(qimg.copy())
        except Exception as e:
            self._preview.set_error(f"图像转换失败: {e}")
            return

        self._frame_count += 1
        elapsed = time.time() - self._fps_timer_start
        if elapsed >= 1.0:
            self._actual_fps = self._frame_count / elapsed
            self._fps_label.setText(f"实际: {self._actual_fps:.1f} FPS")
            self._ms_label.setText(f"单帧: {self._last_capture_ms:.1f} ms")
            self._frame_count = 0
            self._fps_timer_start = time.time()

    def closeEvent(self, event):
        self._timer.stop()
        event.accept()

def main():
    app = QApplication(sys.argv)
    app.setFont(QFont("Microsoft YaHei UI", 9))

    hwnd = find_game_window("QQ三国")
    if not hwnd:
        print("未找到 QQ三国 窗口！请确认游戏已启动。")
        results = []
        def _list_enum(h, _):
            if win32gui.IsWindowVisible(h):
                t = win32gui.GetWindowText(h)
                if t and not any(kw in t for kw in _SELF_KEYWORDS):
                    results.append((h, t))
            return True
        win32gui.EnumWindows(_list_enum, None)
        results.sort(key=lambda x: x[1].lower())
        for i, (h, t) in enumerate(results):
            print(f"  [{i}] hwnd={h}  {t}")
        choice = input("\n选择窗口编号（回车退出）: ").strip()
        if not choice:
            return
        try:
            hwnd = results[int(choice)][0]
        except (ValueError, IndexError):
            return

    print(f"目标窗口: hwnd={hwnd}, 标题={win32gui.GetWindowText(hwnd)}")
    window = CapturePreviewWindow(hwnd)
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
