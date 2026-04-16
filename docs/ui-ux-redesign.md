# UI/UX 重新设计方案

## 1. 核心问题

用户主要通过交互式菜单（`ccprofile` 无参数启动）使用工具。当前交互式菜单体验割裂：

**菜单导航** → 箭头选择，视觉精致（reverse video 高亮、dim 提示文字）
**执行结果** → 突然变成裸 `print()` 文本，无颜色无边框
**交互输入** → 突然变成 `input()` 手打 / `input("y/N")` 确认

这种「精致 → 粗糙 → 精致」的反复跳转，是体验不优雅的根源。

---

## 2. 交互式菜单中的具体问题

### 2.1 显示类命令 — 裸文本输出

用户操作路径：主菜单 → 查看配置 ←→ → 列出所有配置

**当前 `list` 输出**（`commands.py:237-272`）：
```
   名称               模式      URL/映射                                 模型      通知
  ----------------------------------------------------------------------------------
 * home                单一      https://api.anthropic.com                 opus
   work                单一      https://proxy.example.com                 sonnet     🔔
```
问题：固定列宽 ASCII 表格，长名称/URL 对不齐；无颜色区分活动/非活动配置；`---` 分隔线简陋。

**当前 `show` 输出**（`commands.py:275-331`）：
```
配置: home
  模式:          单一模式
  模型:          opus
  API 密钥:      sk-ant-a...bCD1
  API 地址:      https://api.anthropic.com
  禁用标志:
    禁用遥测: ON
    ...
```
问题：无分组、无边框，所有字段平铺在一起，模型覆盖和标志项混在一起，无法快速扫读。

**当前 `current` 输出**（`commands.py:385-419`）：
```
当前活动配置: home (单一模式)
  URL: https://api.anthropic.com
  模型: opus
```
问题：信息稀疏，与 `show` 风格重复但不完整；混合模式时代理状态混在文本中。

### 2.2 交互类命令 — `input()` 手打

用户操作路径：主菜单 → 管理配置 ←→ → 添加配置

**`add` 中的模式选择**（`menu.py:123-127`）：
```python
print("  选择配置模式:")
print("    [1] 单一模式 (single) - 一个提供商对应所有模型")
print("    [2] 混合模式 (mixed) - 不同模型使用不同提供商")
mode_choice = input("  请选择 [1/2] [1]: ").strip()
```
问题：明明已有 `select_from_list()` 箭头选择机制，这里却退化成数字输入。

**`add`/`edit` 中的字段输入**（`prompts.py:10-78`）：
```python
value = input(f"  {label}{hint}: ").strip()
```
一连串 `input()` 调用。对于自由文本字段（API 密钥、URL）这是合理的，但对于**有明确选项集的字段**应该用箭头选择：

| 字段 | 当前方式 | 应改为 |
|------|---------|--------|
| 模型 (opus/sonnet/haiku) | `input()` 手打 | 箭头选择 |
| 努力等级 (low/medium/high) | `input()` 手打 | 箭头选择 |
| 禁用/启用标志 (y/n) | 每个 `input("y/n")` | 箭头选择 y/n |
| 混合模式提供商选择 | `input("1-N")` | 箭头选择 |
| 混合模式模型选择 | `input()` 手打模型名 | 箭头选择（从提供商的 models 列表） |

**`delete` 的确认**（`commands.py:372`）：
```python
ans = input(f"确认删除配置 '{name}'？[y/N] ").strip().lower()
```
问题：与菜单中的箭头选择风格不一致。

### 2.3 问题总结

| 场景 | 当前方式 | 问题 |
|------|---------|------|
| 菜单导航 | `select_from_list()` 箭头 | OK |
| 配置选择（switch/show/edit/delete） | `select_from_list()` 箭头 | OK |
| 显示结果（list/show/current） | `print()` 裸文本 | 无边框、无颜色、无分组 |
| 模式选择（add） | `input("1/2")` | 应该用箭头选择 |
| 枚举字段（model/effort/flags） | `input()` 手打 | 应该用箭头选择 |
| 混合模式提供商选择 | `input("1-N")` | 应该用箭头选择 |
| 确认操作（delete/init） | `input("y/N")` | 应该用箭头选择 |
| 自由文本字段（URL/key/名称） | `input()` 手打 | 合理，保持 |

