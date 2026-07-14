"""主窗口。

PyQt5 深色游戏工具风格主窗口，集成配置编辑、脚本启停控制、
运行时热更新和实时日志显示。
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
    QPushButton, QScrollArea, QSpinBox, QTextEdit,
    QVBoxLayout, QWidget, QInputDialog, QToolButton,
)

import win32gui

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


class MainWindow(QMainWindow):
    """辅助机器人主窗口。"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("辅助机器人")
        self.resize(900, 720)
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowSystemMenuHint
            | Qt.WindowMinMaxButtonsHint
        )

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
        self._selected_type: str = "sequential"
        self._selected_seq_index: int = -1
        self._selected_ind_index: int = -1
        self._hotkey_mgr = HotkeyManager()
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
        toolbar_frame.setStyleSheet(
            "QFrame#toolbarFrame { background: #1e1e1e; border: 1px solid "
            "#3a3a3a; border-radius: 8px; }"
        )
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

    # ------------------------------------------------------------------
    # 标题栏
    # ------------------------------------------------------------------

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

        title_label = QLabel("辅助机器人")
        title_label.setObjectName("titleBarLabel")
        title_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        title_label.setStyleSheet(
            "QLabel#titleBarLabel { color: #e0e0e0; font-size: 13px; "
            "font-weight: 500; background: transparent; }"
        )
        layout.addWidget(title_label)
        layout.addStretch()

        btn_size = 36

        # 最小化按钮
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
        min_btn.clicked.connect(self._title_minimize)
        layout.addWidget(min_btn)

        # 最大化/还原按钮
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

        # 关闭按钮
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

        self._min_btn = min_btn
        self._close_btn = close_btn
        return title_bar, max_btn

    def _title_minimize(self):
        self.showMinimized()

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

    # ------------------------------------------------------------------
    # 工具栏
    # ------------------------------------------------------------------

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
        populate_hotkey_combo(self.hotkey_combo)
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

    # ------------------------------------------------------------------
    # 设置区
    # ------------------------------------------------------------------

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

        self.btn_refresh_windows = QPushButton("\u27F3")
        self.btn_refresh_windows.setFixedWidth(32)
        self.btn_refresh_windows.setToolTip("刷新窗口列表")
        self.btn_refresh_windows.clicked.connect(self._refresh_window_list)
        window_select_row.addWidget(self.btn_refresh_windows)

        form.addRow("选择窗口：", window_select_row)

        self.cmb_input_mode = QComboBox()
        self.cmb_input_mode.addItems(["foreground", "postmsg", "focus"])
        self.cmb_input_mode.setToolTip(
            "foreground: 前台发键\npostmsg: 后台消息\nfocus: 快速切焦点"
        )
        form.addRow("输入模式：", self.cmb_input_mode)

        hint = QLabel("前台模式已验证有效；后台模式(postmsg)需测试是否兼容")
        hint.setStyleSheet("color: #888888; font-size: 11px;")
        form.addRow("", hint)

        layout.addLayout(form)

    def _build_debug_group_into(self, layout: QVBoxLayout):
        self.dpi_scale_check = QCheckBox(
            "自适应屏幕缩放 (开启后界面清晰，不影响底层抓图)"
        )
        self.dpi_scale_check.setToolTip(
            "根据Windows屏幕缩放比例自动调整UI大小，确保文字清晰"
        )
        self.dpi_scale_check.toggled.connect(self._on_dpi_scale_toggled)
        layout.addWidget(self.dpi_scale_check)

        self.debug_check = QCheckBox("启用调试日志")
        self.debug_check.toggled.connect(self._on_debug_toggled)
        layout.addWidget(self.debug_check)

    # ------------------------------------------------------------------
    # 预览区
    # ------------------------------------------------------------------

    def _build_preview_into(self, layout: QVBoxLayout):
        top_row = QHBoxLayout()
        top_row.setContentsMargins(4, 2, 4, 2)
        header = QLabel("画面预览")
        header.setStyleSheet(
            "color: #6b8cff; font-size: 13px; font-weight: 600;"
        )
        top_row.addWidget(header)
        top_row.addSpacing(10)

        top_row.addWidget(QLabel("截图方案:"))
        self._capture_method_combo = QComboBox()
        self._capture_method_combo.addItems(
            ["PrintWindow（屏幕分辨率）", "PrintWindow+全内容（渲染分辨率）",
             "BitBlt+GetDC（客户区）", "BitBlt+WindowDC（完整窗口）"]
        )
        self._capture_method_combo.setCurrentText("PrintWindow（屏幕分辨率）")
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
        fps_container = QFrame()
        fps_container.setFixedWidth(92)
        fps_container.setStyleSheet(
            "QFrame { background: #1e1e1e; border: 1px solid #3a3a3a; border-radius: 5px; }"
        )
        fps_container_layout = QHBoxLayout(fps_container)
        fps_container_layout.setSpacing(0)
        fps_container_layout.setContentsMargins(0, 0, 0, 0)

        self._preview_fps_spin = QSpinBox()
        self._preview_fps_spin.setRange(1, 60)
        self._preview_fps_spin.setValue(30)
        self._preview_fps_spin.setSuffix(" FPS")
        self._preview_fps_spin.setButtonSymbols(QSpinBox.NoButtons)
        self._preview_fps_spin.setStyleSheet(
            "QSpinBox { background: transparent; border: none; padding: 5px 8px; color: #f0f0f0; font-size: 13px; }"
        )
        self._preview_fps_spin.valueChanged.connect(self._on_preview_fps_changed)
        fps_container_layout.addWidget(self._preview_fps_spin, 1)

        btn_col = QVBoxLayout()
        btn_col.setSpacing(0)
        btn_col.setContentsMargins(0, 0, 0, 0)

        self._fps_up_btn = QPushButton("▲")
        self._fps_up_btn.setFixedHeight(13)
        self._fps_up_btn.setCursor(Qt.PointingHandCursor)
        self._fps_up_btn.setFocusPolicy(Qt.NoFocus)
        self._fps_up_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #888888; border: none; border-top-right-radius: 4px; font-size: 9px; padding: 0; } "
            "QPushButton:hover { background: #3a3a3a; color: #e0e0e0; } "
            "QPushButton:pressed { background: #2a2a2a; }"
        )
        self._fps_up_btn.clicked.connect(self._preview_fps_spin.stepUp)
        btn_col.addWidget(self._fps_up_btn)

        self._fps_down_btn = QPushButton("▼")
        self._fps_down_btn.setFixedHeight(13)
        self._fps_down_btn.setCursor(Qt.PointingHandCursor)
        self._fps_down_btn.setFocusPolicy(Qt.NoFocus)
        self._fps_down_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #888888; border: none; border-bottom-right-radius: 4px; font-size: 9px; padding: 0; } "
            "QPushButton:hover { background: #3a3a3a; color: #e0e0e0; } "
            "QPushButton:pressed { background: #2a2a2a; }"
        )
        self._fps_down_btn.clicked.connect(self._preview_fps_spin.stepDown)
        btn_col.addWidget(self._fps_down_btn)

        fps_container_layout.addLayout(btn_col)
        top_row.addWidget(fps_container)
        top_row.addStretch()

        layout.addLayout(top_row)

        self._preview_widget = PreviewWidget()
        layout.addWidget(self._preview_widget, 1)

    # ------------------------------------------------------------------
    # 日志区
    # ------------------------------------------------------------------

    def _build_log_into(self, layout: QVBoxLayout):
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(200)
        layout.addWidget(self.log_text)

    # ------------------------------------------------------------------
    # 任务编辑器
    # ------------------------------------------------------------------

    def _build_task_editor_into(self, layout: QVBoxLayout):
        panel = QFrame()
        panel.setObjectName("taskPanel")
        panel_layout = QHBoxLayout(panel)
        panel_layout.setContentsMargins(8, 8, 8, 8)
        panel_layout.setSpacing(6)

        left_col = QVBoxLayout()
        left_col.setSpacing(4)

        # ------------------- 顺序任务列表 -------------------
        seq_header = QHBoxLayout()
        seq_header.setSpacing(4)
        seq_label = QLabel("顺序任务")
        seq_label.setStyleSheet(
            "color: #6b8cff; font-size: 13px; font-weight: 600;"
        )
        seq_header.addWidget(seq_label)
        btn_add_seq = QPushButton("+")
        btn_add_seq.setFixedWidth(24)
        btn_add_seq.clicked.connect(lambda: self._on_add_task("sequential"))
        seq_header.addWidget(btn_add_seq)
        btn_del_seq = QPushButton("\u00D7")
        btn_del_seq.setFixedWidth(24)
        btn_del_seq.clicked.connect(self._on_del_task)
        seq_header.addWidget(btn_del_seq)
        seq_header.addStretch()
        left_col.addLayout(seq_header)

        self.seq_task_list = QListWidget()
        self.seq_task_list.setSelectionMode(QListWidget.SingleSelection)
        self.seq_task_list.setMinimumWidth(140)
        self.seq_task_list.currentRowChanged.connect(
            lambda r: self._on_list_selected(r, "sequential")
        )
        left_col.addWidget(self.seq_task_list, 1)

        # ------------------- 独立任务列表 -------------------
        ind_header = QHBoxLayout()
        ind_header.setSpacing(4)
        ind_label = QLabel("独立任务")
        ind_label.setStyleSheet(
            "color: #f59e0b; font-size: 13px; font-weight: 600;"
        )
        ind_header.addWidget(ind_label)
        btn_add_ind = QPushButton("+")
        btn_add_ind.setFixedWidth(24)
        btn_add_ind.clicked.connect(lambda: self._on_add_task("independent"))
        ind_header.addWidget(btn_add_ind)
        btn_del_ind = QPushButton("\u00D7")
        btn_del_ind.setFixedWidth(24)
        btn_del_ind.clicked.connect(self._on_del_task)
        ind_header.addWidget(btn_del_ind)
        ind_header.addStretch()
        left_col.addLayout(ind_header)

        self.ind_task_list = QListWidget()
        self.ind_task_list.setSelectionMode(QListWidget.SingleSelection)
        self.ind_task_list.setMinimumWidth(140)
        self.ind_task_list.currentRowChanged.connect(
            lambda r: self._on_list_selected(r, "independent")
        )
        left_col.addWidget(self.ind_task_list, 1)

        # ------------------- 共有属性 -------------------
        rename_btn = QPushButton("\u270E 重命名")
        rename_btn.clicked.connect(self._on_rename_task)
        rename_btn.setStyleSheet(
            "QPushButton { background: #3a3a3a; color: #d0d0d0; border: none; "
            "border-radius: 4px; padding: 4px 8px; font-size: 12px; } "
            "QPushButton:hover { background: #4a4a4a; color: #f0f0f0; }"
        )
        left_col.addWidget(rename_btn)

        repeat_row = QHBoxLayout()
        repeat_row.addWidget(QLabel("重复:"))
        self.repeat_spin = QSpinBox()
        self.repeat_spin.setRange(1, 999)
        self.repeat_spin.valueChanged.connect(self._on_repeat_changed)
        repeat_row.addWidget(self.repeat_spin)
        repeat_row.addStretch()
        left_col.addLayout(repeat_row)

        type_row = QHBoxLayout()
        type_row.addWidget(QLabel("类型:"))
        self._task_type_combo = QComboBox()
        self._task_type_combo.addItem("顺序", "sequential")
        self._task_type_combo.addItem("独立", "independent")
        self._task_type_combo.currentIndexChanged.connect(self._on_task_type_changed)
        type_row.addWidget(self._task_type_combo)
        type_row.addStretch()
        left_col.addLayout(type_row)

        panel_layout.addLayout(left_col, 1)

        mid_col = QVBoxLayout()
        mid_col.setSpacing(4)
        mid_label = QLabel("事件列表")
        mid_label.setStyleSheet(
            "color: #6b8cff; font-size: 13px; font-weight: 600;"
        )
        mid_col.addWidget(mid_label)
        self.event_list = EventListWidget(self)
        mid_col.addWidget(self.event_list, 1)
        panel_layout.addLayout(mid_col, 1)

        right_col = QVBoxLayout()
        right_col.setSpacing(4)
        right_label = QLabel("快捷积木")
        right_label.setStyleSheet(
            "color: #6b8cff; font-size: 13px; font-weight: 600;"
        )
        right_col.addWidget(right_label)

        right_col.addWidget(QLabel("按键:"))
        self._key1_combo = QComboBox()
        _populate_key_combo(self._key1_combo)
        key_row = QHBoxLayout()
        key_row.setSpacing(2)
        key_row.addWidget(self._key1_combo)

        plus1 = QLabel("+")
        plus1.setStyleSheet("color: #888; font-size: 13px; font-weight: 700; padding: 0 2px;")
        plus1.setFixedWidth(14)
        key_row.addWidget(plus1)

        self._key2_combo = QComboBox()
        _populate_key_combo(self._key2_combo)
        self._key2_combo.setPlaceholderText("")
        key_row.addWidget(self._key2_combo)

        plus2 = QLabel("+")
        plus2.setStyleSheet("color: #888; font-size: 13px; font-weight: 700; padding: 0 2px;")
        plus2.setFixedWidth(14)
        key_row.addWidget(plus2)

        self._key3_combo = QComboBox()
        _populate_key_combo(self._key3_combo)
        key_row.addWidget(self._key3_combo)

        key_row.addStretch()
        right_col.addLayout(key_row)

        btn_block_down = QPushButton("\u2193 按下")
        btn_block_down.setStyleSheet(
            "background: #3b82f6; color: white; border: none; "
            "border-radius: 6px; padding: 8px; font-weight: 600;"
        )
        btn_block_down.clicked.connect(lambda: self._add_event("keydown"))
        right_col.addWidget(btn_block_down)

        btn_block_up = QPushButton("\u2191 松开")
        btn_block_up.setStyleSheet(
            "background: #8b5cf6; color: white; border: none; "
            "border-radius: 6px; padding: 8px; font-weight: 600;"
        )
        btn_block_up.clicked.connect(lambda: self._add_event("keyup"))
        right_col.addWidget(btn_block_up)

        btn_block_click = QPushButton("\u2195 单击")
        btn_block_click.setStyleSheet(
            "background: #10b981; color: white; border: none; "
            "border-radius: 6px; padding: 8px; font-weight: 600;"
        )
        btn_block_click.clicked.connect(lambda: self._add_event("keyclick"))
        right_col.addWidget(btn_block_click)

        right_col.addWidget(QLabel(""))
        right_col.addWidget(QLabel("等待 (ms):"))
        self.wait_random_check = QCheckBox("区间随机")
        self.wait_random_check.setStyleSheet(
            "color: #d0d0d0; font-size: 12px;"
        )
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

        btn_block_wait = QPushButton("\u23F1 等待")
        btn_block_wait.setStyleSheet(
            "background: #f59e0b; color: #1a1a1a; border: none; "
            "border-radius: 6px; padding: 8px; font-weight: 600;"
        )
        btn_block_wait.clicked.connect(self._on_add_wait_event)
        right_col.addWidget(btn_block_wait)
        right_col.addStretch()
        panel_layout.addLayout(right_col, 1)
        layout.addWidget(panel)

        interval_frame = QFrame()
        interval_frame.setStyleSheet(
            "QFrame { background: #1e1e1e; border: 1px solid #3a3a3a; "
            "border-radius: 6px; }"
        )
        interval_layout = QHBoxLayout(interval_frame)
        interval_layout.setContentsMargins(12, 8, 12, 8)
        interval_layout.setSpacing(12)

        interval_label = QLabel("最小动作间隔:")
        interval_label.setStyleSheet(
            "color: #e8e8e8; font-size: 12px; font-weight: 500;"
        )
        interval_layout.addWidget(interval_label)

        self.min_interval_spin = QSpinBox()
        self.min_interval_spin.setRange(0, 5000)
        self.min_interval_spin.setValue(200)
        self.min_interval_spin.setSuffix(" ms")
        self.min_interval_spin.setFixedWidth(100)
        interval_layout.addWidget(self.min_interval_spin)

        self.min_interval_random_check = QCheckBox("区间随机")
        self.min_interval_random_check.setStyleSheet(
            "color: #d0d0d0; font-size: 12px;"
        )
        self.min_interval_random_check.toggled.connect(
            self._on_min_interval_random_toggled
        )
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
        block_frame.setStyleSheet(
            "QFrame { background: #1e1e1e; border: 1px solid #3a3a3a; "
            "border-radius: 6px; }"
        )
        block_layout = QVBoxLayout(block_frame)
        block_layout.setContentsMargins(12, 8, 12, 8)
        block_layout.setSpacing(8)

        block_title_row = QHBoxLayout()
        self.cb_block_actions = QCheckBox("屏蔽动作列表")
        self.cb_block_actions.setStyleSheet(
            "color: #e8e8e8; font-size: 12px; font-weight: 500;"
        )
        self.cb_block_actions.toggled.connect(self._on_block_actions_toggled)
        block_title_row.addWidget(self.cb_block_actions)
        block_title_row.addStretch()
        btn_add_block = QPushButton("+ 添加")
        btn_add_block.setStyleSheet(
            "background: #2a2a2a; color: #6b8cff; border: none; "
            "border-radius: 4px; padding: 4px 12px; font-size: 11px;"
        )
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
        btn_import.setStyleSheet(
            "background: #1e1e1e; color: #6b8cff; border: 1px solid #3a3a3a; "
            "border-radius: 6px; padding: 6px 16px; font-size: 12px;"
        )
        btn_import.clicked.connect(self._on_import_tasks)
        io_row.addWidget(btn_import)
        btn_export = QPushButton("导出 JSON")
        btn_export.setStyleSheet(
            "background: #1e1e1e; color: #6b8cff; border: 1px solid #3a3a3a; "
            "border-radius: 6px; padding: 6px 16px; font-size: 12px;"
        )
        btn_export.clicked.connect(self._on_export_tasks)
        io_row.addWidget(btn_export)
        layout.addLayout(io_row)

    # ------------------------------------------------------------------
    # 任务相关方法
    # ------------------------------------------------------------------

    def _get_seq_indices(self) -> list[int]:
        """返回 tasks 列表中所有顺序类型任务的索引。"""
        if self._task_queue is None:
            return []
        return [i for i, t in enumerate(self._task_queue.tasks)
                if t.task_type == "sequential"]

    def _get_ind_indices(self) -> list[int]:
        """返回 tasks 列表中所有独立类型任务的索引。"""
        if self._task_queue is None:
            return []
        return [i for i, t in enumerate(self._task_queue.tasks)
                if t.task_type == "independent"]

    def _get_selected_task(self) -> Task | None:
        if self._task_queue is None:
            return None
        if self._selected_type == "sequential":
            idx = self._selected_seq_index
        else:
            idx = self._selected_ind_index
        if 0 <= idx < len(self._task_queue.tasks):
            return self._task_queue.tasks[idx]
        return None

    def _refresh_task_list(self):
        """刷新顺序任务列表和独立任务列表。"""
        if self._task_queue is None:
            self._selected_seq_index = -1
            self._selected_ind_index = -1
            self.seq_task_list.clear()
            self.ind_task_list.clear()
            self.event_list.clear()
            return

        # 刷新顺序列表
        seq_indices = self._get_seq_indices()
        self.seq_task_list.blockSignals(True)
        self.seq_task_list.clear()
        for vi, fi in enumerate(seq_indices):
            t = self._task_queue.tasks[fi]
            item = QListWidgetItem()
            widget = TaskItemWidget(t, vi, self.seq_task_list, self, "sequential")
            self.seq_task_list.addItem(item)
            self.seq_task_list.setItemWidget(item, widget)
            item.setSizeHint(widget.sizeHint())
        self.seq_task_list.blockSignals(False)

        # 刷新独立列表
        ind_indices = self._get_ind_indices()
        self.ind_task_list.blockSignals(True)
        self.ind_task_list.clear()
        for vi, fi in enumerate(ind_indices):
            t = self._task_queue.tasks[fi]
            item = QListWidgetItem()
            widget = TaskItemWidget(t, vi, self.ind_task_list, self, "independent")
            self.ind_task_list.addItem(item)
            self.ind_task_list.setItemWidget(item, widget)
            item.setSizeHint(widget.sizeHint())
        self.ind_task_list.blockSignals(False)

        # 恢复选中状态
        if self._selected_seq_index >= 0 and self._selected_seq_index in seq_indices:
            self.seq_task_list.setCurrentRow(seq_indices.index(self._selected_seq_index))
        if self._selected_ind_index >= 0 and self._selected_ind_index in ind_indices:
            self.ind_task_list.setCurrentRow(ind_indices.index(self._selected_ind_index))

        # 如果两个列表都空了，清空事件列表
        if not seq_indices and not ind_indices:
            self._selected_seq_index = -1
            self._selected_ind_index = -1
            self.event_list.clear()

    def _on_list_selected(self, view_row: int, task_type: str):
        """任务列表项被选中时的回调。

        Args:
            view_row: 在对应列表中的视图索引（-1 表示取消选中）。
            task_type: "sequential" 或 "independent"。
        """
        if view_row < 0 or self._task_queue is None:
            return

        if task_type == "sequential":
            indices = self._get_seq_indices()
            if view_row >= len(indices):
                return
            fi = indices[view_row]
            self._selected_type = "sequential"
            self._selected_seq_index = fi
        else:
            indices = self._get_ind_indices()
            if view_row >= len(indices):
                return
            fi = indices[view_row]
            self._selected_type = "independent"
            self._selected_ind_index = fi

        task = self._task_queue.tasks[fi]
        self.event_list.refresh_events(task)
        self.repeat_spin.setValue(task.repeat)

        idx = self._task_type_combo.findData(task.task_type)
        if idx >= 0:
            self._task_type_combo.blockSignals(True)
            self._task_type_combo.setCurrentIndex(idx)
            self._task_type_combo.blockSignals(False)

    def _on_add_task(self, task_type: str = "sequential"):
        """添加新任务到指定类型列表。"""
        if self._task_queue is None:
            self._task_queue = TaskQueue.create_default()
            # 确保默认任务类型正确
            if self._task_queue.tasks:
                self._task_queue.tasks[0].task_type = task_type
        else:
            task = Task(name=f"任务 {len(self._task_queue.tasks) + 1}",
                        task_type=task_type)
            self._task_queue.tasks.append(task)
        self._refresh_task_list()

        # 选中新添加的任务
        if task_type == "sequential":
            indices = self._get_seq_indices()
            if indices:
                self.seq_task_list.setCurrentRow(len(indices) - 1)
        else:
            indices = self._get_ind_indices()
            if indices:
                self.ind_task_list.setCurrentRow(len(indices) - 1)

    def _on_del_task(self):
        """删除当前选中的任务。"""
        if self._task_queue is None:
            return
        if self._selected_type == "sequential":
            idx = self._selected_seq_index
        else:
            idx = self._selected_ind_index
        if idx < 0 or idx >= len(self._task_queue.tasks):
            return
        reply = QMessageBox.question(
            self, "确认",
            f"删除任务 '{self._task_queue.tasks[idx].name}'？"
        )
        if reply == QMessageBox.Yes:
            old_type = self._task_queue.tasks[idx].task_type
            self._task_queue.tasks.pop(idx)
            if old_type == "sequential":
                self._selected_seq_index = -1
            else:
                self._selected_ind_index = -1
            self._refresh_task_list()

    def _on_rename_task(self):
        task = self._get_selected_task()
        if not task:
            return
        new_name, ok = QInputDialog.getText(
            self, "重命名", "任务名称:", text=task.name
        )
        if ok and new_name.strip():
            task.name = new_name.strip()
            self._refresh_task_list()
            if self._selected_type == "sequential":
                indices = self._get_seq_indices()
                if self._selected_seq_index in indices:
                    self.seq_task_list.setCurrentRow(
                        indices.index(self._selected_seq_index))
            else:
                indices = self._get_ind_indices()
                if self._selected_ind_index in indices:
                    self.ind_task_list.setCurrentRow(
                        indices.index(self._selected_ind_index))

    def _on_repeat_changed(self, value: int):
        task = self._get_selected_task()
        if task:
            task.repeat = value
            self._refresh_task_list()

    def _on_task_type_changed(self, idx: int):
        """修改当前选中任务的类型（顺序 ↔ 独立）。"""
        task = self._get_selected_task()
        if not task:
            return
        new_type = self._task_type_combo.itemData(idx)
        if new_type and new_type != task.task_type:
            task.task_type = new_type
            if new_type == "sequential":
                self._selected_type = "sequential"
                self._selected_seq_index = self._get_seq_indices()[-1]
                self._selected_ind_index = -1
            else:
                self._selected_type = "independent"
                self._selected_ind_index = self._get_ind_indices()[-1]
                self._selected_seq_index = -1
            self._refresh_task_list()

    def _on_import_tasks(self):
        from PyQt5.QtWidgets import QFileDialog
        file_path, _ = QFileDialog.getOpenFileName(
            self, "导入任务配置", "", "JSON 文件 (*.json)"
        )
        if not file_path:
            return
        try:
            self._task_queue, warnings = TaskQueue.load_safe(file_path)
            self._selected_seq_index = -1
            self._selected_ind_index = -1
            self._selected_type = "sequential"
            self._refresh_task_list()
            self._sync_interval_to_ui()
            self._refresh_block_actions()
            seq_indices = self._get_seq_indices()
            ind_indices = self._get_ind_indices()
            if seq_indices:
                self.seq_task_list.setCurrentRow(0)
            elif ind_indices:
                self.ind_task_list.setCurrentRow(0)

            # 显示导入结果
            total = len(self._task_queue.tasks)
            event_count = sum(len(t.events) for t in self._task_queue.tasks)
            if warnings:
                warn_text = "导入完成，存在以下问题：\n\n"
                warn_text += "\n".join(f"\u2022 {w}" for w in warnings[:20])
                if len(warnings) > 20:
                    warn_text += f"\n\n...以及另外 {len(warnings) - 20} 条警告"
                warn_text += f"\n\n任务: {total} 个 | 事件: {event_count} 个"
                QMessageBox.warning(self, "导入完成（有警告）", warn_text)
            else:
                QMessageBox.information(
                    self, "导入成功",
                    f"成功导入 {total} 个任务，{event_count} 个事件"
                )
        except Exception as e:
            QMessageBox.critical(
                self, "导入失败", f"导入任务配置失败: {e}"
            )

    def _on_export_tasks(self):
        from PyQt5.QtWidgets import QFileDialog
        if self._task_queue is None:
            QMessageBox.warning(self, "提示", "当前没有任务可导出")
            return
        self._sync_interval_to_queue()
        self._collect_block_actions()
        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出任务配置", "TaskConfig.json", "JSON 文件 (*.json)"
        )
        if not file_path:
            return
        try:
            self._task_queue.save(file_path)
            QMessageBox.information(
                self, "导出成功", f"任务配置已导出至 {file_path}"
            )
        except Exception as e:
            QMessageBox.critical(
                self, "导出失败", f"导出任务配置失败: {e}"
            )

    def _on_min_interval_random_toggled(self, checked: bool):
        self.min_interval_spin.setVisible(not checked)
        self._min_interval_min_widget.setVisible(checked)
        self._min_interval_max_widget.setVisible(checked)
        if checked:
            if self.min_interval_max_spin.value() < self.min_interval_min_spin.value():
                self.min_interval_max_spin.setValue(
                    self.min_interval_min_spin.value()
                )

    def _sync_interval_to_ui(self):
        if self._task_queue is None:
            return
        self.min_interval_spin.setValue(self._task_queue.min_action_interval)
        self.min_interval_random_check.setChecked(
            self._task_queue.min_action_interval_random
        )
        self.min_interval_min_spin.setValue(
            self._task_queue.min_action_interval_min
        )
        self.min_interval_max_spin.setValue(
            self._task_queue.min_action_interval_max
        )

    def _sync_interval_to_queue(self):
        if self._task_queue is None:
            return
        self._task_queue.min_action_interval = self.min_interval_spin.value()
        self._task_queue.min_action_interval_random = (
            self.min_interval_random_check.isChecked()
        )
        self._task_queue.min_action_interval_min = (
            self.min_interval_min_spin.value()
        )
        self._task_queue.min_action_interval_max = (
            self.min_interval_max_spin.value()
        )

    def _on_block_actions_toggled(self, checked: bool):
        self._btn_add_block.setEnabled(checked)
        self.block_scroll.setEnabled(checked)
        if self._task_queue:
            self._task_queue.block_actions_enabled = checked

    def _add_block_action(self, key: str = "Space", action_type: str = "keyclick"):
        if self._task_queue is None:
            return
        widget = BlockActionItemWidget(
            key=key, action_type=action_type, parent=self,
            index=len(self._block_action_widgets)
        )
        self._block_flow_layout.insertWidget(
            self._block_flow_layout.count() - 1, widget
        )
        self._block_action_widgets.append(widget)

    def _remove_block_action(self, index: int):
        if index < 0 or index >= len(self._block_action_widgets):
            return
        widget = self._block_action_widgets.pop(index)
        widget.setParent(None)
        widget.deleteLater()
        for i, w in enumerate(self._block_action_widgets):
            w.index = i

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

        self.cb_block_actions.setChecked(
            self._task_queue.block_actions_enabled
        )
        self._btn_add_block.setEnabled(
            self._task_queue.block_actions_enabled
        )
        self.block_scroll.setEnabled(
            self._task_queue.block_actions_enabled
        )

        for blocked in self._task_queue.blocked_actions:
            parts = blocked.split(":", 1)
            if len(parts) == 2:
                self._add_block_action(key=parts[0], action_type=parts[1])
            else:
                self._add_block_action(key=blocked, action_type="keyclick")

    def _collect_block_actions(self):
        if self._task_queue is None:
            return
        self._task_queue.block_actions_enabled = (
            self.cb_block_actions.isChecked()
        )
        result = []
        for widget in self._block_action_widgets:
            key = widget.get_key()
            action_type = widget.get_type()
            if key:
                result.append(f"{key}:{action_type}")
        self._task_queue.blocked_actions = result

    def _on_wait_random_toggled(self, checked: bool):
        self.block_wait_spin.setVisible(not checked)
        self._wait_min_widget.setVisible(checked)
        self._wait_max_widget.setVisible(checked)
        if checked:
            if self.block_wait_max_spin.value() < self.block_wait_min_spin.value():
                self.block_wait_max_spin.setValue(
                    self.block_wait_min_spin.value()
                )

    def _on_add_wait_event(self):
        task = self._get_selected_task()
        if not task:
            QMessageBox.warning(self, "提示", "请先选择或添加一个任务")
            return
        if self.wait_random_check.isChecked():
            min_ms = self.block_wait_min_spin.value()
            max_ms = self.block_wait_max_spin.value()
            if min_ms > max_ms:
                min_ms, max_ms = max_ms, min_ms
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
            key1 = self._key1_combo.currentData() or self._key1_combo.currentText()
            key2 = self._key2_combo.currentData() or self._key2_combo.currentText()
            key3 = self._key3_combo.currentData() or self._key3_combo.currentText()
            keys = [k for k in (key1, key2, key3) if k and k != "空" and not k.startswith("\u2500")]
            if not keys:
                QMessageBox.warning(self, "提示", "请先选择一个按键")
                return
            event = TaskEvent(type=event_type, keys=keys)
        elif event_type == "wait":
            event = TaskEvent(type="wait", ms=self.block_wait_spin.value())
        else:
            return
        current_row = self.event_list.currentRow()
        if current_row >= 0 and current_row < len(task.events):
            task.events.insert(current_row + 1, event)
        else:
            task.events.append(event)
        self.event_list.refresh_events(task)

    # ------------------------------------------------------------------
    # 预览控制
    # ------------------------------------------------------------------

    def on_frame(self, data) -> None:
        if self._preview_widget is None or data is None:
            return
        try:
            pil_img, _monsters, _items = data
        except (TypeError, ValueError):
            return
        if pil_img.mode != "RGB":
            pil_img = pil_img.convert("RGB")
        data_bytes = pil_img.tobytes("raw", "RGB")
        qimg = QImage(
            data_bytes, pil_img.width, pil_img.height,
            pil_img.width * 3, QImage.Format_RGB888
        )
        self._last_frame = qimg.copy()
        self._preview_widget.set_image(self._last_frame)

    def _on_preview_start(self):
        if self._preview_widget is None:
            return
        hwnd = self._get_target_hwnd()
        if not hwnd:
            self._preview_widget.set_error(
                "未找到游戏窗口，请在「设置」中配置窗口标题"
            )
            return
        if win32gui.IsIconic(hwnd):
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
        if not self._preview_capturing or self._preview_widget is None:
            return
        hwnd = getattr(self, '_preview_hwnd', 0)
        if not hwnd or win32gui.IsIconic(hwnd):
            return
        method_name = self._capture_method_combo.currentText()
        method = CAPTURE_METHODS.get(method_name, capture_getdc)
        try:
            img = method(hwnd)
            if img.size == (1, 1):
                return
            if img.mode != "RGB":
                img = img.convert("RGB")
            data_bytes = img.tobytes("raw", "RGB")
            qimg = QImage(
                data_bytes, img.width, img.height,
                img.width * 3, QImage.Format_RGB888
            )
            self._preview_widget.set_image(qimg.copy())
        except Exception:
            pass

    def _get_target_hwnd(self) -> int:
        title = self.title_edit.text().strip() or "QQ三国"
        selected_hwnd = self.cmb_window_select.currentData()
        if selected_hwnd and selected_hwnd != 0:
            return selected_hwnd
        try:
            from gameassistant.platform.window_win import get_hwnd
            return get_hwnd(title)
        except Exception:
            return 0

    def _refresh_window_list(self) -> None:
        title_keyword = self.title_edit.text().strip()
        try:
            from gameassistant.platform.window_win import list_windows
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
            if idx >= 0:
                self.cmb_window_select.setCurrentIndex(idx)
        self.cmb_window_select.blockSignals(False)

    def _on_window_title_changed(self, _text: str) -> None:
        self._refresh_window_list()

    # ------------------------------------------------------------------
    # 配置与热键
    # ------------------------------------------------------------------

    def _populate_form(self) -> None:
        self.title_edit.setText(self.config.window_title)
        self._refresh_window_list()
        self.cmb_input_mode.setCurrentText(self.config.input_mode)
        self.debug_check.setChecked(self.config.debug)

        self.dpi_scale_check.blockSignals(True)
        self.dpi_scale_check.setChecked(self.config.auto_dpi_scale)
        self.dpi_scale_check.blockSignals(False)

        self.hotkey_checkbox.setChecked(self.config.hotkey_enabled)
        hotkey_lower = self.config.hotkey_toggle.lower()
        found_idx = -1
        for i in range(self.hotkey_combo.count()):
            data = self.hotkey_combo.itemData(i)
            if data and isinstance(data, str) and data.lower() == hotkey_lower:
                found_idx = i
                break
        if found_idx >= 0:
            self.hotkey_combo.setCurrentIndex(found_idx)
        if self.config.hotkey_enabled:
            self._setup_hotkey()

    def _load_task_queue_config(self) -> None:
        if os.path.exists(TASK_QUEUE_CONFIG_PATH):
            self._task_queue, warnings = TaskQueue.load_safe(TASK_QUEUE_CONFIG_PATH)
            if warnings:
                for w in warnings:
                    logger.warning("配置加载: %s", w)
            self._refresh_task_list()
            self._sync_interval_to_ui()
            self._refresh_block_actions()

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
                hotkey_toggle=(self.hotkey_combo.currentData() or self.hotkey_combo.currentText()).lower(),
            )
        except ValueError as e:
            QMessageBox.warning(self, "配置错误", str(e))
            return None

    def _setup_hotkey(self) -> None:
        if not has_keyboard():
            return
        hotkey = (self.hotkey_combo.currentData() or self.hotkey_combo.currentText()).lower()
        if not hotkey:
            return
        self._hotkey_mgr.set_hotkey(hotkey)
        if self._hotkey_mgr.is_hooked and not self._hotkey_signal_connected:
            self._hotkey_mgr.hotkey_triggered.connect(
                self._on_hotkey_triggered
            )
            self._hotkey_signal_connected = True

    def _on_hotkey_toggled(self, checked: bool) -> None:
        if checked:
            self._setup_hotkey()
            self.hotkey_combo.setEnabled(True)
        else:
            self._hotkey_mgr.unhook()
            self.hotkey_combo.setEnabled(False)

    def _on_hotkey_changed(self, text: str) -> None:
        if text and self.hotkey_checkbox.isChecked():
            self._setup_hotkey()

    def _on_hotkey_triggered(self) -> None:
        if self.worker is None:
            self.on_start()
        else:
            self.on_stop()

    def _on_debug_toggled(self, checked: bool) -> None:
        if self.worker is not None and self.worker.isRunning():
            self.worker.set_log_level(
                logging.DEBUG if checked else logging.INFO
            )

    def _on_dpi_scale_toggled(self, checked: bool) -> None:
        self.config.auto_dpi_scale = checked
        new_config = self._collect_config()
        if new_config is not None:
            new_config.save()
            self.config.apply_from(new_config)

        ret = QMessageBox.question(
            self, "需要重启",
            "自适应屏幕缩放设置需要重启程序才能生效。\n\n是否立即重启？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
        )
        if ret == QMessageBox.Yes:
            self._restart_app()

    def _restart_app(self):
        if self.worker is not None and self.worker.isRunning():
            self.worker.stop()
            finished = self.worker.wait(5000)
            if not finished:
                logging.warning("重启时工作线程超时未退出，强制终止")
                self.worker.terminate()
                self.worker.wait(2000)
            self.worker = None
        self._hotkey_mgr.unhook()

        if getattr(sys, "frozen", False):
            target = sys.executable
            params = ""
            work_dir = None
        else:
            target = sys.executable
            params = "-m gui"
            work_dir = os.getcwd()

        ctypes.windll.shell32.ShellExecuteW(
            None, "open", target, params, work_dir, 1
        )
        QApplication.instance().quit()

    # ------------------------------------------------------------------
    # 启停控制
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        new_config = self._collect_config()
        if new_config is None:
            return
        self.config.apply_from(new_config)
        self.config.save()

        selected_hwnd = self.cmb_window_select.currentData()
        if selected_hwnd and selected_hwnd != 0:
            self.config._target_hwnd = selected_hwnd
        else:
            self.config._target_hwnd = 0

        if self._task_queue is None:
            self._task_queue = TaskQueue.create_default()
        self._sync_interval_to_queue()
        self._collect_block_actions()

        self.worker = BotWorker(self.config, task_queue=self._task_queue)
        self.worker.log_signal.connect(self.on_log)
        self.worker.status_signal.connect(self.on_status)
        self.worker.frame_signal.connect(self.on_frame)
        self.worker.start()

        if self.debug_check.isChecked():
            self.worker.set_log_level(logging.DEBUG)
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.apply_btn.setEnabled(True)
        self._set_status("运行中", "#4ade80")

    def on_stop(self) -> None:
        if self.worker is not None:
            self.worker.stop()
            finished = self.worker.wait(5000)
            if not finished:
                # 5秒后仍未退出，强制终止线程
                logging.warning("工作线程超时未退出，强制终止")
                self.worker.terminate()
                self.worker.wait(2000)
                # 释放可能按住的键（强制终止后 send_key_up 不可用，
                # 但 _release_all_keys 的异常会被捕获）
                if self.worker.bot is not None:
                    self.worker.bot._release_all_keys()
            self.worker = None
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.apply_btn.setEnabled(False)
        self._set_status("已停止", "#666666")

    def on_apply(self) -> None:
        if self.worker is None:
            return
        new_config = self._collect_config()
        if new_config is None:
            return
        self.worker.apply_config(new_config)

    def on_save(self) -> None:
        new_config = self._collect_config()
        if new_config is None:
            return
        new_config.save()
        self.config.apply_from(new_config)

        saved_files = ["config.json"]
        if self._task_queue is not None:
            try:
                self._sync_interval_to_queue()
                self._collect_block_actions()
                self._task_queue.save(TASK_QUEUE_CONFIG_PATH)
                saved_files.append("TaskConfig.json")
            except Exception as e:
                logger.warning("保存任务队列配置失败: %s", e)
        QMessageBox.information(
            self, "保存成功",
            f"配置已保存至 {', '.join(saved_files)}"
        )

    # ------------------------------------------------------------------
    # 日志与状态
    # ------------------------------------------------------------------

    def on_log(self, message: str, level: str) -> None:
        if not self.debug_check.isChecked() and level == "DEBUG":
            return
        color = LEVEL_COLORS.get(level, "#e0e0e0")
        safe_msg = (
            message.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        self.log_text.append(
            f'<span style="color:{color};">{safe_msg}</span>'
        )
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.log_text.setTextCursor(cursor)

    def on_status(self, status: str) -> None:
        if status == "运行中":
            self._set_status("运行中", "#4ade80")
        elif status == "已停止":
            self._set_status("已停止", "#666666")
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.apply_btn.setEnabled(False)
        elif status == "配置已热更新":
            self._set_status("运行中 (已更新)", "#6b8cff")

    def _set_status(self, text: str, color: str) -> None:
        self.status_dot.setStyleSheet(f"color: {color}; font-size: 18px;")
        self.status_label.setText(text)

    # ------------------------------------------------------------------
    # 无边框窗口 Native Event
    # ------------------------------------------------------------------

    def nativeEvent(self, eventType, message):
        if eventType == b"windows_generic_MSG":
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == WM_NCCALCSIZE and msg.wParam:
                return True, 0
            elif msg.message == WM_NCHITTEST:
                result = self._handle_nchittest()
                if result is not None:
                    return True, result
        return super().nativeEvent(eventType, message)

    def _handle_nchittest(self):
        pos = QCursor.pos()
        window_rect = self.frameGeometry()
        local_x = pos.x() - window_rect.left()
        local_y = pos.y() - window_rect.top()
        w, h = window_rect.width(), window_rect.height()
        if local_x < 0 or local_y < 0 or local_x > w or local_y > h:
            return None

        bw = BORDER_WIDTH
        left = local_x <= bw
        right = local_x >= w - bw
        top = local_y <= bw
        bottom = local_y >= h - bw

        if top and left:
            return HTTOPLEFT
        if top and right:
            return HTTOPRIGHT
        if bottom and left:
            return HTBOTTOMLEFT
        if bottom and right:
            return HTBOTTOMRIGHT
        if top:
            return HTTOP
        if bottom:
            return HTBOTTOM
        if left:
            return HTLEFT
        if right:
            return HTRIGHT

        if local_y <= 36:
            btn_min_left = w - 4 - 36 * 3
            if local_x >= btn_min_left:
                return HTCLIENT
            return HTCAPTION
        return None

    def closeEvent(self, event) -> None:
        if self.worker is not None and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(3000)
            self.worker = None
        self._hotkey_mgr.unhook()
        event.accept()
