<div align="center">

# ccprofile

**Claude Code 多配置管理工具**

加密保存多套 Claude Code API 配置，支持单一提供商切换、混合提供商路由和 Bark 推送通知。

</div>

---

## 它能做什么？

如果你经常在 Claude Code 的官方 API、第三方代理或多个兼容 Anthropic Messages API 的服务之间切换，手动修改 `~/.claude/settings.json` 容易出错。`ccprofile` 将这些配置加密保存，并用命令或交互菜单完成切换。

- **单一模式**：一套配置对应一个 API 地址和密钥，切换时直接写入 Claude Code 设置。
- **混合模式**：把 `opus`、`sonnet`、`haiku` 三个模型槽位映射到不同提供商，由本地代理自动路由。
- **加密存储**：profile 和 provider 使用 Fernet 对称加密保存。
- **自动备份**：切换前备份 `~/.claude/settings.json` 到 `settings.json.bak`。
- **Bark 推送**：Claude 等待输入、请求批准、任务结束时可推送到手机。
- **跨平台**：Windows / macOS / Linux。

## 安装

### 预编译二进制

从 [Releases](https://github.com/ZCXU0421/ccprofile/releases/latest) 下载对应平台的安装脚本。

**Linux**

```bash
curl -sLO "https://github.com/ZCXU0421/ccprofile/releases/latest/download/install-linux.sh"
chmod +x install-linux.sh
./install-linux.sh
```

**macOS**

```bash
curl -sLO "https://github.com/ZCXU0421/ccprofile/releases/latest/download/install-macos.sh"
chmod +x install-macos.sh
./install-macos.sh
```

安装脚本会自动检测 Apple Silicon / Intel，下载对应平台压缩包，校验后解压安装。

**Windows**

```cmd
curl -sLO "https://github.com/ZCXU0421/ccprofile/releases/latest/download/install-windows.bat"
install-windows.bat
```

或从 Releases 页面下载 `install-windows.bat`，双击运行。

### 从源码运行

```bash
git clone https://github.com/ZCXU0421/ccprofile.git
cd ccprofile
pip install cryptography
python ccprofile.py init
```

源码模式下可用 `python ccprofile.py ...` 代替 `ccprofile ...`。

## 快速开始

### 单一模式

```bash
# 1. 初始化，仅需一次
ccprofile init

# 2. 添加一个配置
ccprofile add official \
  -t sk-ant-xxxxx \
  -u https://api.anthropic.com \
  -m sonnet

# 3. 切换到该配置
ccprofile switch official

# 4. 查看当前配置
ccprofile current
```

不带 `-t`、`-u`、`-m` 时，`add` 会进入交互式引导：

```bash
ccprofile add work
```

### 混合模式

混合模式适合把不同模型槽位分配给不同提供商，例如 `opus` 走提供商 A，`sonnet` 和 `haiku` 走提供商 B。

```bash
# 1. 添加提供商
ccprofile provider add zhipu \
  -u https://open.bigmodel.cn/api/paas/v4 \
  -k YOUR_ZHIPU_KEY \
  -m glm-5.1,glm-4-flash

ccprofile provider add minimax \
  -u https://api.minimax.chat/v1 \
  -k YOUR_MINIMAX_KEY \
  -m minimax-m2.7

# 2. 交互式创建混合配置
ccprofile add mixed-work --mode mixed

# 3. 切换后会自动启动本地代理
ccprofile switch mixed-work

# 4. 查看代理状态
ccprofile proxy status
```

混合模式切换后，ccprofile 会把 Claude Code 的 opus/sonnet/haiku 默认模型设置为 `ccprofile-opus`、`ccprofile-sonnet`、`ccprofile-haiku`。Claude Code 请求本地代理时，代理按这些虚拟模型名选择 mixed profile 中配置的真实 provider/model。

**注意**：混合模式不能混用 Claude Code Coding Plan 订阅；如需使用官方 Anthropic API，需要把 Anthropic API key 作为一个 provider 添加。

## 命令一览

| 命令 | 说明 | 示例 |
|------|------|------|
| `init` | 初始化加密密钥和 profile 存储 | `ccprofile init` |
| `add <名称>` | 添加配置 | `ccprofile add work` |
| `switch <名称>` | 切换到指定配置 | `ccprofile switch work` |
| `list` | 列出所有配置 | `ccprofile list` |
| `show <名称>` | 显示配置详情，密钥脱敏 | `ccprofile show work` |
| `edit <名称>` | 交互式编辑配置 | `ccprofile edit work` |
| `delete <名称>` | 删除配置 | `ccprofile delete work` |
| `current` | 显示当前活动配置 | `ccprofile current` |
| `provider ...` | 管理混合模式使用的提供商 | `ccprofile provider list` |
| `proxy ...` | 管理混合模式本地代理 | `ccprofile proxy status` |

直接运行 `ccprofile` 会进入交互式菜单。

## Profile 命令

### 添加单一配置

```bash
ccprofile add <名称> [选项]
```

常用选项：

| 选项 | 说明 |
|------|------|
| `--mode single` | 单一模式，默认值 |
| `-t, --token` | API 密钥 |
| `-u, --url` | API 基础地址 |
| `-m, --model` | Claude Code 默认模型槽位：`opus` / `sonnet` / `haiku` |
| `-e, --effort` | 努力等级：`low` / `medium` / `high`，默认 `high` |
| `--anthropic-model` | 设置 `ANTHROPIC_MODEL` |
| `--haiku-model` | 设置 `ANTHROPIC_DEFAULT_HAIKU_MODEL` |
| `--sonnet-model` | 设置 `ANTHROPIC_DEFAULT_SONNET_MODEL` |
| `--opus-model` | 设置 `ANTHROPIC_DEFAULT_OPUS_MODEL` |
| `--disable-all` | 写入全部禁用标志 |
| `--enable-teams` | 启用 Agent Teams |
| `--bark-key` | Bark 推送 Key |
| `--host-label` | 推送中的主机标签 |
| `--notify-sound` | Bark 通知铃声，默认 `minuet` |
| `--hooks-json` | 写入自定义 hooks JSON |

非交互添加单一配置时，`-t`、`-u`、`-m` 必须同时提供。

### 添加混合配置

```bash
ccprofile add <名称> --mode mixed
```

混合配置目前使用交互式流程创建。创建前需要先用 `ccprofile provider add` 添加至少一个提供商。配置时会分别为 `opus`、`sonnet`、`haiku` 三个槽位选择提供商和模型。

## Provider 命令

Provider 是混合模式的 API 提供商配置，独立加密保存在 `~/.ccprofile/providers.enc`。

| 命令 | 说明 | 示例 |
|------|------|------|
| `provider add <名称>` | 添加提供商 | `ccprofile provider add zhipu` |
| `provider list` | 列出提供商 | `ccprofile provider list` |
| `provider show <名称>` | 显示提供商详情 | `ccprofile provider show zhipu` |
| `provider edit <名称>` | 编辑提供商 | `ccprofile provider edit zhipu` |
| `provider delete <名称>` | 删除提供商 | `ccprofile provider delete zhipu` |

非交互添加：

```bash
ccprofile provider add <名称> \
  -u <API基础地址或/v1/messages端点> \
  -k <API密钥> \
  -m <模型1,模型2,模型3>
```

`-u` / `--url` 应填写兼容 Anthropic Messages API 的基础地址或完整 `/v1/messages` 端点。代理会把请求体中的 `model` 替换为映射后的模型，其余请求字段保持原样，并同时写入 `x-api-key` 与 `Authorization: Bearer <API密钥>` 后转发。

删除 provider 时，如果它正在被某个混合 profile 引用，命令会拒绝删除。

## Proxy 命令

混合模式切换时会自动启动本地代理；切换回单一模式时会自动停止代理。

| 命令 | 说明 | 示例 |
|------|------|------|
| `proxy status` | 查看代理 PID、端口和模型映射 | `ccprofile proxy status` |
| `proxy stop` | 停止代理并清理运行时配置 | `ccprofile proxy stop` |
| `proxy logs` | 查看代理日志最后 50 行 | `ccprofile proxy logs` |
| `proxy logs -n <行数>` | 查看指定行数日志 | `ccprofile proxy logs -n 200` |

默认代理端口是 `18888`。混合配置切换成功后，`~/.claude/settings.json` 会被写入：

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://localhost:18888",
    "ANTHROPIC_AUTH_TOKEN": "ccprofile-proxy",
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "ccprofile-opus",
    "ANTHROPIC_DEFAULT_SONNET_MODEL": "ccprofile-sonnet",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": "ccprofile-haiku"
  }
}
```

## 配置字段说明

### 单一配置

| 字段 | 写入位置 | 说明 | 默认值 |
|------|----------|------|--------|
| `ANTHROPIC_AUTH_TOKEN` | `env` | API 密钥 | 必填 |
| `ANTHROPIC_BASE_URL` | `env` | API 基础地址 | 必填 |
| `model` | 顶层 | Claude Code 默认模型槽位 | `opus` |
| `effortLevel` | 顶层 | 努力等级 | `high` |
| `ANTHROPIC_MODEL` | `env` | 默认模型覆盖 | 空 |
| `ANTHROPIC_DEFAULT_HAIKU_MODEL` | `env` | Haiku 模型覆盖 | 空 |
| `ANTHROPIC_DEFAULT_SONNET_MODEL` | `env` | Sonnet 模型覆盖 | 空 |
| `ANTHROPIC_DEFAULT_OPUS_MODEL` | `env` | Opus 模型覆盖 | 空 |

### 混合配置

| 字段 | 说明 |
|------|------|
| `mode` | 固定为 `mixed` |
| `model_mapping` | `opus`、`sonnet`、`haiku` 到 provider/model 的映射 |
| `model` | Claude Code 默认模型槽位 |
| `effortLevel` | 努力等级 |
| `hooks` | 可选推送或自定义 hooks 配置 |
| `proxy_port` | 可选代理端口，默认 `18888` |

## 标志与通知

### 禁用标志

`--disable-all` 会写入以下环境变量：

| 变量 | 说明 |
|------|------|
| `DISABLE_TELEMETRY` | 禁用遥测 |
| `DISABLE_AUTOUPDATER` | 禁用自动更新 |
| `CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS` | 禁用实验性功能 |
| `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` | 禁用非必要流量 |

### 启用标志

| 变量 | 说明 |
|------|------|
| `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` | 启用 Agent Teams 模式 |

### Bark 推送

添加配置时可以直接写入 Bark 配置：

```bash
ccprofile add work \
  -t sk-xxxxx \
  -u https://api.example.com \
  -m opus \
  --bark-key YOUR_BARK_KEY \
  --host-label "MacBook" \
  --notify-sound minuet
