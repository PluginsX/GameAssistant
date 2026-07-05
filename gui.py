"""QQ三国挂机脚本图形化配置控制台。

PyQt5 实现的深色游戏工具风格主窗口，集成配置编辑、脚本启停控制、
运行时热更新和实时日志显示。与命令行入口（python main.py）共存。

用法：
    python gui.py
"""

import os
import sys
import json
import ctypes
import ctypes.wintypes
import logging
from contextlib import contextmanager

# =================================================================================
# 【核心修复】：DPI 缩放与底层图形抓取（BitBlt）完美兼容方案
#
# 1. 在程序绝对顶层（Qt 加载前）读取配置文件，根据用户设置真实开启/关闭 Qt 的高清缩放。
# 2. 引入 dpi_unaware_context 临时上下文。
# 3. 拦截修补（Monkey Patch） win32gui，保证抓图时获取的是不受缩放污染的原始物理坐标。
# =================================================================================
_ENABLE_DPI_SCALE = True
if sys.platform == "win32":
    try:
        # 尝试在 Qt 初始化前提取 DPI 配置
        if os.path.exists("config.json"):
            with open("config.json", "r", encoding="utf-8") as f:
                _cfg = json.load(f)
                if "auto_dpi_scale" in _cfg:
                    _ENABLE_DPI_SCALE = bool(_cfg["auto_dpi_scale"])
    except Exception:
        pass

    if _ENABLE_DPI_SCALE:
        # 开启 Qt 级别的高清自适应缩放（界面清晰，字体锐利）
        os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
        os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
    else:
        # 关闭缩放，强制由 Windows DWM 进行全局拉伸（界面可能会发虚）
        os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
        os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "0"
        try:
            ctypes.windll.user32.SetProcessDpiAwarenessContext(-1)
        except AttributeError:
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(0)
            except Exception:
                pass

@contextmanager
def dpi_unaware_context():
    """临时切换当前线程为 DPI 无感知，避免高缩放时 BitBlt 抓出大量黑边的问题。"""
    old_ctx = None
    if sys.platform == "win32":
        try:
            user32 = ctypes.windll.user32
            if hasattr(user32, 'SetThreadDpiAwarenessContext'):
                # DPI_AWARENESS_CONTEXT_UNAWARE = -1 (c_void_p(-1))
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


from PyQt5.QtCore import Qt, pyqtSignal, QObject, QTimer, QRect
from PyQt5.QtGui import QCursor, QFont, QImage, QPixmap, QTextCursor, QPainter, QPen, QColor
from PyQt5.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDoubleSpinBox,
    QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QMessageBox, QPushButton, QScrollArea,
    QSizePolicy, QSpinBox, QTextEdit, QVBoxLayout, QWidget, QInputDialog,
)

try:
    import keyboard
    _HAS_KEYBOARD = True
except ImportError:
    _HAS_KEYBOARD = False

# --- 猴子补丁 (Monkey Patch) win32gui ---
import win32gui
import win32ui
import win32con
from PIL import Image

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
# -------------------------------------


WM_NCCALCSIZE = 0x0083
WM_NCHITTEST = 0x0084
WM_NCLBUTTONDOWN = 0x00A1
WM_NCLBUTTONUP = 0x00A2
WM_NCLBUTTONDBLCLK = 0x00A3

HTCLIENT = 1
HTCAPTION = 2
HTMINBUTTON = 8
HTMAXBUTTON = 9
HTCLOSE = 20
HTTOP = 12
HTTOPLEFT = 13
HTTOPRIGHT = 14
HTLEFT = 10
HTRIGHT = 11
HTBOTTOM = 15
HTBOTTOMLEFT = 16
HTBOTTOMRIGHT = 17

WS_THICKFRAME = 0x00040000
WS_MINIMIZEBOX = 0x00020000
WS_MAXIMIZEBOX = 0x00010000

GWL_STYLE = -16
BORDER_WIDTH = 6