---

## 3. 设计目标

1. **显示面板化**：`list`、`show`、`current`、`provider list`、`provider show` 全部用带边框的面板输出，有颜色、有分组、有高亮。
2. **选择统一化**：所有「从有限集合中选一项」的场景都走 `select_from_list()` 箭头选择。
3. **确认箭头化**：所有 y/N 确认改为箭头选择的是/否。
4. **非 TTY 退化**：管道/脚本模式下退化为纯文本（无边框无颜色），保证 `ccprofile list | grep home` 正常。

---

## 4. 改进方案

### 4.1 新增 `display.py` — 面板绘制工具

提供统一的终端面板渲染能力。

#### ANSI 颜色常量

```python
CYAN    = "\x1b[36m"
GREEN   = "\x1b[32m"
RED     = "\x1b[31m"
YELLOW  = "\x1b[33m"
BOLD    = "\x1b[1m"
DIM     = "\x1b[2m"
REVERSE = "\x1b[7m"
RESET   = "\x1b[0m"
```

#### 面板 API

```python
def panel(title, right_text, body_lines, width=None):
    """外层面板。

    title:       左侧标题
    right_text:  右侧补充文字（如 "共 3 个"、"单一模式"）
    body_lines:  内容行列表，支持嵌套：
                 - str:           普通行
                 - ("sub", title, lines): 子面板
    width:       面板宽度，默认自适应终端（最小 40，最大 60）
    """

def sub_panel(title, body_lines, indent=2, width=None):
    """子面板（左右缩进 indent 字符）。"""

def kv(key, value, key_width=14):
    """格式化 key-value 行。"""

def status_dot(running):
    """● 运行中（绿）/ ● 已停止（红）。"""

def active_marker():
    """▸ 活动配置标记（cyan + bold）。"""
```

#### 面板字符集

```
┌ ─ ┐     顶部
│         侧边
├ ─ ┤     分隔线
└ ─ ┘     底部
```

所有面板统一使用直线字符。子面板通过缩进（前导空格）区分层级。

#### TTY 检测

`display.py` 内部维护一个 `USE_ANSI` 标志：

```python
import sys, shutil

USE_ANSI = sys.stdout.isatty()

def _term_width():
    if not USE_ANSI:
        return 80
    return max(40, min(60, shutil.get_terminal_size().columns))
```

非 TTY 时：颜色常量全部为空字符串，面板边框不绘制，只输出缩进文本。

---

### 4.2 `list` 命令改造

用户路径：主菜单 → 查看配置 ←→ → 列出所有配置

**当前** → **改为**：

```
┌─────────────────────────────────────────────────────┐
│  配置列表                                    共 3 个  │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ▸ home *                    单一 · opus             │
│    https://api.anthropic.com                        │
│                                                     │
│    work                       单一 · sonnet    🔔    │
│    https://proxy.example.com                        │
│                                                     │
│    mixed-test                 混合                   │
│    opus→provider-a/claude-opus                      │
│    sonnet→provider-b/claude-sonnet                  │
│                                                     │
└─────────────────────────────────────────────────────┘
```

设计要点：
- 每个配置两行：第一行 `名称 + 模式·模型 + 通知图标`，第二行 `URL 或映射详情`
- 活动配置：`▸` 前缀 + **cyan bold** 高亮 + `*` 标记
- 非活动配置：无前缀，普通文本
- 混合模式配置：映射详情每个槽位一行，用 `slot→provider/model` 格式

`cmd_list` 改造伪码：

