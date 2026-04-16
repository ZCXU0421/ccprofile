# ccprofile 混合提供商代理方案

## 概述

允许用户配置多个 API 提供商（智谱、MiniMax、自定义），将不同提供商的模型映射到 Claude Code 的模型槽位（opus/sonnet/haiku），通过本地代理服务器实现请求路由。

混合模式混合的是 `base_url + api_key` 形式的 API provider，不混合 Claude Code Coding Plan 订阅。Claude Code 官方订阅不是普通 Anthropic API key，切换到本地代理后，请求会走 `ANTHROPIC_BASE_URL=http://localhost:{port}`，因此不能把某个槽位继续保留在 Claude Code 官方订阅通道里。

**示例场景**: zhipu glm-5.1 → opus, minimax m2.7 → haiku, zhipu glm-4-flash → sonnet

**协议**: Anthropic Messages API 原生格式，代理只做路由转发，不做格式转换。

## 一、数据模型

### 1.1 Provider（API 提供商）

独立存储，与 profile 分离。加密存储在 `~/.ccprofile/providers.enc`。
`base_url` 可以填写 API 基础地址，也可以填写完整 `/v1/messages` 端点；代理会统一转发到 Anthropic Messages 路径。

```python
{
    "zhipu": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "api_key": "xxx.xxx",
        "models": ["glm-5.1", "glm-4-plus", "glm-4-flash"]
    },
    "minimax": {
        "base_url": "https://api.minimax.chat/v1",
        "api_key": "yyy",
        "models": ["minimax-m2.7", "minimax-m2.5"]
    }
}
```

### 1.2 Profile 扩展

在现有 profile 中增加 `mode` 字段，区分单一/混合模式：

```python
# 单一模式（完全兼容现有格式）
{
    "mode": "single",
    "env": {
        "ANTHROPIC_AUTH_TOKEN": "...",
        "ANTHROPIC_BASE_URL": "...",
        ...
    },
    "model": "opus",
    "effortLevel": "high",
    "hooks": { ... }
}

# 混合模式（新增）
{
    "mode": "mixed",
    "model_mapping": {
        "opus":   {"provider": "zhipu",   "model": "glm-5.1"},
        "sonnet": {"provider": "zhipu",   "model": "glm-4-flash"},
        "haiku":  {"provider": "minimax", "model": "minimax-m2.7"}
    },
    "model": "opus",
    "effortLevel": "high",
    "hooks": { ... },
    "proxy_port": 18888  # 可选，默认 18888
}
```

混合模式下**不再需要** `env.ANTHROPIC_AUTH_TOKEN` 和 `env.ANTHROPIC_BASE_URL`（由代理动态注入）。

### 1.3 代理配置文件

`~/.ccprofile/proxy_config.json` — switch 时写入，代理进程读取：

```python
{
    "port": 18888,
    "virtual_model_prefix": "ccprofile",
    "model_mapping": {
        "opus":   {"provider": "zhipu",   "model": "glm-5.1", "base_url": "...", "api_key": "..."},
        "sonnet": {"provider": "zhipu",   "model": "glm-4-flash", "base_url": "...", "api_key": "..."},
        "haiku":  {"provider": "minimax", "model": "minimax-m2.7", "base_url": "...", "api_key": "..."}
    }
}
```

> 注意：`proxy_config.json` 包含明文 API key，权限与 `.profile_key` 相同（chmod 600）。

### 1.4 文件路径新增

| 文件 | 用途 |
|------|------|
| `~/.ccprofile/providers.enc` | 加密的提供商配置 |
| `~/.ccprofile/proxy_config.json` | 代理运行时配置 |
| `~/.ccprofile/proxy.pid` | 代理进程 PID |
| `~/.ccprofile/proxy.log` | 代理日志 |

## 二、本地代理架构

### 2.1 核心流程

```
ccprofile switch mixed profile
    ↓ 写入 settings.json
      ANTHROPIC_BASE_URL=http://localhost:18888
      ANTHROPIC_AUTH_TOKEN=ccprofile-proxy
      ANTHROPIC_DEFAULT_OPUS_MODEL=ccprofile-opus
      ANTHROPIC_DEFAULT_SONNET_MODEL=ccprofile-sonnet
      ANTHROPIC_DEFAULT_HAIKU_MODEL=ccprofile-haiku
    ↓
Claude Code
    ↓ POST /v1/messages (model: "ccprofile-opus")
    ↓
本地代理 (localhost:18888)
    ↓ 读取 model 字段 → 解析虚拟模型名 → 查找 model_mapping
    ↓ model_mapping.opus → provider=zhipu, model=glm-5.1
    ↓ 替换 model 字段为 "glm-5.1"
    ↓ 替换认证 header 为 zhipu 的 api_key
    ↓
POST https://open.bigmodel.cn/api/paas/v4/v1/messages
    ↓
流式响应 SSE → 原样回传给 Claude Code
```

### 2.2 代理实现（proxy.py）

使用 Python 标准库 `http.server` + `http.client`，零额外依赖：

