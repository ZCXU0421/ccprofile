# 交互式菜单层级化改造方案

## 1. 现状分析

当前 `interactive_menu()` 使用单一平铺列表展示 9 个选项：

```
请选择操作  (↑↓ 选择 · Enter 确认 · Esc 取消)
 > 列出所有配置
   显示当前活动配置
   显示配置详情
   切换配置
   添加配置
   编辑配置
   删除配置
   初始化 / 重置密钥
   退出
```

### 问题

| 问题 | 说明 |
|------|------|
| **选项过多** | 9 项平铺超过 Miller's Law 建议的 7±2 认知上限，用户需要逐行扫描 |
| **频率不均** | "切换配置"是最高频操作，却和低频的"初始化密钥"混在一起 |
| **缺乏分类** | 查看类、管理类、系统类操作没有视觉区分 |
| **扩展性差** | 未来新增命令（导入/导出、复制、排序）会让列表更长 |

## 2. 设计目标

1. 主菜单控制在 5-6 项以内
2. 按操作性质分组，减少认知负担
3. 高频操作（切换、查看当前）保持一级可达
4. 支持返回上一级，Esc 始终可退回
5. 改动范围限制在 `menu.py` 和 `terminal.py`，不影响 `commands.py`

## 3. 推荐方案：两级菜单

### 3.1 主菜单

```
请选择操作  (↑↓ 选择 · Enter 确认 · Esc 退出)
 > 切换配置
   查看配置 ←→
   管理配置 ←→
   系统设置 ←→
   退出
```

- 最高频操作 **切换配置** 放在第一位（默认高亮），一次 Enter 即可进入配置选择
- 带有 `←→` 标记的选项表示有子菜单
- 主菜单 5 项，一目了然

### 3.2 子菜单

**查看配置** → 进入：

```
查看配置  (↑↓ 选择 · Enter 确认 · Esc 返回)
 > 列出所有配置
   显示当前活动配置
   显示配置详情
```

**管理配置** → 进入：

```
管理配置  (↑↓ 选择 · Enter 确认 · Esc 返回)
 > 添加配置
   编辑配置
   删除配置
```

**系统设置** → 进入：

```
系统设置  (↑↓ 选择 · Enter 确认 · Esc 返回)
 > 初始化 / 重置密钥
```

### 3.3 导航流程图

```
主菜单
 ├─ [Enter] 切换配置 → 选择配置列表 → 切换/取消 → 返回主菜单
 ├─ [Enter] 查看配置
 │    ├─ 列出所有配置 → 显示结果 → 返回"查看配置"
 │    ├─ 显示当前活动配置 → 显示结果 → 返回"查看配置"
 │    └─ 显示配置详情 → 选择配置 → 显示 → 返回"查看配置"
 ├─ [Enter] 管理配置
 │    ├─ 添加配置 → 输入名称 → 交互填写 → 返回"管理配置"
 │    ├─ 编辑配置 → 选择配置 → 交互填写 → 返回"管理配置"
 │    └─ 删除配置 → 选择配置 → 确认 → 返回"管理配置"
 ├─ [Enter] 系统设置
 │    └─ 初始化 / 重置密钥 → 执行 → 返回"系统设置"
 └─ [Enter] 退出 → 程序结束
```

关键导航规则：
- **Esc**：子菜单 → 返回主菜单；主菜单 → 退出程序
- **操作完成后**：停留当前子菜单（不是自动返回主菜单），方便连续操作
- **选择配置后 Esc/取消**：返回上一层子菜单

## 4. 数据结构设计

### 4.1 菜单定义

```python
# menu.py 中的菜单结构定义

MAIN_MENU = [
    ("switch",  "切换配置"),
    ("_view",   "查看配置 ←→"),
    ("_manage", "管理配置 ←→"),
    ("_system", "系统设置 ←→"),
    ("__exit__", "退出"),
]

VIEW_MENU = [
    ("list",    "列出所有配置"),
    ("current", "显示当前活动配置"),
    ("show",    "显示配置详情"),
]

MANAGE_MENU = [
    ("add",     "添加配置"),
    ("edit",    "编辑配置"),
    ("delete",  "删除配置"),
]

SYSTEM_MENU = [
    ("init",    "初始化 / 重置密钥"),
]

SUB_MENUS = {
    "_view":   ("查看配置", VIEW_MENU),
    "_manage": ("管理配置", MANAGE_MENU),
    "_system": ("系统设置", SYSTEM_MENU),
}
```

以 `_` 前缀的 key 标识子菜单入口，普通 key 对应直接命令。这个约定简单且不需要额外数据结构。

### 4.2 菜单路由逻辑（伪代码）

```python
def interactive_menu():
    current_menu = MAIN_MENU

    while True:
        selected = select_from_list(current_menu, prompt_for(current_menu))

        if selected is None or selected == "__exit__":
            if current_menu is MAIN_MENU:
                break           # 主菜单 Esc/退出 → 结束
            else:
                current_menu = MAIN_MENU  # 子菜单 Esc → 回主菜单
                continue

        if selected in SUB_MENUS:
            prompt, items = SUB_MENUS[selected]
            current_menu = items  # 进入子菜单
            continue

        # 执行命令...
        execute(selected)
        # 操作完成后不自动跳回主菜单，停留在当前子菜单
```

## 5. 备选方案对比

### 方案 B：分组标题 + 平铺

```
请选择操作
 ── 查看 ──
 > 列出所有配置
   显示当前活动配置
   显示配置详情
 ── 管理 ──
   切换配置
   添加配置
   编辑配置
   删除配置
 ── 系统 ──
   初始化 / 重置密钥
   退出
```

