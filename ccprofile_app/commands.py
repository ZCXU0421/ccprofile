"""命令处理：init / add / switch / list / show / edit / delete / current。"""

import json
import socket
import sys

from cryptography.fernet import Fernet

from .constants import (
    CCPROFILE_MANAGED_ENV_KEYS,
    DEFAULT_PROXY_PORT,
    DISABLE_FLAGS,
    ENABLE_FLAGS,
    MODEL_SLOT_PREFIXES,
)
from .crypto import save_key
from .formatting import mask_token
from .hooks import mask_bark_key, generate_hooks
from .prompts import prompt_mixed_profile_fields, prompt_profile_fields
from .proxy_process import get_proxy_info, start_proxy, stop_proxy
from .storage import (
    backup_settings,
    load_meta,
    load_profiles,
    load_providers,
    read_settings,
    save_meta,
    save_profiles,
    write_settings,
)


def cmd_init(_args):
    """初始化：生成加密密钥。"""
    from .constants import KEY_FILE, PROVIDERS_ENC

    if KEY_FILE.exists():
        ans = input("密钥文件已存在。重新生成将导致现有配置不可读！继续？[y/N] ").strip().lower()
        if ans != "y":
            print("已取消。")
            return

    if PROVIDERS_ENC.exists():
        ans = input(
            "重新初始化将删除现有提供商配置 providers.enc。确认删除？[y/N] "
        ).strip().lower()
        if ans != "y":
            print("已取消。")
            return

    key = Fernet.generate_key()
    save_key(key)
    save_profiles({})
    save_meta({"active": None})

    # 删除旧的提供商加密文件（使用新密钥后无法解密）
    if PROVIDERS_ENC.exists():
        PROVIDERS_ENC.unlink()

    print(f"初始化完成。密钥已生成: {KEY_FILE}")


def cmd_add(args):
    """添加配置。"""
    profiles = load_profiles()
    name = args.name

    if name in profiles:
        print(f"错误: 配置 '{name}' 已存在。请使用 edit 命令修改。")
        sys.exit(1)

    # 检查模式
    mode = getattr(args, "mode", "single")

    if mode == "mixed":
        # 混合模式 - 仅支持交互模式
        print(f"添加混合配置 '{name}'。按回车使用默认值。")
        profile = prompt_mixed_profile_fields()
        profile["mode"] = "mixed"
    else:
        # 单一模式
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
        profile["mode"] = "single"

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
    mode = profile.get("mode", "single")

    # 备份当前 settings.json
    backup_settings()

    # 读取并合并
    settings = read_settings()
    if "env" not in settings:
        settings["env"] = {}

    # 清除上一个 profile 写入的所有 ccprofile 管理的 env 变量，
    # 避免旧配置的标志/模型覆盖泄漏到新配置
    for key in CCPROFILE_MANAGED_ENV_KEYS:
        settings["env"].pop(key, None)

    if mode == "mixed":
        # 混合模式：启动代理
        providers = load_providers()
        if not providers:
            print("错误: 暂无可用提供商。请先使用 'ccprofile provider add' 添加提供商。")
            sys.exit(1)

        # 构建 model_mapping，合并 provider 信息
        model_mapping = profile.get("model_mapping", {})
        proxy_config = {
            "port": profile.get("proxy_port", DEFAULT_PROXY_PORT),
            "model_mapping": {},
            "model_slot_prefixes": dict(MODEL_SLOT_PREFIXES),
        }

        for slot, target in model_mapping.items():
            provider_name = target.get("provider")
            if provider_name not in providers:
                print(f"错误: 提供商 '{provider_name}' 不存在。")
                sys.exit(1)

            provider = providers[provider_name]
            proxy_config["model_mapping"][slot] = {
                "provider": provider_name,
                "model": target.get("model"),
                "base_url": provider.get("base_url"),
                "api_key": provider.get("api_key"),
            }

        # 停止旧代理（如果运行中），失败时仅警告
        if not stop_proxy(quiet=True):
            print("警告: 停止旧代理失败，将继续尝试启动新代理。")

        # 启动新代理
        if not start_proxy(proxy_config):
            print("错误: 启动代理失败。")
            sys.exit(1)

        # 设置 settings.json
        port = proxy_config["port"]
        settings["env"]["ANTHROPIC_BASE_URL"] = f"http://localhost:{port}"
        # 设置占位符 ANTHROPIC_AUTH_TOKEN（代理会忽略此值）
        settings["env"]["ANTHROPIC_AUTH_TOKEN"] = "ccprofile-proxy"

    else:
        # 单一模式：停止代理，直接设置
        if not stop_proxy(quiet=True):
            print("警告: 停止代理失败，但将继续切换配置。")

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

    mode_text = "混合模式" if mode == "mixed" else "单一模式"
    print(f"已切换到配置 '{name}' ({mode_text})。")


