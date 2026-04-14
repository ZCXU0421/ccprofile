# ccprofile - Claude Code API 配置管理工具

使用 Fernet 对称加密管理多套 API 提供商配置，支持命令行一键切换。

## 安装

从 [Releases](../../releases) 下载对应平台的文件，然后运行安装脚本。

### 命令行一键下载（推荐）

使用 `curl` 下载最新发行版到当前目录：

**Windows（PowerShell）：**

```powershell
curl -sLO "https://github.com/ZCXU0421/ccprofile/releases/latest/download/ccprofile-windows.exe"
curl -sLO "https://github.com/ZCXU0421/ccprofile/releases/latest/download/install-windows.bat"
```

**macOS：**

```bash
curl -sLO "https://github.com/ZCXU0421/ccprofile/releases/latest/download/ccprofile-macos"
curl -sLO "https://github.com/ZCXU0421/ccprofile/releases/latest/download/install-macos.sh"
chmod +x install-macos.sh ccprofile-macos
```

**Linux：**

```bash
curl -sLO "https://github.com/ZCXU0421/ccprofile/releases/latest/download/ccprofile-linux"
curl -sLO "https://github.com/ZCXU0421/ccprofile/releases/latest/download/install-linux.sh"
chmod +x install-linux.sh ccprofile-linux
```

> **提示**：如果已安装 [GitHub CLI (`gh`)](https://cli.github.com/)，也可以用 `gh` 下载：
>
> ```bash
> gh release download --repo ZCXU0421/ccprofile --pattern "ccprofile-linux" --pattern "install-linux.sh"
> ```

### 手动下载与安装

#### Windows

下载 `ccprofile-windows.exe` 和 `install-windows.bat`，放在同一目录下，双击 `install-windows.bat`。

安装完成后重启终端，即可使用 `ccprofile` 命令。

#### macOS

下载 `ccprofile-macos` 和 `install-macos.sh`，放在同一目录下，运行：

```bash
chmod +x install-macos.sh
bash install-macos.sh
```

#### Linux

下载 `ccprofile-linux` 和 `install-linux.sh`，放在同一目录下，运行：

```bash
chmod +x install-linux.sh
bash install-linux.sh
```

## 快速开始

```bash
# 初始化（生成加密密钥）
ccprofile init

# 添加配置（交互式）
ccprofile add my-provider

# 添加配置（非交互式）
ccprofile add my-provider -t <API密钥> -u <API地址> -m opus

# 列出所有配置
ccprofile list

# 切换配置
ccprofile switch my-provider

# 查看当前活动配置
ccprofile current
```

## 所有命令

| 命令 | 说明 |
|------|------|
| `init` | 初始化，生成加密密钥 |
| `add <名称>` | 添加配置（支持交互式和参数模式） |
| `switch <名称>` | 切换到指定配置 |
| `list` | 列出所有配置 |
| `show <名称>` | 显示配置详情（密钥脱敏） |
| `edit <名称>` | 交互式编辑配置 |
| `delete <名称>` | 删除配置 |
| `current` | 显示当前活动配置 |

## 配置项

| 字段 | 说明 | 必填 |
|------|------|------|
| `ANTHROPIC_AUTH_TOKEN` | API 密钥 | 是 |
| `ANTHROPIC_BASE_URL` | API 基础地址 | 是 |
| `model` | 模型选择 | 是 |
| `effortLevel` | 努力等级 | 否，默认 high |
| `ANTHROPIC_MODEL` | 默认模型 | 否 |
| `ANTHROPIC_DEFAULT_*_MODEL` | 各级别模型覆盖 | 否 |

## 项目结构

```text
ccprofile.py                  # 兼容入口
ccprofile_app/
  __init__.py
  cli.py                      # argparse 定义和 main()
  constants.py                # 路径、字段定义、hooks 模板等常量
  crypto.py                   # Fernet 密钥加载、保存、加解密
  storage.py                  # profiles/meta/settings 读写和备份
  hooks.py                    # hooks 生成、Bark key 脱敏
  formatting.py               # token 脱敏
  prompts.py                  # profile 字段交互输入
  commands.py                 # init/add/switch/... 命令处理
  terminal.py                 # 方向键读取、列表选择、VT mode
  menu.py                     # interactive_menu()
```