```python
def cmd_list(_args):
    body = []
    for name, prof in profiles.items():
        is_active = (name == active)
        prefix = f"{CYAN}{BOLD}▸ " if is_active else "  "
        suffix = f"{RESET}" if is_active else ""
        mode = prof.get("mode", "single")
        mode_tag = "混合" if mode == "mixed" else f"单一 · {prof.get('model', '?')}"

        line1 = f"{prefix}{name}{' *' if is_active else ''}{suffix}    {mode_tag}"
        if "hooks" in prof:
            line1 += "    🔔"
        body.append(line1)

        if mode == "mixed":
            for slot, target in prof.get("model_mapping", {}).items():
                body.append(f"    {DIM}{slot}→{target['provider']}/{target['model']}{RESET}")
        else:
            body.append(f"    {DIM}{prof.get('env', {}).get('ANTHROPIC_BASE_URL', 'N/A')}{RESET}")
        body.append("")  # 空行分隔

    print(panel("配置列表", f"共 {len(profiles)} 个", body))
```

---

### 4.3 `show` 命令改造

用户路径：主菜单 → 查看配置 ←→ → 显示配置详情 → （箭头选择配置）

**单一模式**：

```
┌─────────────────────────────────────────────────────┐
│  home                                     单一模式   │
├─────────────────────────────────────────────────────┤
│                                                     │
│  模型         opus                                  │
│  努力等级     high                                  │
│                                                     │
│  ┌─ 连接 ─────────────────────────────────────────┐ │
│  │  API 密钥    sk-ant-a...bCD1                    │ │
│  │  API 地址    https://api.anthropic.com          │ │
│  └────────────────────────────────────────────────┘ │
│                                                     │
│  ┌─ 模型覆盖 ─────────────────────────────────────┐ │
│  │  默认模型    N/A                                │ │
│  │  Haiku       claude-haiku-4-5-20251001          │ │
│  │  Sonnet      claude-sonnet-4-20250514           │ │
│  │  Opus        N/A                                │ │
│  └────────────────────────────────────────────────┘ │
│                                                     │
│  ┌─ 标志 ─────────────────────────────────────────┐ │
│  │  禁用                                        │ │
│  │    × 禁用遥测          × 禁用自动更新           │ │
│  │    × 禁用实验性功能    × 禁用非必要流量         │ │
│  │  启用                                        │ │
│  │    ✓ Agent Teams                              │ │
│  └────────────────────────────────────────────────┘ │
│                                                     │
│  推送通知    🔔 Bark (my-server)                    │
│                                                     │
└─────────────────────────────────────────────────────┘
```

**混合模式**：

```
┌─────────────────────────────────────────────────────┐
│  mixed-test                                混合模式  │
├─────────────────────────────────────────────────────┤
│                                                     │
│  模型         opus                                  │
│  努力等级     high                                  │
│                                                     │
│  ┌─ 模型映射 ─────────────────────────────────────┐ │
│  │  opus    →  provider-a / claude-opus-4-6       │ │
│  │  sonnet  →  provider-b / claude-sonnet-4-6     │ │
│  │  haiku   →  provider-a / claude-haiku-4-5      │ │
│  └────────────────────────────────────────────────┘ │
│                                                     │
│  代理端口     18888                                 │
│                                                     │
│  推送通知     未配置                                │
│                                                     │
└─────────────────────────────────────────────────────┘
```

设计要点：
- 面板标题行 = `配置名` + 右侧 `模式`
- 子面板分组：`连接`、`模型覆盖`、`标志`（单一模式）；`模型映射`（混合模式）
- 标志用 `✓` / `×` 代替 `ON` / `OFF`
- `N/A` 和未配置项用 DIM 颜色
- 推送通知在底部，简洁一行

---

### 4.4 `current` 命令改造

用户路径：主菜单 → 查看配置 ←→ → 显示当前活动配置

**单一模式**：

```
┌─────────────────────────────────────────────────────┐
│  ▸ home                                     单一模式 │
├─────────────────────────────────────────────────────┤
│                                                     │
│  模型         opus                                  │
│  努力等级     high                                  │
│  API 地址     https://api.anthropic.com             │
│                                                     │
└─────────────────────────────────────────────────────┘
```

**混合模式**：

