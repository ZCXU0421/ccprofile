# "其它设定" 子菜单 + 1M 上下文开关 需求文档

## 1. 需求描述

### 背景

当前"管理配置"子菜单中，Teams 开关直接作为二级菜单项存在，而 1M 上下文设置完全没有入口。用户希望将这类高级设置统一收纳到独立的子菜单中。

### 需求

1. 在"管理配置"下新增"其它设定"三级子菜单
2. 将 Teams 模式开关从二级菜单移入"其它设定"
3. 新增"1M 上下文"开关，用于控制 `CLAUDE_CODE_DISABLE_1M_CONTEXT` 环境变量
4. **默认值**：Teams 默认开启，1M 上下文默认关闭

### 菜单结构

```
管理配置 (_manage)
  ├── 查看配置 → (_view)
  ├── 添加配置
  ├── 编辑配置
  ├── 其它设定 → (_advanced)   ← 新增
  │     ├── 切换 Teams 模式    ← 从二级移入
  │     └── 切换 1M 上下文     ← 新增
  └── 删除配置
```

### 1M 上下文开关逻辑

| 状态 | 环境变量 | 效果 |
|------|---------|------|
| 关闭（默认） | `CLAUDE_CODE_DISABLE_1M_CONTEXT = "1"` | Claude Code 使用 200K 上下文 |
| 开启 | 不写入该变量 | Claude Code 使用 1M 上下文 |

## 2. 数据结构

Profile 新增顶层字段 `enable1MContext`：

```python
profile = {
    "env": { ... },
    "mode": "single",
    "model": "opus",
    "enableTeams": True,           # 已有字段，默认开启
    "enable1MContext": False,      # 新增字段，默认关闭
    ...
}
```

### 存储约定

- `enable1MContext = True` → 不写入 env key（1M 上下文可用）
- `enable1MContext = False` → 写入 `CLAUDE_CODE_DISABLE_1M_CONTEXT = "1"`（禁用 1M）

### 向后兼容

旧格式迁移函数 `_normalize_1m_context_flag()` 会在首次读取时自动将 env 中的 `CLAUDE_CODE_DISABLE_1M_CONTEXT` 转换为顶层 `enable1MContext` 字段。

## 3. 涉及的代码修改

### 3.1 `ccprofile_app/constants.py`

- `CCPROFILE_MANAGED_ENV_KEYS` 集合新增 `"CLAUDE_CODE_DISABLE_1M_CONTEXT"`，确保 switch 时正确清除旧值。

### 3.2 `ccprofile_app/commands.py`

**新增函数：**

| 函数 | 作用 |
|------|------|
| `_normalize_1m_context_flag(profile)` | 兼容旧格式迁移，从 env 提取状态到顶层字段 |
| `cmd_context_1m(args)` | 1M 上下文开关命令，仿照 `cmd_teams` |
| `_apply_1m_context_to_settings(profile, name)` | 将状态写入 settings.json，仿照 `_apply_teams_to_settings` |

**修改的函数：**

| 函数 | 修改内容 |
|------|---------|
| `cmd_add` | 新 profile 默认 `enableTeams = True`，`enable1MContext = False` |
| `cmd_switch` | 调用 `_normalize_1m_context_flag()`，写入/清除 env key |
| `cmd_list` | 显示 1M 上下文状态标签 `📏 1M` |
| `cmd_show` | 显示 1M 上下文状态行 |
| `cmd_current` | 显示 1M 上下文状态行 |
| `cmd_edit` | 保留 `enable1MContext` 字段不被覆盖 |

### 3.3 `ccprofile_app/menu.py`

- `_manage_menu()`：移除 `teams` 项，新增 `_advanced` 子菜单入口
- 新增 `_advanced_menu()`：包含 `teams` 和 `context_1m` 两个选项
- `_sub_menus()`：新增 `_advanced` 条目
- `interactive_menu()`：`commands_map` 新增 `context_1m`，`_execute_command` 新增参数构造

### 3.4 `ccprofile_app/i18n.py`

新增翻译键（中英双语）：

| 键 | 中文 | English |
|----|------|---------|
| `menu.advanced_settings` | 其它设定 | Advanced Settings |
| `menu.switch_1m_context` | 切换 1M 上下文 | Toggle 1M Context |
| `cmd.1m_no_active` | 错误: 当前无活动配置... | Error: No active profile... |
| `cmd.1m_missing` | 错误: 活动配置不存在 | Error: Active profile does not exist |
| `cmd.1m_done` | 配置 '{name}' 的 1M 上下文{status}。 | 1M context {status} for profile '{name}'. |
| `cmd.1m_enabled` | 已启用 | enabled |
| `cmd.1m_disabled` | 已禁用 | disabled |
| `cmd.show.1m_context` | 1M 上下文 | 1M Context |
| `cmd.show.1m_enabled` | ✓ 已启用 | ✓ Enabled |
| `cmd.show.1m_disabled` | 未启用 | Not Enabled |
| `cli.1m_help` | 切换 1M 上下文 | Toggle 1M Context |
| `cli.1m_action_help` | 操作 (on/off/toggle) | Action (on/off/toggle) |
| `cli.1m_apply_help` | 同时更新 settings.json | Also update settings.json |

### 3.5 `ccprofile_app/cli.py`

- 新增 `context-1m` 子命令解析器（参数与 `teams` 一致：`action` + `--apply`）
- `main()` 的 commands 映射注册 `"context-1m": cmd_context_1m`
- import 新增 `cmd_context_1m`

## 4. CLI 用法

```bash
# 交互式菜单
python ccprofile.py
# → 管理配置 → 其它设定 → 切换 Teams 模式 / 切换 1M 上下文

# 命令行
python ccprofile.py context-1m              # toggle
python ccprofile.py context-1m on           # 开启
python ccprofile.py context-1m off          # 关闭
python ccprofile.py context-1m --apply      # toggle 并立即更新 settings.json
```

## 5. 验证清单

- [ ] 交互式菜单 → 管理配置 → 确认 Teams 不再出现在二级菜单
- [ ] 管理配置 → 其它设定 → 确认看到 Teams 和 1M 上下文两个选项
- [ ] 切换 1M 上下文 → `~/.claude/settings.json` 中 env 出现/移除 `CLAUDE_CODE_DISABLE_1M_CONTEXT`
- [ ] `python ccprofile.py list` → 显示 1M 上下文状态标签
- [ ] `python ccprofile.py show <name>` → 显示 1M 上下文状态行
- [ ] `python ccprofile.py current` → 显示 1M 上下文状态行
- [ ] `python ccprofile.py context-1m toggle --apply` → CLI 命令可用
- [ ] 新建 profile → Teams 默认开启，1M 上下文默认关闭
