直接结论（先把我做了什么、接下来要做的方向说清楚）  
我已全面检查了仓库的所有顶层文件与关键源码（config.py、task_queue.py、window.py、main.py、bot_worker.py、TaskConfig.json、config.json、start.bat、requirements.txt 等），识别了模块边界、运行流程、重要数据结构与若干明显的不一致/小 bug。下面先给出规范化的代码仓库概览（包含证据级别的文件/符号引用），然后给出详尽的无损重构/升级计划与分步实现建议（保证功能不变、兼容现有行为并尽可能修复明显错误）。

## What this is
这是一个面向 Windows 的游戏辅助（挂机）程序，主要用于在指定游戏窗口内自动发送按键和执行预定义的“任务队列”，目标用户是需要做按键循环/脚本化操作的玩家（示例默认针对“QQ三国”窗口）。运行时可以用命令行或 PyQt GUI 启动，支持两种执行模式（简单按键循环与任务队列模式）、按键屏蔽、动作间隔控制与调试画面回调。

### Stack
- Language(s): Python (主)，少量 Batchfile (启动脚本)
- Framework / runtime: CPython on Windows; PyQt5 用于 GUI
- Notable libraries: pydirectinput（按键发送）, pywin32（窗口/WinAPI）, Pillow（图像处理）, PyQt5（GUI）, keyboard（全局热键）

## How it's organized
（仓库顶层结构与注释 — 基于我已读取的文件）
```
.gitignore
TaskConfig.json        # 默认/示例任务队列 JSON
config.json            # 运行时配置 JSON（项目根）
config.py              # 配置管理：BotConfig 数据类 + VK_MAP / name_to_vk / vk_to_name
task_queue.py          # 任务/事件模型：TaskEvent, Task, TaskQueue（序列化/反序列化/执行辅助）
window.py              # Windows 窗口与按键发送封装（get_hwnd, list_windows, set_foreground, send_key*, capture_window）
main.py                # 主控制器 SanguoBot：主循环、状态机、两种运行模式（KEY_LOOP / TASK_QUEUE）
bot_worker.py          # Qt 子线程包装：BotWorker (QThread) + QtLogHandler，用于 GUI 集成运行脚本
gui.py                 # （存在但未深入阅读 GUI 细节 — 有 PyQt 界面入口）
requirements.txt
start.bat              # Windows 启动脚本（尝试以管理员权限启动并调用 gui.py）
```

How it fits together (运行/数据流，关键模块)  
- 配置（config.BotConfig）从 config.json 读取，GUI 或命令行可修改并保存。BotConfig 提供属性访问与序列化方法，并有若干 runtime 标志（例如 _hwnd_dirty）。
- 任务队列通过 task_queue.TaskQueue（和 Task/TaskEvent）表示并序列化为 JSON（TaskConfig.json 为示例）。TaskEvent 提供 vk_code 解析（通过 config.name_to_vk）。
- window.py 提供与 Windows 窗口交互与按键发送：支持三种模式（foreground / postmsg / focus），并使用 pydirectinput 或 PostMessage 实现。SanguoBot 调用这些 API 来发送 keydown/keyup/keyclick。
- main.SanguoBot 负责主循环：维护状态机（KEY_LOOP / TASK_QUEUE / PAUSED），处理热更新的 config、测试按键队列、截图回调（debug 模式），以及按键发送逻辑与按键释放（释放已按下的键避免卡键）。
- bot_worker.BotWorker 把 SanguoBot 封装到 QThread 中，通过 Qt 信号把日志与帧发送回 GUI。

## How to run it
从代码注释与 start.bat 推断的最短启动步骤（在 Windows 上）：
- 建议在虚拟环境中安装依赖：
  - python -m pip install -r requirements.txt
- 命令行运行主脚本：
  - python main.py
  - python main.py --debug            # 启用调试可视化
  - 或使用 GUI：python gui.py 或双击 start.bat（start.bat 期望 venv\Scripts\pythonw.exe）
- 运行时使用 config.json（项目根）作为持久化设置；TaskConfig.json 为任务队列示例。

（需要注意：start.bat 中会尝试以管理员权限重启自身，然后以 venv\Scripts\pythonw.exe 启动 gui.py。）

## 我在代码中发现的具体符号和关键点（证据级）
- 数据/模型
  - task_queue.py: TaskEvent, Task, TaskQueue.create_default(), TaskQueue.load/save/to_json/from_json、is_event_blocked、get_action_interval_ms 等。
  - config.py: VK_MAP、VK_REVERSE_MAP、vk_to_name(), name_to_vk(), BotConfig（字段见文件）。
- 运行逻辑
  - main.py: class SanguoBot (run, stop, _tick, _handle_key_loop, _handle_task_queue)、BotState enum、main() 入口。
- GUI 线程
  - bot_worker.py: BotWorker (QThread)、QtLogHandler、frame_signal 等。
- Windows I/O
  - window.py: get_hwnd(), list_windows(), set_foreground(), send_key(), send_key_foreground/focus/postmsg、send_key_down/up、_press_vk(), capture_window()。

