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
    LEGACY_MODEL_SLOT_PREFIXES,
    VIRTUAL_MODEL_NAMES,
    VIRTUAL_MODEL_PREFIX,
)
from .crypto import save_key
from .display import panel, kv, status_dot, active_marker, CYAN, GREEN, RED, BOLD, DIM, RESET
from .formatting import mask_token
from .hooks import generate_hooks
from .picker import pick_profile, pick_provider
from .terminal import confirm_action
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


def _normalize_teams_flag(profile):
    """统一处理 enableTeams 字段，兼容旧格式。"""
    if "enableTeams" in profile:
        return
    env = profile.get("env", {})
    profile["enableTeams"] = env.pop("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS", None) == "1"


def cmd_init(_args):
    """初始化：生成加密密钥。"""
    from .constants import KEY_FILE, PROVIDERS_ENC

    if KEY_FILE.exists():
        if not confirm_action("密钥文件已存在。重新生成将导致现有配置不可读！继续？", default_yes=False):
            print("已取消。")
            return

    if PROVIDERS_ENC.exists():
        if not confirm_action("重新初始化将删除现有提供商配置 providers.enc。确认？", default_yes=False):
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

    # --enable-teams 在所有模式下都生效
    if args.enable_teams:
        profile["enableTeams"] = True

    profiles[name] = profile
    save_profiles(profiles)
    print(f"配置 '{name}' 已添加。")


def cmd_switch(args):
    """切换到指定配置。"""
    profiles = load_profiles()
    name = args.name
    if name is None:
        name = pick_profile("选择要切换的配置")
        if name is None:
            return

    if name not in profiles:
        print(f"错误: 配置 '{name}' 不存在。")
        sys.exit(1)

    profile = profiles[name]
    mode = profile.get("mode", "single")
    _normalize_teams_flag(profile)

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
            "virtual_model_prefix": VIRTUAL_MODEL_PREFIX,
            "model_mapping": {},
            "legacy_model_slot_prefixes": LEGACY_MODEL_SLOT_PREFIXES,
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
        # 写入虚拟模型名，让 Claude Code 使用 ccprofile-opus/sonnet/haiku
        settings["env"]["ANTHROPIC_DEFAULT_OPUS_MODEL"] = VIRTUAL_MODEL_NAMES["opus"]
        settings["env"]["ANTHROPIC_DEFAULT_SONNET_MODEL"] = VIRTUAL_MODEL_NAMES["sonnet"]
        settings["env"]["ANTHROPIC_DEFAULT_HAIKU_MODEL"] = VIRTUAL_MODEL_NAMES["haiku"]

    else:
        # 单一模式：停止代理，直接设置
        if not stop_proxy(quiet=True):
            print("警告: 停止代理失败，但将继续切换配置。")

        for key, value in profile.get("env", {}).items():
            settings["env"][key] = value

    # 写入 Teams 模式环境变量
    if profile.get("enableTeams"):
        settings["env"]["CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"] = "1"

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

    # 保存迁移后的 profile（如果格式有变化）
    profiles[name] = profile
    save_profiles(profiles)

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

    body = []
    profile_items = list(profiles.items())
    for idx, (name, prof) in enumerate(profile_items):
        _normalize_teams_flag(prof)
        is_active = (name == active)
        prefix = active_marker() if is_active else "  "
        mode = prof.get("mode", "single")

        if mode == "mixed":
            mode_tag = "混合"
        else:
            mode_tag = f"单一 · {prof.get('model', '?')}"

        line1 = f"{prefix}{name}{' *' if is_active else ''}    {mode_tag}"
        if prof.get("enableTeams"):
            line1 += "    👥 Teams"
        if "hooks" in prof:
            line1 += "    \U0001f514"
        body.append(line1)

        if mode == "mixed":
            for slot, target in prof.get("model_mapping", {}).items():
                body.append(f"    {DIM}{slot}→{target['provider']}/{target['model']}{RESET}")
        else:
            url = prof.get("env", {}).get("ANTHROPIC_BASE_URL", "N/A")
            body.append(f"    {DIM}{url}{RESET}")
        if idx < len(profile_items) - 1:
            body.append("")

    print(panel("配置列表", f"共 {len(profiles)} 个", body))


