"""Bot 工作线程模块。

将 SanguoBot 包装为 QThread 子线程运行，避免阻塞 GUI 主线程。
通过 Qt 信号槽机制将日志和状态安全转发到 GUI，实现跨线程通信。
支持运行时热更新配置（apply_config），无需重启脚本。
"""

import logging
from typing import Optional

from PyQt5.QtCore import QThread, pyqtSignal

from config import BotConfig
from main import SanguoBot


class QtLogHandler(logging.Handler):
    """自定义日志处理器，通过 Qt 信号将日志从子线程转发到 GUI 主线程。

    Qt 的信号槽机制默认使用队列连接（跨线程时），保证线程安全。
    """

    def __init__(self, log_signal):
        super().__init__()
        self._log_signal = log_signal

    def emit(self, record: logging.LogRecord) -> None:
        """将日志记录格式化后通过信号发送。"""
        try:
            msg = self.format(record)
            self._log_signal.emit(msg, record.levelname)
        except Exception:
            self.handleError(record)


class BotWorker(QThread):
    """挂机脚本工作线程。

    在子线程中运行 SanguoBot 主循环，通过信号向 GUI 报告日志和状态。
    持有共享的 BotConfig 引用，GUI 可通过 apply_config 热更新字段。

    Signals:
        log_signal(str, str): 日志消息 + 级别（INFO/WARNING/ERROR）。
        status_signal(str): 运行状态文本（运行中/已停止/配置已热更新）。
    """

    log_signal = pyqtSignal(str, str)    # (message, level)
    status_signal = pyqtSignal(str)      # 状态文本
    frame_signal = pyqtSignal(object)    # (pil_img, monsters, items) 供 GUI 绘制图层

    def __init__(self, config: BotConfig, task_queue=None):
        super().__init__()
        self.config = config
        self.task_queue = task_queue
        self.bot: Optional[SanguoBot] = None
        self._handler: Optional[QtLogHandler] = None

    def run(self) -> None:
        """线程入口：安装日志处理器 → 创建 SanguoBot → 运行主循环。

        日志处理器安装到 root logger，捕获所有模块的日志。
        线程结束时移除处理器，避免重复输出。
        """
        # 安装 Qt 日志处理器
        self._handler = QtLogHandler(self.log_signal)
        self._handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s - %(message)s")
        )
        root_logger = logging.getLogger()
        root_logger.addHandler(self._handler)
        root_logger.setLevel(logging.INFO)

        self.status_signal.emit("运行中")
        try:
            self.bot = SanguoBot(self.config, frame_callback=self._on_frame)
            if self.task_queue is not None:
                self.bot.set_task_queue(self.task_queue)
            self.bot.run()
        except Exception as e:
            logging.getLogger(__name__).error("挂机脚本异常退出: %s", e)
        finally:
            if self._handler is not None:
                root_logger.removeHandler(self._handler)
            self.status_signal.emit("已停止")

    def _on_frame(self, pil_img, monsters, items) -> None:
        """帧回调：将原始画面+坐标通过信号发送到 GUI 主线程。"""
        self.frame_signal.emit((pil_img, monsters, items))

    def stop(self) -> None:
        """请求 bot 优雅停止（非阻塞，实际退出由主循环检测 _running 标志）。"""
        if self.bot is not None:
            self.bot.stop()

    def apply_config(self, new_config: BotConfig) -> None:
        """热更新：将新配置字段写入共享 config 对象，下一轮 tick 自动生效。

        窗口标题变更会设置 _hwnd_dirty 标志，Bot 在 _tick 开头重新绑定 hwnd。

        Args:
            new_config: 包含新配置值的 BotConfig 对象。
        """
        self.config.apply_from(new_config)
        self.status_signal.emit("配置已热更新")

    def set_log_level(self, level: int) -> None:
        """设置 root logger 的日志级别。

        Args:
            level: logging.INFO / logging.DEBUG 等
        """
        root_logger = logging.getLogger()
        root_logger.setLevel(level)
        if self._handler is not None:
            self._handler.setLevel(level)
