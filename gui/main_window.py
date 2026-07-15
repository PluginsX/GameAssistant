"""主窗口。

PyQt5 深色游戏工具风格主窗口，集成配置编辑、脚本启停控制、
运行时热更新和实时日志显示。

新版布局（五大区）：
┌──────────────────────────────────────────────┐
│ 标题栏  菜单 文件 | 视图 | 设置 | 帮助        │
├──────────────────────────────────────────────┤
│ 控制栏  启动 停止 应用 保存 ... 状态指示灯    │
├──────────────────┬───────────┬───────────────┤
│  串行 | 并行      │ 事件列表   │ 属性栏        │
│  ┌──────────────┐ │          │ 任务名 重复    │
│  │ 任务列表      │ │          │ 间隔 屏蔽     │
│  ├──────────────┤ │          │ 导入/导出     │
│  │ 动作库        │ │          │               │
│  │ 按键 按下/松开│ │          │               │
│  │ 等待...      │ │          │               │
│  └──────────────┘ │          │               │
├──────────────────┴───────────┴───────────────┤
│ 状态栏  日志信息...                           │
└──────────────────────────────────────────────┘
"""

import ctypes
import ctypes.wintypes
import logging
import os
import sys
import time

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import (
    QCursor, QFont, QImage, QTextCursor,
)
from PyQt5.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDoubleSpinBox,
    QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
    QPushButton, QScrollArea, QSpinBox, QSplitter, QStackedWidget,
    QTextEdit, QVBoxLayout, QWidget, QInputDialog, QToolButton,
    QTabWidget, QSizePolicy,
)

import win32gui
import win32ui
import win32con
import win32api

from PIL import Image

from gameassistant.config import BotConfig
from gameassistant.models.tasks import Task, TaskEvent, TaskQueue, TASK_QUEUE_CONFIG_PATH
from gameassistant.worker.qt_worker import BotWorker

from gui.utils.dpi import dpi_unaware_context, is_admin
from gui.utils.theme import (
    STYLE_SHEET, LEVEL_COLORS, BORDER_WIDTH, GWL_STYLE,
    WM_NCCALCSIZE, WM_NCHITTEST,
    HTCAPTION, HTCLIENT, HTTOP, HTTOPLEFT, HTTOPRIGHT,
    HTLEFT, HTRIGHT, HTBOTTOM, HTBOTTOMLEFT, HTBOTTOMRIGHT,
    WS_THICKFRAME, WS_MINIMIZEBOX, WS_MAXIMIZEBOX,
)
from gui.utils.hotkey import HotkeyManager, has_keyboard
from gui.widgets.preview import PreviewWidget
from gui.widgets.collapsible import CollapsibleSection
from gui.widgets.capture import CAPTURE_METHODS, capture_getdc
from gui.widgets.task_editor import (
    EventListWidget, TaskItemWidget, BlockActionItemWidget,
    _populate_key_combo, populate_hotkey_combo,
)
from gui.resources.icons import (
    ICON_SIZE,
    build_minimize_icon,
    build_maximize_icon,
    build_restore_icon,
    build_close_icon,
)

logger = logging.getLogger(__name__)

# ── 样式常量 ──────────────────────────────────────────────────
_TAB_STYLE = """
QTabWidget::pane { border: 1px solid #3a3a3a; border-radius: 4px; background: #1e1e1e; }
QTabBar::tab { background: #2a2a2a; color: #a0a0a0; padding: 4px 14px;
               border: 1px solid #3a3a3a; border-bottom: none; border-radius: 4px 4px 0 0;
               margin-right: 2px; font-size: 12px; font-weight: 500; }
QTabBar::tab:selected { background: #1e1e1e; color: #6b8cff; border-bottom: 2px solid #6b8cff; }
QTabBar::tab:hover:!selected { background: #333; color: #d0d0d0; }
"""
_SECTION_TITLE_STYLE = "color: #6b8cff; font-size: 12px; font-weight: 600; padding: 2px 0;"
_SUB_TITLE_STYLE = "color: #888888; font-size: 11px;"


