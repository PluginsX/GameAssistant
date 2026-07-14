"""任务队列数据模型。

定义任务队列的完整数据结构，支持 JSON 序列化/反序列化，
供 GUI 编辑器和执行引擎共用。

事件类型（积木）：
    keydown       — 按键按下（按住不放）
    keyup         — 按键松开
    keyclick      — 按键单击（按下再松开）
    wait          — 固定等待（毫秒）
    wait_random   — 随机等待（最小~最大毫秒）
"""

import json
import logging
import os
import random
from dataclasses import dataclass, field
from typing import Optional

from gameassistant.config import name_to_vk
from gameassistant.paths import get_task_config_path

logger = logging.getLogger(__name__)

TASK_QUEUE_CONFIG_PATH = get_task_config_path()

# 有效的事件类型集合
VALID_EVENT_TYPES = {"keydown", "keyup", "keyclick", "wait", "wait_random"}

# 有效的任务类型集合
VALID_TASK_TYPES = {"sequential", "independent"}


def _clamp(value, lo, hi):
    """将数值限制在 [lo, hi] 范围内。"""
    return max(lo, min(hi, value))


@dataclass
class TaskEvent:
    """单个事件（积木块）。

    支持单一按键和复合按键（最多三个键的组合触发）。

    Attributes:
        type: 事件类型："keydown" / "keyup" / "keyclick" / "wait" / "wait_random"
        key: 单一按键名称（如 "1", "C", "Right"），仅 keydown/keyup/keyclick 使用
        keys: 复合按键列表（如 ["Ctrl", "Shift", "A"]），优先于 key
              最多支持 3 个键的组合。
        ms: 等待毫秒，仅 wait 使用
        min_ms: 最小等待毫秒，仅 wait_random 使用
        max_ms: 最大等待毫秒，仅 wait_random 使用
        comment: 备注信息（可选，不影响执行）
    """
    type: str = "keyclick"
    key: str = ""
    keys: list[str] = field(default_factory=list)
    ms: int = 100
    min_ms: int = 100
    max_ms: int = 300
    comment: str = ""

    @property
    def vk_code(self) -> int:
        """将 key 名称转为虚拟键码（向后兼容，返回首个按键的键码）。"""
        if self.keys:
            return name_to_vk(self.keys[0]) if self.keys[0] else 0
        return name_to_vk(self.key) if self.key else 0

    @property
    def vk_codes(self) -> list[int]:
        """获取所有按键的虚拟键码列表。

        优先返回 keys（复合按键）的键码列表，若为空则返回单一 key 的键码。
        """
        if self.keys:
            return [name_to_vk(k) for k in self.keys if k]
        if self.key:
            return [name_to_vk(self.key)]
        return []

    @property
    def display_key(self) -> str:
        """返回按键显示文本，如 "Ctrl+Shift+A" 或 "Space"。"""
        if self.keys:
            return "+".join(self.keys)
        return self.key

    def to_dict(self) -> dict:
        """转为 JSON 可序列化字典。"""
        d: dict = {"type": self.type}
        if self.type in ("keydown", "keyup", "keyclick"):
            if self.keys:
                d["keys"] = self.keys
            else:
                d["key"] = self.key
        elif self.type == "wait":
            d["ms"] = self.ms
        elif self.type == "wait_random":
            d["min"] = self.min_ms
            d["max"] = self.max_ms
        if self.comment:
            d["comment"] = self.comment
        return d

    @classmethod
    def validate_event_dict(cls, d: dict) -> list[str]:
        """校验事件字典，返回错误消息列表（为空表示完全有效）。

        检查项：类型是否合法、按键事件是否有 key/keys、
        wait 相关数值是否有效。
        """
        errors: list[str] = []
        if not isinstance(d, dict):
            return ["事件不是字典格式"]

        event_type = d.get("type", "")
        if not isinstance(event_type, str) or event_type not in VALID_EVENT_TYPES:
            errors.append(f"未知事件类型: {event_type!r}，跳过该事件")
            return errors  # 类型无效，后续检查无意义

        if event_type in ("keydown", "keyup", "keyclick"):
            key = d.get("key", "")
            keys = d.get("keys", [])
            has_combo = isinstance(keys, list) and any(k for k in keys)
            has_single = isinstance(key, str) and bool(key.strip())
            if not has_combo and not has_single:
                errors.append(f"{event_type} 事件缺少有效的 key 或 keys 字段")

            # 验证 keys 中的每一项都是字符串
            if has_combo:
                for i, k in enumerate(keys):
                    if not isinstance(k, str):
                        errors.append(f"keys[{i}] 类型错误: {type(k).__name__}")

        elif event_type == "wait":
            ms = d.get("ms", 0)
            if not isinstance(ms, (int, float)) or ms <= 0:
                errors.append(f"wait 事件的 ms 无效: {ms!r}，使用默认值 100")

        elif event_type == "wait_random":
            min_ms = d.get("min", 0)
            max_ms = d.get("max", 0)
            if not isinstance(min_ms, (int, float)) or min_ms < 0:
                errors.append(f"wait_random 的 min 无效: {min_ms!r}，使用默认值 100")
            if not isinstance(max_ms, (int, float)) or max_ms < 0:
                errors.append(f"wait_random 的 max 无效: {max_ms!r}，使用默认值 300")

        return errors

    @classmethod
    def from_dict(cls, d: dict) -> "TaskEvent":
        """从字典构造 TaskEvent。

        向后兼容：优先读取 keys（复合按键），否则读取 key（单一按键）。

        健壮性保证：
            - 未知类型 → 降级为 keyclick，key 置空
            - 无效数值 → 自动限幅到合理范围
            - 类型错误 → 使用默认值
        """
        if not isinstance(d, dict):
            return cls()

        event_type = d.get("type", "")
        if not isinstance(event_type, str) or event_type not in VALID_EVENT_TYPES:
            event_type = "keyclick"

        # 处理按键事件
        if event_type in ("keydown", "keyup", "keyclick"):
            keys_raw = d.get("keys", [])
            if isinstance(keys_raw, list) and any(isinstance(k, str) and k.strip() for k in keys_raw):
                valid_keys = [str(k) for k in keys_raw if isinstance(k, str) and k.strip()]
            else:
                valid_keys = []
            single_key = ""
            if not valid_keys:
                raw_key = d.get("key", "")
                single_key = str(raw_key).strip() if isinstance(raw_key, str) else ""
            return cls(
                type=event_type,
                key=single_key,
                keys=valid_keys,
                comment=str(d.get("comment", "")) if d.get("comment") else "",
            )

        # 处理等待事件
        if event_type == "wait":
            ms_raw = d.get("ms", 100)
            ms = _clamp(int(ms_raw), 10, 999999) if isinstance(ms_raw, (int, float)) else 100
            return cls(
                type="wait",
                ms=ms,
                comment=str(d.get("comment", "")) if d.get("comment") else "",
            )

        if event_type == "wait_random":
            min_raw = d.get("min", 100)
            max_raw = d.get("max", 300)
            min_ms = _clamp(int(min_raw), 10, 999999) if isinstance(min_raw, (int, float)) else 100
            max_ms = _clamp(int(max_raw), 10, 999999) if isinstance(max_raw, (int, float)) else 300
            return cls(
                type="wait_random",
                min_ms=min(min_ms, max_ms),
                max_ms=max(min_ms, max_ms),
                comment=str(d.get("comment", "")) if d.get("comment") else "",
            )

        return cls(type=event_type)

    def get_display_text(self) -> str:
        """返回用于 UI 显示的简短文本。"""
        key_text = self.display_key
        if self.type == "keydown":
            return f"\u2193 {key_text}"
        elif self.type == "keyup":
            return f"\u2191 {key_text}"
        elif self.type == "keyclick":
            return f"\u2195 {key_text}"
        elif self.type == "wait":
            return f"\u23F1 {self.ms}ms"
        elif self.type == "wait_random":
            return f"\u23F1 ~{self.min_ms}-{self.max_ms}ms"
        return "?"

    def get_color(self) -> str:
        """返回积木颜色（hex 格式）。"""
        colors = {
            "keydown": "#3B82F6",       # 蓝色
            "keyup": "#8B5CF6",         # 紫色
            "keyclick": "#10B981",      # 绿色
            "wait": "#F59E0B",          # 橙色
            "wait_random": "#F97316",   # 深橙
        }
        return colors.get(self.type, "#64748B")