def cmd_show(args):
    """显示配置详情。"""
    profiles = load_profiles()
    name = args.name
    if name is None:
        name = pick_profile("选择要查看的配置")
        if name is None:
            return

    if name not in profiles:
        print(f"错误: 配置 '{name}' 不存在。")
        sys.exit(1)

    prof = profiles[name]
    _normalize_teams_flag(prof)
    mode = prof.get("mode", "single")
    mode_label = "混合模式" if mode == "mixed" else "单一模式"

    body = []
    body.append("")
    body.append(kv("模型", prof.get("model", "N/A")))
    body.append(kv("努力等级", prof.get("effortLevel", "high")))
    teams_status = f"{GREEN}✓ 已启用{RESET}" if prof.get("enableTeams") else f"{DIM}未启用{RESET}"
    body.append(kv("Teams 模式", teams_status))
    body.append("")

    if mode == "mixed":
        # 模型映射子面板
        mapping_lines = []
        for slot, target in prof.get("model_mapping", {}).items():
            mapping_lines.append(f"{slot}    →  {target.get('provider', '?')} / {target.get('model', '?')}")
        body.append(("sub", "模型映射", mapping_lines))
        body.append("")
        body.append(kv("代理端口", str(prof.get("proxy_port", 18888))))
    else:
        # 连接子面板
        env = prof.get("env", {})
        conn_lines = [
            kv("API 密钥", mask_token(env.get("ANTHROPIC_AUTH_TOKEN", ""))),
            kv("API 地址", env.get("ANTHROPIC_BASE_URL", "N/A")),
        ]
        body.append(("sub", "连接", conn_lines))
        body.append("")

        # 模型覆盖子面板
        override_lines = []
        for label, key in [
            ("默认模型", "ANTHROPIC_MODEL"),
            ("Haiku", "ANTHROPIC_DEFAULT_HAIKU_MODEL"),
            ("Sonnet", "ANTHROPIC_DEFAULT_SONNET_MODEL"),
            ("Opus", "ANTHROPIC_DEFAULT_OPUS_MODEL"),
        ]:
            val = env.get(key)
            override_lines.append(kv(label, val if val else f"{DIM}N/A{RESET}"))
        body.append(("sub", "模型覆盖", override_lines))
        body.append("")

        # 标志子面板
        flag_lines = []
        flag_lines.append("禁用")
        for flag, desc in DISABLE_FLAGS:
            mark = f"{GREEN}✓{RESET}" if env.get(flag) == "1" else f"{RED}×{RESET}"
            flag_lines.append(f"  {mark} {desc}")
        flag_lines.append("启用")
        for flag, desc in ENABLE_FLAGS:
            mark = f"{GREEN}✓{RESET}" if env.get(flag) == "1" else f"{RED}×{RESET}"
            flag_lines.append(f"  {mark} {desc}")
        body.append(("sub", "标志", flag_lines))
        body.append("")

    # 推送通知
    hooks = prof.get("hooks")
    if hooks and "bark_key" in hooks:
        body.append(kv("推送通知", f"\U0001f514 Bark ({hooks.get('host_label', 'N/A')})"))
    elif hooks:
        body.append(kv("推送通知", "自定义 hooks 配置"))
    else:
        body.append(kv("推送通知", f"{DIM}未配置{RESET}"))
    body.append("")

    print(panel(name, mode_label, body))


