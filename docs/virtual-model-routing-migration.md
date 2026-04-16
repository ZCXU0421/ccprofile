# ccprofile 虚拟模型路由迁移说明

## 背景

当前 mixed 模式通过 Claude 官方模型名前缀反推槽位：

```text
claude-opus-*   -> opus
claude-sonnet-* -> sonnet
claude-haiku-*  -> haiku
```

这个设计会依赖 Claude / Anthropic 的模型命名规则。实际 Haiku 模型可能是 `claude-3-5-haiku-20241022`，不会命中旧的 `claude-haiku` 前缀。

mixed 模式本质上混合的是 API provider，不是 Claude Code Coding Plan 订阅。因此没有必要保留 Claude 官方模型名作为主路由信号。更稳定的方案是让 ccprofile 写入自己控制的虚拟模型名：

```text
ccprofile-opus
ccprofile-sonnet
ccprofile-haiku
```

代理按这些虚拟模型名选择槽位，再把请求体中的 `model` 替换成 mixed profile 中配置的真实上游模型。

## 目标行为

切换 mixed profile 后，`settings.json` 应写入：

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

代理路由规则：

| 请求 model | 槽位 | 转发目标 |
|------------|------|----------|
| `ccprofile-opus` | `opus` | `model_mapping["opus"]` |
| `ccprofile-sonnet` | `sonnet` | `model_mapping["sonnet"]` |
| `ccprofile-haiku` | `haiku` | `model_mapping["haiku"]` |

兼容策略：

- 主路径必须优先支持 `ccprofile-{slot}`。
- 旧的 Claude 模型名前缀匹配可以作为 fallback 保留一版，避免已有手动配置立刻失效。
- 文档和默认写入逻辑都应引导用户走 `ccprofile-{slot}`。

## 需要修改的代码

### 1. `ccprofile_app/constants.py`

当前代码：

```python
MODEL_SLOTS = ["opus", "sonnet", "haiku"]

MODEL_SLOT_PREFIXES = {
    "opus": "claude-opus",
    "sonnet": "claude-sonnet",
    "haiku": "claude-haiku",
}
```

建议修改：

```python
MODEL_SLOTS = ["opus", "sonnet", "haiku"]
VIRTUAL_MODEL_PREFIX = "ccprofile"

VIRTUAL_MODEL_NAMES = {
    slot: f"{VIRTUAL_MODEL_PREFIX}-{slot}"
    for slot in MODEL_SLOTS
}

# 旧逻辑仅作为 proxy fallback 使用。
LEGACY_MODEL_SLOT_PREFIXES = {
    "opus": ("claude-opus",),
    "sonnet": ("claude-sonnet",),
    "haiku": (
        "claude-haiku",
        "claude-3-haiku",
        "claude-3-5-haiku",
    ),
}
```

注意点：

- `CCPROFILE_MANAGED_ENV_KEYS` 已包含 `ANTHROPIC_DEFAULT_*_MODEL`，不需要新增 key。
- 如果为了减少改动，也可以暂时保留 `MODEL_SLOT_PREFIXES` 名称，但语义上建议改成 `LEGACY_MODEL_SLOT_PREFIXES`，避免继续把旧前缀当主路径。

### 2. `ccprofile_app/commands.py`

当前 mixed switch 只写：

```python
settings["env"]["ANTHROPIC_BASE_URL"] = f"http://localhost:{port}"
settings["env"]["ANTHROPIC_AUTH_TOKEN"] = "ccprofile-proxy"
```

需要增加虚拟模型名写入：

```python
settings["env"]["ANTHROPIC_BASE_URL"] = f"http://localhost:{port}"
settings["env"]["ANTHROPIC_AUTH_TOKEN"] = "ccprofile-proxy"
settings["env"]["ANTHROPIC_DEFAULT_OPUS_MODEL"] = VIRTUAL_MODEL_NAMES["opus"]
settings["env"]["ANTHROPIC_DEFAULT_SONNET_MODEL"] = VIRTUAL_MODEL_NAMES["sonnet"]
settings["env"]["ANTHROPIC_DEFAULT_HAIKU_MODEL"] = VIRTUAL_MODEL_NAMES["haiku"]
```

同时 `proxy_config` 建议从：

```python
proxy_config = {
    "port": profile.get("proxy_port", DEFAULT_PROXY_PORT),
    "model_mapping": {},
    "model_slot_prefixes": dict(MODEL_SLOT_PREFIXES),
}
```

改成：

```python
proxy_config = {
    "port": profile.get("proxy_port", DEFAULT_PROXY_PORT),
    "virtual_model_prefix": VIRTUAL_MODEL_PREFIX,
    "model_mapping": {},
    "legacy_model_slot_prefixes": LEGACY_MODEL_SLOT_PREFIXES,
}
```

如果决定不保留 legacy fallback，则可以不写 `legacy_model_slot_prefixes`。

注意点：

- `commands.py` 的 import 需要从 `constants.py` 引入 `VIRTUAL_MODEL_NAMES` 和可选的 `LEGACY_MODEL_SLOT_PREFIXES`。
- mixed 模式仍然不应从 profile 的 `env` 读取 `ANTHROPIC_*` key，因为真实认证信息来自 provider。
- single 模式不变，继续把 profile 的 `env` 原样写入 settings。

### 3. `ccprofile_app/proxy.py`

当前代理独立进程不能依赖 `ccprofile_app.constants`，所以需要在 `proxy.py` 内保留本地默认常量。

当前路由逻辑：