@dataclass
class Task:
    """单个任务：有序事件列表。

    Attributes:
        name: 任务名称（用于 UI 显示）
        enabled: 是否启用（禁用的任务在执行时跳过）
        task_type: 任务类型："sequential"（顺序）/"independent"（独立）
            顺序任务：按列表顺序循环执行。
            独立任务：自我循环执行，与顺序任务及其他独立任务同步运行。
        repeat: 重复次数（1=执行1次，3=执行3次）
        events: 事件列表
    """
    name: str = "新任务"
    enabled: bool = True
    task_type: str = "sequential"
    repeat: int = 1
    events: list[TaskEvent] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "enabled": self.enabled,
            "task_type": self.task_type,
            "repeat": self.repeat,
            "events": [e.to_dict() for e in self.events],
        }

    @classmethod
    def validate_task_dict(cls, d: dict) -> list[str]:
        """校验任务字典，返回错误消息列表。"""
        errors: list[str] = []
        if not isinstance(d, dict):
            return ["任务不是字典格式"]

        name = d.get("name", "")
        if not isinstance(name, str) or not name.strip():
            errors.append("任务名称无效，使用默认名称")

        task_type = d.get("task_type", "sequential")
        if task_type not in VALID_TASK_TYPES:
            errors.append(f"未知任务类型: {task_type!r}，使用默认 sequential")

        events_raw = d.get("events", [])
        if not isinstance(events_raw, list):
            errors.append("events 字段不是列表格式，跳过该任务的所有事件")

        return errors

    @classmethod
    def from_dict(cls, d: dict) -> "Task":
        """从字典构造 Task。

        健壮性保证：
            - 无效事件自动丢弃（记录日志）
            - 未知字段使用默认值
            - 类型错误不会崩溃
        """
        if not isinstance(d, dict):
            return cls()

        name = d.get("name", "")
        if not isinstance(name, str) or not name.strip():
            name = "未命名任务"

        task_type = d.get("task_type", "sequential")
        if task_type not in VALID_TASK_TYPES:
            task_type = "sequential"

        repeat_raw = d.get("repeat", 1)
        repeat = _clamp(int(repeat_raw), 1, 999) if isinstance(repeat_raw, (int, float)) else 1

        raw_events = d.get("events", [])
        if not isinstance(raw_events, list):
            raw_events = []

        valid_events: list[TaskEvent] = []
        for i, ed in enumerate(raw_events):
            if not isinstance(ed, dict):
                continue
            errs = TaskEvent.validate_event_dict(ed)
            if errs:
                for err in errs:
                    logger.warning("任务 '%s' 事件[%d] 丢弃: %s", name, i, err)
            else:
                valid_events.append(TaskEvent.from_dict(ed))

        return cls(
            name=name,
            enabled=bool(d.get("enabled", True)),
            task_type=task_type,
            repeat=repeat,
            events=valid_events,
        )


