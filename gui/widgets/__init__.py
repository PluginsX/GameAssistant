"""GUI 控件子包。"""

from gui.widgets.preview import PreviewWidget
from gui.widgets.collapsible import CollapsibleSection
from gui.widgets.capture import capture_getdc, capture_windowdc, CAPTURE_METHODS
from gui.widgets.task_editor import (
    EventListWidget, TaskItemWidget, BlockActionItemWidget,
    _populate_key_combo, populate_hotkey_combo,
)