class MainWindow(QMainWindow):
    """辅助机器人主窗口（新版 5 区布局）。"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("辅助机器人")
        self.resize(1100, 780)
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowSystemMenuHint
            | Qt.WindowMinMaxButtonsHint
        )

        self._drag_pos = None
        self._style_applied = False

        # ── 数据 ──────────────────────────────────────────────
        self.config = BotConfig.load()
        self.worker: BotWorker | None = None
        self._preview_widget: PreviewWidget | None = None
        self._last_frame: QImage | None = None
        self._preview_timer = QTimer(self)
        self._preview_timer.timeout.connect(self._on_preview_tick)
        self._preview_capturing = False
        self._preview_hwnd = 0

        self._task_queue: TaskQueue | None = None
        self._selected_type: str = "sequential"
        self._selected_seq_index: int = -1
        self._selected_ind_index: int = -1
        self._hotkey_mgr = HotkeyManager()
        self._hotkey_signal_connected = False

        # ── 旧代码兼容控件（占位，不显示在 UI 中） ──────────────
        self.debug_check = QCheckBox()
        self.debug_check.setChecked(self.config.debug)
        self.dpi_scale_check = QCheckBox()
        self.dpi_scale_check.setChecked(self.config.auto_dpi_scale)
        self._preview_start_btn = QPushButton()
        self._preview_stop_btn = QPushButton()
        self._preview_fps_spin = QSpinBox()
        self._preview_fps_spin.setRange(1, 60)
        self._preview_fps_spin.setValue(30)
        self._capture_method_combo = QComboBox()

        # ── 根布局：5 大区纵向排列 ─────────────────────────────
        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # 区 1：标题栏
        self._title_bar, self._max_btn = self._build_title_bar()
        root_layout.addWidget(self._title_bar)

        # 区 2：控制栏
        control_frame = self._build_control_bar()
        root_layout.addWidget(control_frame)

        # 区 3：中央三栏（水平分割）
        central_splitter = self._build_central_splitter()
        root_layout.addWidget(central_splitter, 1)

        # 区 4：状态栏（带日志）
        status_bar = self._build_status_bar()
        root_layout.addWidget(status_bar)

        # ── 初始化 ────────────────────────────────────────────
        self._populate_form()
        self._load_task_queue_config()

    # ═══════════════════════════════════════════════════════════
    # 构建：标题栏（区 1）
    # ═══════════════════════════════════════════════════════════

    def _build_title_bar(self):
        title_bar = QWidget()
        title_bar.setObjectName("titleBar")
        title_bar.setFixedHeight(36)
        title_bar.setStyleSheet(
            "QWidget#titleBar { background: #0d0d0d; "
            "border-bottom: 1px solid #2a2a2a; }"
        )
        layout = QHBoxLayout(title_bar)
        layout.setContentsMargins(12, 0, 4, 0)
        layout.setSpacing(0)

        # 标题
        title_label = QLabel("辅助机器人")
        title_label.setObjectName("titleBarLabel")
        title_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        title_label.setStyleSheet(
            "QLabel#titleBarLabel { color: #e0e0e0; font-size: 13px; "
            "font-weight: 500; background: transparent; }"
        )
        layout.addWidget(title_label)
        layout.addSpacing(16)

        # ── 菜单 ──────────────────────────────────────────────
        menu_btn_style = (
            "QPushButton { background: transparent; color: #a0a0a0; border: none; "
            "padding: 4px 10px; font-size: 12px; } "
            "QPushButton:hover { color: #ffffff; background: #2a2a2a; border-radius: 4px; }"
        )

        menus = [
            ("文件", ["保存配置", "导入任务", "导出任务", "─", "退出"]),
            ("视图", ["画面预览", "调试日志", "─", "重置布局"]),
            ("设置", ["窗口设置", "快捷键", "自适应缩放", "─", "重启程序"]),
            ("帮助", ["关于", "使用说明"]),
        ]
        for label, items in menus:
            btn = QPushButton(label)
            btn.setStyleSheet(menu_btn_style)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFocusPolicy(Qt.NoFocus)
            btn.clicked.connect(lambda checked, m=label, it=items: self._on_menu_click(m, it))
            layout.addWidget(btn)

        layout.addStretch()

        btn_size = 36
        # 最小化
        min_btn = QPushButton()
        min_btn.setObjectName("titleBtnMin")
        min_btn.setFixedSize(btn_size, btn_size)
        min_btn.setCursor(Qt.PointingHandCursor)
        min_btn.setFocusPolicy(Qt.NoFocus)
        min_btn.setIcon(build_minimize_icon())
        min_btn.setIconSize(ICON_SIZE)
        min_btn.setFlat(True)
        min_btn.setStyleSheet(
            "QPushButton#titleBtnMin { background: transparent; border: none; } "
            "QPushButton#titleBtnMin:hover { background: #2a2a2a; } "
            "QPushButton#titleBtnMin:pressed { background: #3a3a3a; }"
        )
        min_btn.clicked.connect(self.showMinimized)
        layout.addWidget(min_btn)

        # 最大化/还原
        self._icon_maximize = build_maximize_icon()
        self._icon_restore = build_restore_icon()
        max_btn = QPushButton()
        max_btn.setObjectName("titleBtnMax")
        max_btn.setFixedSize(btn_size, btn_size)
        max_btn.setCursor(Qt.PointingHandCursor)
        max_btn.setFocusPolicy(Qt.NoFocus)
        max_btn.setIcon(self._icon_maximize)
        max_btn.setIconSize(ICON_SIZE)
        max_btn.setFlat(True)
        max_btn.setStyleSheet(
            "QPushButton#titleBtnMax { background: transparent; border: none; } "
            "QPushButton#titleBtnMax:hover { background: #2a2a2a; } "
            "QPushButton#titleBtnMax:pressed { background: #3a3a3a; }"
        )
        max_btn.clicked.connect(self._title_toggle_maximize)
        layout.addWidget(max_btn)

        # 关闭
        close_btn = QPushButton()
        close_btn.setObjectName("titleBtnClose")
        close_btn.setFixedSize(btn_size, btn_size)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setFocusPolicy(Qt.NoFocus)
        close_btn.setIcon(build_close_icon())
        close_btn.setIconSize(ICON_SIZE)
        close_btn.setFlat(True)
        close_btn.setStyleSheet(
            "QPushButton#titleBtnClose { background: transparent; border: none; } "
            "QPushButton#titleBtnClose:hover { background: #e81123; } "
            "QPushButton#titleBtnClose:pressed { background: #c4101f; }"
        )
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)

        return title_bar, max_btn

    def _on_menu_click(self, label: str, items: list[str]):
        if label == "文件":
            action = items[0] if items else ""
            if action == "保存配置":
                self.on_save()
            elif action == "导入任务":
                self._on_import_tasks()
            elif action == "导出任务":
                self._on_export_tasks()
            elif action == "退出":
                self.close()
        elif label == "视图":
            action = items[0] if items else ""
            if action == "画面预览":
                self._toggle_preview()
            elif action == "调试日志":
                self._toggle_debug_log()
            elif action == "重置布局":
                self._reset_layout()
        elif label == "设置":
            action = items[0] if items else ""
            if action == "窗口设置":
                self._open_settings_dialog()
            elif action == "快捷键":
                self._open_hotkey_dialog()
            elif action == "自适应缩放":
                self._on_dpi_scale_toggled(not self.config.auto_dpi_scale)
            elif action == "重启程序":
                self._restart_app()
        elif label == "帮助":
            action = items[0] if items else ""
            if action == "关于":
                QMessageBox.about(self, "关于辅助机器人",
                    "GameAssistant v2.0.0\n\nQQ三国游戏辅助程序\n"
                    "支持按键循环 + 任务队列模式")

    def _title_toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def _sync_max_button(self):
        if self.isMaximized():
            self._max_btn.setIcon(self._icon_restore)
        else:
            self._max_btn.setIcon(self._icon_maximize)

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

    def nativeEvent(self, event_type, message):
        """处理 Windows 原生消息，实现无边框窗口拖拽/缩放/去白边。"""
        try:
            msg = ctypes.wintypes.MSG.from_address(message.__int__())

            if msg.message == WM_NCCALCSIZE:
                # 客户区=整个窗口，消除系统标题栏/边框保留区
                return True, 0

            if msg.message == WM_NCHITTEST:
                # lParam 低位=鼠标X，高位=鼠标Y（屏幕坐标，有符号16位）
                lparam = msg.lParam
                x = ctypes.c_int16(lparam & 0xFFFF).value
                y = ctypes.c_int16((lparam >> 16) & 0xFFFF).value

                from PyQt5.QtCore import QPoint
                local_pos = self.mapFromGlobal(QPoint(x, y))

                # 边缘缩放检测
                rect = self.rect()
                b = BORDER_WIDTH
                l = local_pos.x() < b
                r = local_pos.x() > rect.width() - b
                t = local_pos.y() < b
                bot = local_pos.y() > rect.height() - b

                if t and l:     return True, HTTOPLEFT
                if t and r:     return True, HTTOPRIGHT
                if bot and l:   return True, HTBOTTOMLEFT
                if bot and r:   return True, HTBOTTOMRIGHT
                if t:           return True, HTTOP
                if bot:         return True, HTBOTTOM
                if l:           return True, HTLEFT
                if r:           return True, HTRIGHT

                # 标题栏拖拽（标题栏+边缘b像素高度，方便从顶部边框区域拖拽）
                if hasattr(self, '_title_bar') and self._title_bar:
                    tb = self._title_bar
                    tb_rect = tb.geometry()
                    tb_rect.setHeight(tb_rect.height() + b)
                    if tb_rect.contains(local_pos):
                        # 排除可交互子控件（按钮、下拉框等），否则它们无法点击
                        tb_local = tb.mapFromGlobal(QPoint(x, y))
                        for child in tb.children():
                            if isinstance(child, (QPushButton, QComboBox)):
                                if child.geometry().contains(tb_local) and child.isEnabled():
                                    return True, HTCLIENT
                        return True, HTCAPTION

                return True, HTCLIENT
        except Exception:
            pass
        return super().nativeEvent(event_type, message)

    # ═══════════════════════════════════════════════════════════
    # 构建：控制栏（区 2）
    # ═══════════════════════════════════════════════════════════

    def _build_control_bar(self):
        frame = QFrame()
        frame.setObjectName("controlBar")
        frame.setStyleSheet(
            "QFrame#controlBar { background: #1a1a1a; border-bottom: 1px solid #2a2a2a; }"
        )
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(8)

        btn_style = (
            "QPushButton { background: #2a2a2a; color: #e0e0e0; border: 1px solid #3a3a3a; "
            "border-radius: 6px; padding: 5px 16px; font-size: 12px; font-weight: 600; } "
            "QPushButton:hover { background: #3a3a3a; border-color: #6b8cff; } "
            "QPushButton:disabled { color: #555; background: #1a1a1a; border-color: #2a2a2a; }"
        )

        self.start_btn = QPushButton("▶ 启动")
        self.start_btn.setObjectName("startBtn")
        self.start_btn.setStyleSheet(btn_style.replace("#2a2a2a", "#1a4a1a").replace("#3a3a3a", "#2a6a2a"))
        self.start_btn.clicked.connect(self.on_start)

        self.stop_btn = QPushButton("■ 停止")
        self.stop_btn.setObjectName("stopBtn")
        self.stop_btn.setStyleSheet(btn_style.replace("#2a2a2a", "#4a1a1a").replace("#3a3a3a", "#6a2a2a"))
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.on_stop)

        self.apply_btn = QPushButton("↻ 应用")
        self.apply_btn.setObjectName("applyBtn")
        self.apply_btn.setStyleSheet(btn_style)
        self.apply_btn.setEnabled(False)
        self.apply_btn.clicked.connect(self.on_apply)

        self.save_btn = QPushButton("💾 保存")
        self.save_btn.setStyleSheet(btn_style)
        self.save_btn.clicked.connect(self.on_save)

        layout.addWidget(self.start_btn)
        layout.addWidget(self.stop_btn)
        layout.addWidget(self.apply_btn)
        layout.addWidget(self.save_btn)

        # 分隔线
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet("color: #3a3a3a;")
        layout.addWidget(sep)

        # 窗口选择按钮
        self._window_title = "QQ三国"
        self.title_btn = QPushButton(" QQ三国")
        self.title_btn.setFixedWidth(140)
        self.title_btn.setCursor(Qt.PointingHandCursor)
        self.title_btn.setStyleSheet(
            "QPushButton { background: #2a2a2a; color: #e0e0e0; border: 1px solid #3a3a3a; "
            "border-radius: 4px; padding: 3px 8px; font-size: 11px; text-align: left; } "
            "QPushButton:hover { background: #3a3a3a; border-color: #6b8cff; }"
        )
        self.title_btn.clicked.connect(self._show_window_picker)
        self._window_picker_dialog = None
        layout.addWidget(QLabel("窗口:"))
        layout.addWidget(self.title_btn)

        # 输入模式
        self.cmb_input_mode = QComboBox()
        self.cmb_input_mode.addItems(["foreground", "postmsg", "focus"])
        self.cmb_input_mode.setFixedWidth(85)
        self.cmb_input_mode.setStyleSheet(
            "QComboBox { background: #2a2a2a; color: #e0e0e0; border: 1px solid #3a3a3a; "
            "border-radius: 4px; padding: 2px 4px; font-size: 11px; }"
        )
        layout.addWidget(QLabel("模式:"))
        layout.addWidget(self.cmb_input_mode)

        # 热键
        self.hotkey_checkbox = QCheckBox("快捷键")
        self.hotkey_checkbox.setChecked(True)
        self.hotkey_checkbox.setStyleSheet("color: #c0c0c0; font-size: 12px;")
        self.hotkey_checkbox.toggled.connect(self._on_hotkey_toggled)
        layout.addWidget(self.hotkey_checkbox)

        self.hotkey_combo = QComboBox()
        populate_hotkey_combo(self.hotkey_combo)
        self.hotkey_combo.setFixedWidth(90)
        self.hotkey_combo.setToolTip("切换启动/停止")
        self.hotkey_combo.currentTextChanged.connect(self._on_hotkey_changed)
        layout.addWidget(self.hotkey_combo)

        layout.addStretch()

        # 状态指示
        self.status_dot = QLabel("●")
        self.status_dot.setFixedWidth(16)
        self.status_dot.setStyleSheet("color: #444; font-size: 16px;")
        self.status_label = QLabel("未运行")
        self.status_label.setStyleSheet("color: #808080; font-size: 12px;")
        layout.addWidget(self.status_dot)
        layout.addWidget(self.status_label)

        return frame

    # ═══════════════════════════════════════════════════════════
    # 构建：中央三栏（区 3）
    # ═══════════════════════════════════════════════════════════

    def _build_central_splitter(self):
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(3)
        splitter.setStyleSheet(
            "QSplitter::handle { background: #2a2a2a; } "
            "QSplitter::handle:hover { background: #6b8cff; }"
        )

        left_panel = self._build_left_panel()
        center_panel = self._build_center_panel()
        right_panel = self._build_right_panel()

        splitter.addWidget(left_panel)
        splitter.addWidget(center_panel)
        splitter.addWidget(right_panel)

        total = 400
        splitter.setSizes([int(total * 0.25), int(total * 0.5), int(total * 0.25)])
        return splitter

    # ── 左栏 ──────────────────────────────────────────────────

    def _build_left_panel(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(6, 6, 3, 6)
        layout.setSpacing(6)

        # ── 上半：任务列表（Tab 页签） ─────────────────────────
        self._task_tab = QTabWidget()
        self._task_tab.setStyleSheet(_TAB_STYLE)

        # 串行任务页
        seq_page = QWidget()
        seq_layout = QVBoxLayout(seq_page)
        seq_layout.setContentsMargins(4, 4, 4, 4)
        seq_layout.setSpacing(4)
        seq_header = QHBoxLayout()
        seq_header.setSpacing(4)
        btn_add_seq = QPushButton("+")
        btn_add_seq.setFixedWidth(22)
        btn_add_seq.setStyleSheet(
            "QPushButton { background: #1a3a1a; color: #4ade80; border: 1px solid #2a5a2a; "
            "border-radius: 4px; font-size: 14px; font-weight: 700; } "
            "QPushButton:hover { background: #2a5a2a; }"
        )
        btn_add_seq.clicked.connect(lambda: self._on_add_task("sequential"))
        seq_header.addWidget(btn_add_seq)
        btn_del_seq = QPushButton("×")
        btn_del_seq.setFixedWidth(22)
        btn_del_seq.setStyleSheet(
            "QPushButton { background: #3a1a1a; color: #ef4444; border: 1px solid #5a2a2a; "
            "border-radius: 4px; font-size: 14px; font-weight: 700; } "
            "QPushButton:hover { background: #5a2a2a; }"
        )
        btn_del_seq.clicked.connect(self._on_del_task)
        seq_header.addWidget(btn_del_seq)
        btn_rename_seq = QPushButton("✎")
        btn_rename_seq.setFixedWidth(22)
        btn_rename_seq.setToolTip("重命名")
        btn_rename_seq.setStyleSheet(
            "QPushButton { background: #2a2a2a; color: #d0d0d0; border: 1px solid #3a3a3a; "
            "border-radius: 4px; font-size: 13px; font-weight: 700; } "
            "QPushButton:hover { background: #3a3a3a; }"
        )
        btn_rename_seq.clicked.connect(self._on_rename_task)
        seq_header.addWidget(btn_rename_seq)
        seq_header.addStretch()
        seq_layout.addLayout(seq_header)

        self.seq_task_list = QListWidget()
        self.seq_task_list.setSelectionMode(QListWidget.SingleSelection)
        self.seq_task_list.setStyleSheet(
            "QListWidget { background: #1e1e1e; border: 1px solid #3a3a3a; border-radius: 4px; } "
            "QListWidget::item { border-radius: 4px; } "
            "QListWidget::item:selected { background: #2a3a6a; }"
        )
        self.seq_task_list.currentRowChanged.connect(
            lambda r: self._on_list_selected(r, "sequential")
        )
        seq_layout.addWidget(self.seq_task_list, 1)
        self._task_tab.addTab(seq_page, "串行任务")

        # 并行任务页
        ind_page = QWidget()
        ind_layout = QVBoxLayout(ind_page)
        ind_layout.setContentsMargins(4, 4, 4, 4)
        ind_layout.setSpacing(4)
        ind_header = QHBoxLayout()
        ind_header.setSpacing(4)
        btn_add_ind = QPushButton("+")
        btn_add_ind.setFixedWidth(22)
        btn_add_ind.setStyleSheet(
            "QPushButton { background: #1a3a1a; color: #4ade80; border: 1px solid #2a5a2a; "
            "border-radius: 4px; font-size: 14px; font-weight: 700; } "
            "QPushButton:hover { background: #2a5a2a; }"
        )
        btn_add_ind.clicked.connect(lambda: self._on_add_task("independent"))
        ind_header.addWidget(btn_add_ind)
        btn_del_ind = QPushButton("×")
        btn_del_ind.setFixedWidth(22)
        btn_del_ind.setStyleSheet(
            "QPushButton { background: #3a1a1a; color: #ef4444; border: 1px solid #5a2a2a; "
            "border-radius: 4px; font-size: 14px; font-weight: 700; } "
            "QPushButton:hover { background: #5a2a2a; }"
        )
        btn_del_ind.clicked.connect(self._on_del_task)
        ind_header.addWidget(btn_del_ind)
        btn_rename_ind = QPushButton("✎")
        btn_rename_ind.setFixedWidth(22)
        btn_rename_ind.setToolTip("重命名")
        btn_rename_ind.setStyleSheet(
            "QPushButton { background: #2a2a2a; color: #d0d0d0; border: 1px solid #3a3a3a; "
            "border-radius: 4px; font-size: 13px; font-weight: 700; } "
            "QPushButton:hover { background: #3a3a3a; }"
        )
        btn_rename_ind.clicked.connect(self._on_rename_task)
        ind_header.addWidget(btn_rename_ind)
        ind_header.addStretch()
        ind_layout.addLayout(ind_header)

        self.ind_task_list = QListWidget()
        self.ind_task_list.setSelectionMode(QListWidget.SingleSelection)
        self.ind_task_list.setStyleSheet(
            "QListWidget { background: #1e1e1e; border: 1px solid #3a3a3a; border-radius: 4px; } "
            "QListWidget::item { border-radius: 4px; } "
            "QListWidget::item:selected { background: #2a3a6a; }"
        )
        self.ind_task_list.currentRowChanged.connect(
            lambda r: self._on_list_selected(r, "independent")
        )
        ind_layout.addWidget(self.ind_task_list, 1)
        self._task_tab.addTab(ind_page, "并行任务")

        self._task_tab.currentChanged.connect(self._on_task_tab_changed)

        layout.addWidget(self._task_tab)

        # ── 下半：动作库（可折叠分类） ─────────────────────────
        bricks_label = QLabel("■ 动作库")
        bricks_label.setStyleSheet(_SECTION_TITLE_STYLE)
        layout.addWidget(bricks_label)

        # 按键触发
        self._sec_key = CollapsibleSection("按键触发", expanded=False)
        key_btn = QPushButton("✚ 按键触发")
        key_btn.setStyleSheet(
            "QPushButton { background: #2a3a6a; color: #e0e0e0; border: 1px solid #3a4a7a; "
            "border-radius: 4px; padding: 6px 12px; font-size: 12px; font-weight: 600; "
            "text-align: left; } "
            "QPushButton:hover { background: #3a4a8a; border-color: #6b8cff; }"
        )
        key_btn.setCursor(Qt.PointingHandCursor)
        key_btn.clicked.connect(lambda: self._add_action("keyclick"))
        self._sec_key.addWidget(key_btn)
        layout.addWidget(self._sec_key)

        # 流程控制
        self._sec_flow = CollapsibleSection("流程控制", expanded=False)
        wait_btn = QPushButton("⏱ 等待")
        wait_btn.setStyleSheet(
            "QPushButton { background: #3a2a1a; color: #e0e0e0; border: 1px solid #5a4a2a; "
            "border-radius: 4px; padding: 6px 12px; font-size: 12px; font-weight: 600; "
            "text-align: left; } "
            "QPushButton:hover { background: #4a3a2a; border-color: #f59e0b; }"
        )
        wait_btn.setCursor(Qt.PointingHandCursor)
        wait_btn.clicked.connect(lambda: self._add_action("wait"))
        self._sec_flow.addWidget(wait_btn)
        layout.addWidget(self._sec_flow)

        layout.addStretch()
        return widget

    def _add_action(self, action_type: str):
        """从动作库添加一个默认动作到当前任务的选中事件之后。"""
        if action_type == "keyclick":
            event = TaskEvent(type="keyclick", keys=["A"])
        elif action_type == "wait":
            event = TaskEvent(type="wait", ms=500)
        else:
            return

        tab = self._task_tab.currentIndex()
        task_type = "sequential" if tab == 0 else "independent"
        lst = self.seq_task_list if tab == 0 else self.ind_task_list
        tasks = self._tasks_of_type(task_type)
        task_row = lst.currentRow()
        if task_row < 0 or task_row >= len(tasks):
            return
        task = tasks[task_row]

        # 插入到选中事件之后，没选则追加到末尾
        sel_row = self.event_list.currentRow()
        if 0 <= sel_row < len(task.events):
            task.events.insert(sel_row + 1, event)
        else:
            task.events.append(event)

        self.event_list.refresh_events(task)
        # 选中新插入的事件
        insert_idx = sel_row + 1 if 0 <= sel_row < len(task.events) - 1 else len(task.events) - 1
        self.event_list.setCurrentRow(insert_idx) 

    # ═══════════════════════════════════════════════════════════
    # 按钮动作
    # ═══════════════════════════════════════════════════════════

    def on_start(self):
        """启动挂机脚本。"""
        if self.worker is not None and self.worker.isRunning():
            return

        # 保存当前配置
        self.on_save()

        # 根据执行模式创建 TaskQueue
        task_queue = None
        if self.config.execution_mode == "task_queue":
            task_queue = self._task_queue

        self.worker = BotWorker(self.config, task_queue=task_queue)

        # 连接信号
        self.worker.log_signal.connect(self._on_worker_log)
        self.worker.status_signal.connect(self._on_worker_status)

        self.worker.start()

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.apply_btn.setEnabled(True)
        self.status_label.setText("运行中")
        self.status_dot.setStyleSheet("color: #4ade80; font-size: 16px;")

    def on_stop(self):
        """停止挂机脚本。"""
        if self.worker is not None and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(5000)

        self.worker = None
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.apply_btn.setEnabled(False)
        self.status_label.setText("已停止")
        self.status_dot.setStyleSheet("color: #ef4444; font-size: 16px;")

    def on_apply(self):
        """热更新配置到运行中的 worker。"""
        if self.worker is not None and self.worker.isRunning():
            # 从表单收集最新值
            new_config = self._collect_form_config()
            self.worker.apply_config(new_config)
            self._status_log.setText("配置已热更新")
        else:
            self._status_log.setText("脚本未运行，无需应用")

    def on_save(self):
        """保存当前配置到文件。"""
        new_config = self._collect_form_config()
        new_config.save()
        self.config.apply_from(new_config)
        # 同时持久化 TaskQueue 配置（间隔/屏蔽等）
        self._save_task_queue_config()
        self._status_log.setText("配置已保存")

    def _save_task_queue_config(self):
        """将间隔/屏蔽等 UI 值同步到 TaskQueue 并持久化。"""
        if self._task_queue is not None:
            self._task_queue.min_action_interval = self.min_interval_spin.value()
            self._task_queue.min_action_interval_random = self.min_interval_random_check.isChecked()
            self._task_queue.min_action_interval_min = self.min_interval_min_spin.value()
            self._task_queue.min_action_interval_max = self.min_interval_max_spin.value()
            self._task_queue.block_actions_enabled = self.cb_block_actions.isChecked()
            blocked = []
            for w in self._block_action_widgets:
                k = w.get_key()
                t = w.get_type()
                if k:
                    blocked.append(f"{k}:{t}")
            self._task_queue.blocked_actions = blocked
            try:
                self._task_queue.save(TASK_QUEUE_CONFIG_PATH)
            except Exception as e:
                logger.warning("保存任务配置失败: %s", e)

    def _collect_form_config(self) -> BotConfig:
        """从 UI 表单收集当前值，返回新的 BotConfig 对象。"""
        c = BotConfig()
        c.window_title = self._window_title
        c.input_mode = self.cmb_input_mode.currentText()
        c.execution_mode = "task_queue"  # 当前仅 task_queue 模式
        c.hotkey_enabled = self.hotkey_checkbox.isChecked()
        c.hotkey_toggle = self.hotkey_combo.currentText().lower()
        c.auto_dpi_scale = self.dpi_scale_check.isChecked()
        c.debug = self.debug_check.isChecked()
        return c

    # ═══════════════════════════════════════════════════════════
    # Worker 信号处理
    # ═══════════════════════════════════════════════════════════

    def _on_worker_log(self, message: str, level: str):
        """处理 worker 发来的日志消息。"""
        self._status_log.setText(message)
        if hasattr(self, "log_text") and self.log_text.isVisible():
            self.log_text.append(message)

    def _on_worker_status(self, status: str):
        """处理 worker 发来的状态变化。"""
        self.status_label.setText(status)
        if "运行" in status:
            self.status_dot.setStyleSheet("color: #4ade80; font-size: 16px;")
        else:
            self.status_dot.setStyleSheet("color: #ef4444; font-size: 16px;")
        if status == "已停止":
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.apply_btn.setEnabled(False)

    # ═══════════════════════════════════════════════════════════
    # 任务管理
    # ═══════════════════════════════════════════════════════════

    def _tasks_of_type(self, task_type: str) -> list:
        """从 TaskQueue 的 flat tasks 列表中筛选指定类型的任务。"""
        if self._task_queue is None:
            return []
        return [t for t in self._task_queue.tasks if t.task_type == task_type]

    def _on_add_task(self, task_type: str):
        """添加新任务。"""
        if self._task_queue is None:
            self._task_queue = TaskQueue()

        count = len(self._tasks_of_type(task_type))
        name = f"{'串行' if task_type == 'sequential' else '并行'}任务 {count + 1}"
        self._task_queue.tasks.append(Task(name=name, task_type=task_type))
        self._refresh_task_lists()
        self._select_last_task(task_type)

    def _on_del_task(self):
        """删除选中的任务。"""
        if self._task_queue is None:
            return
        tab = self._task_tab.currentIndex()
        task_type = "sequential" if tab == 0 else "independent"
        lst = self.seq_task_list if tab == 0 else self.ind_task_list
        row = lst.currentRow()
        if row < 0:
            return
        same_type_indices = [
            i for i, t in enumerate(self._task_queue.tasks)
            if t.task_type == task_type
        ]
        if row < len(same_type_indices):
            idx = same_type_indices[row]
            self._task_queue.tasks.pop(idx)
        self._refresh_task_lists()
        self._update_event_list()

    def _on_rename_task(self):
        """重命名选中的任务。"""
        if self._task_queue is None:
            return
        tab = self._task_tab.currentIndex()
        task_type = "sequential" if tab == 0 else "independent"
        lst = self.seq_task_list if tab == 0 else self.ind_task_list
        tasks = self._tasks_of_type(task_type)
        row = lst.currentRow()
        if row < 0 or row >= len(tasks):
            return
        old_name = tasks[row].name
        new_name, ok = QInputDialog.getText(self, "重命名", "任务名称:", text=old_name)
        if ok and new_name.strip():
            tasks[row].name = new_name.strip()
            self._refresh_task_lists()
            self._update_event_list()

    def _on_list_selected(self, row: int, task_type: str):
        """任务列表选择变化。"""
        if row < 0 or self._task_queue is None:
            self._show_task_properties()
            return
        tasks = self._tasks_of_type(task_type)
        if row < len(tasks):
            task = tasks[row]
            # 右侧切换到任务属性
            self._show_task_properties()
            # 更新属性面板
            self._task_type_combo.blockSignals(True)
            idx = self._task_type_combo.findData(task.task_type)
            if idx >= 0:
                self._task_type_combo.setCurrentIndex(idx)
            self._task_type_combo.blockSignals(False)
            self.repeat_spin.blockSignals(True)
            self.repeat_spin.setValue(task.repeat)
            self.repeat_spin.blockSignals(False)
            # 刷新事件列表
            self.event_list.refresh_events(task)

    def _on_task_tab_changed(self, index: int):
        """任务 Tab 切换。"""
        self._show_task_properties()
        self._update_event_list()

    def _on_event_selected(self, row: int):
        """事件列表选中变化。"""
        if row < 0 or self._task_queue is None:
            self._show_task_properties()
            return
        # 获取当前选中的任务
        tab = self._task_tab.currentIndex()
        task_type = "sequential" if tab == 0 else "independent"
        lst = self.seq_task_list if tab == 0 else self.ind_task_list
        tasks = self._tasks_of_type(task_type)
        task_row = lst.currentRow()
        if 0 <= task_row < len(tasks) and row < len(tasks[task_row].events):
            event = tasks[task_row].events[row]
            self._show_event_properties(event)
        else:
            self._show_task_properties()

    def _update_event_list(self):
        """根据当前选中的任务刷新事件列表。"""
        if self._task_queue is None:
            self.event_list.refresh_events(None)
            return
        tab = self._task_tab.currentIndex()
        task_type = "sequential" if tab == 0 else "independent"
        lst = self.seq_task_list if tab == 0 else self.ind_task_list
        tasks = self._tasks_of_type(task_type)
        row = lst.currentRow()
        if 0 <= row < len(tasks):
            self.event_list.refresh_events(tasks[row])
        else:
            self.event_list.refresh_events(None)

    def _refresh_task_lists(self):
        """刷新两侧任务列表 UI。"""
        seq = self._tasks_of_type("sequential")
        ind = self._tasks_of_type("independent")
        self._refresh_list(self.seq_task_list, seq, "sequential")
        self._refresh_list(self.ind_task_list, ind, "independent")

    def _refresh_list(self, list_widget: QListWidget, tasks: list, task_type: str):
        """刷新单个任务列表。"""
        list_widget.blockSignals(True)
        list_widget.clear()
        for i, task in enumerate(tasks):
            item = QListWidgetItem()
            widget = TaskItemWidget(task, i, list_widget, self, task_type)
            item.setSizeHint(widget.sizeHint())
            list_widget.addItem(item)
            list_widget.setItemWidget(item, widget)
        list_widget.blockSignals(False)

    def _select_last_task(self, task_type: str):
        """选中最后一个任务。"""
        if task_type == "sequential":
            lst = self.seq_task_list
        else:
            lst = self.ind_task_list
        count = lst.count()
        if count > 0:
            lst.setCurrentRow(count - 1)

    def _get_selected_task(self):
        """获取当前在事件列表中选中的 Task 对象（供 EventListWidget 调用）。"""
        tab = self._task_tab.currentIndex()
        task_type = "sequential" if tab == 0 else "independent"
        lst = self.seq_task_list if tab == 0 else self.ind_task_list
        tasks = self._tasks_of_type(task_type)
        row = lst.currentRow()
        if 0 <= row < len(tasks):
            return tasks[row]
        return None

    def _on_task_type_changed(self, index: int):
        """任务类型切换：同步迁移任务到对应列表。"""
        if self._task_queue is None:
            return
        tab = self._task_tab.currentIndex()
        task_type = "sequential" if tab == 0 else "independent"
        lst = self.seq_task_list if tab == 0 else self.ind_task_list
        tasks = self._tasks_of_type(task_type)
        row = lst.currentRow()
        if row < 0 or row >= len(tasks):
            return
        task = tasks[row]
        new_type = self._task_type_combo.currentData()
        if task.task_type == new_type:
            return  # 没变
        # 从 flat tasks 中找到实际对象并修改类型
        flat_idx = self._task_queue.tasks.index(task)
        self._task_queue.tasks[flat_idx].task_type = new_type
        # 刷新列表并切换到目标页签
        self._refresh_task_lists()
        target_tab = 0 if new_type == "sequential" else 1
        self._task_tab.setCurrentIndex(target_tab)
        # 选中刚迁移的任务
        target_lst = self.seq_task_list if target_tab == 0 else self.ind_task_list
        target_lst.setCurrentRow(target_lst.count() - 1)

    def _on_repeat_changed(self, value: int):
        """重复次数变化。"""
        if self._task_queue is None:
            return
        tab = self._task_tab.currentIndex()
        task_type = "sequential" if tab == 0 else "independent"
        lst = self.seq_task_list if tab == 0 else self.ind_task_list
        tasks = self._tasks_of_type(task_type)
        row = lst.currentRow()
        if 0 <= row < len(tasks):
            tasks[row].repeat = value

    # ═══════════════════════════════════════════════════════════
    # 对话框
    # ═══════════════════════════════════════════════════════════

    def _open_settings_dialog(self):
        """打开设置对话框（占位）。"""
        QMessageBox.information(self, "设置", "设置对话框（待实现）")

    def _open_hotkey_dialog(self):
        """打开快捷键设置对话框（占位）。"""
        QMessageBox.information(self, "快捷键", "快捷键设置（待实现）")

    def _on_dpi_scale_toggled(self, checked: bool):
        """DPI 自适应缩放开关。"""
        self.config.auto_dpi_scale = checked
        self.config.save()
        if checked:
            QMessageBox.information(
                self, "自适应缩放",
                "下次启动程序时生效。\n"
                "请重启程序以应用缩放设置。"
            )

    def _restart_app(self):
        """重启程序。"""
        QApplication.quit()
        # 使用 QProcess 重启
        from PyQt5.QtCore import QProcess
        QProcess.startDetached(sys.executable, sys.argv)

    # ═══════════════════════════════════════════════════════════
    # 导入 / 导出
    # ═══════════════════════════════════════════════════════════

    def _on_import_tasks(self):
        """从文件导入任务配置。"""
        from PyQt5.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, "导入任务", "", "JSON 文件 (*.json)"
        )
        if not path:
            return
        try:
            q = TaskQueue.load(path)
            if q is not None:
                self._task_queue = q
                self._refresh_task_lists()
                self._update_event_list()
                self._status_log.setText(f"已导入: {path}")
        except Exception as e:
            QMessageBox.warning(self, "导入失败", f"无法导入任务配置:\n{e}")

    def _on_export_tasks(self):
        """导出任务配置到文件。"""
        from PyQt5.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(
            self, "导出任务", "tasks.json", "JSON 文件 (*.json)"
        )
        if not path:
            return
        try:
            if self._task_queue is not None:
                self._task_queue.save(path)
                self._status_log.setText(f"已导出: {path}")
        except Exception as e:
            QMessageBox.warning(self, "导出失败", f"无法导出任务配置:\n{e}")

    # ═══════════════════════════════════════════════════════════
    # 表单初始化
    # ═══════════════════════════════════════════════════════════

    def _populate_form(self):
        """从 config 填充 UI 表单字段。"""
        self._window_title = self.config.window_title
        self.title_btn.setText(f" {self._window_title}")

        # 输入模式
        idx = self.cmb_input_mode.findText(self.config.input_mode)
        if idx >= 0:
            self.cmb_input_mode.setCurrentIndex(idx)

        # 快捷键
        self.hotkey_checkbox.setChecked(self.config.hotkey_enabled)
        hk = self.config.hotkey_toggle.capitalize()
        idx = self.hotkey_combo.findText(hk, Qt.MatchFixedString)
        if idx >= 0:
            self.hotkey_combo.setCurrentIndex(idx)

        self.debug_check.setChecked(self.config.debug)
        self.dpi_scale_check.setChecked(self.config.auto_dpi_scale)

        # 间隔（来自 TaskQueue）
        if self._task_queue is not None:
            self.min_interval_spin.setValue(self._task_queue.min_action_interval)
            self.min_interval_random_check.setChecked(self._task_queue.min_action_interval_random)
            self.min_interval_min_spin.setValue(self._task_queue.min_action_interval_min)
            self.min_interval_max_spin.setValue(self._task_queue.min_action_interval_max)
            self.cb_block_actions.setChecked(self._task_queue.block_actions_enabled)

    def _load_task_queue_config(self):
        """从文件加载任务队列配置。"""
        try:
            q = TaskQueue.load(TASK_QUEUE_CONFIG_PATH)
            if q is not None:
                self._task_queue = q
            else:
                self._task_queue = TaskQueue()
        except Exception:
            self._task_queue = TaskQueue()
        self._refresh_task_lists()

    # ═══════════════════════════════════════════════════════════
    # 热键
    # ═══════════════════════════════════════════════════════════

    def _on_hotkey_toggled(self, checked: bool):
        """全局热键开关。"""
        self.config.hotkey_enabled = checked
        self.hotkey_combo.setEnabled(checked)
        if checked:
            if not self._hotkey_signal_connected:
                self._hotkey_mgr.hotkey_triggered.connect(self._on_hotkey_triggered)
                self._hotkey_signal_connected = True
            self._hotkey_mgr.set_hotkey(self.config.hotkey_toggle)
        else:
            self._hotkey_mgr.unhook()

    def _on_hotkey_changed(self, text: str):
        """热键选择变化。"""
        if not text:
            return
        self.config.hotkey_toggle = text.lower()
        if self.hotkey_checkbox.isChecked():
            self._hotkey_mgr.set_hotkey(self.config.hotkey_toggle)

    def _on_hotkey_triggered(self):
        """热键触发：切换启动/停止。"""
        if self.worker is not None and self.worker.isRunning():
            self.on_stop()
        else:
            self.on_start()

    # ═══════════════════════════════════════════════════════════
    # 其他设置
    # ═══════════════════════════════════════════════════════════

    def _on_min_interval_random_toggled(self, checked: bool):
        """最小动作间隔随机开关。"""
        self._min_interval_min_widget.setVisible(checked)
        self._min_interval_max_widget.setVisible(checked)

    def _on_block_actions_toggled(self, checked: bool):
        """屏蔽动作开关。"""
        self._btn_add_block.setEnabled(checked)
        self.block_scroll.setVisible(checked)

    def _add_block_action(self):
        """添加一个屏蔽动作条目。"""
        w = BlockActionItemWidget()
        self._block_flow_layout.insertWidget(
            self._block_flow_layout.count() - 1, w
        )
        self._block_action_widgets.append(w)

    # ── 中栏 ──────────────────────────────────────────────────

    def _build_center_panel(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(3, 6, 3, 6)
        layout.setSpacing(4)

        header = QLabel("■ 动作列表")
        header.setStyleSheet(_SECTION_TITLE_STYLE)
        layout.addWidget(header)

        self.event_list = EventListWidget(self)
        self.event_list.currentRowChanged.connect(self._on_event_selected)
        layout.addWidget(self.event_list, 1)
        return widget

    # ── 右栏 ──────────────────────────────────────────────────

    def _build_right_panel(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")

        self._right_stack = QStackedWidget()
        self._right_stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._right_stack.setMinimumWidth(0)

        # ── Page 0: 任务属性 ────────────────────────────────
        task_page = QWidget()
        task_layout = QVBoxLayout(task_page)
        task_layout.setContentsMargins(3, 6, 6, 6)
        task_layout.setSpacing(8)

        prop_label = QLabel("■ 属性")
        prop_label.setStyleSheet(_SECTION_TITLE_STYLE)
        task_layout.addWidget(prop_label)

        prop_frame = QFrame()
        prop_frame.setStyleSheet(
            "QFrame { background: #1a1a1a; border: 1px solid #3a3a3a; border-radius: 6px; }"
        )
        prop_layout = QVBoxLayout(prop_frame)
        prop_layout.setContentsMargins(8, 8, 8, 8)
        prop_layout.setSpacing(6)

        type_row = QFormLayout()
        type_row.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self._task_type_combo = QComboBox()
        self._task_type_combo.addItem("串行", "sequential")
        self._task_type_combo.addItem("独立", "independent")
        self._task_type_combo.currentIndexChanged.connect(self._on_task_type_changed)
        type_row.addRow("类型:", self._task_type_combo)
        prop_layout.addLayout(type_row)

        repeat_row = QFormLayout()
        repeat_row.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.repeat_spin = QSpinBox()
        self.repeat_spin.setRange(1, 999)
        self.repeat_spin.valueChanged.connect(self._on_repeat_changed)
        repeat_row.addRow("重复:", self.repeat_spin)
        prop_layout.addLayout(repeat_row)

        task_layout.addWidget(prop_frame)

        # 最小动作间隔
        interval_label = QLabel("■ 最小动作间隔")
        interval_label.setStyleSheet(_SECTION_TITLE_STYLE)
        task_layout.addWidget(interval_label)

        interval_frame = QFrame()
        interval_frame.setStyleSheet(
            "QFrame { background: #1a1a1a; border: 1px solid #3a3a3a; border-radius: 6px; }"
        )
        interval_layout = QVBoxLayout(interval_frame)
        interval_layout.setContentsMargins(8, 8, 8, 8)
        interval_layout.setSpacing(6)

        self.min_interval_spin = QSpinBox()
        self.min_interval_spin.setRange(0, 5000)
        self.min_interval_spin.setValue(200)
        self.min_interval_spin.setSuffix(" ms")
        interval_layout.addWidget(self.min_interval_spin)

        self.min_interval_random_check = QCheckBox("区间随机")
        self.min_interval_random_check.setStyleSheet("color: #c0c0c0; font-size: 11px;")
        self.min_interval_random_check.toggled.connect(self._on_min_interval_random_toggled)
        interval_layout.addWidget(self.min_interval_random_check)

        min_int_row = QHBoxLayout()
        min_int_row.addWidget(QLabel("最小:"))
        self.min_interval_min_spin = QSpinBox()
        self.min_interval_min_spin.setRange(0, 5000)
        self.min_interval_min_spin.setValue(100)
        self.min_interval_min_spin.setSuffix(" ms")
        min_int_row.addWidget(self.min_interval_min_spin)
        self._min_interval_min_widget = QWidget()
        self._min_interval_min_widget.setLayout(min_int_row)
        self._min_interval_min_widget.setVisible(False)
        interval_layout.addWidget(self._min_interval_min_widget)

        max_int_row = QHBoxLayout()
        max_int_row.addWidget(QLabel("最大:"))
        self.min_interval_max_spin = QSpinBox()
        self.min_interval_max_spin.setRange(0, 5000)
        self.min_interval_max_spin.setValue(300)
        self.min_interval_max_spin.setSuffix(" ms")
        max_int_row.addWidget(self.min_interval_max_spin)
        self._min_interval_max_widget = QWidget()
        self._min_interval_max_widget.setLayout(max_int_row)
        self._min_interval_max_widget.setVisible(False)
        interval_layout.addWidget(self._min_interval_max_widget)

        task_layout.addWidget(interval_frame)

        # 屏蔽动作
        block_label = QLabel("■ 屏蔽动作")
        block_label.setStyleSheet(_SECTION_TITLE_STYLE)
        task_layout.addWidget(block_label)

        block_frame = QFrame()
        block_frame.setStyleSheet(
            "QFrame { background: #1a1a1a; border: 1px solid #3a3a3a; border-radius: 6px; }"
        )
        block_layout = QVBoxLayout(block_frame)
        block_layout.setContentsMargins(8, 8, 8, 8)
        block_layout.setSpacing(4)

        self.cb_block_actions = QCheckBox("启用屏蔽动作列表")
        self.cb_block_actions.setStyleSheet("color: #c0c0c0; font-size: 11px;")
        self.cb_block_actions.toggled.connect(self._on_block_actions_toggled)
        block_layout.addWidget(self.cb_block_actions)

        btn_add_block = QPushButton("+ 添加")
        btn_add_block.setStyleSheet(
            "QPushButton { background: #2a2a2a; color: #6b8cff; border: none; "
            "border-radius: 4px; padding: 3px 10px; font-size: 11px; } "
            "QPushButton:hover { background: #3a3a3a; }"
        )
        btn_add_block.setCursor(Qt.PointingHandCursor)
        btn_add_block.clicked.connect(lambda: self._add_block_action())
        self._btn_add_block = btn_add_block
        block_layout.addWidget(btn_add_block)

        self.block_scroll = QScrollArea()
        self.block_scroll.setWidgetResizable(True)
        self.block_scroll.setFrameShape(QScrollArea.NoFrame)
        self.block_scroll.setMaximumHeight(100)
        block_scroll_content = QWidget()
        self._block_flow_layout = QVBoxLayout(block_scroll_content)
        self._block_flow_layout.setContentsMargins(0, 0, 0, 0)
        self._block_flow_layout.setSpacing(4)
        self._block_flow_layout.addStretch()
        self.block_scroll.setWidget(block_scroll_content)
        block_layout.addWidget(self.block_scroll)

        self._block_action_widgets = []
        task_layout.addWidget(block_frame)

        # 导入 / 导出
        io_label = QLabel("■ 数据")
        io_label.setStyleSheet(_SECTION_TITLE_STYLE)
        task_layout.addWidget(io_label)

        io_frame = QFrame()
        io_frame.setStyleSheet(
            "QFrame { background: #1a1a1a; border: 1px solid #3a3a3a; border-radius: 6px; }"
        )
        io_layout = QHBoxLayout(io_frame)
        io_layout.setContentsMargins(8, 6, 8, 6)
        io_layout.setSpacing(6)

        btn_import = QPushButton("📥 导入")
        btn_import.setStyleSheet(
            "QPushButton { background: #2a2a2a; color: #6b8cff; border: 1px solid #3a3a3a; "
            "border-radius: 4px; padding: 4px 10px; font-size: 11px; } "
            "QPushButton:hover { background: #3a3a3a; }"
        )
        btn_import.clicked.connect(self._on_import_tasks)
        io_layout.addWidget(btn_import)

        btn_export = QPushButton("📤 导出")
        btn_export.setStyleSheet(
            "QPushButton { background: #2a2a2a; color: #6b8cff; border: 1px solid #3a3a3a; "
            "border-radius: 4px; padding: 4px 10px; font-size: 11px; } "
            "QPushButton:hover { background: #3a3a3a; }"
        )
        btn_export.clicked.connect(self._on_export_tasks)
        io_layout.addWidget(btn_export)

        io_layout.addStretch()
        task_layout.addWidget(io_frame)

        task_layout.addStretch()

        # ── Page 1: 动作属性（可编辑） ──────────────────────
        event_page = QWidget()
        event_layout = QVBoxLayout(event_page)
        event_layout.setContentsMargins(3, 6, 6, 6)
        event_layout.setSpacing(8)

        event_prop_label = QLabel("■ 动作属性")
        event_prop_label.setStyleSheet(_SECTION_TITLE_STYLE)
        event_layout.addWidget(event_prop_label)

        event_prop_frame = QFrame()
        event_prop_frame.setStyleSheet(
            "QFrame { background: #1a1a1a; border: 1px solid #3a3a3a; border-radius: 6px; }"
        )
        event_prop_layout = QFormLayout(event_prop_frame)
        event_prop_layout.setContentsMargins(8, 8, 8, 8)
        event_prop_layout.setSpacing(6)
        event_prop_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        # 事件类型
        self._event_type_combo = QComboBox()
        self._event_type_combo.addItem("↕ 单击", "keyclick")
        self._event_type_combo.addItem("↓ 按下", "keydown")
        self._event_type_combo.addItem("↑ 松开", "keyup")
        self._event_type_combo.addItem("⏱ 等待", "wait")
        self._event_type_combo.addItem("⏱ 随机等待", "wait_random")
        self._event_type_combo.currentIndexChanged.connect(self._on_event_type_changed)
        event_prop_layout.addRow("类型:", self._event_type_combo)

        # 按键编辑（用于 keydown/keyup/keyclick）
        self._event_key_widget = QWidget()
        event_key_layout = QHBoxLayout(self._event_key_widget)
        event_key_layout.setContentsMargins(0, 0, 0, 0)
        event_key_layout.setSpacing(2)
        self._event_key1 = QComboBox()
        self._event_key1.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        _populate_key_combo(self._event_key1)
        event_key_layout.addWidget(self._event_key1)
        plus1 = QLabel("+")
        plus1.setStyleSheet("color: #888; font-size: 12px; font-weight: 700; padding: 0 1px;")
        plus1.setFixedWidth(12)
        event_key_layout.addWidget(plus1)
        self._event_key2 = QComboBox()
        self._event_key2.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        _populate_key_combo(self._event_key2)
        event_key_layout.addWidget(self._event_key2)
        plus2 = QLabel("+")
        plus2.setStyleSheet("color: #888; font-size: 12px; font-weight: 700; padding: 0 1px;")
        plus2.setFixedWidth(12)
        event_key_layout.addWidget(plus2)
        self._event_key3 = QComboBox()
        self._event_key3.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        _populate_key_combo(self._event_key3)
        event_key_layout.addWidget(self._event_key3)
        event_prop_layout.addRow("按键:", self._event_key_widget)

        # 等待编辑（用于 wait/wait_random）
        self._event_wait_widget = QWidget()
        event_wait_layout = QVBoxLayout(self._event_wait_widget)
        event_wait_layout.setContentsMargins(0, 0, 0, 0)
        event_wait_layout.setSpacing(4)

        wait_single_row = QHBoxLayout()
        self._event_wait_spin = QSpinBox()
        self._event_wait_spin.setRange(10, 999999)
        self._event_wait_spin.setValue(500)
        self._event_wait_spin.setSuffix(" ms")
        wait_single_row.addWidget(self._event_wait_spin)
        wait_single_row.addStretch()
        event_wait_layout.addLayout(wait_single_row)

        wait_range_row = QHBoxLayout()
        self._event_wait_min = QSpinBox()
        self._event_wait_min.setRange(10, 999999)
        self._event_wait_min.setValue(200)
        self._event_wait_min.setSuffix(" ms")
        self._event_wait_min.setPrefix("最小 ")
        wait_range_row.addWidget(self._event_wait_min)
        self._event_wait_max = QSpinBox()
        self._event_wait_max.setRange(10, 999999)
        self._event_wait_max.setValue(500)
        self._event_wait_max.setSuffix(" ms")
        self._event_wait_max.setPrefix("最大 ")
        wait_range_row.addWidget(self._event_wait_max)
        wait_range_row.addStretch()
        self._event_wait_range_widget = QWidget()
        self._event_wait_range_widget.setLayout(wait_range_row)
        self._event_wait_range_widget.setVisible(False)
        event_wait_layout.addWidget(self._event_wait_range_widget)

        event_prop_layout.addRow("等待:", self._event_wait_widget)

        # 同步按钮
        sync_btn = QPushButton("✓ 应用修改")
        sync_btn.setStyleSheet(
            "QPushButton { background: #6b8cff; color: white; border: none; "
            "border-radius: 4px; padding: 6px 12px; font-size: 12px; font-weight: 600; }"
            "QPushButton:hover { background: #5a7cef; }"
        )
        sync_btn.clicked.connect(self._on_sync_event)
        event_prop_layout.addRow("", sync_btn)

        event_layout.addWidget(event_prop_frame)
        event_layout.addStretch()

        self._editing_event: TaskEvent | None = None

        # ── 堆叠 ───────────────────────────────────────────────
        self._right_stack.addWidget(task_page)   # index 0
        self._right_stack.addWidget(event_page)  # index 1
        self._right_stack.setCurrentIndex(0)

        scroll.setWidget(self._right_stack)
        return scroll

    def _show_task_properties(self):
        """右侧切换到任务属性面板。"""
        self._right_stack.setCurrentIndex(0)

    def _show_event_properties(self, event: TaskEvent):
        """右侧切换到动作属性面板并加载事件配置到编辑控件。"""
        if not event:
            return
        self._editing_event = event

        # 加载事件类型
        idx = self._event_type_combo.findData(event.type)
        if idx >= 0:
            self._event_type_combo.blockSignals(True)
            self._event_type_combo.setCurrentIndex(idx)
            self._event_type_combo.blockSignals(False)

        self._sync_event_type_visiblity(event.type)

        # 加载按键
        keys = event.keys if event.keys else ([event.key] if event.key else [])
        for i, combo in enumerate([self._event_key1, self._event_key2, self._event_key3]):
            if i < len(keys):
                ci = combo.findText(keys[i])
                combo.setCurrentIndex(ci if ci >= 0 else 0)
            else:
                combo.setCurrentIndex(0)

        # 加载等待
        self._event_wait_spin.setValue(event.ms if event.type == "wait" else 500)
        self._event_wait_min.setValue(event.min_ms if event.type == "wait_random" else 100)
        self._event_wait_max.setValue(event.max_ms if event.type == "wait_random" else 300)

        self._right_stack.setCurrentIndex(1)

    def _on_event_type_changed(self, index: int):
        """右侧动作类型改变，切换按键/等待控件的显隐。"""
        event_type = self._event_type_combo.currentData()
        self._sync_event_type_visiblity(event_type)
        # 如果是新插入的临时事件，自动应用类型
        if self._editing_event is not None:
            self._editing_event.type = event_type

    def _sync_event_type_visiblity(self, event_type: str):
        """根据事件类型显示/隐藏按键和等待编辑区。"""
        is_key = event_type in ("keydown", "keyup", "keyclick")
        is_wait = event_type == "wait"
        is_wait_random = event_type == "wait_random"
        self._event_key_widget.setVisible(is_key)
        self._event_wait_widget.setVisible(is_wait or is_wait_random)
        self._event_wait_spin.setVisible(is_wait)
        self._event_wait_range_widget.setVisible(is_wait_random)

    def _on_sync_event(self):
        """将右侧编辑控件的值写回到当前编辑的事件。"""
        ev = self._editing_event
        if ev is None:
            return
        ev.type = self._event_type_combo.currentData()

        if ev.type in ("keydown", "keyup", "keyclick"):
            keys = []
            for combo in [self._event_key1, self._event_key2, self._event_key3]:
                t = combo.currentText()
                if t and t != "空":
                    keys.append(t)
            ev.keys = keys
            ev.key = keys[0] if keys else ""
        elif ev.type == "wait":
            ev.ms = self._event_wait_spin.value()
        elif ev.type == "wait_random":
            ev.min_ms = self._event_wait_min.value()
            ev.max_ms = self._event_wait_max.value()

        # 刷新事件列表显示
        tab = self._task_tab.currentIndex()
        task_type = "sequential" if tab == 0 else "independent"
        lst = self.seq_task_list if tab == 0 else self.ind_task_list
        tasks = self._tasks_of_type(task_type)
        task_row = lst.currentRow()
        if 0 <= task_row < len(tasks):
            self.event_list.refresh_events(tasks[task_row])

    # ═══════════════════════════════════════════════════════════
    # 窗口搜索器
    # ═══════════════════════════════════════════════════════════

    def _show_window_picker(self):
        """弹出系统窗口搜索选择器。"""
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView
        from PyQt5.QtCore import QTimer
        from gameassistant.platform.window_win import list_windows

        if self._window_picker_dialog is not None:
            self._window_picker_dialog.close()
            self._window_picker_dialog = None

        dlg = QDialog(self)
        dlg.setWindowTitle("选择目标窗口")
        dlg.resize(420, 380)
        dlg.setStyleSheet("QDialog { background: #1e1e1e; }")
        dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # 搜索框
        search = QLineEdit()
        search.setPlaceholderText("输入关键词搜索窗口...")
        search.setStyleSheet(
            "QLineEdit { background: #2a2a2a; color: #e0e0e0; border: 1px solid #3a3a3a; "
            "border-radius: 4px; padding: 6px 10px; font-size: 12px; }"
        )
        layout.addWidget(search)

        # 表格
        table = QTableWidget(0, 2)
        table.setHorizontalHeaderLabels(["窗口名称", "PID"])
        table.horizontalHeader().setStretchLastSection(False)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setAlternatingRowColors(False)
        table.setShowGrid(False)
        table.setStyleSheet(
            "QTableWidget { background: #121212; border: 1px solid #3a3a3a; "
            "border-radius: 4px; color: #e0e0e0; font-size: 12px; } "
            "QTableWidget::item:selected { background: #2a3a6a; } "
            "QHeaderView::section { background: #1e1e1e; color: #888; "
            "border: none; padding: 4px; font-size: 11px; }"
        )
        table.verticalHeader().setVisible(False)
        layout.addWidget(table)

        def refresh_list(filter_text: str = ""):
            """获取窗口列表并填充表格。"""
            all_windows = list_windows()
            table.setRowCount(0)
            for hwnd, title in all_windows:
                if filter_text and filter_text.lower() not in title.lower():
                    continue
                row = table.rowCount()
                table.insertRow(row)
                name_item = QTableWidgetItem(title)
                name_item.setData(Qt.UserRole, hwnd)
                table.setItem(row, 0, name_item)
                pid_item = QTableWidgetItem(str(hwnd))
                pid_item.setTextAlignment(Qt.AlignCenter)
                table.setItem(row, 1, pid_item)

        refresh_list()

        # 搜索过滤（debounce 300ms）
        debounce = QTimer()
        debounce.setSingleShot(True)
        debounce.setInterval(300)

        def on_search_changed(text: str):
            debounce.start()
        debounce.timeout.connect(lambda: refresh_list(search.text()))

        search.textChanged.connect(on_search_changed)

        # 双击 / 回车选择
        def on_accept():
            row = table.currentRow()
            if row < 0:
                return
            name_item = table.item(row, 0)
            if name_item is None:
                return
            title = name_item.text()
            if title:
                self._window_title = title
                self.title_btn.setText(f" {title}")
            dlg.accept()

        table.cellDoubleClicked.connect(lambda r, c: on_accept())
        search.returnPressed.connect(lambda: on_accept() if table.currentRow() >= 0 else None)

        dlg.exec_()
        self._window_picker_dialog = None

    # ═══════════════════════════════════════════════════════════
    # 构建：状态栏（区 4）
    # ═══════════════════════════════════════════════════════════

    def _build_status_bar(self):
        bar = QFrame()
        bar.setObjectName("statusBar")
        bar.setFixedHeight(28)
        bar.setStyleSheet(
            "QFrame#statusBar { background: #0d0d0d; border-top: 1px solid #2a2a2a; }"
        )
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(6)

        self._status_log = QLineEdit()
        self._status_log.setReadOnly(True)
        self._status_log.setStyleSheet(
            "QLineEdit { background: transparent; border: none; color: #808080; "
            "font-size: 11px; }"
        )
        self._status_log.setPlaceholderText("就绪")
        layout.addWidget(self._status_log, 1)

        self._log_expand_btn = QPushButton("📋")
        self._log_expand_btn.setFixedSize(24, 24)
        self._log_expand_btn.setToolTip("展开日志面板")
        self._log_expand_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #808080; border: none; "
            "border-radius: 4px; font-size: 12px; } "
            "QPushButton:hover { background: #2a2a2a; color: #e0e0e0; }"
        )
        self._log_expand_btn.clicked.connect(self._toggle_log_panel)
        self._log_expand_btn.setCursor(Qt.PointingHandCursor)
        layout.addWidget(self._log_expand_btn)

        # 日志面板（插入到 root_layout 中 bar 之后）
        return bar

    def _build_log_panel(self):
        """构建展开式日志面板（由 _toggle_log_panel 控制显隐）。"""
        panel = QFrame()
        panel.setObjectName("logPanel")
        panel.setVisible(False)
        panel.setStyleSheet(
            "QFrame#logPanel { background: #111; border-top: 1px solid #2a2a2a; }"
        )
        log_layout = QVBoxLayout(panel)
        log_layout.setContentsMargins(0, 0, 0, 0)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(150)
        self.log_text.setMaximumHeight(300)
        self.log_text.setStyleSheet(
            "QTextEdit { background: #111; color: #c0c0c0; border: none; "
            "font-size: 11px; font-family: Consolas, monospace; }"
        )
        log_layout.addWidget(self.log_text)
        return panel

    def __init_log_panel(self, root_layout):
        """在 __init__ 中调用，将日志面板插入到状态栏之后。"""
        self._log_panel = self._build_log_panel()
        root_layout.addWidget(self._log_panel)

    def _toggle_log_panel(self):
        visible = not self._log_panel.isVisible()
        self._log_panel.setVisible(visible)

    # ═══════════════════════════════════════════════════════════
    # 预览：定时截图刷新
    # ═══════════════════════════════════════════════════════════

    def _on_preview_tick(self):
        """定时器回调：捕获窗口画面并刷新预览控件。"""
        if not self._preview_capturing:
            return

        # 获取/刷新窗口句柄
        if not self._preview_hwnd:
            title = self._window_title
            if not title:
                return
            self._preview_hwnd = win32gui.FindWindow(None, title)
            if not self._preview_hwnd:
                return

        hwnd = self._preview_hwnd
        if not win32gui.IsWindow(hwnd):
            self._preview_hwnd = 0
            if self._preview_widget:
                self._preview_widget.set_error("窗口已关闭")
            return

        try:
            # 捕获窗口客户区
            left, top, right, bottom = win32gui.GetClientRect(hwnd)
            w, h = right - left, bottom - top
            if w <= 0 or h <= 0:
                return

            hwnd_dc = win32gui.GetWindowDC(hwnd)
            mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
            save_dc = mfc_dc.CreateCompatibleDC()

            bitmap = win32ui.CreateBitmap()
            bitmap.CreateCompatibleBitmap(mfc_dc, w, h)
            save_dc.SelectObject(bitmap)

            save_dc.BitBlt((0, 0), (w, h), mfc_dc, (0, 0), win32con.SRCCOPY)

            bmp_info = bitmap.GetInfo()
            bmp_bits = bitmap.GetBitmapBits(True)
            img = Image.frombuffer(
                "RGB",
                (bmp_info["bmWidth"], bmp_info["bmHeight"]),
                bmp_bits, "raw", "BGRX", 0, 1,
            )

            save_dc.DeleteDC()
            mfc_dc.DeleteDC()
            win32gui.ReleaseDC(hwnd, hwnd_dc)
            win32gui.DeleteObject(bitmap.GetHandle())

            # 转为 QImage 并显示
            img = img.convert("RGB")
            data = img.tobytes("raw", "RGB")
            qimg = QImage(data, img.width, img.height, QImage.Format_RGB888)
            self._last_frame = qimg
            if self._preview_widget:
                self._preview_widget.set_image(qimg)

        except Exception as e:
            logger.debug("预览截图失败: %s", e)

    def _toggle_preview(self):
        """切换画面预览面板的显示。"""
        if self._preview_widget and self._preview_widget.isVisible():
            # 关闭预览
            self._preview_capturing = False
            self._preview_timer.stop()
            self._preview_widget.setVisible(False)
            # 从布局中移除
            parent_layout = self._preview_widget.parent().layout()
            if parent_layout:
                parent_layout.removeWidget(self._preview_widget)
            self._preview_widget = None
            self._preview_hwnd = 0
        else:
            # 从中央分割区左侧面板获取父容器
            splitter = self.findChild(QSplitter)
            if not splitter:
                return
            left_panel = splitter.widget(0)
            if not left_panel:
                return

            # 创建预览控件插入左面板顶部
            self._preview_widget = PreviewWidget()
            self._preview_widget.setMinimumHeight(120)
            layout = left_panel.layout()
            if layout:
                layout.insertWidget(0, self._preview_widget, 1)

            # 获取窗口标题并查找句柄
            title = self._window_title
            if title:
                self._preview_hwnd = win32gui.FindWindow(None, title)

            # 启动定时器
            self._preview_capturing = True
            interval = max(33, int(1000 / max(1, self._preview_fps_spin.value())))
            self._preview_timer.setInterval(interval)
            self._preview_timer.start()

    def _toggle_debug_log(self):
        """切换调试日志面板。"""
        self._toggle_log_panel()

    def _reset_layout(self):
        """重置窗口布局为默认比例。"""
        splitter = self.findChild(QSplitter)
        if splitter:
            total = splitter.width() or 800
            splitter.setSizes([int(total * 0.25), int(total * 0.5), int(total * 0.25)])