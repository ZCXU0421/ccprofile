# Team 模式开关改造方案

## 1. 现状分析

Team 模式（`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`）当前作为一个**环境变量 flag** 存在于 profile 的 `env` 字典中，与"禁用遥测"、"禁用自动更新"等标志混在一起。

### 当前数据流

```
profile = {
    "env": {
        "ANTHROPIC_AUTH_TOKEN": "sk-...",
        "ANTHROPIC_BASE_URL": "https://...",
        "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1",  ← 混在 env 里
        "DISABLE_TELEMETRY": "1",
        ...
    },
    "model": "opus",
    ...
}
```

### 当前操作入口

| 入口 | 方式 | 体验 |
|------|------|------|
| CLI `add --enable-teams` | 命令行 flag | OK |
| 交互式 `add` | "启用选项: 启用 Agent Teams 模式 (y/N)?" | 夹在禁用选项之后，不醒目 |
| 交互式 `edit` | 同上 | 同上 |
| CLI `edit` | 无对应 flag | **缺失** |
| `show` 命令 | 显示在"标志"子面板 | 不醒目 |
| 独立切换 | 不存在 | **无法快速开关** |

### 问题

1. **无法独立切换**：要开关 Team 模式，必须走完整的 `edit` 流程，重新确认所有字段
2. **CLI 的 `edit` 没有对应 flag**：`build_parser()` 中 `edit` 子命令没有 `--enable-teams` 参数
3. **交互式体验差**：Teams 开关藏在"禁用选项"和"启用选项"的通用确认流程里
4. **`show` 展示不醒目**：Team 模式状态淹没在其他标志中

## 2. 设计目标

1. **一键切换**：提供独立命令或快捷操作，无需重新编辑整个 profile
2. **状态可见**：在 `list`、`show`、`current` 中清晰展示 Team 模式状态
3. **双向兼容**：CLI 和交互式菜单都能操作
4. **数据格式兼容**：升级后旧配置文件仍可正常读取

## 3. 推荐方案：Profile 顶层字段 + 独立切换命令

### 3.1 数据结构变更

将 Team 模式从 `env` 字典中提升为 profile 的**顶层字段**：

```python
# 旧格式（保持向后兼容）
profile = {
    "env": {
        "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1",
        ...
    },
    ...
}

# 新格式
profile = {
    "env": { ... },  # 不再包含 CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS
    "enableTeams": True,  # 新增顶层字段
    ...
}
```

### 3.2 切换时数据转换

`cmd_switch` 写入 `settings.json` 时，根据 `enableTeams` 字段决定是否写入环境变量：

```python
# cmd_switch 中，写入 settings["env"] 后：
if profile.get("enableTeams"):
    settings["env"]["CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"] = "1"
```

### 3.3 读取时向后兼容

`cmd_switch` 读取 profile 时，兼容旧格式：

```python
def _normalize_teams_flag(profile):
    """统一处理 enableTeams 字段，兼容旧格式。"""
    if "enableTeams" in profile:
        return  # 新格式，无需处理

    # 旧格式：从 env 中读取
    env = profile.get("env", {})
    profile["enableTeams"] = env.pop("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS", None) == "1"
```

在 `cmd_switch`、`cmd_show`、`cmd_edit` 等读取 profile 后调用此函数。

### 3.4 显示增强

**`cmd_list`** — 在配置名称后显示 Teams 状态：

```
配置列表                                                      共 2 个
┌──────────────────────────────────────────────────────────────────┐
│ ● pocoprox *         单一 · opus                     👥 Teams   │
│     https://xxx.com/api                                         │
│                                                                  │
│   anthropic           单一 · sonnet                             │
│     https://api.anthropic.com                                   │
└──────────────────────────────────────────────────────────────────┘
```

**`cmd_show`** — 在基本信息区展示 Teams 状态：

```
● pocoprox                                              单一模式

  模型        opus
  努力等级    high
  Teams 模式  ✓ 已启用       ← 新增，醒目展示

  ── 连接 ──
  ...
```

**`cmd_current`** — 同样展示 Teams 状态。

## 4. 各文件具体改动

### 4.1 `constants.py`

**改动**：从 `ENABLE_FLAGS` 中移除 Team 模式（不再作为通用 flag 处理）。

```python
ENABLE_FLAGS = [
    # ("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS", "启用 Agent Teams 模式"),  ← 删除
]
```

> 如果 `ENABLE_FLAGS` 变为空列表，`prompts.py` 中的"启用选项"段落会自动消失（循环零次）。可以保留 `ENABLE_FLAGS` 结构以备将来添加其他启用标志，也可以直接删除空列表及相关代码。

**`CCPROFILE_MANAGED_ENV_KEYS`**：保留 `"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"` 不变，确保 switch 时能正确清除旧值。

### 4.2 `commands.py`

#### `cmd_add`（约 L64-L127）

**改动 1**：非交互模式中，将 `--enable-teams` flag 改为设置顶层字段：

