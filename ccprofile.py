#!/usr/bin/env python3
"""ccprofile - Claude Code API 配置管理工具

使用 Fernet 对称加密管理多套 API 提供商配置，支持命令行一键切换。
"""

import argparse
import json
import os
import shlex
import shutil
import socket
import sys
from pathlib import Path

# Fix encoding on Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

try:
    from cryptography.fernet import Fernet
except ImportError:
    print("Error: cryptography package required. Run: pip install cryptography")
    sys.exit(1)

# --- 常量 ---
CLAUDE_DIR = Path.home() / ".claude"
KEY_FILE = CLAUDE_DIR / ".profile_key"
PROFILES_ENC = CLAUDE_DIR / "profiles.enc"
META_FILE = CLAUDE_DIR / "profiles_meta.json"
SETTINGS_FILE = CLAUDE_DIR / "settings.json"
SETTINGS_BAK = CLAUDE_DIR / "settings.json.bak"

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


# --- 工具函数 ---

def load_key():
    """加载 Fernet 密钥。"""
    if not KEY_FILE.exists():
        print("错误: 未初始化。请先运行: python ccprofile.py init")
        sys.exit(1)
    return KEY_FILE.read_bytes().strip()


def save_key(key):
    """保存密钥并设置隐藏属性（Windows）。"""
    CLAUDE_DIR.mkdir(parents=True, exist_ok=True)
    KEY_FILE.write_bytes(key)
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.kernel32.SetFileAttributesW(str(KEY_FILE), 0x2)
    try:
        os.chmod(str(KEY_FILE), 0o600)
    except OSError:
        pass


def encrypt_data(data, key):
    """将字典加密为字节。"""
    return Fernet(key).encrypt(json.dumps(data).encode())


def decrypt_data(raw, key):
    """将加密字节解密为字典。"""
    return json.loads(Fernet(key).decrypt(raw).decode())


def load_profiles():
    """加载并解密所有配置。"""
    key = load_key()
    if not PROFILES_ENC.exists():
        return {}
    return decrypt_data(PROFILES_ENC.read_bytes(), key)


def save_profiles(profiles):
    """加密并保存所有配置。"""
    key = load_key()
    CLAUDE_DIR.mkdir(parents=True, exist_ok=True)
    PROFILES_ENC.write_bytes(encrypt_data(profiles, key))


def load_meta():
    """加载元数据。"""
    if not META_FILE.exists():
        return {}
    return json.loads(META_FILE.read_text("utf-8"))


def save_meta(meta):
    """保存元数据。"""
    CLAUDE_DIR.mkdir(parents=True, exist_ok=True)
    META_FILE.write_text(json.dumps(meta, indent=2, ensure_ascii=False), "utf-8")


def mask_token(token):
    """脱敏显示 token，保留前8后4字符。"""
    if not token or len(token) < 12:
        return "***"
    return token[:8] + "..." + token[-4:]


def mask_bark_key(key):
    """脱敏显示 Bark key，保留前4后4字符。"""
    if not key or len(key) < 8:
        return "***"
    return key[:4] + "..." + key[-4:]


def generate_hooks(hooks_config):
    """从简化配置生成完整的 Claude Code hooks 结构。"""
    bark_key = hooks_config["bark_key"]
    host = hooks_config["host_label"]
    sound = hooks_config.get("sound", "")

    result = {}
    for event, tpl in HOOK_EVENTS.items():
        payload = {
            "title": tpl["title"].format(host=host),
            "body": tpl["body"].format(host=host),
            "group": "ClaudeCode",
            "icon": "https://claude.ai/apple-touch-icon.png",
        }
        if event == "PermissionRequest" and sound:
            payload["sound"] = sound

        cmd = (
            f"curl -s -X POST "
            f"-H \"Content-Type: application/json\" "
            f"-d {shlex.quote(json.dumps(payload))} "
            f"https://api.day.app/{bark_key}/"
        )
        result[event] = [{"matcher": "", "hooks": [{"type": "command", "command": cmd}]}]

    return result


def backup_settings():
    """备份 settings.json。"""
    if SETTINGS_FILE.exists():
        shutil.copy2(str(SETTINGS_FILE), str(SETTINGS_BAK))


def read_settings():
    """读取 settings.json。"""
    if not SETTINGS_FILE.exists():
        return {}
    return json.loads(SETTINGS_FILE.read_text("utf-8"))