- **请求接收**: `BaseHTTPRequestHandler.do_POST` 处理 `/v1/messages`
- **模型路由**: 解析请求体 JSON 的 `model` 字段，将 `ccprofile-*` 虚拟模型名映射到 model_mapping
- **请求转发**: `http.client` 转发到目标 provider（支持 streaming）
- **SSE 流式**: 逐块读取响应并写回客户端（chunked transfer）
- **错误处理**: provider 不可达时返回 Anthropic 格式错误响应

### 2.3 模型路由调整

当前实现按 Claude 官方模型 ID 前缀反推槽位，例如 `claude-opus-*`、`claude-sonnet-*`、`claude-haiku-*`。这个方案存在两个问题：

1. Claude / Anthropic 模型 ID 会演进，例如当前 Haiku 模型可能是 `claude-3-5-haiku-20241022`，不匹配旧的 `claude-haiku` 前缀。
2. 混合模式不能混用 Claude Code Coding Plan 订阅，因此保留 Claude 官方模型名没有实际订阅通道上的收益，反而让 ccprofile 依赖外部命名规则。

调整后的主路径使用 ccprofile 自己控制的虚拟模型名：

| Claude Code 请求 model | 路由槽位 | 目标 |
|------------------------|----------|------|
| `ccprofile-opus` | `opus` | `model_mapping["opus"]` |
| `ccprofile-sonnet` | `sonnet` | `model_mapping["sonnet"]` |
| `ccprofile-haiku` | `haiku` | `model_mapping["haiku"]` |

`ccprofile switch <mixed-profile>` 写入 `settings.json` 时，应同时设置：

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

代理只把虚拟模型名作为槽位选择信号，真实上游模型仍以 mixed profile 的 `model_mapping` 为准。这样配置的唯一真相是：

```
ccprofile-opus   -> model_mapping.opus.provider/model
ccprofile-sonnet -> model_mapping.sonnet.provider/model
ccprofile-haiku  -> model_mapping.haiku.provider/model
```

兼容策略：

- 主路径只要求支持 `ccprofile-opus`、`ccprofile-sonnet`、`ccprofile-haiku`。
- 可以保留旧的 Claude 模型名前缀匹配作为兼容 fallback，避免用户手动指定旧模型名时立刻失败。
- fallback 不应作为文档推荐路径，也不应阻止未来移除 `MODEL_SLOT_PREFIXES`。

### 2.4 代理进程管理

```
switch 混合 profile:
  1. 写入 proxy_config.json（合并 provider 信息到 model_mapping）
  2. 检查 proxy.pid 是否有运行中代理 → 有则 kill
  3. subprocess.Popen 启动代理（detached, 输出重定向到 proxy.log）
  4. 等待端口就绪（轮询最多 3 秒）
  5. 写入 settings.json:
     - ANTHROPIC_BASE_URL = "http://localhost:{port}"
     - ANTHROPIC_AUTH_TOKEN = "ccprofile-proxy"
     - ANTHROPIC_DEFAULT_OPUS_MODEL = "ccprofile-opus"
     - ANTHROPIC_DEFAULT_SONNET_MODEL = "ccprofile-sonnet"
     - ANTHROPIC_DEFAULT_HAIKU_MODEL = "ccprofile-haiku"

switch 单一 profile:
  1. 检查 proxy.pid → 有则 kill
  2. 清理 proxy_config.json
  3. 正常写入 settings.json（直接用 provider 的 base_url）
```

## 三、CLI 命令设计

### 3.1 新增命令

```
# 提供商管理
ccprofile provider add <name>           # 交互式添加提供商
ccprofile provider add <name> -u <url> -k <key> --models m1,m2
ccprofile provider list                 # 列出所有提供商
ccprofile provider show <name>          # 显示提供商详情
ccprofile provider edit <name>          # 编辑提供商
ccprofile provider delete <name>        # 删除提供商

# 代理管理
ccprofile proxy status                  # 代理状态
ccprofile proxy stop                    # 停止代理
ccprofile proxy logs                    # 查看代理日志
```

### 3.2 修改命令

```
# add — 支持 --mode mixed
ccprofile add my-mix --mode mixed       # 交互式添加混合配置

# switch — 自动管理代理生命周期
ccprofile switch my-mix                 # 自动启动代理
ccprofile switch my-single              # 自动停止代理

# list — 显示模式列
#   名称        模式      URL/映射                模型     通知
# * my-mix     mixed    opus→zhipu,sonnet→...    opus
#   pocoai     single   https://api.pocoai.com   opus

# show — 显示映射详情
```

### 3.3 交互式菜单扩展

```
主菜单:
  切换配置
  查看配置 ←→
  管理配置 ←→
  提供商管理 ←→      ← 新增
  系统设置 ←→

提供商管理 子菜单:
  添加提供商
  列出提供商
  编辑提供商
  删除提供商
```

添加配置时，选择 `single` 或 `mixed` 模式：
- `single` → 现有流程（输入 URL/Key）
- `mixed` → 从已注册提供商中选择，为每个槽位分配模型

