"""Provider CRUD 命令。"""

import re
import sys
from urllib.parse import urlparse

from .display import panel, kv, BOLD, DIM, RESET
from .formatting import mask_token
from .picker import pick_provider
from .prompts import prompt_provider_fields
from .terminal import confirm_action
from .storage import load_profiles, load_providers, save_providers


def _validate_url(url: str) -> None:
    """验证 URL 格式。"""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        print("错误: API 地址必须以 http:// 或 https:// 开头。", file=sys.stderr)
        sys.exit(1)
    if not parsed.netloc:
        print("错误: API 地址格式无效。", file=sys.stderr)
        sys.exit(1)


def _parse_models_arg(models_arg: str):
    """解析并验证 --models 的逗号分隔格式。"""
    raw_models = models_arg.split(",")
    models = []
    seen = set()

    for raw_model in raw_models:
        model = raw_model.strip()
        if not model:
            print("错误: --models 包含空模型名，请检查逗号分隔格式。", file=sys.stderr)
            sys.exit(1)
        if re.search(r"\s", model):
            print(f"错误: 模型名 '{model}' 不能包含空白字符。", file=sys.stderr)
            sys.exit(1)
        if model in seen:
            print(f"错误: --models 中模型名重复: {model}", file=sys.stderr)
            sys.exit(1)
        seen.add(model)
        models.append(model)

    return models


def cmd_provider_add(args):
    """添加提供商。"""
    providers = load_providers()
    name = args.name

    if name in providers:
        print(f"错误: 提供商 '{name}' 已存在。请使用 edit 命令修改。")
        sys.exit(1)

    non_interactive_values = {
        "url": getattr(args, "url", None),
        "key": getattr(args, "key", None),
        "models": getattr(args, "models", None),
    }
    provided_args = [
        key for key, value in non_interactive_values.items() if value is not None
    ]

    if provided_args and len(provided_args) != len(non_interactive_values):
        missing = [f"--{key}" for key in non_interactive_values if key not in provided_args]
        print(
            "错误: 非交互添加提供商时必须同时提供 --url、--key 和 --models。"
            f" 缺少: {', '.join(missing)}",
            file=sys.stderr,
        )
        sys.exit(1)

    if provided_args:
        # 非交互模式
        models = _parse_models_arg(args.models)
        if not args.url.strip() or not args.key.strip() or not models:
            print("错误: --url、--key 和 --models 不能为空。", file=sys.stderr)
            sys.exit(1)

        provider = {
            "base_url": args.url.strip(),
            "api_key": args.key.strip(),
            "models": models,
        }
    else:
        # 交互模式
        print(f"添加提供商 '{name}'。按回车使用默认值。")
        provider = prompt_provider_fields()

    _validate_url(provider["base_url"])

    providers[name] = provider
    save_providers(providers)
    print(f"提供商 '{name}' 已添加。")


def cmd_provider_list(_args):
    """列出所有提供商。"""
    providers = load_providers()

    if not providers:
        print("暂无提供商。")
        return

    body = []
    for name, prov in providers.items():
        url = prov.get("base_url", "N/A")
        models = ", ".join(prov.get("models", []))
        body.append(f"{BOLD}{name}{RESET}")
        body.append(f"  {DIM}{url}{RESET}")
        body.append(f"  模型: {models}")
        body.append("")

    print(panel("提供商列表", f"共 {len(providers)} 个", body))


def cmd_provider_show(args):
    """显示提供商详情。"""
    providers = load_providers()
    name = args.name
    if name is None:
        name = pick_provider("选择要查看的提供商")
        if name is None:
            return

    if name not in providers:
        print(f"错误: 提供商 '{name}' 不存在。")
        sys.exit(1)

    prov = providers[name]
    body = []
    body.append("")
    body.append(kv("API 地址", prov.get("base_url", "N/A")))
    body.append(kv("API 密钥", mask_token(prov.get("api_key", ""))))
    models = prov.get("models", [])
    body.append(kv("可用模型", ", ".join(models) if models else f"{DIM}N/A{RESET}"))
    body.append("")

    print(panel(name, "提供商", body))


def cmd_provider_edit(args):
    """编辑提供商。"""
    providers = load_providers()
    name = args.name
    if name is None:
        name = pick_provider("选择要编辑的提供商")
        if name is None:
            return

    if name not in providers:
        print(f"错误: 提供商 '{name}' 不存在。")
        sys.exit(1)

    print(f"编辑提供商 '{name}'。按回车保留当前值。")
    provider = prompt_provider_fields(providers[name])
    _validate_url(provider["base_url"])
    providers[name] = provider
    save_providers(providers)
    print(f"提供商 '{name}' 已更新。")


def cmd_provider_delete(args):
    """删除提供商。"""
    providers = load_providers()
    name = args.name
    if name is None:
        name = pick_provider("选择要删除的提供商")
        if name is None:
            return

    if name not in providers:
        print(f"错误: 提供商 '{name}' 不存在。")
        sys.exit(1)

    # 检查是否被 mixed profile 引用
    profiles = load_profiles()
    referring = []
    for prof_name, prof in profiles.items():
        if prof.get("mode") == "mixed":
            for slot, target in prof.get("model_mapping", {}).items():
                if target.get("provider") == name:
                    referring.append(prof_name)
                    break
    if referring:
        print(f"错误: 提供商 '{name}' 正被以下配置使用: {', '.join(referring)}")
        print("请先删除或修改这些配置后再删除提供商。")
        sys.exit(1)

    if not confirm_action(f"确认删除提供商 '{name}'？", default_yes=False):
        print("已取消。")
        return

    del providers[name]
    save_providers(providers)
    print(f"提供商 '{name}' 已删除。")