```python
# 旧代码 (L104-105)
if args.enable_teams:
    profile["env"]["CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"] = "1"

# 新代码
if args.enable_teams:
    profile["enableTeams"] = True
```

**改动 2**：在 `cmd_switch` 中增加 `_normalize_teams_flag` 调用和写入逻辑：

```python
def cmd_switch(args):
    ...
    profile = profiles[name]
    _normalize_teams_flag(profile)  # ← 新增：兼容旧格式

    # ... 现有的 settings["env"] 写入 ...

    # 写入 Teams 模式 env 变量
    if profile.get("enableTeams"):
        settings["env"]["CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"] = "1"

    # 保存迁移后的 profile（如果格式有变化）
    profiles[name] = profile
    save_profiles(profiles)
    ...
```

**改动 3**：新增 `cmd_teams` 命令，快速切换当前活动配置的 Team 模式：

```python
def cmd_teams(args):
    """切换当前配置的 Agent Teams 模式。"""
    meta = load_meta()
    active = meta.get("active")
    if not active:
        print("错误: 当前无活动配置。请先使用 'switch' 切换到某个配置。")
        sys.exit(1)

    profiles = load_profiles()
    if active not in profiles:
        print(f"错误: 活动配置 '{active}' 不存在。")
        sys.exit(1)

    profile = profiles[active]
    _normalize_teams_flag(profile)

    if args.action == "on":
        profile["enableTeams"] = True
    elif args.action == "off":
        profile["enableTeams"] = False
    elif args.action == "toggle" or args.action is None:
        profile["enableTeams"] = not profile.get("enableTeams", False)

    profiles[active] = profile
    save_profiles(profiles)

    status = "已启用" if profile["enableTeams"] else "已禁用"
    print(f"配置 '{active}' 的 Agent Teams 模式{status}。")

    # 如果是 toggle/on/off，自动重新应用 settings
    if args.apply or args.action in ("on", "off"):
        _apply_teams_to_settings(profile)
```

**改动 4**：`cmd_list` 中增加 Teams 状态标签：

```python
# 在构建 line1 时追加 Teams 标签
if prof.get("enableTeams"):
    line1 += "    👥 Teams"
```

**改动 5**：`cmd_show` 中增加 Teams 显示行：

```python
# 在基本信息区添加
teams_status = f"{GREEN}✓ 已启用{RESET}" if prof.get("enableTeams") else f"{DIM}未启用{RESET}"
body.append(kv("Teams 模式", teams_status))
```

**改动 6**：`cmd_current` 中同样增加 Teams 显示。

**改动 7**：`cmd_edit` 中，在 `prompt_profile_fields` 后同步 enableTeams 字段：

```python
def cmd_edit(args):
    ...
    old = profiles[name]
    mode = old.get("mode", "single")

    # 保留旧的 enableTeams 状态（prompts 中不再处理此字段）
    old_teams = old.get("enableTeams")

    print(f"编辑配置 '{name}'。按回车保留当前值。")
    ...
    profile["enableTeams"] = old_teams  # 保留原值
    ...
```

### 4.3 `prompts.py`

#### `prompt_profile_fields`（约 L76-L81）

**改动**：移除"启用选项"段落中 Team 模式的处理。如果 `ENABLE_FLAGS` 已清空，则移除整个"启用选项"段落：

```python
    # 删除或注释掉以下代码（如果 ENABLE_FLAGS 已清空）：
    # print("  启用选项:")
    # for flag, desc in ENABLE_FLAGS:
    #     cur = env_defaults.get(flag)
    #     default_on = str(cur) == "1" if cur is not None else False
    #     if confirm_action(f"启用: {desc}", default_yes=default_on):
    #         result["env"][flag] = "1"
```

#### 新增 `prompt_teams_toggle`（可选）

如果希望在交互式菜单中也能切换 Teams，可以在 `prompts.py` 中新增：

```python
def prompt_teams_toggle(current_state):
    """询问是否启用 Teams 模式。"""
    default = "y" if current_state else "n"
    label = "启用" if current_state else "禁用"
    return confirm_action(f"Agent Teams 模式 (当前: {label})", default_yes=current_state)
```

### 4.4 `cli.py`

#### `build_parser`

**改动 1**：新增 `teams` 子命令：

```python
# teams
p_teams = sub.add_parser("teams", help="切换 Agent Teams 模式")
p_teams.add_argument("action", nargs="?", choices=["on", "off", "toggle"],
                     default="toggle", help="操作 (on/off/toggle，默认 toggle)")
p_teams.add_argument("--apply", action="store_true",
                     help="同时更新 settings.json（仅 toggle 时需要）")
```

**改动 2**：`edit` 子命令增加 `--enable-teams` 参数（补充缺失）：

```python
p_edit.add_argument("--enable-teams", action="store_true", help="启用 Agent Teams 模式")
p_edit.add_argument("--disable-teams", action="store_true", help="禁用 Agent Teams 模式")
```

