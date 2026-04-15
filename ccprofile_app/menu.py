"""交互式菜单主循环。"""

from .commands import cmd_add, cmd_current, cmd_delete, cmd_edit, cmd_init, cmd_list, cmd_show, cmd_switch
from .constants import KEY_FILE, PROFILES_ENC
from .provider import cmd_provider_add, cmd_provider_delete, cmd_provider_edit, cmd_provider_list, cmd_provider_show
from .storage import load_meta, load_profiles, load_providers
from .terminal import select_from_list

# ── 菜单结构定义 ──

MAIN_MENU = [
    ("switch",      "切换配置"),
    ("_view",       "查看配置 ←→"),
    ("_manage",     "管理配置 ←→"),
    ("_provider",   "提供商管理 ←→"),
    ("_system",     "系统设置 ←→"),
    ("__exit__",    "退出"),
]

VIEW_MENU = [
    ("list",    "列出所有配置"),
    ("current", "显示当前活动配置"),
    ("show",    "显示配置详情"),
]

MANAGE_MENU = [
    ("add",     "添加配置"),
    ("edit",    "编辑配置"),
    ("delete",  "删除配置"),
]

SYSTEM_MENU = [
    ("init",    "初始化 / 重置密钥"),
]

PROVIDER_MENU = [
    ("provider_add",    "添加提供商"),
    ("provider_list",   "列出所有提供商"),
    ("provider_show",   "显示提供商详情"),
    ("provider_edit",   "编辑提供商"),
    ("provider_delete", "删除提供商"),
]

SUB_MENUS = {
    "_view":     ("查看配置", VIEW_MENU),
    "_manage":   ("管理配置", MANAGE_MENU),
    "_provider": ("提供商管理", PROVIDER_MENU),
    "_system":   ("系统设置", SYSTEM_MENU),
}


def interactive_menu():
    """交互式菜单主循环。"""
    commands_map = {
        "init": cmd_init,
        "add": cmd_add,
        "switch": cmd_switch,
        "list": cmd_list,
        "show": cmd_show,
        "edit": cmd_edit,
        "delete": cmd_delete,
        "current": cmd_current,
        "provider_add": cmd_provider_add,
        "provider_list": cmd_provider_list,
        "provider_show": cmd_provider_show,
        "provider_edit": cmd_provider_edit,
        "provider_delete": cmd_provider_delete,
    }

    def pick_profile(prompt_text):
        """列出配置供用户上下键选择。"""
        if not KEY_FILE.exists() or not PROFILES_ENC.exists():
            print("  暂无配置。请先 init 并 add。")
            return None
        profiles = load_profiles()
        if not profiles:
            print("  暂无配置。请先添加。")
            return None
        names = list(profiles.keys())
        meta = load_meta()
        items = []
        for n in names:
            mark = " *" if n == meta.get("active") else ""
            prof = profiles[n]
            mode = prof.get("mode", "single")
            if mode == "mixed":
                url = "混合模式"
            else:
                url = prof.get("env", {}).get("ANTHROPIC_BASE_URL", "N/A")
            items.append((n, f"{n}{mark}  ({url})"))
        items.append((None, "取消"))
        return select_from_list(items, prompt_text)

    def pick_provider(prompt_text):
        """列出提供商供用户上下键选择。"""
        providers = load_providers()
        if not providers:
            print("  暂无提供商。请先添加提供商。")
            return None
        items = []
        for name, prov in providers.items():
            url = prov.get("base_url", "")
            models = ", ".join(prov.get("models", []))
            items.append((name, f"{name}  ({url})"))
        items.append((None, "取消"))
        return select_from_list(items, prompt_text)

    def _execute_command(cmd_name):
        """执行单个命令，处理参数构造和错误。"""
        class Args:
            pass

        args = Args()

        if cmd_name == "add":
            name = input("  配置名称: ").strip()
            if not name:
                print("  已取消。")
                return
            args.name = name

            # 模式选择
            print("  选择配置模式:")
            print("    [1] 单一模式 (single) - 一个提供商对应所有模型")
            print("    [2] 混合模式 (mixed) - 不同模型使用不同提供商")
            mode_choice = input("  请选择 [1/2] [1]: ").strip()
            args.mode = "mixed" if mode_choice == "2" else "single"

            args.token = None
            args.url = None
            args.model = None
            args.effort = None
            args.anthropic_model = None
            args.haiku_model = None
            args.sonnet_model = None
            args.opus_model = None
            args.disable_all = False
            args.enable_teams = False
            args.bark_key = None
            args.host_label = None
            args.notify_sound = None
            args.hooks_json = None
        elif cmd_name == "provider_add":
            name = input("  提供商名称: ").strip()
            if not name:
                print("  已取消。")
                return
            args.name = name
            args.url = None
            args.key = None
            args.models = None
        elif cmd_name in ("switch", "show", "edit", "delete"):
            name = pick_profile("选择配置")
            if name is None:
                return
            args.name = name
        elif cmd_name in ("provider_show", "provider_edit", "provider_delete"):
            name = pick_provider("选择提供商")
            if name is None:
                return
            args.name = name

        try:
            commands_map[cmd_name](args)
        except SystemExit:
            pass
        except (EOFError, KeyboardInterrupt):
            print("\n  操作已取消。")

    print("\n  ccprofile — Claude Code 配置管理")

    current_menu = MAIN_MENU
    current_prompt = "请选择操作"

    while True:
        meta = load_meta() if KEY_FILE.exists() else {}
        active = meta.get("active", "")
        if active:
            print(f"  当前配置: {active}\n")

        try:
            selected = select_from_list(current_menu, current_prompt)
        except (EOFError, KeyboardInterrupt):
            print("\n  再见！")
            break

        # 取消 / 退出
        if selected is None or selected == "__exit__":
            if current_menu is MAIN_MENU:
                print("  再见！")
                break
            current_menu = MAIN_MENU
            current_prompt = "请选择操作"
            continue

        # 子菜单入口
        if selected in SUB_MENUS:
            current_prompt, current_menu = SUB_MENUS[selected]
            continue

        # 执行命令
        _execute_command(selected)
        print()

    print()
