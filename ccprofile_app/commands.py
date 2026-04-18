"""命令处理：init / add / switch / list / show / edit / delete / current。"""

import json
import socket
import sys

from cryptography.fernet import Fernet

from .i18n import t, FIELD_I18N_KEYS, DISABLE_FLAG_I18N_KEYS
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
    load_proxy_config,
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
        if not confirm_action(t("cmd.init_exists_warn"), default_yes=False):
            print(t("cmd.canceled"))
            return

    if PROVIDERS_ENC.exists():
        if not confirm_action(t("cmd.init_provider_warn"), default_yes=False):
            print(t("cmd.canceled"))
            return

    key = Fernet.generate_key()
    save_key(key)
    save_profiles({})
    save_meta({"active": None})

    # 删除旧的提供商加密文件（使用新密钥后无法解密）
    if PROVIDERS_ENC.exists():
        PROVIDERS_ENC.unlink()

    print(f"{t('cmd.init_done')}: {KEY_FILE}")


def cmd_add(args):
    """添加配置。"""
    profiles = load_profiles()
    name = args.name

    if name in profiles:
        print(t("cmd.add_exists", name=name))
        sys.exit(1)

    # 检查模式
    mode = getattr(args, "mode", "single")

    if mode == "mixed":
        # 混合模式 - 仅支持交互模式
        print(t("cmd.add_mixed_intro", name=name))
        profile = prompt_mixed_profile_fields()
        profile["mode"] = "mixed"
    else:
        # 单一模式
        if args.token or args.url or args.model:
            # 非交互模式
            if not args.token or not args.url or not args.model:
                print(t("cmd.add_noninteractive_error"))
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
                    print(t("cmd.hooks_json_error", error=e))
                    sys.exit(1)
            elif args.bark_key:
                profile["hooks"] = {
                    "bark_key": args.bark_key,
                    "host_label": args.host_label or socket.gethostname(),
                    "sound": args.notify_sound or "minuet",
                }
        else:
            # 交互模式
            print(t("cmd.add_single_intro", name=name))
            profile = prompt_profile_fields()
        profile["mode"] = "single"

    # --enable-teams 在所有模式下都生效
    if args.enable_teams:
        profile["enableTeams"] = True

    profiles[name] = profile
    save_profiles(profiles)
    print(t("cmd.add_done", name=name))


def cmd_switch(args):
    """切换到指定配置。"""
    profiles = load_profiles()
    name = args.name
    if name is None:
        name = pick_profile(t("cmd.switch_pick"))
        if name is None:
            return

    if name not in profiles:
        print(t("cmd.switch_not_found", name=name))
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
            print(t("cmd.switch_no_provider"))
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
                print(t("cmd.switch_provider_not_found", name=provider_name))
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
            print(t("cmd.switch_stop_proxy_warn"))

        # 启动新代理
        if not start_proxy(proxy_config):
            print(t("cmd.switch_start_proxy_error"))
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
            print(t("cmd.switch_stop_proxy_warn2"))

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

    mode_text = t("cmd.mode_mixed") if mode == "mixed" else t("cmd.mode_single")
    print(t("cmd.switch_done", name=name, mode=mode_text))


def cmd_list(_args):
    """列出所有配置。"""
    profiles = load_profiles()
    meta = load_meta()
    active = meta.get("active")

    if not profiles:
        print(t("cmd.list_empty"))
        return

    body = []
    profile_items = list(profiles.items())
    for idx, (name, prof) in enumerate(profile_items):
        prof_copy = dict(prof)
        prof_copy["env"] = dict(prof.get("env", {}))
        _normalize_teams_flag(prof_copy)
        is_active = (name == active)
        prefix = active_marker() if is_active else "  "
        mode = prof_copy.get("mode", "single")

        if mode == "mixed":
            mode_tag = t("cmd.mode_mixed")
        else:
            mode_tag = f"{t('cmd.mode_single')} · {prof_copy.get('model', '?')}"

        line1 = f"{prefix}{name}{' *' if is_active else ''}    {mode_tag}"
        if prof_copy.get("enableTeams"):
            line1 += "    👥 Teams"
        if "hooks" in prof_copy:
            line1 += "    \U0001f514"
        body.append(line1)

        if mode == "mixed":
            for slot, target in prof_copy.get("model_mapping", {}).items():
                body.append(f"    {DIM}{slot}→{target['provider']}/{target['model']}{RESET}")
        else:
            url = prof_copy.get("env", {}).get("ANTHROPIC_BASE_URL", "N/A")
            body.append(f"    {DIM}{url}{RESET}")
        if idx < len(profile_items) - 1:
            body.append("")

    print(panel(t("panel.profile_list"), t("cmd.list_total", n=len(profiles)), body))