| 维度 | 方案 A（两级菜单） | 方案 B（分组平铺） |
|------|-------------------|-------------------|
| 选项数/屏 | 5 | 10（含标题） |
| 操作步数 | 查看：2 步；切换：1 步 | 所有操作：1 步 |
| 扩展性 | 新命令加到子菜单 | 列表越来越长 |
| 实现复杂度 | 中等 | 低（只改 render） |
| 改动范围 | `menu.py` | `terminal.py` + `menu.py` |

**建议**：采用方案 A（两级菜单）。方案 B 本质上没有解决选项过多的问题，只是加了视觉分隔。方案 A 通过真正的层级缩减了每屏显示的选项数量，同时保证最高频操作（切换）只需 1 步。

### 方案 C：命令面板式（输入过滤）

```
> 切换
  切换配置
  切换到上次使用的配置
```

类似 VS Code 命令面板，用户输入关键词实时过滤。

| 维度 | 评价 |
|------|------|
| 效率 | 最高（熟练用户直接输入） |
| 实现复杂度 | 高（需要文本输入框 + 实时过滤 + 新的 UI 组件） |
| 发现性 | 差（新用户不知道有哪些命令） |
| 适合场景 | 命令数量 > 20 以后再考虑 |

**建议**：当前命令量（8 个）不需要这种方案。如果未来命令增长到 15+ 个，可以作为进一步增强。

## 6. 对 `terminal.py` 的影响

`select_from_list()` 的接口不需要修改。当前签名已经足够：

```python
def select_from_list(items, prompt="请选择"):
    """items 为 [(key, display_text), ...]，返回 key 或 None。"""
```

子菜单调用时只需传入不同的 `items` 和 `prompt` 参数。`None` 返回值（Esc/取消）在 `menu.py` 中处理路由即可。

**无需修改 `terminal.py`。**

## 7. 对 `commands.py` 的影响

**无需修改。** 命令函数签名不变，`menu.py` 仍然构造相同的 `Args` 对象调用它们。路由逻辑完全在 `menu.py` 内部消化。

## 8. 实现步骤

### Step 1：在 `menu.py` 中定义菜单结构

添加 `MAIN_MENU`、`VIEW_MENU`、`MANAGE_MENU`、`SYSTEM_MENU`、`SUB_MENUS` 常量。

### Step 2：改写 `interactive_menu()` 的主循环

```python
def interactive_menu():
    print("\n  ccprofile — Claude Code 配置管理")

    current_menu = MAIN_MENU
    current_prompt = "请选择操作"

    while True:
        # 显示当前活动配置（每次都刷新）
        meta = load_meta() if KEY_FILE.exists() else {}
        active = meta.get("active", "")
        if active:
            print(f"  当前配置: {active}\n")

        try:
            selected = select_from_list(current_menu, current_prompt)
        except (EOFError, KeyboardInterrupt):
            print("\n  再见！")
            break

        # 取消 / 退出
        if selected is None or selected == "__exit__":
            if current_menu is MAIN_MENU:
                print("  再见！")
                break
            current_menu = MAIN_MENU
            current_prompt = "请选择操作"
            continue

        # 子菜单入口
        if selected in SUB_MENUS:
            current_prompt, current_menu = SUB_MENUS[selected]
            continue

        # 执行命令
        _execute_command(selected)
        # 不切换 current_menu，停留在当前子菜单

    print()
```

### Step 3：提取命令执行为独立函数

把当前 `interactive_menu()` 中的 `Args` 构造和命令调用逻辑提取为 `_execute_command(cmd_name)`：

```python
def _execute_command(cmd_name):
    """执行单个命令，处理参数构造和错误。"""
    args = _build_args(cmd_name)
    if args is None:
        return  # 用户取消

    try:
        commands_map[cmd_name](args)
    except SystemExit:
        pass
    except (EOFError, KeyboardInterrupt):
        print("\n  操作已取消。")
    print()
```

### Step 4：验证

手动验证以下场景：

```bash
python ccprofile.py
# 1. 主菜单 → Esc → 程序退出
# 2. 主菜单 → 查看配置 → Esc → 返回主菜单
# 3. 主菜单 → 切换配置 → 选择配置 → 切换成功 → 返回主菜单
# 4. 主菜单 → 管理配置 → 添加配置 → 添加成功 → 停留在管理配置子菜单
# 5. 管理配置 → Esc → 返回主菜单
```

## 9. 未来扩展

采用两级菜单后，新增命令只需要在对应子菜单数组中追加一项：

```python
MANAGE_MENU = [
    ("add",     "添加配置"),
    ("edit",    "编辑配置"),
    ("delete",  "删除配置"),
    ("copy",    "复制配置"),      # 新增
    ("rename",  "重命名配置"),    # 新增
]

SYSTEM_MENU = [
    ("init",    "初始化 / 重置密钥"),
    ("export",  "导出配置文件"),   # 新增
    ("import",  "导入配置文件"),   # 新增
]
```

每个子菜单仍保持在 3-5 项，不会随着功能增长而臃肿。

如果某一类操作（如"管理"）子项超过 7 个，可以考虑进一步拆分为三级，或在该子菜单内再做分组。但当前规模不需要。

## 10. 改动范围总结

| 文件 | 改动类型 | 说明 |
|------|----------|------|
| `ccprofile_app/menu.py` | **重写** | 菜单结构定义 + 路由逻辑 + 命令执行提取 |
| `ccprofile_app/terminal.py` | 不变 | `select_from_list` 接口不变 |
| `ccprofile_app/commands.py` | 不变 | 命令函数签名不变 |
| `ccprofile_app/cli.py` | 不变 | CLI 参数不变 |