```
┌─────────────────────────────────────────────────────┐
│  ▸ mixed-test                                混合模式 │
├─────────────────────────────────────────────────────┤
│                                                     │
│  状态    ● 代理运行中 (PID: 12345, 端口: 18888)     │
│                                                     │
│  ┌─ 模型映射 ─────────────────────────────────────┐ │
│  │  opus    →  provider-a / claude-opus-4-6       │ │
│  │  sonnet  →  provider-b / claude-sonnet-4-6     │ │
│  │  haiku   →  provider-a / claude-haiku-4-5      │ │
│  └────────────────────────────────────────────────┘ │
│                                                     │
└─────────────────────────────────────────────────────┘
```

- 状态点 `●`：运行中绿 `\x1b[32m`，未运行红 `\x1b[31m`
- 顶部 `▸` + cyan bold 标记活动配置，与 `list` 风格统一

---

### 4.5 选择统一化 — 改造 `prompts.py` 和 `menu.py`

#### 4.5.1 新增 `confirm_action()`

在 `terminal.py` 中新增：

```python
def confirm_action(prompt_text, default_yes=True):
    """是/否确认，箭头选择。返回 bool。"""
    items = [
        (True,  "是"),
        (False, "否"),
    ]
    result = select_from_list(items, prompt_text, default_index=0 if default_yes else 1)
    if result is None:  # Esc
        return False
    return result
```

需要给 `select_from_list()` 加 `default_index` 参数（默认 0），控制初始光标位置。

#### 4.5.2 替换所有 `input("y/N")`

| 位置 | 当前 | 改为 |
|------|------|------|
| `commands.py:372` `cmd_delete` | `input("确认删除...？[y/N]")` | `confirm_action("确认删除配置？")` |
| `commands.py:40` `cmd_init` | `input("继续？[y/N]")` | `confirm_action("重新生成将导致现有配置不可读！继续？")` |
| `commands.py:48` `cmd_init` | `input("确认删除？[y/N]")` | `confirm_action("重新初始化将删除现有提供商配置。确认？")` |

#### 4.5.3 `add` 的模式选择

**当前**（`menu.py:123-127`）：
```python
print("  选择配置模式:")
print("    [1] 单一模式 ...")
print("    [2] 混合模式 ...")
mode_choice = input("  请选择 [1/2] [1]: ").strip()
```

**改为**：
```python
mode = select_from_list(
    [("single", "单一模式 — 一个提供商对应所有模型"),
     ("mixed",  "混合模式 — 不同模型使用不同提供商")],
    "选择配置模式"
)
if mode is None:
    print("  已取消。")
    return
args.mode = mode
```

#### 4.5.4 `prompts.py` 中的枚举字段

**模型选择**（`prompts.py:22`，字段 `model`）：

当前：`input("  模型 (opus/sonnet/haiku) [opus]: ")`
改为：`select_from_list([("opus", "Opus"), ("sonnet", "Sonnet"), ("haiku", "Haiku")], "选择模型")`

**努力等级**（`prompts.py:22`，字段 `effortLevel`）：

当前：`input("  努力等级 (low/medium/high) [high]: ")`
改为：`select_from_list([("low","Low"), ("medium","Medium"), ("high","High")], "选择努力等级")`

**禁用/启用标志**（`prompts.py:35-59`）：

当前：每个标志一个 `input("y/n")`
改为：每个标志一个 `confirm_action(desc)`，逐个弹出箭头确认。

```python
# 当前
print("  禁用选项 (y/n，留空使用当前值):")
for flag, desc in DISABLE_FLAGS:
    value = input(f"    {desc} [{d}]: ").strip().lower()

# 改为
for flag, desc in DISABLE_FLAGS:
    if confirm_action(f"禁用: {desc}", default_yes=(cur == "1")):
        result["env"][flag] = "1"
```

#### 4.5.5 混合模式提供商选择

**当前**（`prompts.py:106-234`）：

```python
print("  可用提供商:")
for idx, (name, prov) in enumerate(provider_list, 1):
    print(f"    [{idx}] {name} - {models}")
prov_choice = input(f"    选择提供商 (1-{len(provider_list)}): ")
```