def cmd_show(args):
    """显示配置详情。"""
    profiles = load_profiles()
    name = args.name
    if name is None:
        name = pick_profile(t("cmd.show_pick"))
        if name is None:
            return

    if name not in profiles:
        print(t("cmd.show_not_found", name=name))
        sys.exit(1)

    prof = profiles[name]
    prof_copy = dict(prof)
    prof_copy["env"] = dict(prof.get("env", {}))
    _normalize_teams_flag(prof_copy)
    mode = prof_copy.get("mode", "single")
    mode_label = t("cmd.mode_mixed") if mode == "mixed" else t("cmd.mode_single")

    body = []
    body.append("")
    body.append(kv(t("cmd.show.model"), prof_copy.get("model", "N/A")))
    body.append(kv(t("cmd.show.effort"), prof_copy.get("effortLevel", "high")))
    teams_status = f"{GREEN}{t('cmd.show.teams_enabled')}{RESET}" if prof_copy.get("enableTeams") else f"{DIM}{t('cmd.show.teams_disabled')}{RESET}"
    body.append(kv(t("cmd.show.teams_mode"), teams_status))
    body.append("")

    if mode == "mixed":
        # 模型映射子面板
        mapping_lines = []
        for slot, target in prof_copy.get("model_mapping", {}).items():
            mapping_lines.append(f"{slot}    →  {target.get('provider', '?')} / {target.get('model', '?')}")
        body.append(("sub", t("cmd.show.model_mapping"), mapping_lines))
        body.append("")
        body.append(kv(t("cmd.show.proxy_port"), str(prof_copy.get("proxy_port", 18888))))
    else:
        # 连接子面板
        env = prof_copy.get("env", {})
        conn_lines = [
            kv(t("fields.auth_token"), mask_token(env.get("ANTHROPIC_AUTH_TOKEN", ""))),
            kv(t("fields.base_url"), env.get("ANTHROPIC_BASE_URL", "N/A")),
        ]
        body.append(("sub", t("cmd.show.connection"), conn_lines))
        body.append("")

        # 模型覆盖子面板
        override_lines = []
        for label, key in [
            (t("cmd.show.default_model"), "ANTHROPIC_MODEL"),
            (t("fields.haiku_override"), "ANTHROPIC_DEFAULT_HAIKU_MODEL"),
            (t("fields.sonnet_override"), "ANTHROPIC_DEFAULT_SONNET_MODEL"),
            (t("fields.opus_override"), "ANTHROPIC_DEFAULT_OPUS_MODEL"),
        ]:
            val = env.get(key)
            override_lines.append(kv(label, val if val else f"{DIM}N/A{RESET}"))
        body.append(("sub", t("cmd.show.model_override"), override_lines))
        body.append("")

        # 标志子面板
        flag_lines = []
        flag_lines.append(t("cmd.show.flags_disabled"))
        for flag, raw_desc in DISABLE_FLAGS:
            desc = t(DISABLE_FLAG_I18N_KEYS.get(flag, "")) or raw_desc
            mark = f"{GREEN}✓{RESET}" if env.get(flag) == "1" else f"{RED}×{RESET}"
            flag_lines.append(f"  {mark} {desc}")
        flag_lines.append(t("cmd.show.flags_enabled"))
        for flag, desc in ENABLE_FLAGS:
            mark = f"{GREEN}✓{RESET}" if env.get(flag) == "1" else f"{RED}×{RESET}"
            flag_lines.append(f"  {mark} {desc}")
        body.append(("sub", t("cmd.show.flags"), flag_lines))
        body.append("")

    # 推送通知
    hooks = prof_copy.get("hooks")
    if hooks and "bark_key" in hooks:
        body.append(kv(t("cmd.show.push_notification"), f"\U0001f514 {t('cmd.show.bark')} ({hooks.get('host_label', 'N/A')})"))
    elif hooks:
        body.append(kv(t("cmd.show.push_notification"), t("cmd.show.custom_hooks")))
    else:
        body.append(kv(t("cmd.show.push_notification"), f"{DIM}{t('cmd.show.not_configured')}{RESET}"))
    body.append("")

    print(panel(name, mode_label, body))


