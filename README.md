<div align="center">

# ccprofile

**Claude Code 多配置管理工具**

加密存储多套 API 提供商配置，一键切换，告别手动改文件。

</div>

---

## 它能做什么？

如果你同时使用多个 Claude Code API 提供商（比如官方 API、第三方代理等），每次切换都要手动编辑 `~/.claude/settings.json` 里的密钥和地址。**ccprofile** 把这些配置加密存储，用一条命令完成切换：

- 配置用 **Fernet 对称加密**存储，密钥不会泄露
- 切换时**自动备份** `settings.json`，随时可回退
- 支持**交互式菜单**和**命令行参数**两种操作方式
- 内置 **Bark 推送通知**，任务完成、等待输入时手机提醒
- 跨平台：Windows / macOS / Linux

## 安装

### 预编译二进制（推荐）

从 [Releases](https://github.com/ZCXU0421/ccprofile/releases/latest) 下载对应平台的文件，运行安装脚本。

**Linux：**

```bash
curl -sLO "https://github.com/ZCXU0421/ccprofile/releases/latest/download/ccprofile-linux"
curl -sLO "https://github.com/ZCXU0421/ccprofile/releases/latest/download/install-linux.sh"
chmod +x install-linux.sh ccprofile-linux && ./install-linux.sh
```

**macOS：**

根据你的 Mac 芯片选择对应文件：

```bash
# Apple Silicon (M1/M2/M3/M4)
curl -sLO "https://github.com/ZCXU0421/ccprofile/releases/latest/download/ccprofile-macos-arm64"
curl -sLO "https://github.com/ZCXU0421/ccprofile/releases/latest/download/install-macos.sh"
chmod +x install-macos.sh ccprofile-macos-arm64 && ./install-macos.sh
```

```bash
# Intel Mac
curl -sLO "https://github.com/ZCXU0421/ccprofile/releases/latest/download/ccprofile-macos-intel"
curl -sLO "https://github.com/ZCXU0421/ccprofile/releases/latest/download/install-macos.sh"
chmod +x install-macos.sh ccprofile-macos-intel && ./install-macos.sh
```

> 安装脚本会自动识别 macOS 二进制（arm64 / intel），无需单独脚本。

**Windows：**

从 Releases 下载 `ccprofile-windows.exe`，放入任意 `PATH` 目录（如 `%USERPROFILE%\AppData\Local\Microsoft\WindowsApps\`），重命名为 `ccprofile.exe` 即可。

### 从源码运行

```bash
git clone https://github.com/ZCXU0421/ccprofile.git
cd ccprofile
pip install cryptography
python ccprofile.py init
```

## 快速开始

```bash
# 1. 初始化（生成加密密钥，仅需一次）
ccprofile init

# 2. 添加第一个配置（交互式引导）
ccprofile add my-proxy

# 3. 添加第二个配置（命令行参数，适合脚本）
ccprofile add official \
  -t sk-ant-xxxxx \
  -u https://api.anthropic.com \
  -m sonnet

# 4. 切换配置
ccprofile switch my-proxy

# 5. 确认当前使用的配置
ccprofile current
```

直接输入 `ccprofile` 不带参数则进入交互式菜单，支持上下键选择。

## 命令一览

| 命令 | 说明 | 示例 |
|------|------|------|
| `init` | 初始化，生成加密密钥 | `ccprofile init` |
| `add <名称>` | 添加配置 | `ccprofile add work` |
| `switch <名称>` | 切换到指定配置 | `ccprofile switch work` |
| `list` | 列出所有配置（当前激活的标 `*`） | `ccprofile list` |
| `show <名称>` | 显示配置详情（密钥脱敏显示） | `ccprofile show work` |
| `edit <名称>` | 交互式编辑已有配置 | `ccprofile edit work` |
| `delete <名称>` | 删除配置（需确认） | `ccprofile delete work` |
| `current` | 显示当前活动配置名称 | `ccprofile current` |

### `add` 命令参数

```
ccprofile add <名称> [选项]

必填（非交互模式下）:
  -t, --token         API 密钥
  -u, --url           API 基础地址
  -m, --model         模型 (opus / sonnet / haiku)

可选:
  -e, --effort        努力等级 (low / medium / high)，默认 high
  --anthropic-model   覆盖默认模型
  --haiku-model       覆盖 Haiku 级别模型
  --sonnet-model      覆盖 Sonnet 级别模型
  --opus-model        覆盖 Opus 级别模型
  --disable-all       启用所有禁用标志（遥测、自动更新等）
  --enable-teams      启用 Agent Teams 模式
  --bark-key KEY      配置 Bark 推送通知
  --host-label LABEL  推送通知中的主机名标签
  --notify-sound NAME 通知铃声名称
  --hooks-json JSON   自定义 hooks JSON 配置
```

不带任何参数运行 `add` 进入交互式引导，逐项填写。

## 配置字段说明

每个配置（profile）包含以下字段：

| 字段 | 说明 | 必填 | 默认值 |
|------|------|:----:|--------|
| `ANTHROPIC_AUTH_TOKEN` | API 密钥 | 是 | — |
| `ANTHROPIC_BASE_URL` | API 基础地址 | 是 | — |
| `model` | 模型选择 (opus/sonnet/haiku) | 是 | opus |
| `effortLevel` | 努力等级 (low/medium/high) | 否 | high |
| `ANTHROPIC_MODEL` | 默认模型覆盖 | 否 | — |
| `ANTHROPIC_DEFAULT_*_MODEL` | 各级别模型覆盖 | 否 | — |

此外，每个配置还可附加**禁用/启用标志**和**推送通知**设置。

### 禁用标志（默认启用）

| 标志 | 说明 |
|------|------|
| `DISABLE_TELEMETRY` | 禁用遥测 |
| `DISABLE_AUTOUPDATER` | 禁用自动更新 |
| `CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS` | 禁用实验性功能 |
| `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` | 禁用非必要流量 |

### 启用标志

| 标志 | 说明 |
|------|------|
| `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` | 启用 Agent Teams 模式 |

## Bark 推送通知

ccprofile 内置 [Bark](https://github.com/Finb/Bark) 推送支持，可在以下事件发生时向手机发送通知：

- Claude 等待输入（Notification）
- Claude 请求操作批准（PermissionRequest）
- Claude 任务完成（Stop）

**配置方式：**

```bash
# 添加配置时指定
ccprofile add my-profile \
  --bark-key YOUR_BARK_KEY \
  --host-label "我的Mac" \
  --notify-sound minuet

# 或在交互模式中填写
ccprofile add my-profile   # 引导过程中会询问 Bark Key
```

推送消息格式示例：

```
💬 [我的Mac] Claude 需要输入
您的 我的Mac 主机正在等待输入或关注。
```

## 交互式菜单

不带参数直接运行 `ccprofile`，进入上下键选择的交互式菜单：

```
  ccprofile — Claude Code 配置管理
  当前配置: work

  请选择操作  (↑↓ 选择 · Enter 确认 · Esc 取消)
    > 切换配置
      查看配置 ←→
      管理配置 ←→
      系统设置 ←→
      退出
```

菜单结构：

- **切换配置** — 选择并切换到某个配置
- **查看配置** ←→ — 列出 / 详情 / 当前
- **管理配置** ←→ — 添加 / 编辑 / 删除
- **系统设置** ←→ — 初始化 / 重置密钥

## 工作原理

```
~/.ccprofile/
├── .profile_key        # Fernet 加密密钥（Windows 上设为隐藏）
├── profiles.enc        # 加密的配置数据
└── profiles_meta.json  # 元数据（记录当前活动配置）

~/.claude/
├── settings.json       # Claude Code 设置（switch 命令修改此文件）
└── settings.json.bak   # 每次切换前的自动备份
```

**切换流程**：`switch` 命令读取加密配置 → 备份当前 `settings.json` → 将配置中的 `env`、`model`、`effortLevel`、`hooks` 合并写入 `settings.json`。

**安全设计**：
- 所有配置使用 Fernet 对称加密，密钥文件在 Windows 上设为隐藏属性，并通过 `chmod 600` 限制权限
- API 密钥显示时脱敏（保留前 8 位和后 4 位）
- `settings.local.json` 不会被修改
- 切换前自动备份，可手动回滚

## 项目结构

```
ccprofile.py                  # 入口脚本
ccprofile_app/
├── __init__.py
├── cli.py                    # argparse 定义、main()
├── constants.py              # 路径、字段定义、hooks 模板
├── crypto.py                 # Fernet 密钥管理、加解密
├── storage.py                # 文件读写、备份、旧版迁移
├── hooks.py                  # Bark hooks 生成、key 脱敏
├── formatting.py             # API token 脱敏
├── prompts.py                # 交互式字段输入
├── commands.py               # 所有命令处理函数
├── terminal.py               # 终端按键读取、列表选择
└── menu.py                   # 交互式菜单主循环
```

依赖方向：`cli` → `commands`/`menu` → `storage`/`prompts`/`hooks`/`formatting` → `crypto`/`constants`，无反向依赖。

## 许可证

MIT
