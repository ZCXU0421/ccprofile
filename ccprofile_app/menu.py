"""交互式菜单主循环。"""

from .commands import cmd_add, cmd_current, cmd_delete, cmd_edit, cmd_init, cmd_list, cmd_show, cmd_switch
from .constants import KEY_FILE, PROFILES_ENC
from .storage import load_meta, load_profiles
from .terminal import select_from_list


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
    }
    menu_items = [
        ("list",    "列出所有配置"),
        ("current", "显示当前活动配置"),
        ("show",    "显示配置详情"),
        ("switch",  "切换配置"),
        ("add",     "添加配置"),
        ("edit",    "编辑配置"),
        ("delete",  "删除配置"),
        ("init",    "初始化 / 重置密钥"),
        ("__exit__", "退出"),
    ]

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
            url = profiles[n].get("env", {}).get("ANTHROPIC_BASE_URL", "")
            items.append((n, f"{n}{mark}  ({url})"))
        items.append((None, "取消"))
        return select_from_list(items, prompt_text)

    print("\n  ccprofile — Claude Code 配置管理")

    while True:
        meta = load_meta() if KEY_FILE.exists() else {}
        active = meta.get("active", "")
        if active:
            print(f"  当前配置: {active}\n")

        try:
            cmd_name = select_from_list(menu_items, "请选择操作")
        except (EOFError, KeyboardInterrupt):
            print("\n  再见！")
            break

        if cmd_name is None or cmd_name == "__exit__":
            print("  再见！")
            break

        class Args:
            pass

        args = Args()

        try:
            if cmd_name == "add":
                name = input("  配置名称: ").strip()
                if not name:
                    print("  已取消。")
                    continue
                args.name = name
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
                commands_map[cmd_name](args)

            elif cmd_name in ("switch", "show", "edit", "delete"):
                name = pick_profile("选择配置")
                if name is None:
                    continue
                args.name = name
                commands_map[cmd_name](args)

            else:
                commands_map[cmd_name](args)

        except SystemExit:
            pass
        except (EOFError, KeyboardInterrupt):
            print("\n  返回主菜单。")

        print()