**改为**：
```python
prov_items = [(name, f"{name}  ({', '.join(prov.get('models', []))})")
              for name, prov in provider_list]
prov_items.append((None, "跳过"))
provider_name = select_from_list(prov_items, f"选择 {slot} 槽位的提供商")
```

**模型选择同理**：
```python
model_items = [(m, m) for m in available_models]
model_items.append((None, "跳过"))
model_choice = select_from_list(model_items, f"选择模型 ({provider_name})")
```

---

### 4.6 提取共享 `pick_profile()` / `pick_provider()`

当前 `menu.py:70-106` 中有 `pick_profile()` 和 `pick_provider()` 内联函数，只有菜单内可用。

**改为**：提取到 `picker.py`（或 `terminal.py`），让 `commands.py` 的 CLI 路径也能调用。

```python
# picker.py
from .storage import load_profiles, load_providers, load_meta
from .terminal import select_from_list
from .constants import KEY_FILE, PROFILES_ENC

def pick_profile(prompt_text="选择配置"):
    """列出配置供用户箭头选择。CLI 和 menu 共用。"""
    if not KEY_FILE.exists() or not PROFILES_ENC.exists():
        print("  暂无配置。请先 init 并 add。")
        return None
    profiles = load_profiles()
    if not profiles:
        print("  暂无配置。请先添加。")
        return None
    meta = load_meta()
    items = []
    for n, prof in profiles.items():
        mark = " *" if n == meta.get("active") else ""
        mode = prof.get("mode", "single")
        url = "混合模式" if mode == "mixed" else prof.get("env", {}).get("ANTHROPIC_BASE_URL", "N/A")
        items.append((n, f"{n}{mark}  ({url})"))
    items.append((None, "取消"))
    return select_from_list(items, prompt_text)

def pick_provider(prompt_text="选择提供商"):
    """列出提供商供用户箭头选择。CLI 和 menu 共用。"""
    providers = load_providers()
    if not providers:
        print("  暂无提供商。请先添加。")
        return None
    items = [(name, f"{name}  ({prov.get('base_url', '')})")
             for name, prov in providers.items()]
    items.append((None, "取消"))
    return select_from_list(items, prompt_text)
```

同时 CLI 的 `name` 参数改为 `nargs="?"`：

```python
# cli.py — 修改前
parser_switch.add_argument("name", help="配置名称")

# cli.py — 修改后
parser_switch.add_argument("name", nargs="?", default=None, help="配置名称（省略则弹出选择）")
```

`commands.py` 中各命令入口加上 fallback：

```python
def cmd_show(args):
    name = args.name
    if name is None:
        name = pick_profile("选择要查看的配置")
        if name is None:
            return
    # ... 原有逻辑
```

对 `switch`、`show`、`edit`、`delete`、`provider_show`、`provider_edit`、`provider_delete` 做相同改动。

---

### 4.7 Provider 命令的对称改造

| 命令 | 显示改造 | 选择改造 |
|------|---------|---------|
| `provider list` | 面板风格列表（与 `list` 对称） | — |
| `provider show` | 详情面板（名称、URL、模型列表） | 无参数时弹出 `pick_provider()` |
| `provider edit` | — | 无参数时弹出 `pick_provider()` |
| `provider delete` | — | 无参数时弹出 `pick_provider()` + `confirm_action()` |

---

## 5. 实现步骤

### Phase 1：基础设施

| # | 任务 | 涉及文件 |
|---|------|---------|
| 1 | 新建 `display.py`：颜色常量、`panel()`、`sub_panel()`、`kv()`、`status_dot()`、TTY 检测 | `ccprofile_app/display.py`（新建） |
| 2 | `select_from_list()` 增加 `default_index` 参数 | `ccprofile_app/terminal.py` |
| 3 | 新建 `picker.py`：提取 `pick_profile()`、`pick_provider()` | `ccprofile_app/picker.py`（新建） |
| 4 | 新增 `confirm_action()` | `ccprofile_app/terminal.py` |

### Phase 2：显示改造