**改动 3**：`main()` 中注册 `teams` 命令：

```python
commands = {
    "init": cmd_init,
    "add": cmd_add,
    "switch": cmd_switch,
    "list": cmd_list,
    "show": cmd_show,
    "edit": cmd_edit,
    "delete": cmd_delete,
    "current": cmd_current,
    "teams": cmd_teams,  # ← 新增
}
```

### 4.5 `menu.py`

**改动**：在主菜单或系统设置中增加 Teams 切换入口。

方案 A — 主菜单直接入口（推荐，因为高频）：

```python
MAIN_MENU = [
    ("switch",      "切换配置"),
    ("_view",       "查看配置 ←→"),
    ("_manage",     "管理配置 ←→"),
    ("teams",       "切换 Teams 模式"),  # ← 新增
    ("_provider",   "提供商管理 ←→"),
    ("_system",     "系统设置 ←→"),
    ("__exit__",    "退出"),
]
```

方案 B — 系统设置子菜单：

```python
SYSTEM_MENU = [
    ("init",    "初始化 / 重置密钥"),
    ("teams",   "切换 Teams 模式"),  # ← 新增
]
```

在 `_execute_command` 中增加 teams 的参数构造：

```python
elif cmd_name == "teams":
    meta = load_meta()
    active = meta.get("active")
    if not active:
        print("错误: 当前无活动配置。")
        return
    # 交互切换：询问用户
    profiles = load_profiles()
    profile = profiles.get(active, {})
    current = profile.get("enableTeams", False)
    new_state = confirm_action("启用 Agent Teams 模式", default_yes=current)
    profile["enableTeams"] = new_state
    profiles[active] = profile
    save_profiles(profiles)
    status = "已启用" if new_state else "已禁用"
    print(f"配置 '{active}' 的 Agent Teams 模式{status}。")
    return  # 不走 cmd_teams，直接处理
```

## 5. 向后兼容策略

| 场景 | 处理 |
|------|------|
| 旧配置文件（Team flag 在 env 中） | `_normalize_teams_flag()` 自动迁移到顶层字段，并从 env 中移除 |
| 旧版本读取新格式 | `enableTeams` 字段被忽略，env 中无对应值，Team 模式自然关闭 |
| switch 后立即生效 | `cmd_switch` 中根据 `enableTeams` 写入 env 到 `settings.json` |

迁移在首次读取时惰性完成，不增加额外命令。

## 6. 实现步骤

| 步骤 | 文件 | 内容 |
|------|------|------|
| 1 | `constants.py` | 从 `ENABLE_FLAGS` 移除 Teams flag |
| 2 | `commands.py` | 添加 `_normalize_teams_flag()` 辅助函数 |
| 3 | `commands.py` | 修改 `cmd_switch`：兼容旧格式 + 写入 env |
| 4 | `commands.py` | 修改 `cmd_add`：`--enable-teams` 写入顶层字段 |
| 5 | `commands.py` | 新增 `cmd_teams` 命令 |
| 6 | `commands.py` | 修改 `cmd_list`/`cmd_show`/`cmd_current`：展示 Teams 状态 |
| 7 | `commands.py` | 修改 `cmd_edit`：保留 enableTeams 字段 |
| 8 | `prompts.py` | 移除"启用选项"中 Teams 相关代码 |
| 9 | `cli.py` | 新增 `teams` 子命令 + 注册到命令映射 |
| 10 | `menu.py` | 增加 Teams 切换入口 |

## 7. 使用示例

### CLI

```bash
# 快速切换当前配置的 Teams 模式
ccprofile teams              # toggle（默认）
ccprofile teams on           # 启用
ccprofile teams off          # 禁用
ccprofile teams --apply      # toggle 并立即更新 settings.json

# 添加配置时指定
ccprofile add myprofile --enable-teams

# 编辑配置时切换
ccprofile edit myprofile --enable-teams
ccprofile edit myprofile --disable-teams
```

### 交互式菜单

```
  ccprofile — Claude Code 配置管理
  当前配置: pocoprox

  请选择操作  (↑↓ 选择 · Enter 确认 · Esc 退出)
   > 切换配置
     查看配置 ←→
     管理配置 ←→
     切换 Teams 模式          ← 新增
     提供商管理 ←→
     系统设置 ←→
     退出
```

## 8. 改动范围总结

| 文件 | 改动类型 | 行数估计 |
|------|----------|----------|
| `constants.py` | 修改（删除 ENABLE_FLAGS 中一项） | ~2 行 |
| `commands.py` | 修改 + 新增（`cmd_teams`、`_normalize_teams_flag`、显示逻辑） | ~50 行 |
| `prompts.py` | 修改（移除 Teams 相关 prompt） | ~8 行 |
| `cli.py` | 修改（新增子命令 + 注册） | ~15 行 |
| `menu.py` | 修改（新增菜单项 + 参数构造） | ~15 行 |

总计约 **90 行**代码改动，不涉及数据加密、存储格式或依赖方向的变更。
