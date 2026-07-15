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

        # 窗口标题
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("窗口标题(如QQ三国)")
        self.title_edit.setText("QQ三国")
        self.title_edit.setFixedWidth(120)
        self.title_edit.setStyleSheet(
            "QLineEdit { background: #2a2a2a; color: #e0e0e0; border: 1px solid #3a3a3a; "
            "border-radius: 4px; padding: 3px 6px; font-size: 11px; }"
        )
        layout.addWidget(QLabel("窗口:"))
        layout.addWidget(self.title_edit)

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

        # ── 下半：动作库 ──────────────────────────────────────
        bricks_label = QLabel("■ 动作库")
        bricks_label.setStyleSheet(_SECTION_TITLE_STYLE)
        layout.addWidget(bricks_label)

        bricks_frame = QFrame()
        bricks_frame.setStyleSheet(
            "QFrame { background: #1a1a1a; border: 1px solid #3a3a3a; border-radius: 6px; }"
        )
        bricks_layout = QVBoxLayout(bricks_frame)
        bricks_layout.setContentsMargins(8, 6, 8, 6)
        bricks_layout.setSpacing(4)

        bricks_layout.addWidget(QLabel("按键组合:"))
        key_row = QHBoxLayout()
        key_row.setSpacing(2)
        self._key1_combo = QComboBox()
        _populate_key_combo(self._key1_combo)
        key_row.addWidget(self._key1_combo)

        plus1 = QLabel("+")
        plus1.setStyleSheet("color: #888; font-size: 12px; font-weight: 700; padding: 0 1px;")
        plus1.setFixedWidth(12)
        key_row.addWidget(plus1)

        self._key2_combo = QComboBox()
        _populate_key_combo(self._key2_combo)
        key_row.addWidget(self._key2_combo)

        plus2 = QLabel("+")
        plus2.setStyleSheet("color: #888; font-size: 12px; font-weight: 700; padding: 0 1px;")
        plus2.setFixedWidth(12)
        key_row.addWidget(plus2)

        self._key3_combo = QComboBox()
        _populate_key_combo(self._key3_combo)
        key_row.addWidget(self._key3_combo)
        key_row.addStretch()
        bricks_layout.addLayout(key_row)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)
        btn_down = QPushButton("↓ 按下")
        btn_down.setStyleSheet(
            "background: #3b82f6; color: white; border: none; border-radius: 4px; "
            "padding: 5px 10px; font-size: 11px; font-weight: 600;"
        )
        btn_down.clicked.connect(lambda: self._add_event("keydown"))
        btn_row.addWidget(btn_down)

        btn_up = QPushButton("↑ 松开")
        btn_up.setStyleSheet(
            "background: #8b5cf6; color: white; border: none; border-radius: 4px; "
            "padding: 5px 10px; font-size: 11px; font-weight: 600;"
        )
        btn_up.clicked.connect(lambda: self._add_event("keyup"))
        btn_row.addWidget(btn_up)

        btn_click = QPushButton("↕ 单击")
        btn_click.setStyleSheet(
            "background: #10b981; color: white; border: none; border-radius: 4px; "
            "padding: 5px 10px; font-size: 11px; font-weight: 600;"
        )
        btn_click.clicked.connect(lambda: self._add_event("keyclick"))
        btn_row.addWidget(btn_click)

        bricks_layout.addLayout(btn_row)
        bricks_layout.addSpacing(2)

        bricks_layout.addWidget(QLabel("等待 (ms):"))
        wait_row = QHBoxLayout()
        wait_row.setSpacing(4)
        self.wait_random_check = QCheckBox("区间随机")
        self.wait_random_check.setStyleSheet("color: #c0c0c0; font-size: 11px;")
        self.wait_random_check.toggled.connect(self._on_wait_random_toggled)
        wait_row.addWidget(self.wait_random_check)

        self.block_wait_spin = QSpinBox()
        self.block_wait_spin.setRange(10, 999999)
        self.block_wait_spin.setValue(500)
        self.block_wait_spin.setFixedWidth(70)
        wait_row.addWidget(self.block_wait_spin)

        self.block_wait_min_spin = QSpinBox()
        self.block_wait_min_spin.setRange(10, 999999)
        self.block_wait_min_spin.setValue(200)
        self.block_wait_min_spin.setFixedWidth(60)
        self.block_wait_min_spin.setVisible(False)
        wait_row.addWidget(self.block_wait_min_spin)

        self.block_wait_max_spin = QSpinBox()
        self.block_wait_max_spin.setRange(10, 999999)
        self.block_wait_max_spin.setValue(500)
        self.block_wait_max_spin.setFixedWidth(60)
        self.block_wait_max_spin.setVisible(False)
        wait_row.addWidget(self.block_wait_max_spin)

        btn_wait = QPushButton("⏱ 等待")
        btn_wait.setStyleSheet(
            "background: #f59e0b; color: #1a1a1a; border: none; border-radius: 4px; "
            "padding: 5px 10px; font-size: 11px; font-weight: 600;"
        )
        btn_wait.clicked.connect(self._on_add_wait_event)
        wait_row.addWidget(btn_wait)
        wait_row.addStretch()
        bricks_layout.addLayout(wait_row)

        layout.addWidget(bricks_frame, 1)
        return widget

    def _on_wait_random_toggled(self, checked: bool):
        self.block_wait_spin.setVisible(not checked)
        self.block_wait_min_spin.setVisible(checked)
        self.block_wait_max_spin.setVisible(checked)
        if checked:
            if self.block_wait_max_spin.value() < self.block_wait_min_spin.value():
                self.block_wait_max_spin.setValue(self.block_wait_min_spin.value())

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
        layout.addWidget(self.event_list, 1)
        return widget

    # ── 右栏 ──────────────────────────────────────────────────

    def _build_right_panel(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")

        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(3, 6, 6, 6)
        layout.setSpacing(8)

        # ── 任务属性 ──────────────────────────────────────────
        prop_label = QLabel("■ 属性")
        prop_label.setStyleSheet(_SECTION_TITLE_STYLE)
        layout.addWidget(prop_label)

        prop_frame = QFrame()
        prop_frame.setStyleSheet(
            "QFrame { background: #1a1a1a; border: 1px solid #3a3a3a; border-radius: 6px; }"
        )
        prop_layout = QVBoxLayout(prop_frame)
        prop_layout.setContentsMargins(8, 8, 8, 8)
        prop_layout.setSpacing(6)

        type_row = QHBoxLayout()
        type_row.addWidget(QLabel("类型:"))
        self._task_type_combo = QComboBox()
        self._task_type_combo.addItem("顺序", "sequential")
        self._task_type_combo.addItem("独立", "independent")
        self._task_type_combo.currentIndexChanged.connect(self._on_task_type_changed)
        type_row.addWidget(self._task_type_combo)
        type_row.addStretch()
        prop_layout.addLayout(type_row)

        repeat_row = QHBoxLayout()
        repeat_row.addWidget(QLabel("重复:"))
        self.repeat_spin = QSpinBox()
        self.repeat_spin.setRange(1, 999)
        self.repeat_spin.valueChanged.connect(self._on_repeat_changed)
        repeat_row.addWidget(self.repeat_spin)
        repeat_row.addStretch()
        prop_layout.addLayout(repeat_row)

        layout.addWidget(prop_frame)

        # ── 最小动作间隔 ──────────────────────────────────────
        interval_label = QLabel("■ 最小动作间隔")
        interval_label.setStyleSheet(_SECTION_TITLE_STYLE)
        layout.addWidget(interval_label)

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

        layout.addWidget(interval_frame)

        # ── 屏蔽动作 ──────────────────────────────────────────
        block_label = QLabel("■ 屏蔽动作")
        block_label.setStyleSheet(_SECTION_TITLE_STYLE)
        layout.addWidget(block_label)

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
        layout.addWidget(block_frame)

        # ── 导入 / 导出 ───────────────────────────────────────
        io_label = QLabel("■ 数据")
        io_label.setStyleSheet(_SECTION_TITLE_STYLE)
        layout.addWidget(io_label)

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
        layout.addWidget(io_frame)

        layout.addStretch()
        scroll.setWidget(widget)
        return scroll

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