def write_settings(data):
    """写入 settings.json。"""
    CLAUDE_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", "utf-8")


# --- 交互式输入 ---

def prompt_profile_fields(defaults=None):
    """交互式输入配置字段。返回配置字典。"""
    defaults = defaults or {}
    env_defaults = defaults.get("env", {})
    result = {"env": {}}

    for key, label, required, default in FIELDS:
        if key in ("model", "effortLevel"):
            current = defaults.get(key)
        else:
            current = env_defaults.get(key)
        display = current or default
        hint = f" [{display}]" if display else ""
        value = input(f"  {label}{hint}: ").strip()
        if not value:
            value = display
        if required and not value:
            print(f"错误: {label} 为必填项。")
            sys.exit(1)
        if value is not None:
            if key in ("model", "effortLevel"):
                result[key] = value
            else:
                result["env"][key] = value

    print("  禁用选项 (y/n，留空使用当前值):")
    for flag, desc in DISABLE_FLAGS:
        cur = env_defaults.get(flag)
        if cur is not None:
            d = "y" if str(cur) == "1" else "n"
        else:
            d = "y"
        value = input(f"    {desc} [{d}]: ").strip().lower()
        if not value:
            value = d
        if value == "y":
            result["env"][flag] = "1"

    print("  启用选项 (y/n，留空使用当前值):")
    for flag, desc in ENABLE_FLAGS:
        cur = env_defaults.get(flag)
        if cur is not None:
            d = "y" if str(cur) == "1" else "n"
        else:
            d = "n"
        value = input(f"    {desc} [{d}]: ").strip().lower()
        if not value:
            value = d
        if value == "y":
            result["env"][flag] = "1"

    # 推送通知配置
    print("  推送通知配置 (留空跳过):")
    hooks_defaults = defaults.get("hooks", {}) if defaults else {}
    bark_key = input(f"    Bark Key [{hooks_defaults.get('bark_key', '')}]: ").strip()
    if bark_key or hooks_defaults.get("bark_key"):
        if not bark_key:
            bark_key = hooks_defaults["bark_key"]
        host_label_default = hooks_defaults.get("host_label", socket.gethostname())
        sound_default = hooks_defaults.get("sound", "minuet")
        host_label = input(f"    主机名标签 [{host_label_default}]: ").strip() or host_label_default
        sound = input(f"    通知铃声 [{sound_default}]: ").strip() or sound_default
        result["hooks"] = {
            "bark_key": bark_key,
            "host_label": host_label,
            "sound": sound,
        }

    return result


# --- 命令实现 ---

def cmd_init(_args):
    """初始化：生成加密密钥。"""
    if KEY_FILE.exists():
        ans = input("密钥文件已存在。重新生成将导致现有配置不可读！继续？[y/N] ").strip().lower()
        if ans != "y":
            print("已取消。")
            return

    key = Fernet.generate_key()
    save_key(key)
    save_profiles({})
    save_meta({"active": None})
    print(f"初始化完成。密钥已生成: {KEY_FILE}")


def cmd_add(args):
    """添加配置。"""
    profiles = load_profiles()
    name = args.name

    if name in profiles:
        print(f"错误: 配置 '{name}' 已存在。请使用 edit 命令修改。")
        sys.exit(1)

    if args.token or args.url or args.model:
        # 非交互模式
        if not args.token or not args.url or not args.model:
            print("错误: 非交互模式需要 -t, -u, -m 参数。")
            sys.exit(1)
        profile = {"env": {}}
        profile["env"]["ANTHROPIC_AUTH_TOKEN"] = args.token
        profile["env"]["ANTHROPIC_BASE_URL"] = args.url
        profile["model"] = args.model
        profile["effortLevel"] = args.effort or "high"
        if args.anthropic_model:
            profile["env"]["ANTHROPIC_MODEL"] = args.anthropic_model
        if args.haiku_model:
            profile["env"]["ANTHROPIC_DEFAULT_HAIKU_MODEL"] = args.haiku_model
        if args.sonnet_model:
            profile["env"]["ANTHROPIC_DEFAULT_SONNET_MODEL"] = args.sonnet_model
        if args.opus_model:
            profile["env"]["ANTHROPIC_DEFAULT_OPUS_MODEL"] = args.opus_model
        if args.disable_all:
            for flag, _ in DISABLE_FLAGS:
                profile["env"][flag] = "1"
        if args.enable_teams:
            profile["env"]["CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"] = "1"
        # Hooks 配置
        if args.hooks_json:
            try:
                profile["hooks"] = json.loads(args.hooks_json)
            except json.JSONDecodeError as e:
                print(f"错误: --hooks-json 不是有效的 JSON: {e}")
                sys.exit(1)
        elif args.bark_key:
            profile["hooks"] = {
                "bark_key": args.bark_key,
                "host_label": args.host_label or socket.gethostname(),
                "sound": args.notify_sound or "minuet",
            }
    else:
        # 交互模式
        print(f"添加配置 '{name}'。按回车使用默认值。")
        profile = prompt_profile_fields()

    profiles[name] = profile
    save_profiles(profiles)
    print(f"配置 '{name}' 已添加。")