## 已发现的明显问题 / 不一致（优先级与修复建议）
这些是我在阅读源码时识别到，会在重构计划中一并修复以确保“无损升级”：

1. window.py __main__ 中的测试调用使用了错误的关键字参数：
   - 代码片段（lines ~306-308）：
     - send_key(hwnd, 0x31, foreground=False)
   - 问题：send_key 的签名是 (hwnd, vk_code, mode: str = "foreground")，没有 foreground 这个 kw，应该使用 mode 参数。例如改为 send_key(hwnd, 0x31, mode="postmsg") 或 mode="foreground"。这是运行时会抛 TypeError 的明显 bug，需要修复。

2. config.json 与 BotConfig 的序列化/反序列化不一致（持久化字段问题）：
   - BotConfig.load() 在读取时会过滤掉以 "_" 开头的字段（运行时标志），但 BotConfig.save() 只 pop("_hwnd_dirty") 而没有去除 _target_hwnd；因此保存后 config.json 中会包含 _target_hwnd，但下一次 load 时会被忽略，导致行为不一致或困惑。建议：
     - 保存时也排除所有以 "_" 开头的运行时字段，或明确将 _target_hwnd 列为可持久化字段并在 load 中允许读取（两者择一并记录在文档中）。

3. start.bat 假定存在 venv\Scripts\pythonw.exe；这对用户友好性不够（未检查 venv 存在或路径）。建议改为更稳健的启动脚本或在 README 中说明环境要求。

4. window.capture_window() 当前是个占位实现，返回 1x1 图片。若 GUI debug 模式依赖截图显示，需实现或明确文档标注不可用。

5. config.json 中 hotkey_toggle 的示例值看起来不合理（"── 功能键 ──"），应统一默认值为可用串（例如 "f12"），或者在 GUI 上验证输入。

6. window.send_key_postmsg 中对 scancode 的生成与 lParam 位域处理较脆弱（扩展键 E0 前缀只在部分位置考虑）。需要在重构时增加注释/测试，确保对常用按键（方向键、功能键）行为正确。

7. 缺少 README、测试、CI。没有单元测试覆盖 TaskQueue 序列化/反序列化、BotConfig load/save、TaskEvent vk 转换等关键逻辑。重构过程应补上这些测试来保证“无损”。

---

接下来：全面重构与升级计划（目标：模块化、可维护、逐步迁移、功能无损；尽量分小 PR/小步骤）  

总体原则
- 无损迁移：保留现有的外部行为（默认配置值、JSON 文件路径/格式、GUI API、start.bat 启动方式），并在重构阶段通过兼容层（module-level shim）逐步迁移调用方。
- 小步推进：每次 PR 聚焦一件事（移动模块、修复 bug、添加测试、重命名等），每步都要通过自动化测试或手动验证。
- 可测性：为关键逻辑（TaskQueue、TaskEvent、BotConfig、window 输入映射）添加单元测试，避免回归。
- 分层清晰：把“纯逻辑/模型”、“平台交互（WinAPI/pydirectinput）”、“GUI/线程”分离出明确边界。

建议的目标文件/包结构（重构后）
```
gameassistant/                    # new package
  __init__.py                     # 版本 & 导出常用符号（兼容旧导入）
  config.py                       # 迁移自 config.py（改进保存/加载一致性）
  models/
    __init__.py
    tasks.py                       # TaskEvent, Task, TaskQueue（来自 task_queue.py）
  platform/
    __init__.py
    window_win.py                  # Windows 专用实现（来自 window.py）
    window_base.py                 # 抽象接口（WindowController），便于后续测试/mock
  bot/
    __init__.py
    core.py                        # SanguoBot（来自 main.py），只依赖抽象接口
  worker/
    __init__.py
    qt_worker.py                   # BotWorker（来自 bot_worker.py）
  cli/
    main.py                        # thin CLI entry: parses args, loads config, creates SanguoBot
gui.py                             # keep top-level if it’s the GUI entry (可改为 gameassistant.gui)
data/
  TaskConfig.json                   # example data
  config.json                       # default persisted config
tests/
  test_task_queue.py
  test_config.py
  test_window_mapping.py
requirements.txt
start.bat (updated)
README.md
```

分步实施计划（每个步骤对应一个小 PR，便于回滚）
1. 基础准备（PR #1） — “包化 + 不动逻辑”  
   - 新建 gameassistant 包并把 config.py、task_queue.py、main.py、bot_worker.py、window.py 拆分放入对应子模块（如上结构）。  
   - 在每个被移动的原文件处保留一个短 shim 文件（例如旧顶层的 config.py 变为 from gameassistant.config import *），保证现有外部调用（如果用户直接运行 main.py、gui.py）在短期内不破坏。  
   - 在这个 PR 中修复明显的 TypeError（window.__main__ 的 foreground=False），并修复 config.save/load 的不一致（对以 "_" 开头字段的持久化规则做一致处理）。（这一步同时解决已识别的两个高优先级 bug）

