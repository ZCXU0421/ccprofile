# ccprofile 代码拆分方案

## 背景

当前核心逻辑集中在仓库根目录的 `ccprofile.py` 中，文件内同时包含：

- 全局常量和 Claude 配置文件路径
- Fernet 加密、profile 存取、metadata 存取
- `settings.json` 读写和备份
- profile 字段交互输入
- hooks 配置生成
- `init/add/switch/list/show/edit/delete/current` 命令处理
- 终端方向键菜单和交互式主菜单
- argparse CLI 入口

这对 vibe coding 的主要问题不是文件长度本身，而是职责边界不清。AI 每次改一个命令时，容易把存储、UI、CLI 参数、settings 写入逻辑一起放进上下文，导致定位慢、误改概率高。

目标是把代码拆成少量稳定模块，让每次修改只需要打开 1-3 个相关文件，同时保持现有 CLI 用法和打包方式基本不变。

## 拆分原则

1. `ccprofile.py` 保留为薄入口，继续支持 `python ccprofile.py ...` 和 PyInstaller 打包。
2. 先按职责拆，不急着引入复杂架构或类层级。
3. 存储层不依赖 CLI/UI，命令层可以依赖存储层，UI 层只负责输入输出。
4. 每一步迁移后都能运行现有命令验证，避免一次性大搬家。
5. 对 profile 的加密文件格式保持兼容，不迁移用户数据。

## 推荐目录结构

```text
AutoCCSettings/
  ccprofile.py                 # 兼容入口：只调用 ccprofile_app.cli:main
  build.py
  ccprofile.spec
  ccprofile_app/
    __init__.py
    cli.py                     # argparse 定义和 main()
    constants.py               # 路径、字段定义、hooks 模板等常量
    crypto.py                  # Fernet key 加载、保存、加解密
    storage.py                 # profiles/meta/settings 的读写和备份
    hooks.py                   # hooks 生成、Bark key 脱敏
    prompts.py                 # profile 字段交互输入
    commands.py                # cmd_init/cmd_add/... 命令处理
    terminal.py                # 方向键读取、列表选择、VT mode
    menu.py                    # interactive_menu()
    formatting.py              # token 脱敏、输出格式小工具
  docs/
    code-splitting-plan.md
```

如果希望更保守，可以先不建 `formatting.py`，把 `mask_token` 和 `mask_bark_key` 暂放在 `commands.py` 或 `hooks.py`。等输出格式继续变多时再拆。

## 模块职责

### `ccprofile.py`

只保留兼容入口：

```python
#!/usr/bin/env python3
from ccprofile_app.cli import main

if __name__ == "__main__":
    main()
```

这样不破坏当前用户习惯，也方便 PyInstaller 继续从根目录脚本作为入口打包。

### `ccprofile_app/constants.py`

放当前文件顶部的稳定常量：

- `CLAUDE_DIR`
- `KEY_FILE`
- `PROFILES_ENC`
- `META_FILE`
- `SETTINGS_FILE`
- `SETTINGS_BAK`
- `FIELDS`
- `DISABLE_FLAGS`
- `ENABLE_FLAGS`
- `HOOK_EVENTS`
- `HOOKS_FIELDS`

这个文件应尽量没有业务逻辑。

### `ccprofile_app/crypto.py`

迁移：

- `load_key`
- `save_key`
- `encrypt_data`
- `decrypt_data`

依赖：

- `constants.KEY_FILE`
- `constants.CLAUDE_DIR`

注意：Windows 隐藏 key 文件的 `ctypes` 逻辑也放这里，因为它属于 key 文件保存细节。

### `ccprofile_app/storage.py`

迁移：

- `load_profiles`
- `save_profiles`
- `load_meta`
- `save_meta`
- `backup_settings`
- `read_settings`
- `write_settings`

依赖：

- `constants`
- `crypto.load_key`
- `crypto.encrypt_data`
- `crypto.decrypt_data`

这个模块是后续最常被复用的底层能力。以后如果增加导入/导出 profile，也优先放这里或新建专门模块。

### `ccprofile_app/hooks.py`

迁移：

- `generate_hooks`
- `mask_bark_key`

依赖：