```python
for slot, prefix in self._model_slot_prefixes.items():
    if model.startswith(prefix):
        return model_mapping.get(slot)
```

建议改为：

```python
_DEFAULT_VIRTUAL_MODEL_PREFIX = "ccprofile"
_DEFAULT_LEGACY_MODEL_SLOT_PREFIXES = {
    "opus": ("claude-opus",),
    "sonnet": ("claude-sonnet",),
    "haiku": (
        "claude-haiku",
        "claude-3-haiku",
        "claude-3-5-haiku",
    ),
}
```

`ProxyConfig.__init__()` 增加：

```python
self._virtual_model_prefix = _DEFAULT_VIRTUAL_MODEL_PREFIX
self._legacy_model_slot_prefixes = dict(_DEFAULT_LEGACY_MODEL_SLOT_PREFIXES)
```

`_load_config()` 增加：

```python
self._virtual_model_prefix = self.config.get(
    "virtual_model_prefix",
    self._virtual_model_prefix,
)

if "legacy_model_slot_prefixes" in self.config:
    self._legacy_model_slot_prefixes = self.config["legacy_model_slot_prefixes"]
elif "model_slot_prefixes" in self.config:
    # 兼容旧 proxy_config.json。
    self._legacy_model_slot_prefixes = {
        slot: (prefix,)
        for slot, prefix in self.config["model_slot_prefixes"].items()
    }
```

`get_model_target()` 改成先匹配虚拟模型名，再 fallback：

```python
def get_model_target(self, model: str) -> Optional[Dict[str, Any]]:
    if not self.config:
        return None

    model_mapping = self.config.get("model_mapping", {})

    virtual_prefix = f"{self._virtual_model_prefix}-"
    if model.startswith(virtual_prefix):
        slot = model.removeprefix(virtual_prefix)
        if slot in model_mapping:
            return model_mapping.get(slot)

    for slot, prefixes in self._legacy_model_slot_prefixes.items():
        if isinstance(prefixes, str):
            prefixes = (prefixes,)
        if any(model.startswith(prefix) for prefix in prefixes):
            return model_mapping.get(slot)

    return None
```

注意点：

- `removeprefix()` 需要 Python 3.9+。如果项目要支持 Python 3.8，应改成切片：`slot = model[len(virtual_prefix):]`。
- fallback 的 Haiku 前缀建议至少覆盖 `claude-3-haiku` 和 `claude-3-5-haiku`，解决当前 review 指出的 P2。
- 如果不保留 fallback，则 `get_model_target()` 只需要解析 `ccprofile-{slot}`。

### 4. `README.md`

需要更新 mixed 模式说明。当前文档说“按请求中的模型前缀选择目标提供商”，应改成：

```text
混合模式切换后，ccprofile 会把 Claude Code 的 opus/sonnet/haiku 默认模型设置为
ccprofile-opus、ccprofile-sonnet、ccprofile-haiku。Claude Code 请求本地代理时，
代理按这些虚拟模型名选择 mixed profile 中配置的真实 provider/model。
```

还应明确：

```text
mixed 模式不能混用 Claude Code Coding Plan 订阅；如需走官方 Anthropic，
需要把 Anthropic API key 作为一个 provider 添加。
```

### 5. `docs/mixed-provider-proxy-plan.md`

总体方案文档已经应体现新设计。需要保持以下内容一致：

- mixed 模式混合 API provider，不混合 Claude Code Coding Plan 订阅。
- 主路径是 `ccprofile-opus` / `ccprofile-sonnet` / `ccprofile-haiku`。
- Claude 官方模型名前缀只作为可选兼容 fallback。
- switch mixed 会写入 `ANTHROPIC_DEFAULT_*_MODEL`。

## 推荐实现顺序

1. 修改 `constants.py`，引入虚拟模型名常量和 legacy fallback 常量。
2. 修改 `commands.py`，mixed switch 写入 `ANTHROPIC_DEFAULT_*_MODEL`，并在 `proxy_config` 写入 `virtual_model_prefix`。
3. 修改 `proxy.py`，让 `get_model_target()` 优先解析 `ccprofile-{slot}`。
4. 更新 `README.md`，说明 mixed 模式的真实行为和订阅边界。
5. 增加或补充最小验证用例。

## 验证建议

### 手动验证

1. 添加两个 provider。
2. 创建 mixed profile，把不同槽位映射到不同 provider/model。
3. `ccprofile switch <mixed-profile>`。
4. 检查 `~/.claude/settings.json`：

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

5. 发起 Claude Code 请求，确认代理日志中上游 model 被替换为 mixed profile 配置的真实模型。

### 单元级验证

可以对 `ProxyConfig.get_model_target()` 补以下用例：

| 输入 model | 期望 |
|------------|------|
| `ccprofile-opus` | 返回 opus target |
| `ccprofile-sonnet` | 返回 sonnet target |
| `ccprofile-haiku` | 返回 haiku target |
| `claude-3-5-haiku-20241022` | 如果启用 fallback，返回 haiku target |
| `unknown-model` | 返回 `None` |

### 回归点

- single profile 切换仍应停止代理，并按原有 profile `env` 写入 settings。
- mixed profile 切换前会清除旧的 ccprofile 管理 env key，避免上一个 profile 的模型覆盖泄漏。
- 代理转发时仍应替换认证 header，不能把 `ccprofile-proxy` 传给上游。

## 非目标

- 不实现 Claude Code Coding Plan 订阅和第三方 API provider 的混用。
- 不把 Claude 官方模型 ID 作为 mixed 模式主配置入口。
- 不改变 provider 的存储结构和加密方式。
