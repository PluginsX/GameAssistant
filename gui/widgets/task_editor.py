"""任务编辑器组件。

提供任务事件列表、拖拽排序、快捷积木等编辑控件。
"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QPushButton, QSizePolicy, QWidget,
)

from gameassistant.models.tasks import Task, TaskEvent


class _TaskBlockWidget(QWidget):
    """单个事件积木的列表项组件。"""

    def __init__(self, event: TaskEvent, index: int, parent_list=None):
        super().__init__()
        self.event = event
        self.index = index
        self._parent_list = parent_list

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)
        handle = QLabel("\u22EE\u22EE")
        handle.setStyleSheet(
            f"color: {event.get_color()}; font-size: 14px; font-weight: 900;"
        )
        handle.setFixedWidth(18)
        handle.setCursor(Qt.SizeAllCursor)
        layout.addWidget(handle)

        text_label = QLabel(event.get_display_text())
        text_label.setStyleSheet(
            "color: #e8e8e8; font-size: 14px; font-weight: 500;"
        )
        layout.addWidget(text_label)
        layout.addStretch()

        up_btn = QPushButton("\u25B2")
        up_btn.setFixedSize(22, 22)
        up_btn.setStyleSheet(
            "QPushButton { background: #3a3a3a; color: #d0d0d0; border: none; "
            "border-radius: 4px; font-size: 10px; font-weight: 700; } "
            "QPushButton:hover { background: #4a4a4a; color: #f0f0f0; } "
            "QPushButton:disabled { color: #666666; background: #1e1e1e; }"
        )
        up_btn.clicked.connect(self._on_move_up)
        up_btn.setEnabled(index > 0)
        layout.addWidget(up_btn)

        down_btn = QPushButton("\u25BC")
        down_btn.setFixedSize(22, 22)
        down_btn.setStyleSheet(
            "QPushButton { background: #3a3a3a; color: #d0d0d0; border: none; "
            "border-radius: 4px; font-size: 10px; font-weight: 700; } "
            "QPushButton:hover { background: #4a4a4a; color: #f0f0f0; }"
        )
        down_btn.clicked.connect(self._on_move_down)
        layout.addWidget(down_btn)

        del_btn = QPushButton("\u00D7")
        del_btn.setFixedSize(22, 22)
        del_btn.setStyleSheet(
            "QPushButton { background: #ef4444; color: white; border: none; "
            "border-radius: 4px; font-size: 14px; font-weight: 700; } "
            "QPushButton:hover { background: #dc2626; }"
        )
        del_btn.clicked.connect(self._on_delete)
        layout.addWidget(del_btn)

    def _on_delete(self):
        if self._parent_list:
            self._parent_list._delete_event(self.index)

    def _on_move_up(self):
        if self._parent_list and self.index > 0:
            self._parent_list._move_event(self.index, self.index - 1)

    def _on_move_down(self):
        if self._parent_list:
            self._parent_list._move_event(self.index, self.index + 1)


class BlockActionItemWidget(QWidget):
    """屏蔽动作列表的单项组件。"""

    def __init__(self, key: str = "Space", action_type: str = "keyclick",
                 parent=None, index: int = 0):
        super().__init__(parent)
        self._parent = parent
        self.index = index
        self.setStyleSheet(
            "BlockActionItemWidget { background: #1e1e1e; border: 1px solid "
            "#3a3a3a; border-radius: 6px; } "
            "BlockActionItemWidget:hover { border-color: #6b8cff; }"
        )
        self.setFixedHeight(32)
        self.setFixedWidth(177)
        self.setAttribute(Qt.WA_StyledBackground, True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.key_combo = QComboBox()
        _populate_key_combo(self.key_combo)
        self.key_combo.setCurrentText(key)
        self.key_combo.setFixedWidth(70)
        self.key_combo.setCursor(Qt.PointingHandCursor)
        self.key_combo.setStyleSheet(
            "QComboBox { background: #1e1e1e; border: none; "
            "border-right: 1px solid #3a3a3a; border-top-left-radius: 5px; "
            "border-bottom-left-radius: 5px; padding: 0px 12px; color: #f0f0f0; "
            "font-size: 12px; font-weight: 500; } "
            "QComboBox:hover { background: #2a2a2a; } "
            "QComboBox::drop-down { width: 0px; border: none; } "
            "QComboBox QAbstractItemView { background: #1e1e1e; border: 1px "
            "solid #3a3a3a; border-radius: 4px; color: #e8e8e8; "
            "selection-background-color: #6b8cff; selection-color: #ffffff; "
            "padding: 4px; } "
            "QComboBox QAbstractItemView::item { padding: 4px 8px; "
            "min-height: 20px; }"
        )
        layout.addWidget(self.key_combo)

        self.type_combo = QComboBox()
        self.type_combo.addItems(["keydown", "keyup", "keyclick"])
        self.type_combo.setCurrentText(action_type)
        self.type_combo.setFixedWidth(75)
        self.type_combo.setCursor(Qt.PointingHandCursor)
        self.type_combo.setStyleSheet(
            "QComboBox { background: #1e1e1e; border: none; "
            "border-right: 1px solid #3a3a3a; border-radius: 0px; "
            "padding: 0px 12px; color: #a78bfa; font-size: 12px; "
            "font-weight: 500; } "
            "QComboBox:hover { background: #2a2a2a; } "
            "QComboBox::drop-down { width: 0px; border: none; } "
            "QComboBox QAbstractItemView { background: #1e1e1e; border: 1px "
            "solid #3a3a3a; border-radius: 4px; color: #e8e8e8; "
            "selection-background-color: #6b8cff; "
            "selection-color: #ffffff; padding: 4px; } "
            "QComboBox QAbstractItemView::item { padding: 4px 8px; "
            "min-height: 20px; }"
        )
        layout.addWidget(self.type_combo)

        del_btn = QPushButton("\u00D7")
        del_btn.setFixedWidth(32)
        del_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        del_btn.setCursor(Qt.PointingHandCursor)
        del_btn.setStyleSheet(
            "QPushButton { background: #1e1e1e; color: #ef4444; border: none; "
            "border-top-right-radius: 5px; border-bottom-right-radius: 5px; "
            "font-size: 16px; font-weight: 700; padding: 0px; } "
            "QPushButton:hover { background: #ef4444; color: white; }"
        )
        del_btn.clicked.connect(self._on_delete)
        layout.addWidget(del_btn)

    def _on_delete(self):
        if self._parent and hasattr(self._parent, "_remove_block_action"):
            self._parent._remove_block_action(self.index)

    def get_key(self) -> str:
        key = self.key_combo.currentData() or self.key_combo.currentText()
        return "" if key == "空" else key

    def get_type(self) -> str:
        return self.type_combo.currentText()


class EventListWidget(QListWidget):
    """事件列表组件（支持拖拽排序）。"""

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
        if target_idx < 0:
            target_idx = len(task.events) - 1
        super().dropEvent(event)

        if 0 <= from_idx < len(task.events):
            event_obj = task.events.pop(from_idx)
            if target_idx > from_idx:
                target_idx -= 1
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
        if not task:
            return
        if (from_idx < 0 or from_idx >= len(task.events)
                or to_idx < 0 or to_idx >= len(task.events)):
            return
        event = task.events.pop(from_idx)
        task.events.insert(to_idx, event)
        self.refresh_events(task)
        self.setCurrentRow(to_idx)


class TaskItemWidget(QWidget):
    """任务列表项组件（显示任务名、启用状态、类型图标）。"""

    def __init__(self, task: Task, index: int, list_widget: QListWidget,
                 main_window, task_type: str = "sequential"):
        super().__init__()
        self.task = task
        self.index = index
        self._list_widget = list_widget
        self._main = main_window
        self._task_type = task_type
        self.setAutoFillBackground(False)
        self.setCursor(Qt.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        # 类型标记
        badge = QLabel("S" if task_type == "sequential" else "I")
        badge.setFixedSize(16, 16)
        badge.setAlignment(Qt.AlignCenter)
        if task_type == "sequential":
            badge.setStyleSheet(
                "color: #6b8cff; background: #1e2a4a; border-radius: 3px; "
                "font-size: 10px; font-weight: 800;"
            )
        else:
            badge.setStyleSheet(
                "color: #f59e0b; background: #3a2a0a; border-radius: 3px; "
                "font-size: 10px; font-weight: 800;"
            )
        badge.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(badge)

        self.checkbox = QCheckBox()
        self.checkbox.setChecked(task.enabled)
        self.checkbox.stateChanged.connect(self._on_toggled)
        self.checkbox.setCursor(Qt.PointingHandCursor)
        layout.addWidget(self.checkbox)

        name_label = QLabel(task.name)
        name_label.setStyleSheet(
            "color: #e8e8e8; font-size: 14px; font-weight: 500;"
        )
        name_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(name_label)

        if task.repeat > 1:
            repeat_label = QLabel(f"\u00D7{task.repeat}")
            repeat_label.setStyleSheet("color: #808080; font-size: 12px;")
            repeat_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            layout.addWidget(repeat_label)

        layout.addStretch()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._list_widget.setCurrentRow(self.index)
            self._main._on_list_selected(self.index, self._task_type)
        super().mousePressEvent(event)

    def update_index(self, index: int):
        self.index = index

    def _on_toggled(self, state: int):
        self.task.enabled = (state == Qt.Checked)


def _populate_key_combo(combo: QComboBox):
    """填充按键下拉列表。"""
    combo.clear()
    combo.addItem("空", "")
    groups = [
        ("数字", [str(i) for i in range(10)]),
        ("字母", [chr(c) for c in range(0x41, 0x5B)]),
        ("方向", ["Left", "Up", "Right", "Down"]),
        ("控制", ["Space", "Enter", "Tab", "Esc", "Shift", "Ctrl", "Alt"]),
        ("功能", [f"F{i}" for i in range(1, 13)]),
    ]
    for group_name, keys in groups:
        combo.addItem(f"\u2500\u2500 {group_name} \u2500\u2500", "")
        for key in keys:
            combo.addItem(key, key)


def populate_hotkey_combo(combo: QComboBox):
    """填充热键下拉列表。"""
    groups = [
        ("功能键", [f"F{i}" for i in range(1, 13)]),
        ("数字键", [str(i) for i in range(10)]),
        ("字母键", [chr(c) for c in range(0x41, 0x5B)]),
        ("控制键", ["Space", "Enter", "Esc", "Tab", "Backspace"]),
        ("方向键", ["Left", "Up", "Right", "Down"]),
    ]
    for group_name, keys in groups:
        combo.addItem(f"\u2500\u2500 {group_name} \u2500\u2500", "")
        for key in keys:
            combo.addItem(key, key)