def cmd_edit(args):
    """编辑配置。"""
    profiles = load_profiles()
    name = args.name
    if name is None:
        name = pick_profile("选择要编辑的配置")
        if name is None:
            return

    if name not in profiles:
        print(f"错误: 配置 '{name}' 不存在。")
        sys.exit(1)

    old = profiles[name]
    _normalize_teams_flag(old)
    mode = old.get("mode", "single")
    old_teams = old.get("enableTeams")

    # 仅切换 Teams flag 时跳过交互流程
    teams_only = (getattr(args, "enable_teams", False) or getattr(args, "disable_teams", False))
    if teams_only:
        profile = dict(old)
    else:
        print(f"编辑配置 '{name}'。按回车保留当前值。")
        if mode == "mixed":
            profile = prompt_mixed_profile_fields(old)
            profile["mode"] = "mixed"
        else:
            profile = prompt_profile_fields(old)
            profile["mode"] = "single"
        profile["enableTeams"] = old_teams
    # CLI flags override
    if getattr(args, "enable_teams", False):
        profile["enableTeams"] = True
    if getattr(args, "disable_teams", False):
        profile["enableTeams"] = False

    profiles[name] = profile
    save_profiles(profiles)
    print(f"配置 '{name}' 已更新。")


def cmd_delete(args):
    """删除配置。"""
    profiles = load_profiles()
    name = args.name
    if name is None:
        name = pick_profile("选择要删除的配置")
        if name is None:
            return

    if name not in profiles:
        print(f"错误: 配置 '{name}' 不存在。")
        sys.exit(1)

    meta = load_meta()
    if meta.get("active") == name:
        print(f"警告: '{name}' 是当前活动配置。")

    if not confirm_action(f"确认删除配置 '{name}'？", default_yes=False):
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
    _normalize_teams_flag(prof)
    mode = prof.get("mode", "single")
    mode_label = "混合模式" if mode == "mixed" else "单一模式"
    title = f"{active_marker()}{active}"

    body = []
    body.append("")

    teams_status = f"{GREEN}✓ 已启用{RESET}" if prof.get("enableTeams") else f"{DIM}未启用{RESET}"

    if mode == "mixed":
        proxy_info = get_proxy_info()
        body.append(status_dot(proxy_info["running"]))
        if proxy_info["running"]:
            body.append(f"PID: {proxy_info['pid']}  端口: {proxy_info.get('port', 'N/A')}")
        body.append("")
        body.append(kv("Teams 模式", teams_status))
        body.append("")
        # 模型映射子面板
        mapping_lines = []
        for slot, target in prof.get("model_mapping", {}).items():
            mapping_lines.append(f"{slot}    →  {target.get('provider', '?')} / {target.get('model', '?')}")
        body.append(("sub", "模型映射", mapping_lines))
    else:
        body.append(kv("模型", prof.get("model", "N/A")))
        body.append(kv("努力等级", prof.get("effortLevel", "high")))
        body.append(kv("Teams 模式", teams_status))
        url = prof.get("env", {}).get("ANTHROPIC_BASE_URL", "N/A")
        body.append(kv("API 地址", url))

    body.append("")
    print(panel(title, mode_label, body))


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


def cmd_teams(args):
    """切换当前配置的 Agent Teams 模式。"""
    meta = load_meta()
    active = meta.get("active")
    if not active:
        print("错误: 当前无活动配置。请先使用 'switch' 切换到某个配置。")
        sys.exit(1)

    profiles = load_profiles()
    if active not in profiles:
        print(f"错误: 活动配置 '{active}' 不存在。")
        sys.exit(1)

    profile = profiles[active]
    _normalize_teams_flag(profile)

    action = getattr(args, "action", "toggle") or "toggle"
    if action == "on":
        profile["enableTeams"] = True
    elif action == "off":
        profile["enableTeams"] = False
    else:  # toggle
        profile["enableTeams"] = not profile.get("enableTeams", False)

    profiles[active] = profile
    save_profiles(profiles)

    status = "已启用" if profile["enableTeams"] else "已禁用"
    print(f"配置 '{active}' 的 Agent Teams 模式{status}。")

    if args.apply:
        _apply_teams_to_settings(profile, active)


def _apply_teams_to_settings(profile, name):
    """将 Teams 状态应用到 settings.json，无需完整 switch。"""
    settings = read_settings()
    if "env" not in settings:
        settings["env"] = {}
    if profile.get("enableTeams"):
        settings["env"]["CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"] = "1"
    else:
        settings["env"].pop("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS", None)
    write_settings(settings)
