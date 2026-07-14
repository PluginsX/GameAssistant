"""配置管理模块。

定义 BotConfig 数据类，集中管理挂机脚本的全部运行参数。
支持 JSON 持久化（config.json），供 GUI 与命令行入口共用。
同时提供虚拟键码与友好名称的映射表，便于 GUI 下拉选择与存储互转。
"""

import json
import os
from dataclasses import dataclass, field, asdict

from gameassistant.paths import get_config_path

CONFIG_PATH = get_config_path()

# ---------------------------------------------------------------------------
# 虚拟键码映射表（供 GUI 显示与存储互转）
# 格式: "友好名称" -> vk_code
# ---------------------------------------------------------------------------
VK_MAP: dict[str, int] = {
    # 数字键 0-9
    **{str(i): 0x30 + i for i in range(10)},
    # 字母键 A-Z
    **{chr(c): c for c in range(0x41, 0x5B)},
    # 功能键 F1-F12
    **{f"F{i}": 0x70 + i - 1 for i in range(1, 13)},
    # 控制键
    "Space": 0x20,
    "Enter": 0x0D,
    "Tab": 0x09,
    "Esc": 0x1B,
    "Shift": 0x10,
    "Ctrl": 0x11,
    "Alt": 0x12,
    "Backspace": 0x08,
    # 方向键
    "Left": 0x25,
    "Up": 0x26,
    "Right": 0x27,
    "Down": 0x28,
}

# 反向映射: vk_code -> "友好名称"
VK_REVERSE_MAP: dict[int, str] = {v: k for k, v in VK_MAP.items()}


def vk_to_name(vk_code: int) -> str:
    """将虚拟键码转为友好名称，未匹配则返回十六进制字符串。"""
    return VK_REVERSE_MAP.get(vk_code, f"0x{vk_code:02X}")


def name_to_vk(name: str) -> int:
    """将友好名称转为虚拟键码，未匹配则尝试解析十六进制。"""
    if name in VK_MAP:
        return VK_MAP[name]
    # 兼容直接输入十六进制（如 "0x41"）
    try:
        return int(name, 16)
    except (ValueError, TypeError):
        raise ValueError(f"无法识别的按键名称: {name}")


