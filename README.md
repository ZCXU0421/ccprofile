# ccprofile - Claude Code API 配置管理工具

使用 Fernet 对称加密管理多套 API 提供商配置，支持命令行一键切换。

## 依赖

- Python 3.8+
- `cryptography`

```bash
pip install cryptography
```

## 快速开始

```bash
# 初始化（生成加密密钥）
python ccprofile.py init

# 添加配置（交互式）
python ccprofile.py add my-provider

# 添加配置（非交互式）
python ccprofile.py add my-provider -t <API密钥> -u <API地址> -m opus

# 列出所有配置
python ccprofile.py list

# 切换配置
python ccprofile.py switch my-provider

# 查看当前活动配置
python ccprofile.py current
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

### add 命令参数

```
-t, --token          API 密钥
-u, --url            API 基础地址
-m, --model          模型 (opus/sonnet/haiku)
-e, --effort         努力等级 (low/medium/high)
--anthropic-model    默认模型
--haiku-model        Haiku 模型覆盖
--sonnet-model       Sonnet 模型覆盖
--opus-model         Opus 模型覆盖
--disable-all        启用所有禁用标志
--enable-teams       启用 Agent Teams 模式
```

## 配置项

| 字段 | 说明 | 必填 |
|------|------|------|
| `ANTHROPIC_AUTH_TOKEN` | API 密钥 | 是 |
| `ANTHROPIC_BASE_URL` | API 基础地址 | 是 |
| `model` | 模型选择 | 是 |
| `effortLevel` | 努力等级 | 否，默认 high |
| `ANTHROPIC_MODEL` | 默认模型 | 否 |
| `ANTHROPIC_DEFAULT_*_MODEL` | 各级别模型覆盖 | 否 |

## 文件结构

```
~/.claude/
    .profile_key          ← Fernet 加密密钥
    profiles.enc          ← 加密的配置存储
    profiles_meta.json    ← 元数据（当前活动配置）
    settings.json         ← Claude Code 设置（switch 命令修改目标）
    settings.json.bak     ← 切换前自动备份
```

## 安全说明

- 使用 Fernet（AES-128-CBC + HMAC-SHA256）加密存储所有配置
- 密钥文件在 Windows 上设置隐藏属性，并限制文件权限
- `show` 命令对 API 密钥进行脱敏显示（仅保留前8后4字符）
- `switch` 命令在修改前自动备份 `settings.json`
