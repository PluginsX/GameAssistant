"""QQ三国挂机脚本主程序。

状态机驱动的主循环，整合 window（窗口操作）模块，
实现自动按键和任务队列执行。窗口失焦/被遮挡时仍可运行，最小化时自动暂停。

用法：
    1. 激活虚拟环境：f:\\Project\\Game\\sanguo\\venv\\Scripts\\Activate.ps1
    2. 运行：python main.py
    3. 按 Ctrl+C 优雅退出

调试模式（显示画面预览）：
    python main.py --debug

配置文件：config.json（不存在则使用默认值），由 GUI 编辑或手动维护。

双入口：python gui.py 启动图形化配置控制台。
"""

import argparse
import logging
import random
import time
from enum import Enum, auto
from typing import Callable, Optional

from PIL import Image

import window
from config import BotConfig
from task_queue import TaskQueue

logger = logging.getLogger(__name__)


class BotState(Enum):
    """脚本状态机枚举。"""
    KEY_LOOP = auto()    # 纯按键循环模式
    TASK_QUEUE = auto()  # 任务队列模式
    PAUSED = auto()      # 窗口最小化，暂停


class SanguoBot:
    """挂机脚本主控制器。

    持有 BotConfig 引用，每轮 tick 读取最新配置字段，支持运行时热更新。
    窗口标题变更时通过 _hwnd_dirty 标志触发重新绑定句柄。

    Attributes:
        config: 运行配置（BotConfig），支持运行时热更新。
        hwnd: 游戏窗口句柄。
        state: 当前状态机状态。
    """

    def __init__(self, config: BotConfig, frame_callback: Optional[Callable] = None):
        self.config = config
        # 优先使用手动选择的窗口句柄，否则按标题自动查找
        if getattr(config, '_target_hwnd', 0):
            self.hwnd = config._target_hwnd
            logger.info("使用手动选择的窗口句柄: %s", self.hwnd)
        else:
            self.hwnd = window.get_hwnd(config.window_title)
        # 根据执行模式决定初始状态
        if config.execution_mode == "task_queue":
            self.state = BotState.TASK_QUEUE
        else:
            self.state = BotState.KEY_LOOP
        self._running = True
        self.frame_callback = frame_callback  # 调试帧回调 (QImage) -> None
        self._tick_count = 0  # 用于帧降频
        # 测试按键队列：GUI 端调用 request_test_key 追加，_tick 中消费
        # list.append / list.pop(0) 在 GIL 保护下线程安全
        self._test_key_queue: list[int] = []
        # 任务队列（由 GUI 设置）
        self.task_queue: Optional[TaskQueue] = None
        # 已按下的按键集合（用于停止时释放，防止卡键）
        self._pressed_keys: set[int] = set()

    def run(self) -> None:
        """主循环入口，捕获 Ctrl+C 优雅退出。"""
        if not self.hwnd:
            logger.error("未找到游戏窗口 '%s'，请确认游戏已启动且窗口标题正确", self.config.window_title)
            return

        logger.info("脚本启动，窗口句柄: %s，调试模式: %s", self.hwnd, self.config.debug)
        try:
            while self._running:
                self._tick()
        except KeyboardInterrupt:
            logger.info("收到退出信号，正在停止...")
        finally:
            self._release_all_keys()
            logger.info("脚本已停止")

    def stop(self) -> None:
        """请求停止主循环。"""
        self._running = False

    def _release_all_keys(self) -> None:
        """释放所有已按下的键（防止卡键）。"""
        if not self._pressed_keys:
            return
        mode = self.config.input_mode
        for vk in list(self._pressed_keys):
            try:
                window.send_key_up(self.hwnd, vk, mode=mode)
            except Exception as e:
                logger.warning("释放按键 0x%02X 失败: %s", vk, e)
        self._pressed_keys.clear()
        logger.info("已释放所有按下的按键")

    def request_test_key(self, vk_code: int) -> None:
        """请求发送一个测试按键（GUI 调用，线程安全）。

        按键不会立即发送，而是加入队列，在下一轮 _tick 中由 worker 线程
        发送到游戏窗口。这样避免跨线程操作的竞态问题。

        Args:
            vk_code: 虚拟键码。
        """
        self._test_key_queue.append(vk_code)

    def set_task_queue(self, tq: TaskQueue) -> None:
        """设置任务队列（GUI 调用，线程安全引用替换）。

        Args:
            tq: 任务队列对象。
        """
        self.task_queue = tq
        logger.info("任务队列已设置: %d 个任务", len(tq.tasks))

    def _tick(self) -> None:
        """单次状态机循环。"""
        # 优先消费测试按键队列（GUI 通过 request_test_key 追加）
        while self._test_key_queue:
            vk = self._test_key_queue.pop(0)
            logger.info("测试按键已发送: 0x%02X", vk)
            window.send_key(self.hwnd, vk, mode=self.config.input_mode)

        # 热更新窗口标题：检测 dirty 标志，重新获取 hwnd
        if self.config._hwnd_dirty:
            self.config._hwnd_dirty = False
            new_hwnd = window.get_hwnd(self.config.window_title)
            if new_hwnd:
                self.hwnd = new_hwnd
                logger.info("窗口标题变更，重新获取句柄: %s", new_hwnd)
            else:
                logger.warning("窗口标题变更后未找到窗口: %s", self.config.window_title)

        # 每轮先检测最小化状态（守护逻辑）
        if window.is_minimized(self.hwnd):
            if self.state != BotState.PAUSED:
                logger.warning("窗口已最小化，脚本暂停。请恢复窗口以继续。")
                self.state = BotState.PAUSED
            time.sleep(2.0)  # 暂停时降低轮询频率
            return

        if self.state == BotState.PAUSED:
            logger.info("窗口已恢复，脚本继续运行")
            # 恢复时根据执行模式选择状态
            if self.config.execution_mode == "task_queue":
                self.state = BotState.TASK_QUEUE
            else:
                self.state = BotState.KEY_LOOP

        self._tick_count += 1

        # 调试可视化：每 3 轮截图发送到 GUI
        if self.config.debug and self.frame_callback and self._tick_count % 3 == 0:
            img = window.capture_window(self.hwnd)
            if img and img.size != (1, 1):
                w, h = img.size
                scale = min(500 / w, 1.0)
                if scale < 1.0:
                    preview = img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
                else:
                    preview = img
                self.frame_callback(preview, [], [])

        # 状态机分发
        if self.state == BotState.KEY_LOOP:
            self._handle_key_loop()
        elif self.state == BotState.TASK_QUEUE:
            self._handle_task_queue()

        # 主循环随机延迟
        time.sleep(random.uniform(*self.config.loop_delay))

    # ------------------------------------------------------------------
    # 状态处理
    # ------------------------------------------------------------------

    def _handle_key_loop(self) -> None:
        """纯按键循环模式：不依赖图像识别，按配置循环发送技能/拾取键。

        典型场景：把角色放在怪物刷新点，让脚本持续按技能键攻击、按拾取键捡装备。
        - enable_key_loop=False 时不发送任何按键（仅作占位）
        - enable_pickup=False 时只发技能键，不发拾取键
        - attack_rounds 控制每轮技能循环次数
        - attack_keys 为空时只发送拾取键（不攻击）
        """
        if not self.config.enable_key_loop:
            return  # 按键循环未启用，空转等待

        # 循环发送技能键（若为空则跳过）
        if self.config.attack_keys:
            for rnd in range(self.config.attack_rounds):
                for key in self.config.attack_keys:
                    logger.debug("按键循环 (轮次 %d/%d, 键码 0x%02X)",
                                rnd + 1, self.config.attack_rounds, key)
                    window.send_key(self.hwnd, key, mode=self.config.input_mode)
                    time.sleep(random.uniform(*self.config.attack_delay))

        # 穿插发送拾取键（仅在启用拾取时）
        if self.config.enable_pickup:
            logger.debug("按键循环 拾取 (键码 0x%02X)", self.config.pickup_key)
            window.send_key(self.hwnd, self.config.pickup_key, mode=self.config.input_mode)
            time.sleep(random.uniform(0.3, 0.6))

    def _handle_task_queue(self) -> None:
        """任务队列模式：按顺序执行任务队列中的所有事件。

        每个任务按其 repeat 次数重复执行。
        若 loop_forever 为 True，整个队列执行完后从头开始。
        """
        if self.task_queue is None:
            logger.warning("任务队列为空，请先在编辑器中创建任务")
            return

        enabled_tasks = self.task_queue.get_enabled_tasks()
        if not enabled_tasks:
            logger.warning("没有已启用的任务，任务队列空转")
            return

        mode = self.config.input_mode
        for task in enabled_tasks:
            for rnd in range(task.repeat):
                logger.info("执行任务: %s (轮次 %d/%d)", task.name, rnd + 1, task.repeat)
                for event in task.events:
                    if not self._running:
                        return

                    # 检查是否被屏蔽
                    if self.task_queue.is_event_blocked(event):
                        logger.debug("  [屏蔽] %s", event.get_display_text())
                        continue

                    etype = event.type
                    if etype == "keydown":
                        vk = event.vk_code
                        logger.debug("  ↓ %s", event.key)
                        window.send_key_down(self.hwnd, vk, mode=mode)
                        self._pressed_keys.add(vk)
                    elif etype == "keyup":
                        vk = event.vk_code
                        logger.debug("  ↑ %s", event.key)
                        window.send_key_up(self.hwnd, vk, mode=mode)
                        self._pressed_keys.discard(vk)
                    elif etype == "keyclick":
                        vk = event.vk_code
                        logger.debug("  ↕ %s", event.key)
                        window.send_key(self.hwnd, vk, mode=mode)
                    elif etype == "wait":
                        logger.debug("  ⏱ 等待 %dms", event.ms)
                        time.sleep(event.ms / 1000.0)
                    elif etype == "wait_random":
                        wait_s = random.uniform(event.min_ms, event.max_ms) / 1000.0
                        logger.debug("  ⏱ 随机等待 %.0fms", wait_s * 1000)
                        time.sleep(wait_s)

                    # 最小动作间隔（仅对按键类事件生效，等待类事件不加）
                    if etype in ("keydown", "keyup", "keyclick"):
                        interval_ms = self.task_queue.get_action_interval_ms()
                        if interval_ms > 0:
                            time.sleep(interval_ms / 1000.0)

        if self.task_queue.loop_forever:
            logger.debug("任务队列一轮完成，循环继续")
        else:
            logger.info("任务队列执行完毕（非循环模式）")
            self._running = False

def main() -> None:
    """程序入口：加载 config.json 并启动脚本。"""
    parser = argparse.ArgumentParser(description="QQ三国后台挂机脚本")
    parser.add_argument("--debug", action="store_true", help="开启调试可视化窗口")
    parser.add_argument("--title", default=None, help="游戏窗口标题（覆盖 config.json）")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

    # 加载配置文件（不存在则使用默认值）
    config = BotConfig.load()
    if args.title:
        config.window_title = args.title
    if args.debug:
        config.debug = True

    # 启动脚本
    bot = SanguoBot(config)
    bot.run()


if __name__ == "__main__":
    main()
