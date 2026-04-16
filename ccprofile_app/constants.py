"""常量定义：路径、字段、hooks 模板等。"""

from pathlib import Path

VERSION = "0.2.0"

CLAUDE_DIR = Path.home() / ".claude"
PROFILE_DIR = Path.home() / ".ccprofile"
KEY_FILE = PROFILE_DIR / ".profile_key"
PROFILES_ENC = PROFILE_DIR / "profiles.enc"
META_FILE = PROFILE_DIR / "profiles_meta.json"
SETTINGS_FILE = CLAUDE_DIR / "settings.json"
SETTINGS_BAK = CLAUDE_DIR / "settings.json.bak"

# Provider storage
PROVIDERS_ENC = PROFILE_DIR / "providers.enc"

# Proxy runtime files
PROXY_CONFIG = PROFILE_DIR / "proxy_config.json"
PROXY_PID = PROFILE_DIR / "proxy.pid"
PROXY_LOG = PROFILE_DIR / "proxy.log"
DEFAULT_PROXY_PORT = 18888

FIELDS = [
    # (key, label, required, default)
    ("ANTHROPIC_AUTH_TOKEN", "API 密钥", True, None),
    ("ANTHROPIC_BASE_URL", "API 基础地址", True, None),
    ("model", "模型 (opus/sonnet/haiku)", True, "opus"),
    ("effortLevel", "努力等级 (low/medium/high)", False, "high"),
    ("ANTHROPIC_MODEL", "默认模型", False, None),
    ("ANTHROPIC_DEFAULT_HAIKU_MODEL", "Haiku 模型覆盖", False, None),
    ("ANTHROPIC_DEFAULT_SONNET_MODEL", "Sonnet 模型覆盖", False, None),
    ("ANTHROPIC_DEFAULT_OPUS_MODEL", "Opus 模型覆盖", False, None),
]

DISABLE_FLAGS = [
    ("DISABLE_TELEMETRY", "禁用遥测"),
    ("DISABLE_AUTOUPDATER", "禁用自动更新"),
    ("CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS", "禁用实验性功能"),
    ("CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC", "禁用非必要流量"),
]

ENABLE_FLAGS = [
    ("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS", "启用 Agent Teams 模式"),
]

HOOK_EVENTS = {
    "Notification": {
        "title": "\U0001f4ac [{host}] Claude 需要输入",
        "body": "您的 {host} 主机正在等待输入或关注。",
    },
    "PermissionRequest": {
        "title": "\u26a0\ufe0f [{host}] Claude 需要批准",
        "body": "您的 {host} 主机正在请求执行操作，请回终端确认。",
    },
    "Stop": {
        "title": "\u2705 [{host}] Claude 任务完成",
        "body": "您的 {host} 主机上的任务已执行结束。",
    },
}

HOOKS_FIELDS = [
    ("bark_key", "Bark Key", True, None),
    ("host_label", "主机名标签", False, None),
    ("sound", "通知铃声", False, "minuet"),
]

# Provider fields for interactive input
PROVIDER_FIELDS = [
    # (key, label, required, default)
    ("base_url", "API 基础地址或 /v1/messages 端点", True, None),
    ("api_key", "API 密钥", True, None),
    ("models", "可用模型 (逗号分隔)", True, None),
]

# Claude Code model slots
MODEL_SLOTS = ["opus", "sonnet", "haiku"]

# Virtual model names for ccprofile routing
VIRTUAL_MODEL_PREFIX = "ccprofile"

VIRTUAL_MODEL_NAMES = {
    slot: f"{VIRTUAL_MODEL_PREFIX}-{slot}"
    for slot in MODEL_SLOTS
}

# Legacy Claude model name prefixes (fallback only)
LEGACY_MODEL_SLOT_PREFIXES = {
    "opus": ("claude-opus",),
    "sonnet": ("claude-sonnet",),
    "haiku": (
        "claude-haiku",
        "claude-3-haiku",
        "claude-3-5-haiku",
    ),
}

# Env keys that ccprofile manages in settings.json
CCPROFILE_MANAGED_ENV_KEYS = {
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "DISABLE_TELEMETRY",
    "DISABLE_AUTOUPDATER",
    "CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC",
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS",
}