@dataclass
class BotConfig:
    """挂机脚本全部运行参数。

    功能开关（解耦设计，允许自由配置按键循环）：
        enable_key_loop: 是否启用按键循环输入。关闭时不会发送任何按键。
        enable_pickup: 是否在按键循环中发送拾取键。关闭时只发技能键。

    Attributes:
        window_title: 游戏窗口标题（FindWindow 精确/模糊匹配）。
        attack_keys: 技能快捷键的虚拟键码列表（如 [0x31, 0x32, 0x33] 表示 1/2/3）。
        pickup_key: 拾取快捷键的虚拟键码（如 0x41 表示 A）。
        loop_delay_min: 主循环随机延迟下限（秒）。
        loop_delay_max: 主循环随机延迟上限（秒）。
        attack_delay_min: 技能间随机延迟下限（秒）。
        attack_delay_max: 技能间随机延迟上限（秒）。
        attack_rounds: 每次攻击循环释放技能的轮数。
        debug: 是否开启调试可视化窗口。
    """

    # 功能开关（解耦设计）
    enable_key_loop: bool = True      # 是否启用按键循环输入（默认开启）
    enable_pickup: bool = True        # 按键循环中是否发送拾取键

    window_title: str = "QQ三国"
    attack_keys: list[int] = field(default_factory=lambda: [0x31, 0x32, 0x33])
    pickup_key: int = 0x41
    loop_delay_min: float = 0.5
    loop_delay_max: float = 1.0
    attack_delay_min: float = 0.2
    attack_delay_max: float = 0.4
    attack_rounds: int = 3
    debug: bool = False
    input_mode: str = "postmsg"  # foreground / postmsg / focus
    execution_mode: str = "simple"  # simple / task_queue
    auto_dpi_scale: bool = True     # 自适应屏幕DPI缩放（默认开启）

    # 全局热键
    hotkey_enabled: bool = True      # 是否启用全局热键
    hotkey_toggle: str = "f12"       # 启动/停止切换热键（keyboard 库格式，小写）

    # 运行时标志：窗口标题热更新后需重新绑定 hwnd（不持久化）
    _hwnd_dirty: bool = field(default=False, compare=False, repr=False)
    # 运行时：用户手动选择的窗口句柄，0 表示自动按标题查找（不持久化）
    _target_hwnd: int = field(default=0, compare=False, repr=False)

    @property
    def loop_delay(self) -> tuple[float, float]:
        """主循环随机延迟范围元组，兼容现有代码风格。"""
        return (self.loop_delay_min, self.loop_delay_max)

    @property
    def attack_delay(self) -> tuple[float, float]:
        """技能间随机延迟范围元组，兼容现有代码风格。"""
        return (self.attack_delay_min, self.attack_delay_max)

    @classmethod
    def load(cls, path: str = CONFIG_PATH) -> "BotConfig":
        """从 JSON 文件加载配置，文件不存在或损坏返回默认值。

        Args:
            path: 配置文件路径，默认为项目根目录下的 config.json。

        Returns:
            BotConfig 实例。
        """
        if not os.path.exists(path):
            return cls()

        # 预设合法字段名
        valid_keys = {k for k in cls.__dataclass_fields__ if not k.startswith("_")}

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return cls()

        # 过滤：只保留合法的持久化字段
        filtered = {}
        for k, v in data.items():
            if k in valid_keys:
                filtered[k] = v

        # 防御：修正明显损坏的热键值
        if "hotkey_toggle" in filtered:
            val = filtered["hotkey_toggle"]
            if not val or "\u2500" in str(val) or not isinstance(val, str):
                filtered["hotkey_toggle"] = "f12"

        try:
            return cls(**filtered)
        except (TypeError, ValueError) as e:
            import logging
            logging.getLogger(__name__).warning(
                "配置文件字段不兼容，使用默认值: %s", e
            )
            return cls()

    def save(self, path: str = CONFIG_PATH) -> None:
        """保存配置到 JSON 文件。

        Args:
            path: 配置文件路径，默认为项目根目录下的 config.json。
        """
        data = asdict(self)
        # 不持久化所有以 "_" 开头的运行时标志
        keys_to_remove = [k for k in data if k.startswith("_")]
        for k in keys_to_remove:
            data.pop(k, None)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def apply_from(self, other: "BotConfig") -> None:
        """将另一个配置对象的字段值热更新到本对象（运行时生效）。

        逐字段赋值而非替换引用，保证 Bot 持有的 config 对象不变。
        attack_keys 整体替换引用，避免原地修改导致的迭代问题。

        Args:
            other: 包含新配置值的 BotConfig 对象。
        """
        # 功能开关（热更新生效）
        self.enable_key_loop = other.enable_key_loop
        self.enable_pickup = other.enable_pickup

        self.window_title = other.window_title
        self.attack_keys = list(other.attack_keys)  # 整体替换引用
        self.pickup_key = other.pickup_key
        self.loop_delay_min = other.loop_delay_min
        self.loop_delay_max = other.loop_delay_max
        self.attack_delay_min = other.attack_delay_min
        self.attack_delay_max = other.attack_delay_max
        self.attack_rounds = other.attack_rounds
        self.debug = other.debug
        self.input_mode = other.input_mode
        self.execution_mode = other.execution_mode
        self.auto_dpi_scale = other.auto_dpi_scale
        self.hotkey_enabled = other.hotkey_enabled
        self.hotkey_toggle = other.hotkey_toggle
        self._hwnd_dirty = True

    # ------------------------------------------------------------------
    # 按键管理辅助方法（供 GUI 侦听式配置调用）
    # ------------------------------------------------------------------

    def set_attack_key(self, index: int, vk_code: int) -> None:
        """设置指定索引位置的技能键虚拟键码。

        Args:
            index: 技能键索引（0-based）。
            vk_code: 虚拟键码。
        """
        if index < len(self.attack_keys):
            self.attack_keys[index] = vk_code

    def add_attack_key(self, vk_code: int = 0x31) -> None:
        """追加一个技能键。

        Args:
            vk_code: 虚拟键码，默认 0x31（'1'）。
        """
        self.attack_keys.append(vk_code)

    def remove_attack_key(self, index: int) -> None:
        """移除指定索引位置的技能键（允许删除到 0 个）。

        Args:
            index: 技能键索引（0-based）。
        """
        if 0 <= index < len(self.attack_keys) and len(self.attack_keys) > 0:
            self.attack_keys.pop(index)
