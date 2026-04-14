"""命令处理：init / add / switch / list / show / edit / delete / current。"""

import json
import socket
import sys

from cryptography.fernet import Fernet

from .constants import DISABLE_FLAGS, ENABLE_FLAGS
from .crypto import save_key
from .formatting import mask_token
from .hooks import mask_bark_key, generate_hooks
from .prompts import prompt_profile_fields
from .storage import (
    backup_settings,
    load_meta,
    load_profiles,
    read_settings,
    save_meta,
    save_profiles,
    write_settings,
)


def cmd_init(_args):
    """初始化：生成加密密钥。"""
    from .constants import KEY_FILE

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