def cmd_switch(args):
    """切换到指定配置。"""
    profiles = load_profiles()
    name = args.name

    if name not in profiles:
        print(f"错误: 配置 '{name}' 不存在。")
        sys.exit(1)

    profile = profiles[name]

    # 备份当前 settings.json
    backup_settings()

    # 读取并合并
    settings = read_settings()
    if "env" not in settings:
        settings["env"] = {}
    for key, value in profile.get("env", {}).items():
        settings["env"][key] = value
    if "model" in profile:
        settings["model"] = profile["model"]
    if "effortLevel" in profile:
        settings["effortLevel"] = profile["effortLevel"]

    # Hooks 处理：有则写入，无则保留现有
    hooks_cfg = profile.get("hooks")
    if hooks_cfg:
        if "bark_key" in hooks_cfg:
            settings["hooks"] = generate_hooks(hooks_cfg)
        else:
            # 自定义 hooks JSON（--hooks-json 传入的完整结构）
            settings["hooks"] = hooks_cfg

    write_settings(settings)

    meta = load_meta()
    meta["active"] = name
    save_meta(meta)

    print(f"已切换到配置 '{name}'。")


def cmd_list(_args):
    """列出所有配置。"""
    profiles = load_profiles()
    meta = load_meta()
    active = meta.get("active")

    if not profiles:
        print("暂无配置。")
        return

    print(f"{'':2} {'名称':<20} {'URL':<40} {'模型':<10} {'努力':<8} {'通知':<4}")
    print("-" * 86)
    for name, prof in profiles.items():
        mark = "*" if name == active else " "
        url = prof.get("env", {}).get("ANTHROPIC_BASE_URL", "N/A")
        model = prof.get("model", "N/A")
        effort = prof.get("effortLevel", "high")
        notify = "\U0001f514" if "hooks" in prof else ""
        print(f"{mark:2} {name:<20} {url:<40} {model:<10} {effort:<8} {notify}")


def cmd_show(args):
    """显示配置详情。"""
    profiles = load_profiles()
    name = args.name

    if name not in profiles:
        print(f"错误: 配置 '{name}' 不存在。")
        sys.exit(1)

    prof = profiles[name]
    env = prof.get("env", {})

    print(f"配置: {name}")
    print(f"  模型:          {prof.get('model', 'N/A')}")
    print(f"  努力等级:      {prof.get('effortLevel', 'high')}")
    print(f"  API 密钥:      {mask_token(env.get('ANTHROPIC_AUTH_TOKEN'))}")
    print(f"  API 地址:      {env.get('ANTHROPIC_BASE_URL', 'N/A')}")
    print(f"  默认模型:      {env.get('ANTHROPIC_MODEL', 'N/A')}")
    print(f"  Haiku 模型:    {env.get('ANTHROPIC_DEFAULT_HAIKU_MODEL', 'N/A')}")
    print(f"  Sonnet 模型:   {env.get('ANTHROPIC_DEFAULT_SONNET_MODEL', 'N/A')}")
    print(f"  Opus 模型:     {env.get('ANTHROPIC_DEFAULT_OPUS_MODEL', 'N/A')}")
    print("  禁用标志:")
    for flag, desc in DISABLE_FLAGS:
        status = "ON" if env.get(flag) == "1" else "OFF"
        print(f"    {desc}: {status}")
    print("  启用标志:")
    for flag, desc in ENABLE_FLAGS:
        status = "ON" if env.get(flag) == "1" else "OFF"
        print(f"    {desc}: {status}")
    # 推送通知信息
    hooks = prof.get("hooks")
    if hooks:
        if "bark_key" in hooks:
            print("  推送通知:")
            print(f"    Bark Key:      {mask_bark_key(hooks.get('bark_key', ''))}")
            print(f"    主机名标签:    {hooks.get('host_label', 'N/A')}")
            print(f"    通知铃声:      {hooks.get('sound', 'N/A')}")
        else:
            print("  推送通知:       自定义 hooks 配置")
    else:
        print("  推送通知:       未配置")


