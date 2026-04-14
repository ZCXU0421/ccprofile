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

from .commands import cmd_add, cmd_current, cmd_delete, cmd_edit, cmd_init, cmd_list, cmd_show, cmd_switch  # noqa: E402
from .menu import interactive_menu  # noqa: E402


def build_parser():
    """构建 argparse 解析器。"""
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

    return parser


def main():
    """CLI 主入口。"""
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        interactive_menu()
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
    }
    commands[args.command](args)
