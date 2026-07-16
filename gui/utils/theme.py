"""GUI 主题与常量。

集中管理样式表、窗口消息常量与边框参数。
"""

# ---------------------------------------------------------------------------
# 窗口消息常量
# ---------------------------------------------------------------------------
WM_NCCALCSIZE = 0x0083
WM_NCHITTEST = 0x0084

# ---------------------------------------------------------------------------
# 鼠标区域常量（用于无边框窗口拖拽/缩放）
# ---------------------------------------------------------------------------
HTCLIENT = 1
HTCAPTION = 2
HTTOP = 12
HTTOPLEFT = 13
HTTOPRIGHT = 14
HTLEFT = 10
HTRIGHT = 11
HTBOTTOM = 15
HTBOTTOMLEFT = 16
HTBOTTOMRIGHT = 17

# ---------------------------------------------------------------------------
# 窗口样式位
# ---------------------------------------------------------------------------
WS_THICKFRAME = 0x00040000
WS_MINIMIZEBOX = 0x00020000
WS_MAXIMIZEBOX = 0x00010000
GWL_STYLE = -16
BORDER_WIDTH = 6

# ---------------------------------------------------------------------------
# 日志级别颜色
# ---------------------------------------------------------------------------
LEVEL_COLORS = {
    "INFO": "#e0e0e0",
    "WARNING": "#f59e0b",
    "ERROR": "#ef4444",
    "DEBUG": "#a0a0a0",
    "CRITICAL": "#ef4444",
}

# ---------------------------------------------------------------------------
# 全局样式表
# ---------------------------------------------------------------------------
STYLE_SHEET = """
QWidget { background: #121212; color: #e0e0e0; }
QMainWindow, QWidget#central { background: #121212; border: 1px solid #3a3a3a; }
QLabel { color: #e0e0e0; font-size: 13px; }
QLabel#sectionTitle { color: #6b8cff; font-size: 15px; font-weight: 600; }
QScrollArea, QScrollArea > QWidget > QWidget { background: #121212; border: none; }
QScrollArea QWidget#qt_scroll_area_viewport { background: #121212; }
QFormLayout QLabel { color: #e8e8e8; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox { background: #1e1e1e; border: 1px solid #3a3a3a; border-radius: 5px; padding: 5px 8px; color: #f0f0f0; font-size: 13px; selection-background-color: #6b8cff; }
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus { border: 1px solid #6b8cff; }
QLineEdit::placeholder { color: #666666; }
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

# ---------------------------------------------------------------------------
# ADS（Qt Advanced Docking System）深色主题样式
# ---------------------------------------------------------------------------
ADS_STYLE_SHEET = """
/* 停靠容器背景 */
ads--CDockContainerWidget {
    background: #121212;
}

/* 停靠区域 */
ads--CDockAreaWidget {
    background: #121212;
}

/* 停靠区域标签栏 — 紧凑高度 */
ads--CDockAreaTabBar {
    background: #1a1a1a;
    border-bottom: 1px solid #2a2a2a;
    padding: 0px;
    max-height: 26px;
    min-height: 26px;
}

/* 停靠标签页 — 紧凑高度 + 紧凑内边距 */
ads--CDockWidgetTab {
    background: #2a2a2a;
    color: #a0a0a0;
    padding: 2px 6px;
    border: 1px solid #3a3a3a;
    border-bottom: none;
    border-radius: 3px 3px 0 0;
    margin-right: 1px;
    font-size: 11px;
    font-weight: 500;
    max-height: 24px;
    min-height: 24px;
}

ads--CDockWidgetTab[activeTab="true"] {
    background: #1e1e1e;
    color: #6b8cff;
    border-bottom: 2px solid #6b8cff;
}

ads--CDockWidgetTab:hover {
    background: #333333;
    color: #d0d0d0;
}

/* 区域标题栏 — 紧凑高度 24px */
ads--CDockAreaTitleBar {
    background: #1a1a1a;
    border-bottom: 1px solid #2a2a2a;
    padding: 0px 4px;
    max-height: 24px;
    min-height: 24px;
}

/* 标题栏按钮 — 缩小 + 浅灰色图标 */
ads--CTitleBarButton {
    background: transparent;
    border: none;
    border-radius: 2px;
    padding: 0px;
    max-width: 18px;
    max-height: 18px;
    min-width: 18px;
    min-height: 18px;
    color: #c8c8c8;
}

ads--CTitleBarButton:hover {
    background: #3a3a3a;
}

ads--CTitleBarButton#CloseButton:hover {
    background: #e81123;
}

/* 弹性标签文字 */
ads--CElidingLabel {
    color: #a0a0a0;
    background: transparent;
    font-size: 11px;
    padding: 0px 4px;
}

/* 分割器 */
ads--CDockSplitter {
    background: #2a2a2a;
}

ads--CDockSplitter::handle {
    background: #2a2a2a;
    min-width: 3px;
    min-height: 3px;
}

ads--CDockSplitter::handle:hover {
    background: #6b8cff;
}

/* 浮动窗口容器 */
ads--CFloatingDockContainer {
    background: #121212;
    border: 1px solid #3a3a3a;
}

/* 拖拽预览覆盖层 */
ads--CDockOverlay {
    background: rgba(107, 140, 255, 0.15);
}

ads--CDockOverlayCross {
    background: rgba(107, 140, 255, 0.3);
}

/* 标签页关闭图标 — 缩小 */
#tabCloseIcon {
    background: transparent;
    max-width: 12px;
    max-height: 12px;
}
"""