def cmd_edit(args):
    """编辑配置。"""
    profiles = load_profiles()
    name = args.name

    if name not in profiles:
        print(f"错误: 配置 '{name}' 不存在。")
        sys.exit(1)

    print(f"编辑配置 '{name}'。按回车保留当前值。")
    profile = prompt_profile_fields(profiles[name])
    profiles[name] = profile
    save_profiles(profiles)
    print(f"配置 '{name}' 已更新。")


def cmd_delete(args):
    """删除配置。"""
    profiles = load_profiles()
    name = args.name

    if name not in profiles:
        print(f"错误: 配置 '{name}' 不存在。")
        sys.exit(1)

    meta = load_meta()
    if meta.get("active") == name:
        print(f"警告: '{name}' 是当前活动配置。")

    ans = input(f"确认删除配置 '{name}'？[y/N] ").strip().lower()
    if ans != "y":
        print("已取消。")
        return

    del profiles[name]
    save_profiles(profiles)
    if meta.get("active") == name:
        meta["active"] = None
        save_meta(meta)
    print(f"配置 '{name}' 已删除。")


def cmd_current(_args):
    """显示当前活动配置。"""
    meta = load_meta()
    active = meta.get("active")

    if not active:
        print("当前无活动配置。")
        return

    profiles = load_profiles()
    if active not in profiles:
        print(f"活动配置 '{active}' 不存在（可能已被删除）。")
        return

    prof = profiles[active]
    url = prof.get("env", {}).get("ANTHROPIC_BASE_URL", "N/A")
    model = prof.get("model", "N/A")
    print(f"当前活动配置: {active}")
    print(f"  URL: {url}")
    print(f"  模型: {model}")


# --- 入口 ---

def main():
    parser = argparse.ArgumentParser(
        prog="ccprofile",
        description="Claude Code API 配置管理工具"
    )
    sub = parser.add_subparsers(dest="command")

    # init
    sub.add_parser("init", help="初始化：生成加密密钥")

    # add
    p_add = sub.add_parser("add", help="添加配置")
    p_add.add_argument("name", help="配置名称")
    p_add.add_argument("-t", "--token", help="API 密钥")
    p_add.add_argument("-u", "--url", help="API 基础地址")
    p_add.add_argument("-m", "--model", help="模型 (opus/sonnet/haiku)")
    p_add.add_argument("-e", "--effort", help="努力等级")
    p_add.add_argument("--anthropic-model", help="默认模型")
    p_add.add_argument("--haiku-model", help="Haiku 模型覆盖")
    p_add.add_argument("--sonnet-model", help="Sonnet 模型覆盖")
    p_add.add_argument("--opus-model", help="Opus 模型覆盖")
    p_add.add_argument("--disable-all", action="store_true", help="启用所有禁用标志")
    p_add.add_argument("--enable-teams", action="store_true", help="启用 Agent Teams 模式")
    p_add.add_argument("--bark-key", help="Bark 推送 Key")
    p_add.add_argument("--host-label", help="主机名标签")
    p_add.add_argument("--notify-sound", help="通知铃声")
    p_add.add_argument("--hooks-json", help="自定义 hooks JSON 配置")

    # switch
    p_sw = sub.add_parser("switch", help="切换配置")
    p_sw.add_argument("name", help="配置名称")

    # list
    sub.add_parser("list", help="列出所有配置")

    # show
    p_show = sub.add_parser("show", help="显示配置详情")
    p_show.add_argument("name", help="配置名称")

    # edit
    p_edit = sub.add_parser("edit", help="编辑配置")
    p_edit.add_argument("name", help="配置名称")

    # delete
    p_del = sub.add_parser("delete", help="删除配置")
    p_del.add_argument("name", help="配置名称")

    # current
    sub.add_parser("current", help="显示当前活动配置")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    commands = {
        "init": cmd_init,
        "add": cmd_add,
        "switch": cmd_switch,
        "list": cmd_list,
        "show": cmd_show,
        "edit": cmd_edit,
        "delete": cmd_delete,
        "current": cmd_current,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
