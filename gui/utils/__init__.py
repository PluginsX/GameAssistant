"""GUI 工具模块。"""

from gui.utils.dpi import dpi_unaware_context, setup_dpi_scaling, install_win32gui_patches, is_admin
from gui.utils.theme import STYLE_SHEET, LEVEL_COLORS, BORDER_WIDTH, GWL_STYLE
from gui.utils.hotkey import HotkeyManager, has_keyboard
