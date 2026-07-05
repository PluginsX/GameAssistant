"""可折叠区域组件。"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QPushButton, QVBoxLayout, QWidget


class CollapsibleSection(QWidget):
    """可折叠的区域容器，点击标题栏展开/收起内容。"""

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
            QPushButton { background: #1e1e1e; border: 1px solid #3a3a3a;
                border-radius: 6px; color: #6b8cff; text-align: left;
                padding: 0 12px; font-size: 13px; font-weight: 600; }
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
        arrow = "\u25BC" if self._expanded else "\u25B6"
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