# ---------------------------------------------------------------------------
# 预览控件
# ---------------------------------------------------------------------------
class PreviewWidget(QWidget):
    """等比例居中、不裁剪的实时画面预览控件。"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(200, 150)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet("PreviewWidget { background: #0a0a0a; border: none; }")
        self._qimage = QImage()
        self._error_text: str | None = None

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
        painter.fillRect(rect, QColor("#0a0a0a"))

        if self._error_text:
            painter.setPen(QPen(QColor("#FF6666")))
            painter.drawText(rect, Qt.AlignCenter, self._error_text)
            return

        if self._qimage.isNull():
            return

        img_w = self._qimage.width()
        img_h = self._qimage.height()
        view_w = rect.width()
        view_h = rect.height()

        scale = min(view_w / img_w, view_h / img_h)
        new_w = int(img_w * scale)
        new_h = int(img_h * scale)
        x = (view_w - new_w) // 2
        y = (view_h - new_h) // 2

        painter.drawImage(QRect(x, y, new_w, new_h), self._qimage)


class CollapsibleSection(QWidget):
    def __init__(self, title: str, parent=None, expanded: bool = False):
        super().__init__(parent)
        self._expanded = expanded
        self._title = title

        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(0, 0, 0, 0)
        self._main_layout.setSpacing(0)

        self._header = QPushButton()
        self._header.setCursor(Qt.PointingHandCursor)
        self._header.setFixedHeight(36)
        self._header.setStyleSheet("""
            QPushButton { background: #1e1e1e; border: 1px solid #3a3a3a; border-radius: 6px;
                color: #6b8cff; text-align: left; padding: 0 12px; font-size: 13px; font-weight: 600; }
            QPushButton:hover { background: #2a2a2a; border-color: #6b8cff; }
        """)
        self._header.clicked.connect(self._toggle)
        self._main_layout.addWidget(self._header)

        self._content_container = QWidget()
        self._content_layout = QVBoxLayout(self._content_container)
        self._content_layout.setContentsMargins(8, 8, 8, 8)
        self._content_layout.setSpacing(8)
        self._main_layout.addWidget(self._content_container)

        self._update_header_text()
        self._content_container.setVisible(expanded)

    def _toggle(self):
        self._expanded = not self._expanded
        self._content_container.setVisible(self._expanded)
        self._update_header_text()

    def _update_header_text(self):
        arrow = "▼" if self._expanded else "▶"
        self._header.setText(f" {arrow}  {self._title}")

    def setExpanded(self, expanded: bool):
        if expanded != self._expanded:
            self._toggle()

    def isExpanded(self) -> bool:
        return self._expanded

    def contentLayout(self) -> QVBoxLayout:
        return self._content_layout

    def addWidget(self, widget):
        self._content_layout.addWidget(widget)

    def addLayout(self, layout):
        self._content_layout.addLayout(layout)


# ---------------------------------------------------------------------------
# 画面截图函数
# ---------------------------------------------------------------------------
def _capture_getdc(hwnd: int) -> Image.Image:
    """BitBlt + GetDC：只截客户区。"""
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

    return Image.frombuffer("RGB", (bmp_info["bmWidth"], bmp_info["bmHeight"]),
                            bmp_bits, "raw", "BGRX", 0, 1)


def _capture_windowdc(hwnd: int) -> Image.Image:
    """BitBlt + GetWindowDC：截完整窗口。"""
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

    return Image.frombuffer("RGB", (bmp_info["bmWidth"], bmp_info["bmHeight"]),
                            bmp_bits, "raw", "BGRX", 0, 1)


_CAPTURE_METHODS = {
    "BitBlt+GetDC（客户区）": _capture_getdc,
    "BitBlt+WindowDC（完整窗口）": _capture_windowdc,
}


from bot_worker import BotWorker
from config import BotConfig
from task_queue import Task, TaskEvent, TaskQueue

logger = logging.getLogger(__name__)

STYLE_SHEET = """
QWidget { background: #121212; color: #e0e0e0; }
QMainWindow, QWidget#central { background: #121212; border: 1px solid #3a3a3a; }
QLabel { color: #e0e0e0; font-size: 13px; }
QLabel#sectionTitle { color: #6b8cff; font-size: 15px; font-weight: 600; }
QScrollArea, QScrollArea > QWidget > QWidget { background: #121212; border: none; }
QScrollArea QWidget#qt_scrollarea_viewport { background: #121212; }
QFormLayout QLabel { color: #e8e8e8; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox { background: #1e1e1e; border: 1px solid #3a3a3a; border-radius: 5px; padding: 5px 8px; color: #f0f0f0; font-size: 13px; selection-background-color: #6b8cff; }
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus { border: 1px solid #6b8cff; }
QLineEdit::placeholder { color: #666666; }
QSpinBox::up-button, QDoubleSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::down-button { background: #3a3a3a; border: none; width: 16px; }
QComboBox::drop-down { border: none; width: 20px; }
QComboBox::down-arrow { image: none; border-left: 5px solid transparent; border-right: 5px solid transparent; border-top: 5px solid #888888; width: 0; height: 0; }
QComboBox:hover::down-arrow { border-top-color: #e0e0e0; }
QComboBox QAbstractItemView { background: #1e1e1e; border: 1px solid #3a3a3a; border-radius: 4px; color: #e8e8e8; selection-background-color: #6b8cff; selection-color: #ffffff; padding: 4px; outline: none; }
QComboBox QAbstractItemView::item { padding: 4px 8px; min-height: 20px; }
QComboBox QAbstractItemView::item:hover { background: #2a2a2a; }
QPushButton { background: #2a2a2a; border: 1px solid #3a3a3a; border-radius: 6px; padding: 8px 22px; color: #f0f0f0; font-size: 13px; font-weight: 500; }
QPushButton:hover { background: #363636; border-color: #6b8cff; }
QPushButton:pressed { background: #1e1e1e; }
QPushButton:disabled { color: #666666; background: #1e1e1e; border-color: #1e1e1e; }
QPushButton#startBtn { background: #4ade80; color: #0f0f0f; border: none; font-weight: 600; }
QPushButton#startBtn:hover { background: #3dd370; }
QPushButton#startBtn:disabled { background: #1e1e1e; color: #666666; }
QPushButton#stopBtn { background: #ef4444; color: #f0f0f0; border: none; font-weight: 600; }
QPushButton#stopBtn:hover { background: #dc2626; }
QPushButton#stopBtn:disabled { background: #1e1e1e; color: #666666; }
QPushButton#applyBtn { background: #6b8cff; color: #ffffff; border: none; font-weight: 600; }
QPushButton#applyBtn:hover { background: #5a7cef; }
QPushButton#applyBtn:disabled { background: #1e1e1e; color: #666666; }
QCheckBox { color: #e0e0e0; font-size: 13px; spacing: 8px; }
QCheckBox::indicator { width: 18px; height: 18px; border: 1px solid #4a4a4a; border-radius: 4px; background: #1e1e1e; }
QCheckBox::indicator:checked { background: #6b8cff; border: 1px solid #6b8cff; }
QTextEdit { background: #121212; border: 1px solid #3a3a3a; border-radius: 6px; color: #e0e0e0; font-family: 'Consolas', 'Courier New', monospace; font-size: 12px; padding: 4px; }
QScrollBar:vertical { background: #1e1e1e; width: 10px; border: none; }
QScrollBar::handle:vertical { background: #3a3a3a; border-radius: 5px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #4a4a4a; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
QScrollBar:horizontal { background: #1e1e1e; height: 10px; border: none; }
QScrollBar::handle:horizontal { background: #3a3a3a; border-radius: 5px; min-width: 30px; }
QScrollBar::handle:horizontal:hover { background: #4a4a4a; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: none; }
QListWidget { background: #121212; border: 1px solid #3a3a3a; border-radius: 6px; color: #e8e8e8; font-size: 13px; padding: 4px; outline: none; }
QListWidget::item { padding: 0; border-bottom: 1px solid #1e1e1e; }
QListWidget::item:selected { background: #2d3a5a; }
QListWidget::item:hover { background: #1e1e1e; }
QGroupBox { background: #1e1e1e; border: 1px solid #3a3a3a; border-radius: 8px; margin-top: 14px; padding: 16px 12px 12px 12px; color: #f0f0f0; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; color: #6b8cff; }
QSplitter::handle { background: #1e1e1e; }
QSplitter::handle:horizontal { width: 3px; }
QSplitter::handle:vertical { height: 3px; }
QFrame#taskPanel { background: #1e1e1e; border: 1px solid #3a3a3a; border-radius: 8px; }
QToolTip { background: #1e1e1e; color: #e8e8e8; border: 1px solid #3a3a3a; padding: 4px 8px; border-radius: 4px; }
"""

LEVEL_COLORS = {
    "INFO": "#e0e0e0", "WARNING": "#f59e0b", "ERROR": "#ef4444",
    "DEBUG": "#a0a0a0", "CRITICAL": "#ef4444",
}


class _HotkeyManager(QObject):
    hotkey_triggered = pyqtSignal()
    def __init__(self):
        super().__init__()
        self._hooked = False
        self._current_hotkey: str | None = None

    def set_hotkey(self, hotkey: str) -> None:
        self.unhook()
        if not hotkey or not _HAS_KEYBOARD: return
        try:
            keyboard.add_hotkey(hotkey, self._on_hotkey)
            self._current_hotkey = hotkey
            self._hooked = True
        except Exception:
            self._hooked = False

    def unhook(self) -> None:
        if self._hooked and _HAS_KEYBOARD:
            try: keyboard.clear_all_hotkeys()
            except Exception: pass
        self._hooked = False
        self._current_hotkey = None

    def _on_hotkey(self):
        self.hotkey_triggered.emit()

    @property
    def is_hooked(self) -> bool: return self._hooked

    @property
    def current_hotkey(self) -> str | None: return self._current_hotkey


class _TaskBlockWidget(QWidget):
    def __init__(self, event: TaskEvent, index: int, parent_list=None):
        super().__init__()
        self.event = event
        self.index = index
        self._parent_list = parent_list

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)
        handle = QLabel("⋮⋮")
        handle.setStyleSheet(f"color: {event.get_color()}; font-size: 14px; font-weight: 900;")
        handle.setFixedWidth(18)
        handle.setCursor(Qt.SizeAllCursor)
        layout.addWidget(handle)

        text_label = QLabel(event.get_display_text())
        text_label.setStyleSheet("color: #e8e8e8; font-size: 14px; font-weight: 500;")
        layout.addWidget(text_label)
        layout.addStretch()

        up_btn = QPushButton("▲")
        up_btn.setFixedSize(22, 22)
        up_btn.setStyleSheet("QPushButton { background: #3a3a3a; color: #d0d0d0; border: none; border-radius: 4px; font-size: 10px; font-weight: 700; } QPushButton:hover { background: #4a4a4a; color: #f0f0f0; } QPushButton:disabled { color: #666666; background: #1e1e1e; }")
        up_btn.clicked.connect(self._on_move_up)
        up_btn.setEnabled(index > 0)
        layout.addWidget(up_btn)

        down_btn = QPushButton("▼")
        down_btn.setFixedSize(22, 22)
        down_btn.setStyleSheet("QPushButton { background: #3a3a3a; color: #d0d0d0; border: none; border-radius: 4px; font-size: 10px; font-weight: 700; } QPushButton:hover { background: #4a4a4a; color: #f0f0f0; }")
        down_btn.clicked.connect(self._on_move_down)
        layout.addWidget(down_btn)

        del_btn = QPushButton("×")
        del_btn.setFixedSize(22, 22)
        del_btn.setStyleSheet("QPushButton { background: #ef4444; color: white; border: none; border-radius: 4px; font-size: 14px; font-weight: 700; } QPushButton:hover { background: #dc2626; }")
        del_btn.clicked.connect(self._on_delete)
        layout.addWidget(del_btn)

    def _on_delete(self):
        if self._parent_list: self._parent_list._delete_event(self.index)
    def _on_move_up(self):
        if self._parent_list and self.index > 0: self._parent_list._move_event(self.index, self.index - 1)
    def _on_move_down(self):
        if self._parent_list: self._parent_list._move_event(self.index, self.index + 1)


class BlockActionItemWidget(QWidget):
    def __init__(self, key: str = "Space", action_type: str = "keyclick", parent=None, index: int = 0):
        super().__init__(parent)
        self._parent = parent
        self.index = index
        self.setStyleSheet("BlockActionItemWidget { background: #1e1e1e; border: 1px solid #3a3a3a; border-radius: 6px; } BlockActionItemWidget:hover { border-color: #6b8cff; }")
        self.setFixedHeight(32)
        self.setFixedWidth(177)
        self.setAttribute(Qt.WA_StyledBackground, True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.key_combo = QComboBox()
        self._populate_key_combo(self.key_combo)
        self.key_combo.setCurrentText(key)
        self.key_combo.setFixedWidth(70)
        self.key_combo.setCursor(Qt.PointingHandCursor)
        self.key_combo.setStyleSheet("QComboBox { background: #1e1e1e; border: none; border-right: 1px solid #3a3a3a; border-top-left-radius: 5px; border-bottom-left-radius: 5px; padding: 0px 12px; color: #f0f0f0; font-size: 12px; font-weight: 500; } QComboBox:hover { background: #2a2a2a; } QComboBox::drop-down { width: 0px; border: none; } QComboBox QAbstractItemView { background: #1e1e1e; border: 1px solid #3a3a3a; border-radius: 4px; color: #e8e8e8; selection-background-color: #6b8cff; selection-color: #ffffff; padding: 4px; } QComboBox QAbstractItemView::item { padding: 4px 8px; min-height: 20px; }")
        layout.addWidget(self.key_combo)

        self.type_combo = QComboBox()
        self.type_combo.addItems(["keydown", "keyup", "keyclick"])
        self.type_combo.setCurrentText(action_type)
        self.type_combo.setFixedWidth(75)
        self.type_combo.setCursor(Qt.PointingHandCursor)
        self.type_combo.setStyleSheet("QComboBox { background: #1e1e1e; border: none; border-right: 1px solid #3a3a3a; border-radius: 0px; padding: 0px 12px; color: #a78bfa; font-size: 12px; font-weight: 500; } QComboBox:hover { background: #2a2a2a; } QComboBox::drop-down { width: 0px; border: none; } QComboBox QAbstractItemView { background: #1e1e1e; border: 1px solid #3a3a3a; border-radius: 4px; color: #e8e8e8; selection-background-color: #6b8cff; selection-color: #ffffff; padding: 4px; } QComboBox QAbstractItemView::item { padding: 4px 8px; min-height: 20px; }")
        layout.addWidget(self.type_combo)

        del_btn = QPushButton("×")
        del_btn.setFixedWidth(32)
        del_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        del_btn.setCursor(Qt.PointingHandCursor)
        del_btn.setStyleSheet("QPushButton { background: #1e1e1e; color: #ef4444; border: none; border-top-right-radius: 5px; border-bottom-right-radius: 5px; font-size: 16px; font-weight: 700; padding: 0px; } QPushButton:hover { background: #ef4444; color: white; }")
        del_btn.clicked.connect(self._on_delete)
        layout.addWidget(del_btn)

    def _populate_key_combo(self, combo: QComboBox):
        groups = [
            ("数字", [str(i) for i in range(10)]), ("字母", [chr(c) for c in range(0x41, 0x5B)]),
            ("方向", ["Left", "Up", "Right", "Down"]),
            ("控制", ["Space", "Enter", "Tab", "Esc", "Shift", "Ctrl", "Alt"]),
            ("功能", [f"F{i}" for i in range(1, 13)]),
        ]
        for group_name, keys in groups:
            combo.addItem(f"── {group_name} ──", "")
            for key in keys: combo.addItem(key, key)

    def _on_delete(self):
        if self._parent and hasattr(self._parent, "_remove_block_action"):
            self._parent._remove_block_action(self.index)
    def get_key(self) -> str: return self.key_combo.currentData() or self.key_combo.currentText()
    def get_type(self) -> str: return self.type_combo.currentText()


class _EventListWidget(QListWidget):
    def __init__(self, main_window):
        super().__init__()
        self._main = main_window
        self.setSelectionMode(QListWidget.SingleSelection)
        self.setDragDropMode(QListWidget.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setDragDropOverwriteMode(False)
        self.setAlternatingRowColors(False)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self._drag_start_index = -1

    def refresh_events(self, task: Task):
        self.clear()
        for i, event in enumerate(task.events):
            item = QListWidgetItem()
            widget = _TaskBlockWidget(event, i, self)
            self.addItem(item)
            self.setItemWidget(item, widget)
            item.setSizeHint(widget.sizeHint())

    def startDrag(self, supportedActions):
        self._drag_start_index = self.currentRow()
        super().startDrag(supportedActions)

    def dropEvent(self, event):
        from_idx = self._drag_start_index
        if from_idx < 0:
            super().dropEvent(event)
            return
        task = self._main._get_selected_task()
        if not task:
            super().dropEvent(event)
            return

        target_idx = self.indexAt(event.pos()).row()
        if target_idx < 0: target_idx = len(task.events) - 1
        super().dropEvent(event)

        if 0 <= from_idx < len(task.events):
            event_obj = task.events.pop(from_idx)
            if target_idx > from_idx: target_idx -= 1
            target_idx = max(0, min(target_idx, len(task.events)))
            task.events.insert(target_idx, event_obj)
            self.refresh_events(task)
            self.setCurrentRow(target_idx)
        self._drag_start_index = -1

    def _delete_event(self, index: int):
        task = self._main._get_selected_task()
        if task and 0 <= index < len(task.events):
            task.events.pop(index)
            self.refresh_events(task)

    def _move_event(self, from_idx: int, to_idx: int):
        task = self._main._get_selected_task()
        if not task: return
        if from_idx < 0 or from_idx >= len(task.events) or to_idx < 0 or to_idx >= len(task.events): return
        event = task.events.pop(from_idx)
        task.events.insert(to_idx, event)
        self.refresh_events(task)
        self.setCurrentRow(to_idx)


class _TaskItemWidget(QWidget):
    def __init__(self, task: Task, index: int, list_widget: QListWidget, main_window):
        super().__init__()
        self.task = task
        self.index = index
        self._list_widget = list_widget
        self._main = main_window
        self.setAutoFillBackground(False)
        self.setCursor(Qt.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        self.checkbox = QCheckBox()
        self.checkbox.setChecked(task.enabled)
        self.checkbox.stateChanged.connect(self._on_toggled)
        self.checkbox.setCursor(Qt.PointingHandCursor)
        layout.addWidget(self.checkbox)

        name_label = QLabel(task.name)
        name_label.setStyleSheet("color: #e8e8e8; font-size: 14px; font-weight: 500;")
        name_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(name_label)

        if task.repeat > 1:
            repeat_label = QLabel(f"×{task.repeat}")
            repeat_label.setStyleSheet("color: #808080; font-size: 12px;")
            repeat_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            layout.addWidget(repeat_label)

        layout.addStretch()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._list_widget.setCurrentRow(self.index)
            self._main._on_task_selected(self.index)
        super().mousePressEvent(event)

    def update_index(self, index: int): self.index = index
    def _on_toggled(self, state: int): self.task.enabled = (state == Qt.Checked)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("辅助机器人")
        self.resize(900, 720)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowSystemMenuHint | Qt.WindowMinMaxButtonsHint)

        self._drag_pos = None
        self._style_applied = False

        self.config = BotConfig.load()
        self.worker: BotWorker | None = None
        self._preview_widget: PreviewWidget | None = None
        self._last_frame: QImage | None = None
        self._preview_timer = QTimer(self)
        self._preview_timer.timeout.connect(self._on_preview_tick)
        self._preview_capturing = False

        self._task_queue: TaskQueue | None = None
        self._selected_task_index: int = -1
        self._hotkey_mgr = _HotkeyManager()
        self._hotkey_signal_connected = False

        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self._title_bar, self._max_btn = self._build_title_bar()
        root_layout.addWidget(self._title_bar)

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(12, 8, 12, 12)
        content_layout.setSpacing(8)
        root_layout.addWidget(content_widget, 1)

        toolbar_frame = QFrame()
        toolbar_frame.setObjectName("toolbarFrame")
        toolbar_frame.setStyleSheet("QFrame#toolbarFrame { background: #1e1e1e; border: 1px solid #3a3a3a; border-radius: 8px; }")
        toolbar_layout = QVBoxLayout(toolbar_frame)
        toolbar_layout.setContentsMargins(12, 10, 12, 10)
        toolbar_layout.addLayout(self._build_toolbar())
        content_layout.addWidget(toolbar_frame)

        self._main_scroll = QScrollArea()
        self._main_scroll.setWidgetResizable(True)
        self._main_scroll.setFrameShape(QScrollArea.NoFrame)
        scroll_content = QWidget()
        self._scroll_layout = QVBoxLayout(scroll_content)
        self._scroll_layout.setSpacing(8)
        self._scroll_layout.setContentsMargins(2, 2, 2, 2)
        self._main_scroll.setWidget(scroll_content)
        content_layout.addWidget(self._main_scroll, 1)

        self._section_preview = CollapsibleSection("画面预览")
        self._build_preview_into(self._section_preview.contentLayout())
        self._scroll_layout.addWidget(self._section_preview)

        self._section_settings = CollapsibleSection("设置")
        self._build_settings_into(self._section_settings.contentLayout())
        self._scroll_layout.addWidget(self._section_settings)

        self._section_tasks = CollapsibleSection("任务队列")
        self._build_task_editor_into(self._section_tasks.contentLayout())
        self._scroll_layout.addWidget(self._section_tasks)

        self._section_log = CollapsibleSection("运行日志")
        self._build_log_into(self._section_log.contentLayout())
        self._scroll_layout.addWidget(self._section_log)

        self._scroll_layout.addStretch()

        self._populate_form()
        self._load_task_queue_config()

    def _build_title_bar(self):
        title_bar = QWidget()
        title_bar.setObjectName("titleBar")
        title_bar.setFixedHeight(36)
        title_bar.setStyleSheet("QWidget#titleBar { background: #0d0d0d; border-bottom: 1px solid #2a2a2a; }")

        layout = QHBoxLayout(title_bar)
        layout.setContentsMargins(12, 0, 4, 0)
        layout.setSpacing(0)

        title_label = QLabel("辅助机器人")
        title_label.setObjectName("titleBarLabel")
        title_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        title_label.setStyleSheet("QLabel#titleBarLabel { color: #e0e0e0; font-size: 13px; font-weight: 500; background: transparent; }")
        layout.addWidget(title_label)
        layout.addStretch()

        btn_size = 36
        min_btn = QPushButton("─")
        min_btn.setObjectName("titleBtnMin")
        min_btn.setFixedSize(btn_size, btn_size)
        min_btn.setCursor(Qt.PointingHandCursor)
        min_btn.setFocusPolicy(Qt.NoFocus)
        min_btn.setStyleSheet("QPushButton#titleBtnMin { background: transparent; border: none; color: #e0e0e0; font-size: 14px; font-family: 'Segoe UI', 'Microsoft YaHei UI'; } QPushButton#titleBtnMin:hover { background: #2a2a2a; } QPushButton#titleBtnMin:pressed { background: #3a3a3a; }")
        min_btn.clicked.connect(self._title_minimize)
        layout.addWidget(min_btn)

        max_btn = QPushButton("▢")
        max_btn.setObjectName("titleBtnMax")
        max_btn.setFixedSize(btn_size, btn_size)
        max_btn.setCursor(Qt.PointingHandCursor)
        max_btn.setFocusPolicy(Qt.NoFocus)
        max_btn.setStyleSheet("QPushButton#titleBtnMax { background: transparent; border: none; color: #e0e0e0; font-size: 14px; font-family: 'Segoe UI', 'Microsoft YaHei UI'; } QPushButton#titleBtnMax:hover { background: #2a2a2a; } QPushButton#titleBtnMax:pressed { background: #3a3a3a; }")
        max_btn.clicked.connect(self._title_toggle_maximize)
        layout.addWidget(max_btn)

        close_btn = QPushButton("✕")
        close_btn.setObjectName("titleBtnClose")
        close_btn.setFixedSize(btn_size, btn_size)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setFocusPolicy(Qt.NoFocus)
        close_btn.setStyleSheet("QPushButton#titleBtnClose { background: transparent; border: none; color: #e0e0e0; font-size: 14px; font-family: 'Segoe UI', 'Microsoft YaHei UI'; } QPushButton#titleBtnClose:hover { background: #e81123; color: #ffffff; } QPushButton#titleBtnClose:pressed { background: #c4101f; color: #ffffff; }")
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)

        self._min_btn = min_btn
        self._close_btn = close_btn
        return title_bar, max_btn

    def _title_minimize(self): self.showMinimized()
    def _title_toggle_maximize(self):
        if self.isMaximized(): self.showNormal()
        else: self.showMaximized()
    def _sync_max_button(self):
        if self.isMaximized(): self._max_btn.setText("❐")
        else: self._max_btn.setText("▢")

    def showEvent(self, event):
        super().showEvent(event)
        if not self._style_applied:
            self._style_applied = True
            hwnd = int(self.winId())
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_STYLE)
            style |= WS_THICKFRAME | WS_MINIMIZEBOX | WS_MAXIMIZEBOX
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_STYLE, style)

    def changeEvent(self, event):
        if event.type() == event.WindowStateChange:
            self._sync_max_button()
        super().changeEvent(event)

    def _build_toolbar(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(10)

        self.start_btn = QPushButton("启动")
        self.start_btn.setObjectName("startBtn")
        self.start_btn.clicked.connect(self.on_start)

        self.stop_btn = QPushButton("停止")
        self.stop_btn.setObjectName("stopBtn")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.on_stop)

        self.apply_btn = QPushButton("应用")
        self.apply_btn.setObjectName("applyBtn")
        self.apply_btn.setEnabled(False)
        self.apply_btn.clicked.connect(self.on_apply)

        self.save_btn = QPushButton("保存配置")
        self.save_btn.clicked.connect(self.on_save)

        self.hotkey_checkbox = QCheckBox("启用快捷键")
        self.hotkey_checkbox.setChecked(True)
        self.hotkey_checkbox.setStyleSheet("color: #e0e0e0; font-size: 13px;")
        self.hotkey_checkbox.toggled.connect(self._on_hotkey_toggled)

        self.hotkey_combo = QComboBox()
        self._populate_hotkey_combo(self.hotkey_combo)
        self.hotkey_combo.setFixedWidth(100)
        self.hotkey_combo.setToolTip("选择启动/停止切换的全局快捷键")
        self.hotkey_combo.currentTextChanged.connect(self._on_hotkey_changed)

        self.status_dot = QLabel("\u25CF")
        self.status_dot.setFixedWidth(18)
        self.status_dot.setStyleSheet("color: #666666; font-size: 18px;")
        self.status_label = QLabel("未运行")
        self.status_label.setStyleSheet("color: #a0a0a0; font-size: 13px;")

        layout.addWidget(self.start_btn)
        layout.addWidget(self.stop_btn)
        layout.addWidget(self.apply_btn)
        layout.addWidget(self.save_btn)
        layout.addSpacing(8)
        layout.addWidget(self.hotkey_checkbox)
        layout.addWidget(self.hotkey_combo)
        layout.addStretch()
        layout.addWidget(self.status_dot)
        layout.addWidget(self.status_label)
        return layout

    def _build_settings_into(self, layout: QVBoxLayout):
        self._sec_window = CollapsibleSection("窗口设置")
        self._build_window_group_into(self._sec_window.contentLayout())
        layout.addWidget(self._sec_window)

        self._sec_debug = CollapsibleSection("调试")
        self._build_debug_group_into(self._sec_debug.contentLayout())
        layout.addWidget(self._sec_debug)

    def _build_window_group_into(self, layout: QVBoxLayout):
        form = QFormLayout()
        form.setSpacing(8)

        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("如：QQ三国")
        self.title_edit.textChanged.connect(self._on_window_title_changed)
        form.addRow("窗口标题：", self.title_edit)

        window_select_row = QHBoxLayout()
        window_select_row.setSpacing(4)
        self.cmb_window_select = QComboBox()
        self.cmb_window_select.setToolTip("选择要控制的游戏窗口（多开时手动选择）")
        window_select_row.addWidget(self.cmb_window_select, 1)

        self.btn_refresh_windows = QPushButton("⟳")
        self.btn_refresh_windows.setFixedWidth(32)
        self.btn_refresh_windows.setToolTip("刷新窗口列表")
        self.btn_refresh_windows.clicked.connect(self._refresh_window_list)
        window_select_row.addWidget(self.btn_refresh_windows)

        form.addRow("选择窗口：", window_select_row)

        self.cmb_input_mode = QComboBox()
        self.cmb_input_mode.addItems(["foreground", "postmsg", "focus"])
        self.cmb_input_mode.setToolTip("foreground: 前台发键\npostmsg: 后台消息\nfocus: 快速切焦点")
        form.addRow("输入模式：", self.cmb_input_mode)

        hint = QLabel("前台模式已验证有效；后台模式(postmsg)需测试是否兼容")
        hint.setStyleSheet("color: #888888; font-size: 11px;")
        form.addRow("", hint)

        layout.addLayout(form)

    def _build_debug_group_into(self, layout: QVBoxLayout):
        self.dpi_scale_check = QCheckBox("自适应屏幕缩放 (开启后界面清晰，不影响底层抓图)")
        self.dpi_scale_check.setToolTip("根据Windows屏幕缩放比例自动调整UI大小，确保文字清晰")
        self.dpi_scale_check.toggled.connect(self._on_dpi_scale_toggled)
        layout.addWidget(self.dpi_scale_check)

        self.debug_check = QCheckBox("启用调试日志")
        self.debug_check.toggled.connect(self._on_debug_toggled)
        layout.addWidget(self.debug_check)

    def _build_preview_into(self, layout: QVBoxLayout):
        top_row = QHBoxLayout()
        top_row.setContentsMargins(4, 2, 4, 2)
        header = QLabel("画面预览")
        header.setStyleSheet("color: #6b8cff; font-size: 13px; font-weight: 600;")
        top_row.addWidget(header)
        top_row.addSpacing(10)

        top_row.addWidget(QLabel("截图方案:"))
        self._capture_method_combo = QComboBox()
        self._capture_method_combo.addItems(["BitBlt+GetDC（客户区）", "BitBlt+WindowDC（完整窗口）"])
        self._capture_method_combo.setCurrentText("BitBlt+GetDC（客户区）")
        self._capture_method_combo.setFixedWidth(220)
        top_row.addWidget(self._capture_method_combo)
        top_row.addSpacing(10)

        self._preview_start_btn = QPushButton("开始预览")
        self._preview_start_btn.setObjectName("startBtn")
        self._preview_start_btn.setMinimumWidth(90)
        self._preview_start_btn.clicked.connect(self._on_preview_start)
        top_row.addWidget(self._preview_start_btn)

        self._preview_stop_btn = QPushButton("停止")
        self._preview_stop_btn.setObjectName("stopBtn")
        self._preview_stop_btn.setMinimumWidth(70)
        self._preview_stop_btn.setEnabled(False)
        self._preview_stop_btn.clicked.connect(self._on_preview_stop)
        top_row.addWidget(self._preview_stop_btn)
        top_row.addSpacing(10)

        top_row.addWidget(QLabel("FPS:"))
        self._preview_fps_spin = QSpinBox()
        self._preview_fps_spin.setRange(1, 60)
        self._preview_fps_spin.setValue(30)
        self._preview_fps_spin.setSuffix(" FPS")
        self._preview_fps_spin.setFixedWidth(80)
        self._preview_fps_spin.valueChanged.connect(self._on_preview_fps_changed)
        top_row.addWidget(self._preview_fps_spin)
        top_row.addStretch()

        layout.addLayout(top_row)

        self._preview_widget = PreviewWidget()
        self._preview_widget.setMinimumHeight(250)
        layout.addWidget(self._preview_widget, 1)

    def _build_log_into(self, layout: QVBoxLayout):
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(200)
        layout.addWidget(self.log_text)

    def _build_task_editor_into(self, layout: QVBoxLayout):
        panel = QFrame()
        panel.setObjectName("taskPanel")
        panel_layout = QHBoxLayout(panel)
        panel_layout.setContentsMargins(8, 8, 8, 8)
        panel_layout.setSpacing(6)

        left_col = QVBoxLayout()
        left_col.setSpacing(4)
        left_label = QLabel("任务列表")
        left_label.setStyleSheet("color: #6b8cff; font-size: 13px; font-weight: 600;")
        left_col.addWidget(left_label)

        self.task_list = QListWidget()
        self.task_list.setSelectionMode(QListWidget.SingleSelection)
        self.task_list.setFixedWidth(180)
        self.task_list.currentRowChanged.connect(self._on_task_selected)
        left_col.addWidget(self.task_list, 1)

        task_btn_row = QHBoxLayout()
        task_btn_row.setSpacing(4)
        btn_add_task = QPushButton("+")
        btn_add_task.setFixedWidth(28)
        btn_add_task.clicked.connect(self._on_add_task)
        btn_del_task = QPushButton("×")
        btn_del_task.setFixedWidth(28)
        btn_del_task.clicked.connect(self._on_del_task)
        btn_rename_task = QPushButton("✎")
        btn_rename_task.setFixedWidth(28)
        btn_rename_task.clicked.connect(self._on_rename_task)
        task_btn_row.addWidget(btn_add_task)
        task_btn_row.addWidget(btn_del_task)
        task_btn_row.addWidget(btn_rename_task)
        task_btn_row.addStretch()
        left_col.addLayout(task_btn_row)

        repeat_row = QHBoxLayout()
        repeat_row.addWidget(QLabel("重复:"))
        self.repeat_spin = QSpinBox()
        self.repeat_spin.setRange(1, 999)
        self.repeat_spin.valueChanged.connect(self._on_repeat_changed)
        repeat_row.addWidget(self.repeat_spin)
        left_col.addLayout(repeat_row)
        panel_layout.addLayout(left_col)

        mid_col = QVBoxLayout()
        mid_col.setSpacing(4)
        mid_label = QLabel("事件列表")
        mid_label.setStyleSheet("color: #6b8cff; font-size: 13px; font-weight: 600;")
        mid_col.addWidget(mid_label)
        self.event_list = _EventListWidget(self)
        mid_col.addWidget(self.event_list, 1)
        panel_layout.addLayout(mid_col, 1)

        right_col = QVBoxLayout()
        right_col.setSpacing(4)
        right_label = QLabel("快捷积木")
        right_label.setStyleSheet("color: #6b8cff; font-size: 13px; font-weight: 600;")
        right_col.addWidget(right_label)

        right_col.addWidget(QLabel("按键:"))
        self.block_key_combo = QComboBox()
        self._populate_key_combo(self.block_key_combo)
        right_col.addWidget(self.block_key_combo)

        btn_block_down = QPushButton("↓ 按下")
        btn_block_down.setStyleSheet("background: #3b82f6; color: white; border: none; border-radius: 6px; padding: 8px; font-weight: 600;")
        btn_block_down.clicked.connect(lambda: self._add_event("keydown"))
        right_col.addWidget(btn_block_down)

        btn_block_up = QPushButton("↑ 松开")
        btn_block_up.setStyleSheet("background: #8b5cf6; color: white; border: none; border-radius: 6px; padding: 8px; font-weight: 600;")
        btn_block_up.clicked.connect(lambda: self._add_event("keyup"))
        right_col.addWidget(btn_block_up)

        btn_block_click = QPushButton("↕ 单击")
        btn_block_click.setStyleSheet("background: #10b981; color: white; border: none; border-radius: 6px; padding: 8px; font-weight: 600;")
        btn_block_click.clicked.connect(lambda: self._add_event("keyclick"))
        right_col.addWidget(btn_block_click)

        right_col.addWidget(QLabel(""))
        right_col.addWidget(QLabel("等待 (ms):"))
        self.wait_random_check = QCheckBox("区间随机")
        self.wait_random_check.setStyleSheet("color: #d0d0d0; font-size: 12px;")
        self.wait_random_check.toggled.connect(self._on_wait_random_toggled)
        right_col.addWidget(self.wait_random_check)

        self.block_wait_spin = QSpinBox()
        self.block_wait_spin.setRange(10, 999999)
        self.block_wait_spin.setValue(500)
        right_col.addWidget(self.block_wait_spin)

        min_row = QHBoxLayout()
        min_row.addWidget(QLabel("最小:"))
        self.block_wait_min_spin = QSpinBox()
        self.block_wait_min_spin.setRange(10, 999999)
        self.block_wait_min_spin.setValue(200)
        min_row.addWidget(self.block_wait_min_spin)
        min_widget = QWidget()
        min_widget.setLayout(min_row)
        min_widget.setVisible(False)
        self._wait_min_widget = min_widget
        right_col.addWidget(min_widget)

        max_row = QHBoxLayout()
        max_row.addWidget(QLabel("最大:"))
        self.block_wait_max_spin = QSpinBox()
        self.block_wait_max_spin.setRange(10, 999999)
        self.block_wait_max_spin.setValue(500)
        max_row.addWidget(self.block_wait_max_spin)
        max_widget = QWidget()
        max_widget.setLayout(max_row)
        max_widget.setVisible(False)
        self._wait_max_widget = max_widget
        right_col.addWidget(max_widget)

        btn_block_wait = QPushButton("⏱ 等待")
        btn_block_wait.setStyleSheet("background: #f59e0b; color: #1a1a1a; border: none; border-radius: 6px; padding: 8px; font-weight: 600;")
        btn_block_wait.clicked.connect(self._on_add_wait_event)
        right_col.addWidget(btn_block_wait)
        right_col.addStretch()
        panel_layout.addLayout(right_col)
        layout.addWidget(panel)

        interval_frame = QFrame()
        interval_frame.setStyleSheet("QFrame { background: #1e1e1e; border: 1px solid #3a3a3a; border-radius: 6px; }")
        interval_layout = QHBoxLayout(interval_frame)
        interval_layout.setContentsMargins(12, 8, 12, 8)
        interval_layout.setSpacing(12)

        interval_label = QLabel("最小动作间隔:")
        interval_label.setStyleSheet("color: #e8e8e8; font-size: 12px; font-weight: 500;")
        interval_layout.addWidget(interval_label)

        self.min_interval_spin = QSpinBox()
        self.min_interval_spin.setRange(0, 5000)
        self.min_interval_spin.setValue(200)
        self.min_interval_spin.setSuffix(" ms")
        self.min_interval_spin.setFixedWidth(100)
        interval_layout.addWidget(self.min_interval_spin)

        self.min_interval_random_check = QCheckBox("区间随机")
        self.min_interval_random_check.setStyleSheet("color: #d0d0d0; font-size: 12px;")
        self.min_interval_random_check.toggled.connect(self._on_min_interval_random_toggled)
        interval_layout.addWidget(self.min_interval_random_check)

        min_int_row = QHBoxLayout()
        min_int_row.addWidget(QLabel("最小:"))
        self.min_interval_min_spin = QSpinBox()
        self.min_interval_min_spin.setRange(0, 5000)
        self.min_interval_min_spin.setValue(100)
        self.min_interval_min_spin.setSuffix(" ms")
        self.min_interval_min_spin.setFixedWidth(90)
        min_int_row.addWidget(self.min_interval_min_spin)
        min_int_widget = QWidget()
        min_int_widget.setLayout(min_int_row)
        min_int_widget.setVisible(False)
        self._min_interval_min_widget = min_int_widget
        interval_layout.addWidget(min_int_widget)

        max_int_row = QHBoxLayout()
        max_int_row.addWidget(QLabel("最大:"))
        self.min_interval_max_spin = QSpinBox()
        self.min_interval_max_spin.setRange(0, 5000)
        self.min_interval_max_spin.setValue(300)
        self.min_interval_max_spin.setSuffix(" ms")
        self.min_interval_max_spin.setFixedWidth(90)
        max_int_row.addWidget(self.min_interval_max_spin)
        max_int_widget = QWidget()
        max_int_widget.setLayout(max_int_row)
        max_int_widget.setVisible(False)
        self._min_interval_max_widget = max_int_widget
        interval_layout.addWidget(max_int_widget)

        interval_layout.addStretch()
        layout.addWidget(interval_frame)

        block_frame = QFrame()
        block_frame.setStyleSheet("QFrame { background: #1e1e1e; border: 1px solid #3a3a3a; border-radius: 6px; }")
        block_layout = QVBoxLayout(block_frame)
        block_layout.setContentsMargins(12, 8, 12, 8)
        block_layout.setSpacing(8)

        block_title_row = QHBoxLayout()
        self.cb_block_actions = QCheckBox("屏蔽动作列表")
        self.cb_block_actions.setStyleSheet("color: #e8e8e8; font-size: 12px; font-weight: 500;")
        self.cb_block_actions.toggled.connect(self._on_block_actions_toggled)
        block_title_row.addWidget(self.cb_block_actions)
        block_title_row.addStretch()
        btn_add_block = QPushButton("+ 添加")
        btn_add_block.setStyleSheet("background: #2a2a2a; color: #6b8cff; border: none; border-radius: 4px; padding: 4px 12px; font-size: 11px;")
        btn_add_block.setCursor(Qt.PointingHandCursor)
        btn_add_block.clicked.connect(lambda: self._add_block_action())
        self._btn_add_block = btn_add_block
        block_title_row.addWidget(btn_add_block)
        block_layout.addLayout(block_title_row)

        self.block_scroll = QScrollArea()
        self.block_scroll.setWidgetResizable(True)
        self.block_scroll.setFrameShape(QScrollArea.NoFrame)
        self.block_scroll.setMaximumHeight(120)
        block_scroll_content = QWidget()
        self._block_flow_layout = QVBoxLayout(block_scroll_content)
        self._block_flow_layout.setContentsMargins(0, 0, 0, 0)
        self._block_flow_layout.setSpacing(6)
        self._block_flow_layout.addStretch()
        self.block_scroll.setWidget(block_scroll_content)
        block_layout.addWidget(self.block_scroll)

        self._block_action_widgets = []
        layout.addWidget(block_frame)

        io_row = QHBoxLayout()
        io_row.addStretch()
        btn_import = QPushButton("导入 JSON")
        btn_import.setStyleSheet("background: #1e1e1e; color: #6b8cff; border: 1px solid #3a3a3a; border-radius: 6px; padding: 6px 16px; font-size: 12px;")
        btn_import.clicked.connect(self._on_import_tasks)
        io_row.addWidget(btn_import)
        btn_export = QPushButton("导出 JSON")
        btn_export.setStyleSheet("background: #1e1e1e; color: #6b8cff; border: 1px solid #3a3a3a; border-radius: 6px; padding: 6px 16px; font-size: 12px;")
        btn_export.clicked.connect(self._on_export_tasks)
        io_row.addWidget(btn_export)
        layout.addLayout(io_row)

    def _populate_key_combo(self, combo: QComboBox):
        groups = [
            ("数字", [str(i) for i in range(10)]), ("字母", [chr(c) for c in range(0x41, 0x5B)]),
            ("方向", ["Left", "Up", "Right", "Down"]),
            ("控制", ["Space", "Enter", "Tab", "Esc", "Shift", "Ctrl", "Alt"]),
            ("功能", [f"F{i}" for i in range(1, 13)]),
        ]
        for group_name, keys in groups:
            combo.addItem(f"── {group_name} ──", "")
            for key in keys: combo.addItem(key, key)

    def _get_selected_task(self) -> Task | None:
        if self._task_queue is None: return None
        if 0 <= self._selected_task_index < len(self._task_queue.tasks):
            return self._task_queue.tasks[self._selected_task_index]
        return None

    def _refresh_task_list(self):
        prev_index = self._selected_task_index
        self.task_list.clear()
        if self._task_queue is None:
            self._selected_task_index = -1
            self.event_list.clear()
            return
        for i, task in enumerate(self._task_queue.tasks):
            item = QListWidgetItem()
            widget = _TaskItemWidget(task, i, self.task_list, self)
            self.task_list.addItem(item)
            self.task_list.setItemWidget(item, widget)
            item.setSizeHint(widget.sizeHint())
        if self._task_queue.tasks:
            if 0 <= prev_index < len(self._task_queue.tasks):
                self.task_list.setCurrentRow(prev_index)
            else:
                self.task_list.setCurrentRow(0)
        else:
            self._selected_task_index = -1
            self.event_list.clear()

    def _on_task_selected(self, row: int):
        if row < 0 or self._task_queue is None or row >= len(self._task_queue.tasks):
            self._selected_task_index = -1
            self.event_list.clear()
            return
        if row == self._selected_task_index: return
        self._selected_task_index = row
        task = self._task_queue.tasks[row]
        self.event_list.refresh_events(task)
        self.repeat_spin.setValue(task.repeat)

    def _on_add_task(self):
        if self._task_queue is None: self._task_queue = TaskQueue.create_default()
        task = Task(name=f"任务 {len(self._task_queue.tasks) + 1}")
        self._task_queue.tasks.append(task)
        self._refresh_task_list()
        self.task_list.setCurrentRow(len(self._task_queue.tasks) - 1)

    def _on_del_task(self):
        if self._task_queue is None: return
        idx = self.task_list.currentRow()
        if idx < 0 or idx >= len(self._task_queue.tasks): return
        reply = QMessageBox.question(self, "确认", f"删除任务 '{self._task_queue.tasks[idx].name}'？")
        if reply == QMessageBox.Yes:
            self._task_queue.tasks.pop(idx)
            self._refresh_task_list()
            if self._task_queue.tasks:
                new_idx = min(idx, len(self._task_queue.tasks) - 1)
                self.task_list.setCurrentRow(new_idx)

    def _on_rename_task(self):
        task = self._get_selected_task()
        if not task: return
        new_name, ok = QInputDialog.getText(self, "重命名", "任务名称:", text=task.name)
        if ok and new_name.strip():
            task.name = new_name.strip()
            self._refresh_task_list()
            self.task_list.setCurrentRow(self._selected_task_index)

    def _on_repeat_changed(self, value: int):
        task = self._get_selected_task()
        if task:
            task.repeat = value
            self._refresh_task_list()
            self.task_list.setCurrentRow(self._selected_task_index)

    def _on_import_tasks(self):
        from PyQt5.QtWidgets import QFileDialog
        file_path, _ = QFileDialog.getOpenFileName(self, "导入任务配置", "", "JSON 文件 (*.json)")
        if not file_path: return
        try:
            self._task_queue = TaskQueue.load(file_path)
            self._selected_task_index = 0 if self._task_queue.tasks else -1
            self._refresh_task_list()
            self._sync_interval_to_ui()
            self._refresh_block_actions()
            if self._selected_task_index >= 0:
                self.task_list.setCurrentRow(self._selected_task_index)
            QMessageBox.information(self, "导入成功", f"任务配置已从 {file_path} 导入")
        except Exception as e:
            QMessageBox.critical(self, "导入失败", f"导入任务配置失败: {e}")

    def _on_export_tasks(self):
        from PyQt5.QtWidgets import QFileDialog
        if self._task_queue is None:
            QMessageBox.warning(self, "提示", "当前没有任务可导出")
            return
        self._sync_interval_to_queue()
        self._collect_block_actions()
        file_path, _ = QFileDialog.getSaveFileName(self, "导出任务配置", "TaskConfig.json", "JSON 文件 (*.json)")
        if not file_path: return
        try:
            self._task_queue.save(file_path)
            QMessageBox.information(self, "导出成功", f"任务配置已导出至 {file_path}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", f"导出任务配置失败: {e}")

    def _on_min_interval_random_toggled(self, checked: bool):
        self.min_interval_spin.setVisible(not checked)
        self._min_interval_min_widget.setVisible(checked)
        self._min_interval_max_widget.setVisible(checked)
        if checked:
            if self.min_interval_max_spin.value() < self.min_interval_min_spin.value():
                self.min_interval_max_spin.setValue(self.min_interval_min_spin.value())

    def _sync_interval_to_ui(self):
        if self._task_queue is None: return
        self.min_interval_spin.setValue(self._task_queue.min_action_interval)
        self.min_interval_random_check.setChecked(self._task_queue.min_action_interval_random)
        self.min_interval_min_spin.setValue(self._task_queue.min_action_interval_min)
        self.min_interval_max_spin.setValue(self._task_queue.min_action_interval_max)

    def _sync_interval_to_queue(self):
        if self._task_queue is None: return
        self._task_queue.min_action_interval = self.min_interval_spin.value()
        self._task_queue.min_action_interval_random = self.min_interval_random_check.isChecked()
        self._task_queue.min_action_interval_min = self.min_interval_min_spin.value()
        self._task_queue.min_action_interval_max = self.min_interval_max_spin.value()

    def _on_block_actions_toggled(self, checked: bool):
        self._btn_add_block.setEnabled(checked)
        self.block_scroll.setEnabled(checked)
        if self._task_queue: self._task_queue.block_actions_enabled = checked

    def _add_block_action(self, key: str = "Space", action_type: str = "keyclick"):
        if self._task_queue is None: return
        widget = BlockActionItemWidget(key=key, action_type=action_type, parent=self, index=len(self._block_action_widgets))
        self._block_flow_layout.insertWidget(self._block_flow_layout.count() - 1, widget)
        self._block_action_widgets.append(widget)

    def _remove_block_action(self, index: int):
        if index < 0 or index >= len(self._block_action_widgets): return
        widget = self._block_action_widgets.pop(index)
        widget.setParent(None)
        widget.deleteLater()
        for i, w in enumerate(self._block_action_widgets): w.index = i

    def _refresh_block_actions(self):
        for widget in self._block_action_widgets:
            widget.setParent(None)
            widget.deleteLater()
        self._block_action_widgets.clear()

        if self._task_queue is None:
            self.cb_block_actions.setChecked(False)
            self._btn_add_block.setEnabled(False)
            self.block_scroll.setEnabled(False)
            return

        self.cb_block_actions.setChecked(self._task_queue.block_actions_enabled)
        self._btn_add_block.setEnabled(self._task_queue.block_actions_enabled)
        self.block_scroll.setEnabled(self._task_queue.block_actions_enabled)

        for blocked in self._task_queue.blocked_actions:
            parts = blocked.split(":", 1)
            if len(parts) == 2: self._add_block_action(key=parts[0], action_type=parts[1])
            else: self._add_block_action(key=blocked, action_type="keyclick")

    def _collect_block_actions(self):
        if self._task_queue is None: return
        self._task_queue.block_actions_enabled = self.cb_block_actions.isChecked()
        result = []
        for widget in self._block_action_widgets:
            key = widget.get_key()
            action_type = widget.get_type()
            if key: result.append(f"{key}:{action_type}")
        self._task_queue.blocked_actions = result

    def _on_wait_random_toggled(self, checked: bool):
        self.block_wait_spin.setVisible(not checked)
        self._wait_min_widget.setVisible(checked)
        self._wait_max_widget.setVisible(checked)
        if checked:
            if self.block_wait_max_spin.value() < self.block_wait_min_spin.value():
                self.block_wait_max_spin.setValue(self.block_wait_min_spin.value())

    def _on_add_wait_event(self):
        task = self._get_selected_task()
        if not task:
            QMessageBox.warning(self, "提示", "请先选择或添加一个任务")
            return
        if self.wait_random_check.isChecked():
            min_ms = self.block_wait_min_spin.value()
            max_ms = self.block_wait_max_spin.value()
            if min_ms > max_ms: min_ms, max_ms = max_ms, min_ms
            event = TaskEvent(type="wait_random", min_ms=min_ms, max_ms=max_ms)
        else:
            event = TaskEvent(type="wait", ms=self.block_wait_spin.value())
        current_row = self.event_list.currentRow()
        if current_row >= 0 and current_row < len(task.events):
            task.events.insert(current_row + 1, event)
        else:
            task.events.append(event)
        self.event_list.refresh_events(task)

    def _add_event(self, event_type: str):
        task = self._get_selected_task()
        if not task:
            QMessageBox.warning(self, "提示", "请先选择或添加一个任务")
            return
        if event_type in ("keydown", "keyup", "keyclick"):
            key = self.block_key_combo.currentData()
            if not key:
                QMessageBox.warning(self, "提示", "请先选择一个按键")
                return
            event = TaskEvent(type=event_type, key=key)
        elif event_type == "wait":
            event = TaskEvent(type="wait", ms=self.block_wait_spin.value())
        else: return
        current_row = self.event_list.currentRow()
        if current_row >= 0 and current_row < len(task.events):
            task.events.insert(current_row + 1, event)
        else:
            task.events.append(event)
        self.event_list.refresh_events(task)

    def on_frame(self, data) -> None:
        if self._preview_widget is None or data is None: return
        try: pil_img, _monsters, _items = data
        except (TypeError, ValueError): return
        if pil_img.mode != "RGB": pil_img = pil_img.convert("RGB")
        data_bytes = pil_img.tobytes("raw", "RGB")
        qimg = QImage(data_bytes, pil_img.width, pil_img.height, pil_img.width * 3, QImage.Format_RGB888)
        self._last_frame = qimg.copy()
        self._preview_widget.set_image(self._last_frame)

    def _on_preview_start(self):
        if self._preview_widget is None: return
        if self.worker is not None and self.worker.isRunning():
            self._preview_widget.set_error("Bot 已在运行中，预览自动由脚本驱动")
            return
        hwnd = self._get_target_hwnd()
        if not hwnd:
            self._preview_widget.set_error("未找到游戏窗口，请在「设置」中配置窗口标题")
            return
        if win32gui.IsIconic(hwnd):
            import time
            win32gui.ShowWindow(hwnd, 9)
            time.sleep(0.3)
        self._preview_hwnd = hwnd
        self._preview_capturing = True
        self._preview_start_btn.setEnabled(False)
        self._preview_stop_btn.setEnabled(True)
        fps = max(1, self._preview_fps_spin.value())
        self._preview_timer.start(int(1000 / fps))

    def _on_preview_stop(self):
        self._preview_capturing = False
        self._preview_timer.stop()
        self._preview_start_btn.setEnabled(True)
        self._preview_stop_btn.setEnabled(False)

    def _on_preview_fps_changed(self, value: int):
        if self._preview_timer.isActive():
            self._preview_timer.setInterval(int(1000 / max(1, value)))

    def _on_preview_tick(self):
        if not self._preview_capturing or self._preview_widget is None: return
        hwnd = getattr(self, '_preview_hwnd', 0)
        if not hwnd or win32gui.IsIconic(hwnd): return
        method_name = self._capture_method_combo.currentText()
        method = _CAPTURE_METHODS.get(method_name, _capture_getdc)
        try:
            img = method(hwnd)
            if img.size == (1, 1): return
            if img.mode != "RGB": img = img.convert("RGB")
            data_bytes = img.tobytes("raw", "RGB")
            qimg = QImage(data_bytes, img.width, img.height, img.width * 3, QImage.Format_RGB888)
            self._preview_widget.set_image(qimg.copy())
        except Exception:
            pass

    def _get_target_hwnd(self) -> int:
        title = self.title_edit.text().strip() or "QQ三国"
        selected_hwnd = self.cmb_window_select.currentData()
        if selected_hwnd and selected_hwnd != 0: return selected_hwnd
        try:
            from window import get_hwnd
            return get_hwnd(title)
        except Exception:
            return 0

    def _refresh_window_list(self) -> None:
        title_keyword = self.title_edit.text().strip()
        try:
            from window import list_windows
            windows = list_windows(title_keyword)
        except Exception:
            windows = []
        current_hwnd = self.cmb_window_select.currentData()
        self.cmb_window_select.blockSignals(True)
        self.cmb_window_select.clear()
        if not windows:
            self.cmb_window_select.addItem("未找到匹配窗口", 0)
        else:
            for hwnd, title in windows:
                self.cmb_window_select.addItem(f"{title} [{hwnd}]", hwnd)
        if current_hwnd and current_hwnd != 0:
            idx = self.cmb_window_select.findData(current_hwnd)
            if idx >= 0: self.cmb_window_select.setCurrentIndex(idx)
        self.cmb_window_select.blockSignals(False)

    def _on_window_title_changed(self, _text: str) -> None:
        self._refresh_window_list()

    def _populate_form(self) -> None:
        self.title_edit.setText(self.config.window_title)
        self._refresh_window_list()
        self.cmb_input_mode.setCurrentText(self.config.input_mode)
        self.debug_check.setChecked(self.config.debug)

        self.dpi_scale_check.blockSignals(True)
        self.dpi_scale_check.setChecked(self.config.auto_dpi_scale)
        self.dpi_scale_check.blockSignals(False)

        self.hotkey_checkbox.setChecked(self.config.hotkey_enabled)
        self.hotkey_combo.setCurrentText(self.config.hotkey_toggle.upper())
        if self.config.hotkey_enabled: self._setup_hotkey()

    def _load_task_queue_config(self) -> None:
        from task_queue import TASK_QUEUE_CONFIG_PATH
        try:
            if os.path.exists(TASK_QUEUE_CONFIG_PATH):
                self._task_queue = TaskQueue.load(TASK_QUEUE_CONFIG_PATH)
                self._refresh_task_list()
                self._sync_interval_to_ui()
                self._refresh_block_actions()
        except Exception as e:
            logging.getLogger(__name__).warning("自动加载任务队列配置失败: %s", e)

    def _collect_config(self) -> BotConfig | None:
        try:
            return BotConfig(
                enable_key_loop=True, enable_pickup=True,
                window_title=self.title_edit.text().strip() or "QQ三国",
                attack_keys=list(self.config.attack_keys),
                pickup_key=self.config.pickup_key,
                loop_delay_min=self.config.loop_delay_min,
                loop_delay_max=self.config.loop_delay_max,
                attack_delay_min=self.config.attack_delay_min,
                attack_delay_max=self.config.attack_delay_max,
                attack_rounds=self.config.attack_rounds,
                debug=self.debug_check.isChecked(),
                input_mode=self.cmb_input_mode.currentText(),
                execution_mode="task_queue",
                auto_dpi_scale=self.dpi_scale_check.isChecked(),
                hotkey_enabled=self.hotkey_checkbox.isChecked(),
                hotkey_toggle=self.hotkey_combo.currentText().lower(),
            )
        except ValueError as e:
            QMessageBox.warning(self, "配置错误", str(e))
            return None

    def _populate_hotkey_combo(self, combo: QComboBox) -> None:
        groups = [
            ("功能键", [f"F{i}" for i in range(1, 13)]), ("数字键", [str(i) for i in range(10)]),
            ("字母键", [chr(c) for c in range(0x41, 0x5B)]),
            ("控制键", ["Space", "Enter", "Esc", "Tab", "Backspace"]),
            ("方向键", ["Left", "Up", "Right", "Down"]),
        ]
        for group_name, keys in groups:
            combo.addItem(f"── {group_name} ──", "")
            for key in keys: combo.addItem(key, key)

    def _setup_hotkey(self) -> None:
        if not _HAS_KEYBOARD: return
        hotkey = self.hotkey_combo.currentText().lower()
        if not hotkey: return
        self._hotkey_mgr.set_hotkey(hotkey)
        if self._hotkey_mgr.is_hooked and not self._hotkey_signal_connected:
            self._hotkey_mgr.hotkey_triggered.connect(self._on_hotkey_triggered)
            self._hotkey_signal_connected = True

    def _on_hotkey_toggled(self, checked: bool) -> None:
        if checked:
            self._setup_hotkey()
            self.hotkey_combo.setEnabled(True)
        else:
            self._hotkey_mgr.unhook()
            self.hotkey_combo.setEnabled(False)

    def _on_hotkey_changed(self, text: str) -> None:
        if text and self.hotkey_checkbox.isChecked(): self._setup_hotkey()

    def _on_hotkey_triggered(self) -> None:
        if self.worker is None: self.on_start()
        else: self.on_stop()

    def _on_debug_toggled(self, checked: bool) -> None:
        if self.worker is not None and self.worker.isRunning():
            self.worker.set_log_level(logging.DEBUG if checked else logging.INFO)

    def _on_dpi_scale_toggled(self, checked: bool) -> None:
        self.config.auto_dpi_scale = checked
        new_config = self._collect_config()
        if new_config is not None:
            new_config.save()
            self.config.apply_from(new_config)

        ret = QMessageBox.question(
            self, "需要重启", "自适应屏幕缩放设置需要重启程序才能生效。\n\n是否立即重启？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
        )
        if ret == QMessageBox.Yes: self._restart_app()

    def _restart_app(self):
        if self.worker is not None and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(3000)
            self.worker = None
        self._hotkey_mgr.unhook()
        params = " ".join([f'"{arg}"' for arg in sys.argv])
        ctypes.windll.shell32.ShellExecuteW(None, "open", sys.executable, f'"{sys.argv[0]}"', None, 1)
        QApplication.instance().quit()

    def on_start(self) -> None:
        new_config = self._collect_config()
        if new_config is None: return
        self.config.apply_from(new_config)
        self.config.save()

        selected_hwnd = self.cmb_window_select.currentData()
        if selected_hwnd and selected_hwnd != 0: self.config._target_hwnd = selected_hwnd
        else: self.config._target_hwnd = 0

        if self._task_queue is None: self._task_queue = TaskQueue.create_default()
        self._sync_interval_to_queue()
        self._collect_block_actions()

        self.worker = BotWorker(self.config, task_queue=self._task_queue)
        self.worker.log_signal.connect(self.on_log)
        self.worker.status_signal.connect(self.on_status)
        self.worker.frame_signal.connect(self.on_frame)
        self.worker.start()

        if self.debug_check.isChecked(): self.worker.set_log_level(logging.DEBUG)
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.apply_btn.setEnabled(True)
        self._preview_start_btn.setEnabled(False)
        self._preview_stop_btn.setEnabled(False)
        self._set_status("运行中", "#4ade80")

    def on_stop(self) -> None:
        if self.worker is not None:
            self.worker.stop()
            self.worker.wait(3000)
            self.worker = None
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.apply_btn.setEnabled(False)
        self._preview_start_btn.setEnabled(True)
        self._preview_stop_btn.setEnabled(False)
        self._preview_capturing = False
        self._preview_timer.stop()
        self._set_status("已停止", "#666666")

    def on_apply(self) -> None:
        if self.worker is None: return
        new_config = self._collect_config()
        if new_config is None: return
        self.worker.apply_config(new_config)

    def on_save(self) -> None:
        new_config = self._collect_config()
        if new_config is None: return
        new_config.save()
        self.config.apply_from(new_config)

        saved_files = ["config.json"]
        if self._task_queue is not None:
            from task_queue import TASK_QUEUE_CONFIG_PATH
            try:
                self._sync_interval_to_queue()
                self._collect_block_actions()
                self._task_queue.save(TASK_QUEUE_CONFIG_PATH)
                saved_files.append("TaskConfig.json")
            except Exception as e:
                logging.getLogger(__name__).warning("保存任务队列配置失败: %s", e)
        QMessageBox.information(self, "保存成功", f"配置已保存至 {', '.join(saved_files)}")

    def on_log(self, message: str, level: str) -> None:
        if not self.debug_check.isChecked() and level == "DEBUG": return
        color = LEVEL_COLORS.get(level, "#e0e0e0")
        safe_msg = message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        self.log_text.append(f'<span style="color:{color};">{safe_msg}</span>')
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.log_text.setTextCursor(cursor)

    def on_status(self, status: str) -> None:
        if status == "运行中": self._set_status("运行中", "#4ade80")
        elif status == "已停止":
            self._set_status("已停止", "#666666")
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.apply_btn.setEnabled(False)
        elif status == "配置已热更新": self._set_status("运行中 (已更新)", "#6b8cff")

    def _set_status(self, text: str, color: str) -> None:
        self.status_dot.setStyleSheet(f"color: {color}; font-size: 18px;")
        self.status_label.setText(text)

    def nativeEvent(self, eventType, message):
        if eventType == b"windows_generic_MSG":
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == WM_NCCALCSIZE and msg.wParam: return True, 0
            elif msg.message == WM_NCHITTEST:
                result = self._handle_nchittest()
                if result is not None: return True, result
        return super().nativeEvent(eventType, message)

    def _handle_nchittest(self):
        pos = QCursor.pos()
        window_rect = self.frameGeometry()
        local_x, local_y = pos.x() - window_rect.left(), pos.y() - window_rect.top()
        w, h = window_rect.width(), window_rect.height()
        if local_x < 0 or local_y < 0 or local_x > w or local_y > h: return None

        bw = BORDER_WIDTH
        left, right = local_x <= bw, local_x >= w - bw
        top, bottom = local_y <= bw, local_y >= h - bw

        if top and left: return HTTOPLEFT
        if top and right: return HTTOPRIGHT
        if bottom and left: return HTBOTTOMLEFT
        if bottom and right: return HTBOTTOMRIGHT
        if top: return HTTOP
        if bottom: return HTBOTTOM
        if left: return HTLEFT
        if right: return HTRIGHT

        if local_y <= 36:
            btn_min_left = w - 4 - 36 * 3
            if local_x >= btn_min_left: return HTCLIENT
            return HTCAPTION
        return None

    def closeEvent(self, event) -> None:
        if self.worker is not None and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(3000)
            self.worker = None
        self._hotkey_mgr.unhook()
        event.accept()

def _is_admin() -> bool:
    try: return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception: return False

def main() -> None:
    from config import BotConfig
    cfg = BotConfig.load()

    # 高级兼容逻辑（确保用户勾选自适应缩放时起作用）
    if cfg.auto_dpi_scale:
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)

    if not _is_admin():
        ret = QMessageBox.question(
            None, "需要管理员权限",
            "pydirectinput 需要管理员权限才能向游戏窗口发送按键。\n\n是否以管理员身份重新运行？\n（选择「否」将以普通权限运行，按键可能无效）",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
        )
        if ret == QMessageBox.Yes:
            params = " ".join([f'"{arg}"' for arg in sys.argv])
            ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)
            sys.exit(0)

    app.setStyleSheet(STYLE_SHEET)
    font = QFont("Microsoft YaHei UI", 9)
    app.setFont(font)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()