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
import os
import random
from dataclasses import dataclass, field
from typing import Optional

from gameassistant.config import name_to_vk

# 项目根目录（TaskConfig.json 始终位于仓库根目录）
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TASK_QUEUE_CONFIG_PATH = os.path.join(_PROJECT_ROOT, "TaskConfig.json")


@dataclass
class TaskEvent:
    """单个事件（积木块）。

    Attributes:
        type: 事件类型："keydown" / "keyup" / "keyclick" / "wait" / "wait_random"
        key: 按键名称（如 "1", "C", "Right"），仅 keydown/keyup/keyclick 使用
        ms: 等待毫秒，仅 wait 使用
        min_ms: 最小等待毫秒，仅 wait_random 使用
        max_ms: 最大等待毫秒，仅 wait_random 使用
        comment: 备注信息（可选，不影响执行）
    """
    type: str = "keyclick"
    key: str = ""
    ms: int = 100
    min_ms: int = 100
    max_ms: int = 300
    comment: str = ""

    @property
    def vk_code(self) -> int:
        """将 key 名称转为虚拟键码。"""
        return name_to_vk(self.key) if self.key else 0

    def to_dict(self) -> dict:
        """转为 JSON 可序列化字典。"""
        d: dict = {"type": self.type}
        if self.type in ("keydown", "keyup", "keyclick"):
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
    def from_dict(cls, d: dict) -> "TaskEvent":
        """从字典构造 TaskEvent。"""
        return cls(
            type=d.get("type", "keyclick"),
            key=d.get("key", ""),
            ms=d.get("ms", 100),
            min_ms=d.get("min", 100),
            max_ms=d.get("max", 300),
            comment=d.get("comment", ""),
        )

    def get_display_text(self) -> str:
        """返回用于 UI 显示的简短文本。"""
        if self.type == "keydown":
            return f"\u2193 {self.key}"
        elif self.type == "keyup":
            return f"\u2191 {self.key}"
        elif self.type == "keyclick":
            return f"\u2195 {self.key}"
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
        repeat: 重复次数（1=执行1次，3=执行3次）
        events: 事件列表
    """
    name: str = "新任务"
    enabled: bool = True
    repeat: int = 1
    events: list[TaskEvent] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "enabled": self.enabled,
            "repeat": self.repeat,
            "events": [e.to_dict() for e in self.events],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Task":
        return cls(
            name=d.get("name", "新任务"),
            enabled=d.get("enabled", True),
            repeat=d.get("repeat", 1),
            events=[TaskEvent.from_dict(e) for e in d.get("events", [])],
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
    def from_dict(cls, d: dict) -> "TaskQueue":
        return cls(
            loop_forever=d.get("loop_forever", True),
            tasks=[Task.from_dict(t) for t in d.get("tasks", [])],
            block_actions_enabled=d.get("block_actions_enabled", False),
            blocked_actions=list(d.get("blocked_actions", [])),
            min_action_interval=d.get("min_action_interval", 200),
            min_action_interval_random=d.get("min_action_interval_random", False),
            min_action_interval_min=d.get("min_action_interval_min", 100),
            min_action_interval_max=d.get("min_action_interval_max", 300),
        )

    @classmethod
    def from_json(cls, json_str: str) -> "TaskQueue":
        """从 JSON 字符串反序列化。"""
        d = json.loads(json_str)
        return cls.from_dict(d)

    def save(self, path: str) -> None:
        """保存到文件。"""
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.to_json())

    @classmethod
    def load(cls, path: str) -> "TaskQueue":
        """从文件加载。"""
        with open(path, "r", encoding="utf-8") as f:
            return cls.from_json(f.read())

    def get_enabled_tasks(self) -> list[Task]:
        """返回所有已启用的任务。"""
        return [t for t in self.tasks if t.enabled]

    def is_event_blocked(self, event: TaskEvent) -> bool:
        """判断事件是否在屏蔽列表中。

        屏蔽格式："KeyName:event_type"，如 "Space:keyclick", "C:keydown"
        仅按键类事件（keydown/keyup/keyclick）会被屏蔽，等待类事件不受影响。
        """
        if not self.block_actions_enabled:
            return False
        if event.type not in ("keydown", "keyup", "keyclick"):
            return False
        key_upper = event.key.upper() if event.key else ""
        for blocked in self.blocked_actions:
            parts = blocked.split(":", 1)
            if len(parts) == 2:
                b_key, b_type = parts[0].strip().upper(), parts[1].strip().lower()
                if b_key == key_upper and b_type == event.type:
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
                        TaskEvent(type="keyclick", key="1"),
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