## 四、文件变更清单

### 新建文件

| 文件 | 职责 |
|------|------|
| `ccprofile_app/proxy.py` | HTTP 代理服务器（接收请求、路由、转发、SSE 流式） |
| `ccprofile_app/provider.py` | Provider CRUD 命令（cmd_provider_add/list/show/edit/delete） |
| `ccprofile_app/proxy_process.py` | 代理进程管理（start/stop/status，PID 文件，端口检测） |

### 修改文件

| 文件 | 变更内容 |
|------|----------|
| `constants.py` | 新增路径（PROVIDERS_ENC, PROXY_*），PROVIDER_FIELDS 定义，MODEL_SLOTS 定义，VIRTUAL_MODEL_PREFIX 定义 |
| `storage.py` | 新增 load_providers()/save_providers()，代理配置文件读写 |
| `commands.py` | cmd_switch 增加混合模式分支（启动/停止代理，并写入 ccprofile 虚拟模型名）；cmd_add 支持 --mode mixed |
| `cli.py` | 新增 provider/ proxy 子命令组 |
| `menu.py` | 新增提供商管理子菜单；add 流程增加模式选择 |
| `prompts.py` | 新增 prompt_mixed_profile_fields()、prompt_provider_fields() |

### 不变文件

| 文件 | 说明 |
|------|------|
| `crypto.py` | 加解密逻辑不变 |
| `formatting.py` | token masking 不变 |
| `hooks.py` | hooks 生成不变 |
| `terminal.py` | 终端 UI 不变 |

## 五、实现步骤

### Step 1: 基础设施 — constants.py + storage.py 扩展
- 新增 PROVIDERS_ENC, PROXY_PID, PROXY_CONFIG, PROXY_LOG, PROXY_PORT 路径常量
- 新增 PROVIDER_FIELDS, MODEL_SLOTS 定义
- 新增 VIRTUAL_MODEL_PREFIX = "ccprofile"，并约定虚拟模型名为 `ccprofile-{slot}`
- storage.py 增加 load_providers(), save_providers()（使用相同加密体系）
- storage.py 增加 proxy_config 读写函数

### Step 2: Provider 管理 — provider.py + cli.py + menu.py
- 实现 cmd_provider_add/list/show/edit/delete
- cli.py 增加 provider 子命令
- menu.py 增加"提供商管理"子菜单
- prompts.py 增加 prompt_provider_fields()

### Step 3: 混合配置添加 — prompts.py + commands.py
- prompts.py 增加 prompt_mixed_profile_fields()（选提供商 → 选模型 → 组装 mapping）
- cmd_add 支持 --mode mixed 参数
- 交互菜单 add 流程增加模式选择

### Step 4: 本地代理 — proxy.py
- 实现 Anthropic Messages API 代理
- 模型路由主路径：`ccprofile-opus` / `ccprofile-sonnet` / `ccprofile-haiku`
- 可选兼容 fallback：继续识别旧的 Claude 模型名前缀
- SSE 流式转发
- 错误处理

### Step 5: 代理进程管理 — proxy_process.py
- start_proxy() / stop_proxy() / proxy_status()
- PID 文件管理
- 端口就绪检测
- 日志输出

### Step 6: Switch 集成 — commands.py
- cmd_switch 增加混合模式分支
- 混合模式：写 proxy_config → 启动代理 → 设置 localhost URL 和 `ccprofile-{slot}` 虚拟模型名
- 单一模式：停止代理 → 设置 provider URL
- cmd_list/cmd_show 适配混合模式显示

### Step 7: 代理管理命令 — cli.py
- proxy status / stop / logs 子命令

### Step 8: 迁移当前前缀匹配实现
- `constants.py` 增加 `VIRTUAL_MODEL_PREFIX`，减少对 `MODEL_SLOT_PREFIXES` 的主路径依赖。
- `commands.py` 在 mixed switch 中写入 `ANTHROPIC_DEFAULT_OPUS_MODEL`、`ANTHROPIC_DEFAULT_SONNET_MODEL`、`ANTHROPIC_DEFAULT_HAIKU_MODEL`。
- `proxy.py` 的 `get_model_target()` 优先解析 `ccprofile-{slot}`，再进入旧 Claude 前缀 fallback。
- README 中混合模式说明改为“Claude Code 使用 ccprofile 虚拟模型名，代理按槽位转发到真实 provider/model”。
- 添加或补充验证：`ccprofile-haiku` 能命中 haiku 槽位；`claude-3-5-haiku-20241022` 如果保留 fallback，也应命中 haiku 槽位。

## 六、依赖关系

```
Step 1 (基础设施)
    ↓
Step 2 (Provider 管理)  ← 可独立使用
    ↓
Step 3 (混合配置添加)
    ↓
Step 4 (代理服务器)
    ↓
Step 5 (进程管理)
    ↓
Step 6 (Switch 集成)    ← 核心串联
    ↓
Step 7 (代理管理命令)
```

**零新依赖**：仅使用 Python 标准库（http.server, http.client, urllib.parse, subprocess, json, threading）。