@dataclass
class TaskQueue:
    """任务队列：有序任务列表 + 循环控制。

    Attributes:
        loop_forever: 是否无限循环执行整个队列
        tasks: 任务列表
        block_actions_enabled: 是否启用屏蔽动作列表
        blocked_actions: 屏蔽动作列表，格式如 ["Space:keyclick", "C:keyclick"]
        min_action_interval: 最小动作间隔时长(毫秒)，每个动作执行后强制等待
        min_action_interval_random: 是否启用随机最小动作间隔
        min_action_interval_min: 随机最小动作间隔的最小值(毫秒)
        min_action_interval_max: 随机最小动作间隔的最大值(毫秒)
    """
    loop_forever: bool = True
    tasks: list[Task] = field(default_factory=list)
    block_actions_enabled: bool = False
    blocked_actions: list[str] = field(default_factory=list)
    min_action_interval: int = 200
    min_action_interval_random: bool = False
    min_action_interval_min: int = 100
    min_action_interval_max: int = 300

    def to_dict(self) -> dict:
        return {
            "version": 1,
            "loop_forever": self.loop_forever,
            "tasks": [t.to_dict() for t in self.tasks],
            "block_actions_enabled": self.block_actions_enabled,
            "blocked_actions": list(self.blocked_actions),
            "min_action_interval": self.min_action_interval,
            "min_action_interval_random": self.min_action_interval_random,
            "min_action_interval_min": self.min_action_interval_min,
            "min_action_interval_max": self.min_action_interval_max,
        }

    def to_json(self, indent: int = 2) -> str:
        """序列化为 JSON 字符串。"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def validate_queue_dict(cls, d: dict) -> list[str]:
        """校验队列顶层字典，返回错误消息列表。"""
        errors: list[str] = []
        if not isinstance(d, dict):
            return ["配置文件根结构不是 JSON 对象"]

        tasks_raw = d.get("tasks", [])
        if not isinstance(tasks_raw, list):
            errors.append("tasks 字段不是列表格式，忽略所有任务定义")
        else:
            for i, td in enumerate(tasks_raw):
                if not isinstance(td, dict):
                    errors.append(f"tasks[{i}] 不是字典格式，跳过该任务")
                    continue
                task_errs = Task.validate_task_dict(td)
                for err in task_errs:
                    task_name = td.get("name", f"tasks[{i}]")
                    errors.append(f"任务 '{task_name}': {err}")

        blocked = d.get("blocked_actions", [])
        if not isinstance(blocked, (list, tuple)):
            errors.append("blocked_actions 格式无效，使用空列表")

        for field_name in ("min_action_interval", "min_action_interval_min",
                          "min_action_interval_max"):
            val = d.get(field_name, 0)
            if not isinstance(val, (int, float)) or val < 0:
                errors.append(f"{field_name} 值无效: {val!r}，使用默认值")

        return errors

    @classmethod
    def from_dict(cls, d: dict) -> "TaskQueue":
        """从字典构造 TaskQueue。

        健壮性保证：
            - 无效格式的字段自动使用默认值
            - 无效任务跳过（记录日志）
            - 类型错误不会崩溃
        """
        if not isinstance(d, dict):
            return cls()

        raw_tasks = d.get("tasks", [])
        if not isinstance(raw_tasks, list):
            raw_tasks = []

        valid_tasks: list[Task] = []
        for i, td in enumerate(raw_tasks):
            if not isinstance(td, dict):
                continue
            task_errs = Task.validate_task_dict(td)
            if task_errs:
                task_name = td.get("name", f"tasks[{i}]")
                for err in task_errs:
                    logger.warning("任务 '%s' 丢弃: %s", task_name, err)
            valid_tasks.append(Task.from_dict(td))

        blocked_raw = d.get("blocked_actions", [])
        if isinstance(blocked_raw, (list, tuple)):
            blocked_actions = [str(x) for x in blocked_raw if isinstance(x, (str, int, float))]
        else:
            blocked_actions = []

        def _safe_int(val, default):
            return _clamp(int(val), 0, 99999) if isinstance(val, (int, float)) else default

        return cls(
            loop_forever=bool(d.get("loop_forever", True)),
            tasks=valid_tasks,
            block_actions_enabled=bool(d.get("block_actions_enabled", False)),
            blocked_actions=blocked_actions,
            min_action_interval=_safe_int(d.get("min_action_interval"), 200),
            min_action_interval_random=bool(d.get("min_action_interval_random", False)),
            min_action_interval_min=_safe_int(d.get("min_action_interval_min"), 100),
            min_action_interval_max=_safe_int(d.get("min_action_interval_max"), 300),
        )

    @classmethod
    def from_json(cls, json_str: str) -> "TaskQueue":
        """从 JSON 字符串反序列化。"""
        d = json.loads(json_str)
        return cls.from_dict(d)

    @classmethod
    def load(cls, path: str) -> "TaskQueue":
        """从文件加载。"""
        with open(path, "r", encoding="utf-8") as f:
            return cls.from_json(f.read())

    def save(self, path: str) -> None:
        """保存到文件。"""
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.to_json())

    @classmethod
    def load_safe(cls, path: str) -> tuple["TaskQueue", list[str]]:
        """从文件安全加载，返回 (TaskQueue, warnings)。

        和 load() 的区别：
            - 执行完整校验，收集所有警告信息
            - 即使顶层 JSON 无效也返回一个有效的默认 TaskQueue
            - 永远不会抛出异常

        Args:
            path: JSON 文件路径。

        Returns:
            (TaskQueue, warnings) 元组。
            warnings 包含所有修复/丢弃的详细信息，GUI 可据此展示给用户。
        """
        warnings: list[str] = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        except (FileNotFoundError, PermissionError, OSError) as e:
            return cls(), [f"无法读取配置文件: {e}"]

        try:
            d = json.loads(content)
        except json.JSONDecodeError as e:
            return cls(), [f"JSON 解析失败: {e}，已创建默认配置"]

        if not isinstance(d, dict):
            return cls(), ["配置文件根结构不是 JSON 对象，已创建默认配置"]

        queue_errs = cls.validate_queue_dict(d)
        warnings.extend(queue_errs)

        tq = cls.from_dict(d)

        # 检查是否有完全空的任务（无有效事件）
        empty_tasks = [t for t in tq.tasks if not t.events]
        if empty_tasks:
            names = ", ".join(f"'{t.name}'" for t in empty_tasks)
            warnings.append(f"以下任务无有效事件: {names}")
            tq.tasks = [t for t in tq.tasks if t.events]

        return tq, warnings

    def get_enabled_tasks(self) -> list[Task]:
        """返回所有已启用的任务。"""
        return [t for t in self.tasks if t.enabled]

    def get_sequential_enabled(self) -> list[Task]:
        """返回所有已启用的顺序类型任务。"""
        return [t for t in self.tasks if t.enabled and t.task_type == "sequential"]

    def get_independent_enabled(self) -> list[Task]:
        """返回所有已启用的独立类型任务。"""
        return [t for t in self.tasks if t.enabled and t.task_type == "independent"]

    def is_event_blocked(self, event: TaskEvent) -> bool:
        """判断事件是否在屏蔽列表中。

        屏蔽格式：
            "KeyName:event_type"             — 单一按键，如 "Space:keyclick"
            "Key1+Key2:event_type"           — 复合按键，如 "Ctrl+Shift+A:keyclick"
        仅按键类事件（keydown/keyup/keyclick）会被屏蔽，等待类事件不受影响。
        """
        if not self.block_actions_enabled:
            return False
        if event.type not in ("keydown", "keyup", "keyclick"):
            return False
        event_key_upper = event.display_key.upper() if event.display_key else ""
        for blocked in self.blocked_actions:
            parts = blocked.split(":", 1)
            if len(parts) == 2:
                b_key, b_type = parts[0].strip().upper(), parts[1].strip().lower()
                if b_key == event_key_upper and b_type == event.type:
                    return True
        return False

    def execute_wait(self, event: TaskEvent) -> float:
        """执行等待事件，返回实际等待秒数。"""
        if event.type == "wait":
            return event.ms / 1000.0
        elif event.type == "wait_random":
            return random.uniform(event.min_ms, event.max_ms) / 1000.0
        return 0.0

    def get_action_interval_ms(self) -> int:
        """获取动作间隔时长（毫秒），若启用随机则返回随机值。"""
        if self.min_action_interval_random:
            return random.randint(
                min(self.min_action_interval_min, self.min_action_interval_max),
                max(self.min_action_interval_min, self.min_action_interval_max)
            )
        return self.min_action_interval

    @classmethod
    def create_default(cls) -> "TaskQueue":
        """创建一个默认任务队列示例。"""
        return cls(
            loop_forever=True,
            tasks=[
                Task(
                    name="攻击循环",
                    enabled=True,
                    repeat=1,
                    events=[
                        TaskEvent(type="keyclick", keys=["Ctrl", "Shift", "A"]),
                        TaskEvent(type="wait_random", min_ms=200, max_ms=400),
                        TaskEvent(type="keyclick", key="2"),
                        TaskEvent(type="wait_random", min_ms=200, max_ms=400),
                        TaskEvent(type="keyclick", key="3"),
                        TaskEvent(type="wait", ms=500),
                        TaskEvent(type="keyclick", key="Space"),
                        TaskEvent(type="wait", ms=1000),
                    ],
                ),
            ],
        )