def cmd_list(_args):
    """列出所有配置。"""
    profiles = load_profiles()
    meta = load_meta()
    active = meta.get("active")

    if not profiles:
        print("暂无配置。")
        return

    print(f"{'':2} {'名称':<18} {'模式':<8} {'URL/映射':<38} {'模型':<8} {'通知':<4}")
    print("-" * 82)
    for name, prof in profiles.items():
        mark = "*" if name == active else " "
        mode = prof.get("mode", "single")
        mode_text = "混合" if mode == "mixed" else "单一"
        model = prof.get("model", "N/A")
        notify = "\U0001f514" if "hooks" in prof else ""

        if mode == "mixed":
            # 显示模型映射
            mapping = prof.get("model_mapping", {})
            mapping_parts = []
            for slot, target in mapping.items():
                provider = target.get("provider", "?")
                model_name = target.get("model", "?")
                mapping_parts.append(f"{slot}→{provider}/{model_name[:10]}")
            url_mapping = ", ".join(mapping_parts)
            if len(url_mapping) > 36:
                url_mapping = url_mapping[:33] + "..."
        else:
            url_mapping = prof.get("env", {}).get("ANTHROPIC_BASE_URL", "N/A")
            if len(url_mapping) > 36:
                url_mapping = url_mapping[:33] + "..."

        print(f"{mark:2} {name:<18} {mode_text:<8} {url_mapping:<38} {model:<8} {notify}")


def cmd_show(args):
    """显示配置详情。"""
    profiles = load_profiles()
    name = args.name

    if name not in profiles:
        print(f"错误: 配置 '{name}' 不存在。")
        sys.exit(1)

    prof = profiles[name]
    mode = prof.get("mode", "single")

    print(f"配置: {name}")
    print(f"  模式:          {'混合模式' if mode == 'mixed' else '单一模式'}")
    print(f"  模型:          {prof.get('model', 'N/A')}")
    print(f"  努力等级:      {prof.get('effortLevel', 'high')}")

    if mode == "mixed":
        # 显示模型映射
        print("  模型映射:")
        model_mapping = prof.get("model_mapping", {})
        for slot, target in model_mapping.items():
            provider = target.get("provider", "?")
            model = target.get("model", "?")
            print(f"    {slot}:  {provider} → {model}")
        port = prof.get("proxy_port", "18888")
        print(f"  代理端口:      {port}")
    else:
        # 单一模式显示
        env = prof.get("env", {})
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

    old = profiles[name]
    mode = old.get("mode", "single")

    print(f"编辑配置 '{name}'。按回车保留当前值。")
    if mode == "mixed":
        profile = prompt_mixed_profile_fields(old)
        profile["mode"] = "mixed"
    else:
        profile = prompt_profile_fields(old)
        profile["mode"] = "single"

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
    mode = prof.get("mode", "single")
    model = prof.get("model", "N/A")

    print(f"当前活动配置: {active} ({'混合模式' if mode == 'mixed' else '单一模式'})")

    if mode == "mixed":
        # 显示代理状态
        proxy_info = get_proxy_info()
        if proxy_info["running"]:
            print(f"  代理状态:      运行中 (PID: {proxy_info['pid']}, 端口: {proxy_info.get('port', 'N/A')})")
            if "mapping" in proxy_info:
                print("  模型映射:")
                for m in proxy_info["mapping"]:
                    print(f"    {m}")
        else:
            print("  代理状态:      未运行")
    else:
        url = prof.get("env", {}).get("ANTHROPIC_BASE_URL", "N/A")
        print(f"  URL: {url}")
    print(f"  模型: {model}")


def cmd_proxy_status(_args):
    """显示代理进程状态。"""
    proxy_info = get_proxy_info()

    if proxy_info["running"]:
        print(f"代理状态: 运行中")
        print(f"  PID:   {proxy_info['pid']}")
        print(f"  端口:  {proxy_info.get('port', 'N/A')}")
        if "mapping" in proxy_info:
            print("  模型映射:")
            for m in proxy_info["mapping"]:
                print(f"    {m}")
    else:
        print("代理状态: 未运行")
        if proxy_info["config"]:
            print(f"  配置端口: {proxy_info.get('port', 'N/A')}")


def cmd_proxy_stop(_args):
    """停止代理进程。"""
    stop_proxy()


def cmd_proxy_logs(args):
    """显示代理日志。"""
    from .proxy_process import show_proxy_logs

    lines = getattr(args, "lines", 50)
    show_proxy_logs(lines)
