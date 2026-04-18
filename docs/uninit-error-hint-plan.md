# 未初始化错误提示优化方案

## 问题

`ccprofile_app/crypto.py:16` 中 `load_key()` 的未初始化错误提示硬编码了 `python ccprofile.py init`：

```python
print("错误: 未初始化。请先运行: python ccprofile.py init")
```

打包后的程序没有 Python 环境，用户无法执行 `python ccprofile.py init`。交互界面下也应给出更明确的指引。

## 现状分析

### 错误来源

`crypto.py:load_key()` 是唯一的未初始化检查点。所有需要加解密的操作（add/switch/list/show/edit/delete/current/teams 及全部 provider 命令）都通过 `storage.py` 间接调用 `load_key()`，触发时执行 `sys.exit(1)`。

### 两种运行场景

| 场景 | 入口 | 正确的初始化命令 |
|------|------|-----------------|
| Python 源码运行 | `python ccprofile.py init` | `python ccprofile.py init` |
| 打包程序运行 | `ccprofile init` | `ccprofile init` |

### 交互菜单中的表现

`menu.py` 的 `_execute_command()` 用 `except SystemExit: pass` 捕获退出，用户看到错误消息后菜单继续运行。但错误消息中的 `python ccprofile.py init` 对打包用户没有帮助。

## 修改方案

### 核心思路

运行时检测当前是否在 PyInstaller 打包环境中，动态生成正确的初始化命令提示。同时优化交互菜单中的体验。

### 修改 1：`ccprofile_app/crypto.py` — 动态生成初始化提示

```python
import sys

def _init_hint():
    """返回当前环境下正确的初始化命令。"""
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包环境
        exe = os.path.basename(sys.executable)
        return f"{exe} init"
    else:
        return "python ccprofile.py init"

def load_key():
    """加载 Fernet 密钥。"""
    if not KEY_FILE.exists():
        print(f"错误: 未初始化。请先运行: {_init_hint()}")
        sys.exit(1)
    return KEY_FILE.read_bytes().strip()
```

**说明：**
- `sys.frozen` 是 PyInstaller 打包时设置的属性，打包环境为 `True`，源码运行为 `False`
- `sys.executable` 在打包环境下指向可执行文件路径（如 `/path/to/ccprofile` 或 `C:\...\ccprofile.exe`），`os.path.basename` 提取文件名
- 源码环境保持原提示 `python ccprofile.py init`

### 修改 2：`ccprofile_app/menu.py` — 交互菜单未初始化友好提示

在交互菜单中，当检测到未初始化状态时，在菜单顶部显示醒目提示，并引导用户到"系统设置"中初始化：

```python
def interactive_menu():
    """交互式菜单主循环。"""
    # ... (commands_map, _execute_command 保持不变)

    print("\n  ccprofile — Claude Code 配置管理")

    current_menu = MAIN_MENU
    current_prompt = "请选择操作"

    while True:
        meta = load_meta() if KEY_FILE.exists() else {}
        active = meta.get("active", "")

        # 未初始化提示
        if not KEY_FILE.exists():
            from .crypto import _init_hint
            print("  ⚠ 系统尚未初始化，请先进入「系统设置」→「初始化」\n")
        elif active:
            print(f"  当前配置: {active}\n")

        # ... (后续逻辑保持不变)
```

**说明：**
- 在每次菜单循环渲染时检查 `KEY_FILE.exists()`，若不存在则显示醒目的初始化提示
- 提示指向交互菜单内的「系统设置 → 初始化」选项，而非命令行命令
- 已初始化但无活动配置时，不显示额外提示（和现有行为一致）

### 修改 3：`ccprofile_app/crypto.py` — 解密失败提示同步优化

```python
def decrypt_data(raw, key):
    """将加密字节解密为字典。"""
    try:
        return json.loads(Fernet(key).decrypt(raw).decode())
    except InvalidToken:
        print("错误: 解密失败，密钥可能不匹配或数据已损坏。请尝试重新初始化。")
        sys.exit(1)
```

将"请尝试重新初始化"作为补充提示，不涉及具体命令（因为解密失败通常意味着需要删除旧数据重新 `init`，两种环境操作相同）。

## 不修改的部分

| 文件 | 原因 |
|------|------|
| `commands.py` | 不直接包含初始化检查逻辑，无需修改 |
| `cli.py` | 命令行场景下错误消息由 `crypto.py` 统一输出，`cli.py` 只负责路由 |
| `storage.py` | 只调用 `load_key()`，不涉及提示消息 |

## 测试要点

1. **源码运行**：删除 `.profile_key` 后运行 `python ccprofile.py list`，确认提示为 `python ccprofile.py init`
2. **源码交互菜单**：删除 `.profile_key` 后运行 `python ccprofile.py`（无参数进入菜单），确认显示「系统设置 → 初始化」提示，选择其他操作时提示 `python ccprofile.py init`
3. **打包运行**：用 PyInstaller 打包后，删除 `.profile_key`，运行 `./ccprofile list`，确认提示为 `ccprofile init`
4. **打包交互菜单**：删除 `.profile_key` 后运行 `./ccprofile`，确认显示菜单内初始化引导