- `constants.HOOK_EVENTS`

`generate_hooks` 里当前用到了 `json` 和 `shlex`，继续保留在这个模块内。它和 profile 存储无关，不应该依赖 `storage.py`。

### `ccprofile_app/formatting.py`

建议迁移：

- `mask_token`

可选迁移：

- `mask_bark_key`

如果保持简单，也可以暂时不建该文件。拆出它的价值在于 `cmd_show`、未来的导出/诊断命令都可能复用脱敏逻辑。

### `ccprofile_app/prompts.py`

迁移：

- `prompt_profile_fields`

依赖：

- `socket`
- `constants.FIELDS`
- `constants.DISABLE_FLAGS`
- `constants.ENABLE_FLAGS`

这个模块只处理交互式录入，不负责保存 profile，也不直接写 settings。

### `ccprofile_app/commands.py`

迁移：

- `cmd_init`
- `cmd_add`
- `cmd_switch`
- `cmd_list`
- `cmd_show`
- `cmd_edit`
- `cmd_delete`
- `cmd_current`

依赖：

- `storage`
- `crypto.save_key`
- `hooks.generate_hooks`
- `prompts.prompt_profile_fields`
- `formatting.mask_token`

这里是命令级业务编排层。以后改某个子命令，大多数情况下只需要看 `commands.py` 和它依赖的一个辅助模块。

### `ccprofile_app/terminal.py`

迁移：

- `_enable_vt_mode`
- `_read_key`
- `select_from_list`

依赖：

- `sys`
- Windows: `msvcrt`, `ctypes`
- Unix-like: `termios`, `tty`, `select`

这个模块只处理终端按键和选择列表，不知道 profile 是什么。

### `ccprofile_app/menu.py`

迁移：

- `interactive_menu`

依赖：

- `commands`
- `storage.load_profiles`
- `storage.load_meta`
- `constants.KEY_FILE`
- `constants.PROFILES_ENC`
- `terminal.select_from_list`

菜单里的 `Args` 临时对象可以先保留。后续如果想更清晰，可以改成 `types.SimpleNamespace`。

### `ccprofile_app/cli.py`

迁移：

- `main`
- argparse 子命令定义

依赖：

- `commands`
- `menu.interactive_menu`

建议额外提供一个小函数：

```python
def build_parser():
    ...
    return parser
```

这样后续可以单独测试 CLI 参数解析，不需要真的执行命令。

## 依赖方向

推荐依赖关系：

```text
ccprofile.py
  -> ccprofile_app.cli
       -> ccprofile_app.commands
       -> ccprofile_app.menu

commands
  -> storage
  -> crypto
  -> prompts
  -> hooks
  -> formatting

menu
  -> commands
  -> storage
  -> terminal
  -> constants

prompts
  -> constants

hooks
  -> constants

storage
  -> constants
  -> crypto

crypto
  -> constants
```

尽量避免反向依赖：

- `storage.py` 不 import `commands.py`
- `prompts.py` 不 import `commands.py`
- `terminal.py` 不 import profile/storage 相关模块
- `constants.py` 不 import 项目内其他模块

## 迁移批次

### Phase 1: 建包和纯工具模块

新增：

- `ccprofile_app/__init__.py`
- `ccprofile_app/constants.py`
- `ccprofile_app/crypto.py`
- `ccprofile_app/storage.py`
- `ccprofile_app/hooks.py`
- 可选：`ccprofile_app/formatting.py`

迁移函数：

- 常量
- `load_key/save_key/encrypt_data/decrypt_data`
- `load_profiles/save_profiles/load_meta/save_meta`
- `backup_settings/read_settings/write_settings`
- `generate_hooks`
- `mask_token/mask_bark_key`

验证：

```bash
python ccprofile.py list
python ccprofile.py current
```

这个阶段先不要动 argparse 和菜单，只把底层函数搬走，并从 `ccprofile.py` import 回来使用。这样风险最低。

### Phase 2: 拆交互输入和命令处理

新增：

- `ccprofile_app/prompts.py`
- `ccprofile_app/commands.py`

迁移函数：