def cmd_edit(args):
    """编辑配置。"""
    profiles = load_profiles()
    name = args.name
    if name is None:
        name = pick_profile(t("cmd.edit_pick"))
        if name is None:
            return

    if name not in profiles:
        print(t("cmd.edit_not_found", name=name))
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
        print(t("cmd.edit_intro", name=name))
        if mode == "mixed":
            profile = prompt_mixed_profile_fields(old)
            profile["mode"] = "mixed"
        else:
            profile = prompt_profile_fields(old)
            profile["mode"] = "single"
        profile["enableTeams"] = old_teams
    # CLI flags override
    if getattr(args, "enable_teams", False) and getattr(args, "disable_teams", False):
        print(t("cmd.edit_teams_conflict"))
        sys.exit(1)
    if getattr(args, "enable_teams", False):
        profile["enableTeams"] = True
    if getattr(args, "disable_teams", False):
        profile["enableTeams"] = False

    profiles[name] = profile
    save_profiles(profiles)
    print(t("cmd.edit_done", name=name))


def cmd_delete(args):
    """删除配置。"""
    profiles = load_profiles()
    name = args.name
    if name is None:
        name = pick_profile(t("cmd.delete_pick"))
        if name is None:
            return

    if name not in profiles:
        print(t("cmd.delete_not_found", name=name))
        sys.exit(1)

    meta = load_meta()
    is_active = meta.get("active") == name
    if is_active:
        print(t("cmd.delete_active_warn", name=name))

    if not confirm_action(t("cmd.delete_confirm", name=name), default_yes=False):
        print(t("cmd.canceled"))
        return

    # Stop proxy only after confirmation
    if is_active:
        proxy_cfg = load_proxy_config()
        if proxy_cfg:
            stop_proxy()

    del profiles[name]
    save_profiles(profiles)
    if is_active:
        meta["active"] = None
        save_meta(meta)
    print(t("cmd.delete_done", name=name))


def cmd_current(_args):
    """显示当前活动配置。"""
    meta = load_meta()
    active = meta.get("active")

    if not active:
        print(t("cmd.current_none"))
        return

    profiles = load_profiles()
    if active not in profiles:
        print(t("cmd.current_missing", name=active))
        return

    prof = profiles[active]
    prof_copy = dict(prof)
    prof_copy["env"] = dict(prof.get("env", {}))
    _normalize_teams_flag(prof_copy)
    mode = prof_copy.get("mode", "single")
    mode_label = t("cmd.mode_mixed") if mode == "mixed" else t("cmd.mode_single")
    title = f"{active_marker()}{active}"

    body = []
    body.append("")

    teams_status = f"{GREEN}{t('cmd.show.teams_enabled')}{RESET}" if prof_copy.get("enableTeams") else f"{DIM}{t('cmd.show.teams_disabled')}{RESET}"

    if mode == "mixed":
        proxy_info = get_proxy_info()
        body.append(status_dot(proxy_info["running"]))
        if proxy_info["running"]:
            body.append(f"{t('cmd.proxy_pid')}: {proxy_info['pid']}  {t('cmd.proxy_port')}: {proxy_info.get('port', 'N/A')}")
        body.append("")
        body.append(kv(t("cmd.show.teams_mode"), teams_status))
        body.append("")
        # 模型映射子面板
        mapping_lines = []
        for slot, target in prof_copy.get("model_mapping", {}).items():
            mapping_lines.append(f"{slot}    →  {target.get('provider', '?')} / {target.get('model', '?')}")
        body.append(("sub", t("cmd.show.model_mapping"), mapping_lines))
    else:
        body.append(kv(t("cmd.show.model"), prof_copy.get("model", "N/A")))
        body.append(kv(t("cmd.show.effort"), prof_copy.get("effortLevel", "high")))
        body.append(kv(t("cmd.show.teams_mode"), teams_status))
        url = prof_copy.get("env", {}).get("ANTHROPIC_BASE_URL", "N/A")
        body.append(kv(t("fields.base_url"), url))

    body.append("")
    print(panel(title, mode_label, body))


def cmd_proxy_status(_args):
    """显示代理进程状态。"""
    proxy_info = get_proxy_info()

    if proxy_info["running"]:
        print(t("cmd.proxy_running"))
        print(f"  {t('cmd.proxy_pid')}:   {proxy_info['pid']}")
        print(f"  {t('cmd.proxy_port')}:  {proxy_info.get('port', 'N/A')}")
        if "mapping" in proxy_info:
            print(f"  {t('cmd.proxy_model_mapping')}:")
            for m in proxy_info["mapping"]:
                print(f"    {m}")
    else:
        print(t("cmd.proxy_stopped"))
        if proxy_info["config"]:
            print(f"  {t('cmd.proxy_config_port')}: {proxy_info.get('port', 'N/A')}")


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
        print(t("cmd.teams_no_active"))
        sys.exit(1)

    profiles = load_profiles()
    if active not in profiles:
        print(t("cmd.teams_missing", active=active))
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

    status = t("cmd.teams_enabled") if profile["enableTeams"] else t("cmd.teams_disabled")
    print(t("cmd.teams_done", name=active, status=status))

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