| # | 任务 | 涉及文件 |
|---|------|---------|
| 5 | `cmd_list` 改用面板输出 | `ccprofile_app/commands.py` |
| 6 | `cmd_show` 改用面板 + 子面板输出 | `ccprofile_app/commands.py` |
| 7 | `cmd_current` 改用状态面板输出 | `ccprofile_app/commands.py` |
| 8 | `cmd_provider_list`、`cmd_provider_show` 对称改造 | `ccprofile_app/provider.py` |

### Phase 3：选择改造

| # | 任务 | 涉及文件 |
|---|------|---------|
| 9 | `cli.py` 的 `name` 参数改为 `nargs="?"` | `ccprofile_app/cli.py` |
| 10 | `commands.py` 各命令入口加 `pick_profile()` fallback | `ccprofile_app/commands.py` |
| 11 | 所有 `input("y/N")` 改为 `confirm_action()` | `ccprofile_app/commands.py` |
| 12 | `menu.py` 删除内联 `pick_profile()` / `pick_provider()`，改用共享函数 | `ccprofile_app/menu.py` |
| 13 | `menu.py` 的 `add` 模式选择改为 `select_from_list()` | `ccprofile_app/menu.py` |
| 14 | `prompts.py` 枚举字段改为箭头选择（model/effort/flags/provider/model slot） | `ccprofile_app/prompts.py` |

### Phase 4：收尾

| # | 任务 | 涉及文件 |
|---|------|---------|
| 15 | 非 TTY 退化测试 | 手动测试 |
| 16 | Windows Terminal 兼容性验证 | 手动测试 |

---

## 6. 文件改动清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `ccprofile_app/display.py` | **新建** | 面板绘制、颜色常量、TTY 检测 |
| `ccprofile_app/picker.py` | **新建** | 提取 `pick_profile()`、`pick_provider()` |
| `ccprofile_app/terminal.py` | 修改 | 新增 `confirm_action()`、`select_from_list` 加 `default_index` |
| `ccprofile_app/commands.py` | 修改 | `list`/`show`/`current` 面板化；`delete`/`init` 确认箭头化；CLI fallback |
| `ccprofile_app/menu.py` | 修改 | 删除内联 pick 函数，`add` 模式选择箭头化 |
| `ccprofile_app/prompts.py` | 修改 | 枚举字段箭头化（model/effort/flags/provider slot） |
| `ccprofile_app/cli.py` | 修改 | `name` 参数 `nargs="?"` |
| `ccprofile_app/provider.py` | 修改 | `list`/`show` 面板化；无参数 fallback |

---

## 7. 风险与注意事项

1. **Windows 兼容性**：box-drawing 字符（`┌─┐`）在旧版 cmd.exe 中可能乱码。Windows Terminal 和 PowerShell 7 均支持。`display.py` 的 TTY 检测可扩展为：检测到 Windows 旧终端时用 ASCII 字符（`+---+`）。

2. **管道/脚本场景**：所有面板绘制检测 `sys.stdout.isatty()`。非 TTY 时退化为缩进文本，无边框无颜色。`select_from_list()` 已有非 TTY fallback（编号输入），不受影响。

3. **终端宽度**：`display.py` 用 `shutil.get_terminal_size().columns` 自适应，clamp 到 40–60 范围。

4. **`select_from_list` 的 `default_index`**：当前不支持设置初始选中项。`confirm_action()` 需要此参数控制光标在"是"还是"否"。改动量很小：`terminal.py:113` 将 `selected = 0` 改为 `selected = default_index`。

5. **字段箭头选择 vs `input()` 的边界**：只有值域为有限集合的字段（model: 3 选项、effort: 3 选项、flag: y/n、provider slot: 列表）才用箭头。自由文本字段（API 密钥、URL、配置名称、Bark Key）保持 `input()` 手打，这是合理的。

6. **`confirm_action` 在标志循环中的体验**：`prompts.py` 中有 4 个禁用标志 + 1 个启用标志 = 5 轮 `confirm_action()`。每轮都要箭头选是/否。可以考虑一次 `select_from_list()` 多选（但目前不支持多选），或者保持逐个确认。后者虽然轮次多，但每个操作极简（上下+确认），总时间反而可能比手打 y/n 快。