- `prompt_profile_fields`
- `cmd_init`
- `cmd_add`
- `cmd_switch`
- `cmd_list`
- `cmd_show`
- `cmd_edit`
- `cmd_delete`
- `cmd_current`

验证：

```bash
python ccprofile.py show <已有配置名>
python ccprofile.py switch <已有配置名>
python ccprofile.py add test-profile -t test-token -u https://example.com -m opus
```

注意：如果不想污染真实 `~/.claude`，可以临时把 `CLAUDE_DIR` 做成可注入配置。但这属于第二轮改造，不建议和首次拆分混在一起。

### Phase 3: 拆终端 UI 和 CLI 入口

新增：

- `ccprofile_app/terminal.py`
- `ccprofile_app/menu.py`
- `ccprofile_app/cli.py`

迁移函数：

- `_enable_vt_mode`
- `_read_key`
- `select_from_list`
- `interactive_menu`
- `main`

将根目录 `ccprofile.py` 改成薄入口。

验证：

```bash
python ccprofile.py
python ccprofile.py list
python ccprofile.py current
```

交互菜单需要手动验证方向键、Enter、Esc、非 TTY fallback。

### Phase 4: 更新打包配置

`build.py` 当前仍然可以继续把根目录 `ccprofile.py` 作为入口，因为它会 import `ccprofile_app` 包。需要重点确认 PyInstaller 能收集包内模块。

建议更新点：

- `ccprofile.spec` 的入口脚本仍指向根目录 `ccprofile.py`
- 如果 PyInstaller 自动收集失败，再在 spec 或 build 命令中显式加入 `--collect-submodules ccprofile_app`
- 构建后运行产物验证：

```bash
python build.py
dist/ccprofile.exe list
dist/ccprofile.exe current
```

Windows 下实际命令使用 `dist\ccprofile.exe`。

## 推荐最终文件大小

拆完后大致控制在：

| 文件 | 预期大小 | 说明 |
| --- | ---: | --- |
| `ccprofile.py` | < 20 行 | 兼容入口 |
| `constants.py` | 80-140 行 | 常量和字段定义 |
| `crypto.py` | 40-80 行 | key 和 Fernet |
| `storage.py` | 60-120 行 | 文件读写 |
| `hooks.py` | 40-90 行 | hooks 生成 |
| `prompts.py` | 80-140 行 | 交互输入 |
| `commands.py` | 180-300 行 | 子命令业务逻辑 |
| `terminal.py` | 80-140 行 | 终端按键 |
| `menu.py` | 100-180 行 | 菜单 |
| `cli.py` | 80-140 行 | argparse |

`commands.py` 仍然会是最大文件，这是合理的。它是命令编排层，过早把每个命令拆成一个文件会增加跳转成本，不一定降低 AI 上下文压力。

## 后续可选改造

首次拆分完成后，再考虑这些改造：

1. 引入 `Profile` / `ProfileStore` 数据结构，减少裸字典访问。
2. 给 `CLAUDE_DIR` 增加环境变量覆盖，例如 `CCPROFILE_CLAUDE_DIR`，方便测试不污染真实配置。
3. 把输出渲染从 `commands.py` 中拆出，例如 `render_profile_detail()`。
4. 为 `build_parser()`、`generate_hooks()`、`read/write settings` 增加单元测试。
5. 将 `cmd_add` 的非交互模式判断从 `if args.token or args.url or args.model` 改成更明确的参数校验函数。

这些不建议和第一次文件拆分同时做，避免“移动代码”和“改行为”混在同一个变更里。

## AI 协作建议

拆分后可以按以下方式给 AI 分配上下文：

- 改 CLI 参数：只给 `ccprofile_app/cli.py` 和相关 `commands.py` 片段。
- 改配置文件读写：只给 `storage.py`、`constants.py`。
- 改 hooks：只给 `hooks.py`、`commands.py` 中 `cmd_switch/cmd_show/cmd_add` 相关片段。
- 改交互式录入：只给 `prompts.py`。
- 改方向键菜单：只给 `terminal.py` 和 `menu.py`。
- 改 PyInstaller 打包：只给 `build.py`、`ccprofile.spec`、`ccprofile.py`。

这样每次上下文可以稳定控制在一个小模块范围内，AI 更容易保持局部一致性。
