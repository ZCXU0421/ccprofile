"""交互式菜单主循环。"""

from .commands import (
    cmd_add,
    cmd_context_1m,
    cmd_current,
    cmd_delete,
    cmd_edit,
    cmd_init,
    cmd_list,
    cmd_show,
    cmd_switch,
    cmd_teams,
)
from .constants import KEY_FILE
from .i18n import get_language, set_language, t
from .provider import cmd_provider_add, cmd_provider_delete, cmd_provider_edit, cmd_provider_list, cmd_provider_show
from .sync import (
    cmd_sync_auto,
    cmd_sync_config,
    cmd_sync_reset,
    cmd_sync_status,
    cmd_sync_strategy,
)
from .storage import load_meta
from .picker import pick_profile, pick_provider
from .terminal import select_from_list


def _main_menu():
    return [
        ("switch",      t("menu.switch_profile")),
        ("_manage",     t("menu.manage_profiles")),
        ("_provider",   t("menu.provider_mgmt")),
        ("_system",     t("menu.system_settings")),
        ("__exit__",    t("menu.exit")),
    ]


def _view_menu():
    return [
        ("list",    t("menu.list_profiles")),
        ("current", t("menu.show_current")),
        ("show",    t("menu.show_profile")),
    ]


def _manage_menu():
    return [
        ("_view",     t("menu.view_profiles")),
        ("add",       t("menu.add_profile")),
        ("edit",      t("menu.edit_profile")),
        ("_advanced", t("menu.advanced_settings")),
        ("delete",    t("menu.delete_profile")),
    ]


def _advanced_menu():
    return [
        ("teams",      t("menu.switch_teams")),
        ("context_1m", t("menu.switch_1m_context")),
    ]


def _system_menu():
    return [
        ("init",     t("menu.init_reset")),
        ("language", t("menu.language_settings")),
        ("_sync",    t("menu.sync_settings")),
    ]


def _provider_menu():
    return [
        ("provider_add",    t("menu.add_provider")),
        ("provider_list",   t("menu.list_providers")),
        ("provider_show",   t("menu.show_provider")),
        ("provider_edit",   t("menu.edit_provider")),
        ("provider_delete", t("menu.delete_provider")),
    ]


def _sync_menu():
    return [
        ("sync_auto",     t("menu.sync_auto")),
        ("sync_config",   t("menu.sync_config")),
        ("sync_status",   t("menu.sync_status")),
        ("sync_strategy", t("menu.sync_strategy")),
        ("sync_reset",    t("menu.sync_reset")),
    ]


def _sub_menus():
    return {
        "_view":     (t("menu.view_profiles"), _view_menu()),
        "_manage":   (t("menu.manage_profiles"), _manage_menu()),
        "_provider": (t("menu.provider_mgmt"), _provider_menu()),
        "_system":   (t("menu.system_settings"), _system_menu()),
        "_advanced": (t("menu.advanced_settings"), _advanced_menu()),
        "_sync":     (t("menu.sync_settings"), _sync_menu()),
    }


def interactive_menu():
    """交互式菜单主循环。"""
    commands_map = {
        "init": cmd_init,
        "add": cmd_add,
        "switch": cmd_switch,
        "list": cmd_list,
        "show": cmd_show,
        "current": cmd_current,
        "edit": cmd_edit,
        "delete": cmd_delete,
        "teams": cmd_teams,
        "context_1m": cmd_context_1m,
        "sync_auto": cmd_sync_auto,
        "sync_config": cmd_sync_config,
        "sync_status": cmd_sync_status,
        "sync_strategy": cmd_sync_strategy,
        "sync_reset": cmd_sync_reset,
        "provider_add": cmd_provider_add,
        "provider_list": cmd_provider_list,
        "provider_show": cmd_provider_show,
        "provider_edit": cmd_provider_edit,
        "provider_delete": cmd_provider_delete,
    }

    def _execute_command(cmd_name):
        """执行单个命令，处理参数构造和错误。"""
        class Args:
            pass

        args = Args()

        if cmd_name == "add":
            name = input(f"  {t('menu.profile_name_prompt')}: ").strip()
            if not name:
                print(f"  {t('menu.canceled')}")
                return
            args.name = name

            # 模式选择
            mode = select_from_list(
                [("single", t("menu.single_mode_desc")),
                 ("mixed",  t("menu.mixed_mode_desc"))],
                t("menu.select_mode")
            )
            if mode is None:
                print(f"  {t('menu.canceled')}")
                return
            args.mode = mode

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
            name = input(f"  {t('menu.provider_name_prompt')}: ").strip()
            if not name:
                print(f"  {t('menu.canceled')}")
                return
            args.name = name
            args.url = None
            args.key = None
            args.models = None
        elif cmd_name in ("switch", "show", "edit", "delete"):
            name = pick_profile(t("menu.view_profiles"))
            if name is None:
                return
            args.name = name
        elif cmd_name in ("provider_show", "provider_edit", "provider_delete"):
            name = pick_provider(t("menu.provider_mgmt"))
            if name is None:
                return
            args.name = name
        elif cmd_name == "teams":
            args.action = "toggle"
            args.apply = True
        elif cmd_name == "context_1m":
            args.action = "toggle"
            args.apply = True
        elif cmd_name == "sync_strategy":
            args.strategy_arg = None

        try:
            commands_map[cmd_name](args)
        except SystemExit:
            pass
        except (EOFError, KeyboardInterrupt):
            print(f"\n  {t('menu.op_canceled')}")

    print(f"\n  {t('menu.banner')}")

    current_menu = _main_menu()
    current_prompt = t("menu.select_op")
    sub_menus = _sub_menus()
    menu_stack = []

    while True:
        meta = load_meta() if KEY_FILE.exists() else {}
        active = meta.get("active", "")

        if not KEY_FILE.exists():
            print(f"  ⚠ {t('menu.not_initialized')}\n")
        elif active:
            print(f"  {t('menu.current_profile')}: {active}\n")

        try:
            selected = select_from_list(current_menu, current_prompt)
        except (EOFError, KeyboardInterrupt):
            print(f"\n  {t('menu.goodbye')}")
            break

        # 取消 / 退出
        if selected is None or selected == "__exit__":
            if not menu_stack:
                print(f"  {t('menu.goodbye')}")
                break
            current_prompt, current_menu = menu_stack.pop()
            sub_menus = _sub_menus()
            continue

        # 语言设置
        if selected == "language":
            _handle_language_setting()
            # 重建当前菜单以反映新语言
            current_menu = _main_menu()
            current_prompt = t("menu.select_op")
            sub_menus = _sub_menus()
            menu_stack = []
            print()
            continue

        # 子菜单入口
        if selected in sub_menus:
            menu_stack.append((current_prompt, current_menu))
            current_prompt, current_menu = sub_menus[selected]
            continue

        # 执行命令
        _execute_command(selected)
        print()

    print()


def _handle_language_setting():
    """处理语言设置。"""
    current = get_language()
    items = [
        ("zh", t("menu.lang_zh")),
        ("en", t("menu.lang_en")),
    ]
    default_idx = 0 if current == "zh" else 1
    selected = select_from_list(items, t("menu.select_language"), default_index=default_idx)
    if selected is None:
        return
    if selected != current:
        set_language(selected)
        print(f"  {t('menu.language_changed')}")
