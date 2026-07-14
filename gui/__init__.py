"""GUI 图形化配置控制台入口。

PyQt5 深色游戏工具风格主窗口，集成配置编辑、脚本启停控制、
运行时热更新和实时日志显示。

用法：
    python gui.py
    python -m gui
"""

import ctypes
import logging
import os
import sys
import traceback

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QIcon
from PyQt5.QtWidgets import QApplication, QMessageBox

from gui.utils.dpi import setup_dpi_scaling, install_win32gui_patches, is_admin
from gui.utils.theme import STYLE_SHEET
from gui.utils.logger import setup_file_logger
from gui.resources.icons import get_app_icon_path

logger = logging.getLogger(__name__)


def _install_excepthook():
    """安装全局异常钩子，确保所有未捕获异常写入日志并显示友好提示。

    PyQt5 在信号/槽处理中发⽣的 Python 异常会被 Qt 事件循环静默吞掉。
    这个钩子确保：
        1. 任何未捕获的异常都会被写入文件日志（含完整调用栈）
        2. 用户会看到友好提示对话框
        3. 异常不会导致进程直接崩溃（保留现场）
    """
    original_hook = sys.excepthook

    def _global_excepthook(exc_type, exc_value, exc_tb):
        tb_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        logger.critical("未捕获异常\n%s", tb_text)

        if issubclass(exc_type, (SystemExit, KeyboardInterrupt)):
            original_hook(exc_type, exc_value, exc_tb)
            return

        try:
            msg = (
                f"程序遇到未预期的错误，已记录到日志。\n\n"
                f"错误类型: {exc_type.__name__}\n"
                f"错误信息: {exc_value}\n\n"
                f"请查看日志文件获取详细信息。"
            )
            QMessageBox.critical(None, "程序错误", msg)
        except Exception:
            pass

    sys.excepthook = _global_excepthook


def main() -> None:
    """GUI 主入口。"""
    from gui.main_window import MainWindow

    setup_file_logger()
    _install_excepthook()

    # DPI 缩放配置（必须在 Qt 加载前）
    enable_dpi = setup_dpi_scaling()

    # 高级兼容逻辑（确保用户勾选自适应缩放时起作用）
    if enable_dpi:
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)

    # 管理员权限检查：直接触发 UAC，仅此一次提示
    if not is_admin():
        params = " ".join([f'"{arg}"' for arg in sys.argv])
        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, params, None, 1
        )
        # ShellExecuteW 成功返回 > 32
        if ret > 32:
            sys.exit(0)
        # UAC 被取消 → 询问是否以普通权限继续
        ret = QMessageBox.question(
            None, "管理员权限",
            "以管理员权限运行可以确保按键正确发送到游戏窗口。\n\n"
            "是否以普通权限继续运行？（按键功能可能受限）",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
        )
        if ret != QMessageBox.Yes:
            sys.exit(0)

    # 安装 win32gui DPI Monkey Patch
    install_win32gui_patches()

    app.setStyleSheet(STYLE_SHEET)
    font = QFont("Microsoft YaHei UI", 9)
    app.setFont(font)

    icon_path = get_app_icon_path()
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
