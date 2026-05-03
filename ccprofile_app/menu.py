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
from .provider import cmd_provider_add, cmd_provider_delete, cmd_provider_edit, cmd_provider_list, cmd_provider_show
from .sync import (
    cmd_sync_auto,
    cmd_sync_config,
    cmd_sync_pull,
    cmd_sync_push,
    cmd_sync_reset,
    cmd_sync_status,
    cmd_sync_strategy,
)
from .storage import load_meta
from .picker import pick_profile, pick_provider
from .terminal import select_from_list

# ── 菜单结构定义 ──

MAIN_MENU = [
    ("switch",      "切换配置"),
    ("_manage",     "管理配置"),
    ("_provider",   "提供商管理"),
    ("_system",     "系统设置"),
    ("__exit__",    "退出"),
]

VIEW_MENU = [
    ("list",    "列出所有配置"),
    ("current", "显示当前活动配置"),
    ("show",    "显示配置详情"),
]

MANAGE_MENU = [
    ("_view",  "查看配置"),
    ("add",    "添加配置"),
    ("edit",   "编辑配置"),
    ("_advanced", "其它设定"),
    ("delete", "删除配置"),
]

ADVANCED_MENU = [
    ("teams", "切换 Teams 模式"),
    ("context_1m", "切换 1M 上下文"),
]

SYSTEM_MENU = [
    ("init",    "初始化 / 重置密钥"),
    ("_sync",   "同步管理"),
]

PROVIDER_MENU = [
    ("provider_add",    "添加提供商"),
    ("provider_list",   "列出所有提供商"),
    ("provider_show",   "显示提供商详情"),
    ("provider_edit",   "编辑提供商"),
    ("provider_delete", "删除提供商"),
]

SYNC_MENU = [
    ("sync_auto", "立即同步"),
    ("sync_config", "配置 WebDAV 同步"),
    ("sync_status", "查看同步状态"),
    ("sync_push", "推送数据到远端"),
    ("sync_pull", "从远端拉取数据"),
    ("sync_strategy", "冲突解决策略"),
    ("sync_reset", "重置同步配置"),
]

SUB_MENUS = {
    "_view":     ("查看配置", VIEW_MENU),
    "_manage":   ("管理配置", MANAGE_MENU),
    "_advanced": ("其它设定", ADVANCED_MENU),
    "_provider": ("提供商管理", PROVIDER_MENU),
    "_system":   ("系统设置", SYSTEM_MENU),
    "_sync":     ("同步管理", SYNC_MENU),
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
        "sync_push": cmd_sync_push,
        "sync_pull": cmd_sync_pull,
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
            name = input("  配置名称: ").strip()
            if not name:
                print("  已取消。")
                return
            args.name = name

            # 模式选择
            mode = select_from_list(
                [("single", "单一模式 — 一个提供商对应所有模型"),
                 ("mixed",  "混合模式 — 不同模型使用不同提供商")],
                "选择配置模式"
            )
            if mode is None:
                print("  已取消。")
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
        elif cmd_name == "teams":
            args.action = "toggle"
            args.apply = True
        elif cmd_name == "context_1m":
            args.action = "toggle"
            args.apply = True
        elif cmd_name in ("sync_push", "sync_pull"):
            args.force = False
        elif cmd_name == "sync_strategy":
            args.strategy_arg = None

        try:
            commands_map[cmd_name](args)
        except SystemExit:
            pass
        except (EOFError, KeyboardInterrupt):
            print("\n  操作已取消。")

    print("\n  ccprofile — Claude Code 配置管理")

    current_menu = MAIN_MENU
    current_prompt = "请选择操作"
    menu_stack = []

    while True:
        meta = load_meta() if KEY_FILE.exists() else {}
        active = meta.get("active", "")

        if not KEY_FILE.exists():
            print("  ⚠ 系统尚未初始化，请先进入「系统设置」→「初始化」\n")
        elif active:
            print(f"  当前配置: {active}\n")

        try:
            selected = select_from_list(current_menu, current_prompt)
        except (EOFError, KeyboardInterrupt):
            print("\n  再见！")
            break

        # 取消 / 退出
        if selected is None or selected == "__exit__":
            if not menu_stack:
                print("  再见！")
                break
            current_prompt, current_menu = menu_stack.pop()
            continue

        # 子菜单入口
        if selected in SUB_MENUS:
            menu_stack.append((current_prompt, current_menu))
            current_prompt, current_menu = SUB_MENUS[selected]
            continue

        # 执行命令
        _execute_command(selected)
        print()

    print()