```

支持的事件：

| 事件 | 说明 |
|------|------|
| `Notification` | Claude 等待输入或关注 |
| `PermissionRequest` | Claude 请求操作批准 |
| `Stop` | Claude 任务完成 |

也可以使用 `--hooks-json` 写入完整自定义 hooks 配置。

## 交互式菜单

直接运行：

```bash
ccprofile
```

可通过菜单完成配置切换、查看、添加、编辑、删除、提供商管理和系统设置。菜单支持方向键选择、Enter 确认、Esc 取消。

## 工作原理

### 文件位置

```text
~/.ccprofile/
├── .profile_key        # Fernet 加密密钥
├── profiles.enc        # 加密的 profile 数据
├── providers.enc       # 加密的 provider 数据
├── profiles_meta.json  # 当前活动 profile 等元数据
├── proxy_config.json   # 代理运行时配置，包含明文 API key
├── proxy.pid           # 代理进程 PID
└── proxy.log           # 代理日志

~/.claude/
├── settings.json       # Claude Code 设置，switch 命令会修改
└── settings.json.bak   # 切换前自动备份
```

### 单一模式切换流程

1. 读取并解密指定 profile。
2. 备份当前 `~/.claude/settings.json`。
3. 停止可能存在的混合模式代理。
4. 将 profile 中的 `env`、`model`、`effortLevel`、`hooks` 合并写入 `settings.json`。
5. 更新 `profiles_meta.json` 中的当前活动配置。

### 混合模式切换流程

1. 读取混合 profile 的 `model_mapping`。
2. 读取并解密 provider 配置。
3. 生成 `~/.ccprofile/proxy_config.json`。
4. 停止旧代理并启动新的本地代理进程。
5. 将 Claude Code 的 `ANTHROPIC_BASE_URL` 指向 `http://localhost:18888`，并将 opus/sonnet/haiku 默认模型设置为 `ccprofile-opus`、`ccprofile-sonnet`、`ccprofile-haiku`。
6. 请求到达代理后，按虚拟模型名路由：

