"""Bot 核心引擎。

状态机驱动的主循环，整合窗口操作模块，
实现自动按键和任务队列执行。
"""

import logging
import random
import time
from enum import Enum, auto
from typing import Callable, Optional

from PIL import Image

from gameassistant.config import BotConfig
from gameassistant.models.tasks import Task, TaskQueue
from gameassistant.platform.window_win import (
    get_hwnd, is_minimized, send_key, send_key_down, send_key_up,
    send_keys, send_keys_down, send_keys_up, capture_window,
)

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
        if getattr(config, '_target_hwnd', 0):
            self.hwnd = config._target_hwnd
            logger.info("使用手动选择的窗口句柄: %s", self.hwnd)
        else:
            self.hwnd = get_hwnd(config.window_title)
        if config.execution_mode == "task_queue":
            self.state = BotState.TASK_QUEUE
        else:
            self.state = BotState.KEY_LOOP
        self._running = True
        self.frame_callback = frame_callback
        self._tick_count = 0
        self._test_key_queue: list[int] = []
        self.task_queue: Optional[TaskQueue] = None
        self._pressed_keys: set[int] = set()
        self._seq_task_index: int = 0
        self._seq_state: dict = {"event_idx": 0, "repeat_idx": 0, "wait_until": 0.0}
        self._seq_loop_completed: int = 0
        self._ind_task_states: dict[int, dict] = {}

    def run(self) -> None:
        """主循环入口，捕获 Ctrl+C 优雅退出。"""
        if not self.hwnd:
            logger.error("未找到游戏窗口 '%s'，请确认游戏已启动且窗口标题正确",
                         self.config.window_title)
            return

        logger.info("脚本启动，窗口句柄: %s，调试模式: %s",
                    self.hwnd, self.config.debug)
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

    def _interruptible_sleep(self, seconds: float) -> bool:
        """可中断睡眠：每 0.1s 轮询检查 _running 标志。

        相比 time.sleep，该方法支持毫秒级的停止响应，
        避免长时间 sleep 阻塞 stop() 请求。

        Args:
            seconds: 总睡眠秒数。

        Returns:
            True 表示正常完成，False 表示因 _running=False 被中断。
        """
        elapsed = 0.0
        step = 0.1
        while elapsed < seconds:
            if not self._running:
                return False
            remaining = seconds - elapsed
            time.sleep(min(step, remaining))
            elapsed += step
        return True

    def _release_all_keys(self) -> None:
        """释放所有已按下的键（防止卡键）。"""
        if not self._pressed_keys:
            return
        mode = self.config.input_mode
        for vk in list(self._pressed_keys):
            try:
                send_key_up(self.hwnd, vk, mode=mode)
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
        while self._test_key_queue:
            vk = self._test_key_queue.pop(0)
            logger.info("测试按键已发送: 0x%02X", vk)
            send_key(self.hwnd, vk, mode=self.config.input_mode)

        if self.config._hwnd_dirty:
            self.config._hwnd_dirty = False
            new_hwnd = get_hwnd(self.config.window_title)
            if new_hwnd:
                self.hwnd = new_hwnd
                logger.info("窗口标题变更，重新获取句柄: %s", new_hwnd)
            else:
                logger.warning("窗口标题变更后未找到窗口: %s",
                             self.config.window_title)

        if is_minimized(self.hwnd):
            if self.state != BotState.PAUSED:
                logger.warning("窗口已最小化，脚本暂停。请恢复窗口以继续。")
                self.state = BotState.PAUSED
            self._interruptible_sleep(2.0)
            return

        if self.state == BotState.PAUSED:
            logger.info("窗口已恢复，脚本继续运行")
            if self.config.execution_mode == "task_queue":
                self.state = BotState.TASK_QUEUE
            else:
                self.state = BotState.KEY_LOOP

        self._tick_count += 1

        if self.config.debug and self.frame_callback and self._tick_count % 3 == 0:
            img = capture_window(self.hwnd)
            if img and img.size != (1, 1):
                w, h = img.size
                scale = min(500 / w, 1.0)
                if scale < 1.0:
                    preview = img.resize(
                        (int(w * scale), int(h * scale)),
                        Image.Resampling.LANCZOS
                    )
                else:
                    preview = img
                self.frame_callback(preview, [], [])

        if self.state == BotState.KEY_LOOP:
            self._handle_key_loop()
        elif self.state == BotState.TASK_QUEUE:
            self._handle_task_queue()

        self._interruptible_sleep(random.uniform(*self.config.loop_delay))

    # ------------------------------------------------------------------
    # 状态处理
    # ------------------------------------------------------------------

    def _handle_key_loop(self) -> None:
        """纯按键循环模式：按配置循环发送技能/拾取键。"""
        if not self.config.enable_key_loop:
            return

        if self.config.attack_keys:
            for rnd in range(self.config.attack_rounds):
                if not self._running:
                    return
                for key in self.config.attack_keys:
                    if not self._running:
                        return
                    logger.debug("按键循环 (轮次 %d/%d, 键码 0x%02X)",
                                rnd + 1, self.config.attack_rounds, key)
                    send_key(self.hwnd, key, mode=self.config.input_mode)
                    if not self._interruptible_sleep(random.uniform(*self.config.attack_delay)):
                        return

        if self.config.enable_pickup and self._running:
            logger.debug("按键循环 拾取 (键码 0x%02X)", self.config.pickup_key)
            send_key(self.hwnd, self.config.pickup_key, mode=self.config.input_mode)
            self._interruptible_sleep(random.uniform(0.3, 0.6))

    def _handle_task_queue(self) -> None:
        """任务队列模式：顺序任务与独立任务均按时间分片执行，每 tick 各推进一步。"""
        if self.task_queue is None:
            logger.warning("任务队列为空，请先在编辑器中创建任务")
            return

        mode = self.config.input_mode

        seq_tasks = self.task_queue.get_sequential_enabled()
        if seq_tasks:
            if self._seq_task_index >= len(seq_tasks):
                self._seq_task_index = 0
                self._seq_state = {"event_idx": 0, "repeat_idx": 0, "wait_until": 0.0}
            task = seq_tasks[self._seq_task_index]
            if self._running:
                finished = self._advance_task_step(task, self._seq_state, mode, prefix="")
                if finished:
                    self._seq_task_index += 1
                    self._seq_state = {"event_idx": 0, "repeat_idx": 0, "wait_until": 0.0}
                    if self._seq_task_index >= len(seq_tasks):
                        self._seq_loop_completed += 1
                        if self.task_queue.loop_forever:
                            self._seq_task_index = 0
                            logger.debug("顺序任务第 %d 轮完成，继续循环", self._seq_loop_completed)
                        else:
                            if self._seq_loop_completed >= self.task_queue.loop_count:
                                logger.info("顺序任务全部执行完毕（共 %d 轮）", self._seq_loop_completed)
                                self._running = False
                            else:
                                self._seq_task_index = 0
                                logger.info("顺序任务第 %d/%d 轮完成，继续下一轮",
                                            self._seq_loop_completed, self.task_queue.loop_count)

        ind_tasks = self.task_queue.get_independent_enabled()
        for task in ind_tasks:
            if not self._running:
                return
            self._advance_independent_task(task, mode)

    def _advance_task_step(self, task: Task, state: dict, mode: str, prefix: str = "") -> bool:
        """推进任务一个事件步（时间分片）。

        每 tick 调用一次，只执行当前事件，等待类事件设置 wait_until 后返回。
        事件执行完自动推进索引，所有 repeat 轮次完成返回 True。

        Args:
            task: 任务对象。
            state: 任务执行状态字典（event_idx, repeat_idx, wait_until）。
            mode: 输入模式。
            prefix: 日志前缀（如 "[独立] "）。

        Returns:
            True 表示该任务的所有 repeat 轮次都已完成，False 表示还在执行中。
        """
        events = task.events
        if not events:
            return True

        if state["wait_until"] > time.time():
            return False

        state["wait_until"] = 0.0

        if state["event_idx"] == 0 and state["repeat_idx"] == 0:
            if prefix:
                logger.info("%s任务 '%s' 启动", prefix, task.name)
            else:
                logger.info("执行任务: %s (轮次 1/%d)", task.name, task.repeat)

        event = events[state["event_idx"]]

        if not self.task_queue.is_event_blocked(event):
            etype = event.type
            if etype == "keydown":
                vk_codes = event.vk_codes
                logger.info("%s↓ %s", prefix, event.get_display_text())
                send_keys_down(self.hwnd, vk_codes, mode=mode)
                self._pressed_keys.update(vk_codes)
            elif etype == "keyup":
                vk_codes = event.vk_codes
                logger.info("%s↑ %s", prefix, event.get_display_text())
                send_keys_up(self.hwnd, vk_codes, mode=mode)
                for vk in vk_codes:
                    self._pressed_keys.discard(vk)
            elif etype == "keyclick":
                vk_codes = event.vk_codes
                logger.info("%s↕ %s", prefix, event.get_display_text())
                send_keys(self.hwnd, vk_codes, mode=mode)
            elif etype == "wait":
                wait_s = event.ms / 1000.0
                logger.debug("%s⏱ 等待 %dms", prefix, event.ms)
                state["wait_until"] = time.time() + wait_s
            elif etype == "wait_random":
                wait_s = random.uniform(event.min_ms, event.max_ms) / 1000.0
                logger.debug("%s⏱ 随机等待 %.0fms", prefix, wait_s * 1000)
                state["wait_until"] = time.time() + wait_s
            if etype in ("keydown", "keyup", "keyclick"):
                interval_ms = task.get_action_interval_ms()
                if interval_ms > 0:
                    state["wait_until"] = time.time() + (interval_ms / 1000.0)

        state["event_idx"] += 1

        if state["event_idx"] >= len(events):
            state["event_idx"] = 0
            state["repeat_idx"] += 1
            if state["repeat_idx"] >= task.repeat:
                state["repeat_idx"] = 0
                if prefix:
                    logger.info("%s任务 '%s' 一轮完成，继续循环", prefix, task.name)
                else:
                    logger.info("任务 '%s' 执行完成（共 %d 轮）", task.name, task.repeat)
                return True
            else:
                if not prefix:
                    logger.info("执行任务: %s (轮次 %d/%d)",
                                task.name, state["repeat_idx"] + 1, task.repeat)

        return False

    def _advance_independent_task(self, task: Task, mode: str) -> None:
        """独立任务每 tick 推进一个事件（时间分片调度）。

        每个独立任务拥有独立的状态跟踪，每个 tick 只执行一个事件，
        这样独立任务之间以及与顺序任务之间可以"并发"执行——每个 tick
        各推进一小步，不会互相阻塞。

        Args:
            task: 独立任务对象。
            mode: 输入模式。
        """
        task_id = id(task)
        state = self._ind_task_states.get(task_id)
        if state is None:
            state = {"event_idx": 0, "repeat_idx": 0, "wait_until": 0.0}
            self._ind_task_states[task_id] = state

        self._advance_task_step(task, state, mode, prefix="[独立] ")
