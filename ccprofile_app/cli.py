"""CLI 入口：argparse 定义和 main()。"""

import argparse
import sys

# Fix encoding on Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

try:
    from cryptography.fernet import Fernet  # noqa: F401
except ImportError:
    print("Error: cryptography package required. Run: pip install cryptography")
    sys.exit(1)

from .commands import (  # noqa: E402
    cmd_add,
    cmd_context_1m,
    cmd_current,
    cmd_delete,
    cmd_edit,
    cmd_init,
    cmd_list,
    cmd_proxy_logs,
    cmd_proxy_status,
    cmd_proxy_stop,
    cmd_show,
    cmd_switch,
    cmd_teams,
)
from .constants import VERSION  # noqa: E402
from .i18n import init_language, t  # noqa: E402
from .menu import interactive_menu  # noqa: E402
from .provider import (  # noqa: E402
    cmd_provider_add,
    cmd_provider_delete,
    cmd_provider_edit,
    cmd_provider_list,
    cmd_provider_show,
)
from .sync import (  # noqa: E402
    cmd_sync_auto,
    cmd_sync_config,
    cmd_sync_reset,
    cmd_sync_status,
    cmd_sync_strategy,
)
from .storage import migrate_from_legacy  # noqa: E402
from .updater import cmd_update, maybe_check_on_launch, emit_launch_hint  # noqa: E402


def build_parser():
    """构建 argparse 解析器。"""
    parser = argparse.ArgumentParser(
        prog="ccprofile",
        description=t("cli.description")
    )
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {VERSION}")
    sub = parser.add_subparsers(dest="command")

    # init
    sub.add_parser("init", help=t("cli.init_help"))

    # add
    p_add = sub.add_parser("add", help=t("cli.add_help"))
    p_add.add_argument("name", help=t("cli.add_name_help"))
    p_add.add_argument("--mode", choices=["single", "mixed"], default="single", help=t("cli.add_mode_help"))
    p_add.add_argument("-t", "--token", help=t("cli.add_token_help"))
    p_add.add_argument("-u", "--url", help=t("cli.add_url_help"))
    p_add.add_argument("-m", "--model", help=t("cli.add_model_help"))
    p_add.add_argument("-e", "--effort", help=t("cli.add_effort_help"))
    p_add.add_argument("--anthropic-model", help=t("cli.add_anthropic_model_help"))
    p_add.add_argument("--haiku-model", help=t("cli.add_haiku_model_help"))
    p_add.add_argument("--sonnet-model", help=t("cli.add_sonnet_model_help"))
    p_add.add_argument("--opus-model", help=t("cli.add_opus_model_help"))
    p_add.add_argument("--disable-all", action="store_true", help=t("cli.add_disable_all_help"))
    p_add.add_argument("--enable-teams", action="store_true", help=t("cli.add_enable_teams_help"))
    p_add.add_argument("--bark-key", help=t("cli.add_bark_key_help"))
    p_add.add_argument("--host-label", help=t("cli.add_host_label_help"))
    p_add.add_argument("--notify-sound", help=t("cli.add_notify_sound_help"))
    p_add.add_argument("--hooks-json", help=t("cli.add_hooks_json_help"))

    # switch
    p_sw = sub.add_parser("switch", help=t("cli.switch_help"))
    p_sw.add_argument("name", nargs="?", default=None, help=t("cli.switch_name_help"))

    # list
    sub.add_parser("list", help=t("cli.list_help"))

    # show
    p_show = sub.add_parser("show", help=t("cli.show_help"))
    p_show.add_argument("name", nargs="?", default=None, help=t("cli.show_name_help"))

    # edit
    p_edit = sub.add_parser("edit", help=t("cli.edit_help"))
    p_edit.add_argument("name", nargs="?", default=None, help=t("cli.edit_name_help"))
    p_edit.add_argument("--enable-teams", action="store_true", help=t("cli.edit_enable_teams_help"))
    p_edit.add_argument("--disable-teams", action="store_true", help=t("cli.edit_disable_teams_help"))

    # delete
    p_del = sub.add_parser("delete", help=t("cli.delete_help"))
    p_del.add_argument("name", nargs="?", default=None, help=t("cli.delete_name_help"))

    # current
    sub.add_parser("current", help=t("cli.current_help"))

    # teams
    p_teams = sub.add_parser("teams", help=t("cli.teams_help"))
    p_teams.add_argument("action", nargs="?", choices=["on", "off", "toggle"],
                         default="toggle", help=t("cli.teams_action_help"))
    p_teams.add_argument("--apply", action="store_true",
                         help=t("cli.teams_apply_help"))

    # context-1m
    p_context_1m = sub.add_parser("context-1m", help=t("cli.1m_help"))
    p_context_1m.add_argument("action", nargs="?", choices=["on", "off", "toggle"],
                              default="toggle", help=t("cli.1m_action_help"))
    p_context_1m.add_argument("--apply", action="store_true",
                              help=t("cli.1m_apply_help"))

    # provider
    p_prov = sub.add_parser("provider", help=t("cli.provider_help"))
    prov_sub = p_prov.add_subparsers(dest="provider_command")

    # provider add
    p_prov_add = prov_sub.add_parser("add", help=t("cli.provider_add_help"))
    p_prov_add.add_argument("name", help=t("cli.provider_name_help"))
    p_prov_add.add_argument("-u", "--url", help=t("cli.provider_url_help"))
    p_prov_add.add_argument("-k", "--key", help=t("cli.provider_key_help"))
    p_prov_add.add_argument("-m", "--models", help=t("cli.provider_models_help"))

    # provider list
    prov_sub.add_parser("list", help=t("cli.provider_list_help"))

    # provider show
    p_prov_show = prov_sub.add_parser("show", help=t("cli.provider_show_help"))
    p_prov_show.add_argument("name", nargs="?", default=None, help=t("cli.provider_show_name_help"))

    # provider edit
    p_prov_edit = prov_sub.add_parser("edit", help=t("cli.provider_edit_help"))
    p_prov_edit.add_argument("name", nargs="?", default=None, help=t("cli.provider_edit_name_help"))

    # provider delete
    p_prov_delete = prov_sub.add_parser("delete", help=t("cli.provider_delete_help"))
    p_prov_delete.add_argument("name", nargs="?", default=None, help=t("cli.provider_delete_name_help"))

    # proxy
    p_proxy = sub.add_parser("proxy", help=t("cli.proxy_help"))
    proxy_sub = p_proxy.add_subparsers(dest="proxy_command")

    # proxy status
    proxy_sub.add_parser("status", help=t("cli.proxy_status_help"))

    # proxy stop
    proxy_sub.add_parser("stop", help=t("cli.proxy_stop_help"))

    # proxy logs
    p_proxy_logs = proxy_sub.add_parser("logs", help=t("cli.proxy_logs_help"))
    p_proxy_logs.add_argument("-n", "--lines", type=int, default=50, help=t("cli.proxy_logs_lines_help"))

    # sync
    p_sync = sub.add_parser("sync", help=t("cli.sync_help"))
    sync_sub = p_sync.add_subparsers(dest="sync_command")

    sync_sub.add_parser("config", help=t("cli.sync_config_help"))

    sync_sub.add_parser("status", help=t("cli.sync_status_help"))

    p_sync_strategy = sync_sub.add_parser("strategy", help=t("cli.sync_strategy_help"))
    p_sync_strategy.add_argument(
        "strategy_arg",
        nargs="?",
        default=None,
        choices=["merge", "local-wins", "remote-wins"],
        help=t("cli.sync_strategy_arg_help"),
    )

    sync_sub.add_parser("reset", help=t("cli.sync_reset_help"))

    # update
    p_upd = sub.add_parser("update", help=t("cli.update_help"))
    p_upd.add_argument("--check", action="store_true", help=t("cli.update_check_help"))
    p_upd.add_argument("-y", "--yes", action="store_true", help=t("cli.update_yes_help"))
    p_upd.add_argument("--force", action="store_true", help=t("cli.update_force_help"))
    p_upd.add_argument("--prerelease", action="store_true", help=t("cli.update_prerelease_help"))

    return parser