```text
ccprofile-opus   -> model_mapping.opus
ccprofile-sonnet -> model_mapping.sonnet
ccprofile-haiku  -> model_mapping.haiku
```

代理会替换请求体中的 `model` 字段和 provider 认证头，再把 Anthropic Messages 请求转发到目标 provider。流式响应会原样转发回 Claude Code。

## 安全说明

- `profiles.enc` 和 `providers.enc` 使用 Fernet 加密。
- API 密钥在 `show` 输出中会脱敏。
- `.profile_key` 和 `proxy_config.json` 会尽量限制为当前用户可读写。
- `proxy_config.json` 是运行时文件，混合模式代理需要它读取明文 API key；停止代理时会清理。
- `settings.local.json` 不会被修改。
- 切换前会备份 `settings.json`，必要时可手动恢复 `settings.json.bak`。

## 项目结构

```text
ccprofile.py                  # 入口脚本
build.py                      # PyInstaller 打包脚本
install.sh                    # Unix 安装脚本
install.bat                   # Windows 安装脚本
ccprofile_app/
├── __init__.py
├── cli.py                    # argparse 定义和 main()
├── commands.py               # profile 和 proxy 命令处理
├── constants.py              # 路径、字段和 hooks 常量
├── crypto.py                 # Fernet 密钥管理、加解密
├── formatting.py             # token 脱敏
├── hooks.py                  # Bark hooks 生成
├── menu.py                   # 交互式菜单
├── prompts.py                # 交互式输入
├── provider.py               # provider CRUD 命令
├── proxy.py                  # 本地 HTTP 代理
├── proxy_process.py          # 代理进程管理
├── storage.py                # 文件读写、备份、迁移
└── terminal.py               # 终端按键读取、列表选择
```

## 开发

源码运行：

```bash
python ccprofile.py --help
python ccprofile.py init
```

本地打包：

```bash
python build.py
```

打包产物为 PyInstaller onedir 目录：`dist/ccprofile/`，可执行入口在 `dist/ccprofile/ccprofile`。发布或本地安装时需要保留整个目录。

GitHub Release 会把该目录打包为 `ccprofile-macos-arm64.tar.gz`、`ccprofile-linux.tar.gz` 或 `ccprofile-windows.zip`。不再支持 Intel Mac。请勿只发布或下载目录中的单个可执行文件。

依赖：

- Python 3
- `cryptography`
- 打包时需要 `pyinstaller`

## 许可证

MIT