2. 单元测试与 CI（PR #2） — “建立安全网”  
   - 添加 pytest、简单的 tests/（覆盖 TaskQueue JSON 序列化、BotConfig load/save、name_to_vk/vk_to_name 边界）。  
   - 添加 GitHub Actions CI：运行 lint、pytest。确保每次改动都有自动验证。

3. 抽象 platform 接口（PR #3） — “把 platform 依赖抽象化”  
   - 定义 window_base.py 中的 WindowController 接口（get_hwnd, send_key, send_key_down/up, capture_window, is_minimized, list_windows, set_foreground）。  
   - 把原 window.py 的实现迁移为 window_win.py，实现该接口。  
   - 修改 bot/core.py 使其依赖于抽象接口（依赖注入），便于单元测试和未来扩展到非-Windows 或模拟模式。

4. 重构 SanguoBot（PR #4） — “逻辑清晰化与可测性”  
   - 把 SanguoBot 提取到 gameassistant.bot.core，删除模块级副作用，确保通过注入 config 和 WindowController 运行。  
   - 增加更多日志点以便调试，确保原有的随机延迟/行为完全一致（默认值不变）。

5. GUI 与线程整合（PR #5）  
   - 把 BotWorker（Qt）迁移并改为使用新包路径，确保信号接口不变。  
   - GUI（gui.py）更新为导入新的模块或使用兼容 shim。手动验证 GUI 与子线程日志/帧信号行为一致。

6. 文档与示例（PR #6）  
   - 添加 README（如何安装、运行、如何调试），说明 config.json/TaskConfig.json 格式与字段（包括说明哪些字段是运行时字段不会被持久化）。  
   - 提供 start.bat 的改进版（检测 venv 或直接用 pythonw.exe，从而容错）。

7. 清理与升级（PR #7）  
   - 移除兼容 shim（在确认没有外部依赖仍使用旧导入后），完善类型注解、mypy 检查、格式化（black）、CI 增加 test coverage 阈值。  
   - 如果需要，把 window.capture_window 实现完善或把它标为已知未实现并在 GUI 上相应地降级显示。

确保“无损”策略（每步的具体措施）
- 每个 PR 在合并前都运行现有逻辑的手动回归用例（在 VM/Windows 上），尤其是：
  - 简单按键循环（KEY_LOOP）行为：默认 attack_keys 与 pickup_key 生效，按键间延迟及轮数一致。
  - 任务队列（TASK_QUEUE）行为：TaskConfig.json 的事件逐条发送（keydown/keyup/keyclick/wait/wait_random），事件屏蔽逻辑保持。
  - 最小动作间隔与随机化行为保持（TaskQueue.get_action_interval_ms 的行为不变）。
- 保留 JSON 文件格式兼容性：TaskConfig.json 的字段名/结构保持原样，BotConfig 的默认字段与默认值保持不变（除非用户显式修改）。
- 兼容层（shim）保证短期内外部脚本或用户习惯不会被破坏；最后才移除 shim。

优先级与估时（粗略）
- PR #1（包化 + 修复明显 bug + 小改动）：1-2 天（含本地验证）
- PR #2（测试 + CI）：0.5-1 天
- PR #3（抽象 platform）：1-2 天（需要手工验证 Windows API 行为）
- PR #4（重构 bot）：1-2 天
- PR #5（GUI 适配）：1-2 天（视 GUI 复杂程度）
- PR #6/7（文档/清理/提升质量）：1-2 天

我建议的首要动作（马上要做的事）
1. 立即修复两个高优先级的问题（在最小变更下）：
   - 把 window.py 的 __main__ 中 send_key(...) 调用改为使用 mode=...（避免 TypeError）。
   - 统一 config.save/load 的持久化策略（排除所有以 "_" 开头的运行时字段，或把 _target_hwnd 列为可持久化并允许 load）。
2. 在同一小 PR 中把 task_queue.py、config.py 包装进 gameassistant 包并添加基本单元测试（TaskQueue 序列化/反序列化）。建立 CI 后再做更大改动。

3 个建议性的具体问题以供我继续（请你回答其中任何一个，或都回答，这有助于我开始实施重构并生成具体补丁）：  
- 你希望我先把哪个优先级的问题修复并提交 PR？（1) 仅修复明显 bug 并加测试；2) 直接开始包化并添加兼容 shim；3) 先实现 CI + 测试再迁移）  
- 关于 config 中的运行时字段：你偏向把 _target_hwnd 保持可持久化（用户希望记住上次选择的句柄）还是把所有以 "_" 开头的字段都视为运行时并不持久化？  
- GUI 方面：你是否希望在重构中同步改进 GUI（例如让 GUI 依赖注入 window 控制器以支持“模拟模式”用于无窗口测试），还是保持 GUI 代码暂不改动以最小化风险？

如果你同意，我可以马上开始按“首要动作”做第一轮变更（生成具体的代码修改/PR 列表并按照小 PR 顺序实现）。