def main():
    """CLI 主入口。"""
    init_language()
    # 内部代理模式：PyInstaller 打包后通过 --_internal-proxy 启动代理子进程
    if len(sys.argv) > 1 and sys.argv[1] == "--_internal-proxy":
        sys.argv = [sys.argv[0]] + sys.argv[2:]  # 移除 --_internal-proxy，保留其余参数
        from .proxy import main as proxy_main
        proxy_main()
        return

    parser = build_parser()
    args = parser.parse_args()

    migrate_from_legacy()

    # Kick off the background update check early so the fetch overlaps whatever
    # the user does and never blocks the CLI. Skip it for the `update` subcommand,
    # which fetches itself and sets _updated_this_run to mute the exit hint.
    if args.command != "update":
        maybe_check_on_launch()

    if not args.command:
        interactive_menu()
        emit_launch_hint()
        return

    commands = {
        "init": cmd_init,
        "add": cmd_add,
        "switch": cmd_switch,
        "list": cmd_list,
        "show": cmd_show,
        "edit": cmd_edit,
        "delete": cmd_delete,
        "current": cmd_current,
        "teams": cmd_teams,
        "context-1m": cmd_context_1m,
        "update": cmd_update,
    }

    provider_commands = {
        "add": cmd_provider_add,
        "list": cmd_provider_list,
        "show": cmd_provider_show,
        "edit": cmd_provider_edit,
        "delete": cmd_provider_delete,
    }

    proxy_commands = {
        "status": cmd_proxy_status,
        "stop": cmd_proxy_stop,
        "logs": cmd_proxy_logs,
    }

    sync_commands = {
        "config": cmd_sync_config,
        "status": cmd_sync_status,
        "strategy": cmd_sync_strategy,
        "reset": cmd_sync_reset,
    }

    if args.command == "provider":
        if args.provider_command:
            provider_commands[args.provider_command](args)
        else:
            parser.parse_args(["provider", "--help"])
    elif args.command == "proxy":
        if args.proxy_command:
            proxy_commands[args.proxy_command](args)
        else:
            parser.parse_args(["proxy", "--help"])
    elif args.command == "sync":
        if args.sync_command:
            sync_commands[args.sync_command](args)
        else:
            cmd_sync_auto(args)
    else:
        commands[args.command](args)

    emit_launch_hint()
