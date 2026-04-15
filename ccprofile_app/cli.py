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
)
from .constants import VERSION  # noqa: E402
from .menu import interactive_menu  # noqa: E402
from .provider import (  # noqa: E402
    cmd_provider_add,
    cmd_provider_delete,
    cmd_provider_edit,
    cmd_provider_list,
    cmd_provider_show,
)
from .storage import migrate_from_legacy  # noqa: E402


def build_parser():
    """构建 argparse 解析器。"""
    parser = argparse.ArgumentParser(
        prog="ccprofile",
        description="Claude Code API 配置管理工具"
    )
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {VERSION}")
    sub = parser.add_subparsers(dest="command")

    # init
    sub.add_parser("init", help="初始化：生成加密密钥")

    # add
    p_add = sub.add_parser("add", help="添加配置")
    p_add.add_argument("name", help="配置名称")
    p_add.add_argument("--mode", choices=["single", "mixed"], default="single", help="配置模式 (single/mixed)")
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

    # provider
    p_prov = sub.add_parser("provider", help="提供商管理")
    prov_sub = p_prov.add_subparsers(dest="provider_command")

    # provider add
    p_prov_add = prov_sub.add_parser("add", help="添加提供商")
    p_prov_add.add_argument("name", help="提供商名称")
    p_prov_add.add_argument("-u", "--url", help="API 基础地址或 /v1/messages 端点")
    p_prov_add.add_argument("-k", "--key", help="API 密钥")
    p_prov_add.add_argument("-m", "--models", help="可用模型 (逗号分隔)")

    # provider list
    prov_sub.add_parser("list", help="列出所有提供商")

    # provider show
    p_prov_show = prov_sub.add_parser("show", help="显示提供商详情")
    p_prov_show.add_argument("name", help="提供商名称")

    # provider edit
    p_prov_edit = prov_sub.add_parser("edit", help="编辑提供商")
    p_prov_edit.add_argument("name", help="提供商名称")

    # provider delete
    p_prov_delete = prov_sub.add_parser("delete", help="删除提供商")
    p_prov_delete.add_argument("name", help="提供商名称")

    # proxy
    p_proxy = sub.add_parser("proxy", help="代理管理")
    proxy_sub = p_proxy.add_subparsers(dest="proxy_command")

    # proxy status
    proxy_sub.add_parser("status", help="显示代理状态")

    # proxy stop
    proxy_sub.add_parser("stop", help="停止代理")

    # proxy logs
    p_proxy_logs = proxy_sub.add_parser("logs", help="显示代理日志")
    p_proxy_logs.add_argument("-n", "--lines", type=int, default=50, help="显示最后 N 行 (默认 50)")

    return parser


def main():
    """CLI 主入口。"""
    # 内部代理模式：PyInstaller 打包后通过 --_internal-proxy 启动代理子进程
    if len(sys.argv) > 1 and sys.argv[1] == "--_internal-proxy":
        sys.argv = [sys.argv[0]] + sys.argv[2:]  # 移除 --_internal-proxy，保留其余参数
        from .proxy import main as proxy_main
        proxy_main()
        return

    parser = build_parser()
    args = parser.parse_args()

    migrate_from_legacy()

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
    else:
        commands[args.command](args)
