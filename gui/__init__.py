"""GUI 图形化配置控制台入口。

PyQt5 深色游戏工具风格主窗口，集成配置编辑、脚本启停控制、
运行时热更新和实时日志显示。

用法：
    python gui.py
    python -m gui
"""

import ctypes
import sys

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QApplication, QMessageBox

from gui.utils.dpi import setup_dpi_scaling, install_win32gui_patches, is_admin
from gui.utils.theme import STYLE_SHEET
from gui.utils.logger import setup_file_logger


def main() -> None:
    """GUI 主入口。"""
    from gui.main_window import MainWindow

    setup_file_logger()

    # DPI 缩放配置（必须在 Qt 加载前）
    enable_dpi = setup_dpi_scaling()

    # 高级兼容逻辑（确保用户勾选自适应缩放时起作用）
    if enable_dpi:
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)

    # 管理员权限检查
    if not is_admin():
        ret = QMessageBox.question(
            None, "需要管理员权限",
            "pydirectinput 需要管理员权限才能向游戏窗口发送按键。\n\n"
            "是否以管理员身份重新运行？\n"
            "（选择「否」将以普通权限运行，按键可能无效）",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
        )
        if ret == QMessageBox.Yes:
            params = " ".join([f'"{arg}"' for arg in sys.argv])
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable, params, None, 1
            )
            sys.exit(0)

    # 安装 win32gui DPI Monkey Patch
    install_win32gui_patches()

    app.setStyleSheet(STYLE_SHEET)
    font = QFont("Microsoft YaHei UI", 9)
    app.setFont(font)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
