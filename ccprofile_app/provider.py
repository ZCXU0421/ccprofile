"""Provider CRUD 命令。"""

import re
import sys
from urllib.parse import urlparse

from .display import panel, kv, BOLD, DIM, RESET
from .formatting import mask_token
from .i18n import t
from .picker import pick_provider
from .prompts import prompt_provider_fields
from .terminal import confirm_action
from .storage import load_profiles, load_providers, save_providers


def _mark_sync_dirty():
    """在同步已配置时标记本地数据变更。"""
    from .sync import _sync_mark_dirty as _mark
    try:
        _mark()
    except Exception:
        pass


def _validate_url(url: str) -> None:
    """验证 URL 格式。"""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        print(t("prov.url_scheme_error"), file=sys.stderr)
        sys.exit(1)
    if not parsed.netloc:
        print(t("prov.url_format_error"), file=sys.stderr)
        sys.exit(1)


def _parse_models_arg(models_arg: str):
    """解析并验证 --models 的逗号分隔格式。"""
    raw_models = models_arg.split(",")
    models = []
    seen = set()

    for raw_model in raw_models:
        model = raw_model.strip()
        if not model:
            print(t("prov.models_empty_error"), file=sys.stderr)
            sys.exit(1)
        if re.search(r"\s", model):
            print(t("prov.models_whitespace_error", model=model), file=sys.stderr)
            sys.exit(1)
        if model in seen:
            print(t("prov.models_duplicate_error", model=model), file=sys.stderr)
            sys.exit(1)
        seen.add(model)
        models.append(model)

    return models


def cmd_provider_add(args):
    """添加提供商。"""
    providers = load_providers()
    name = args.name

    if name in providers:
        print(t("prov.add_exists", name=name))
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
            t("prov.add_noninteractive_all_required", missing=", ".join(missing)),
            file=sys.stderr,
        )
        sys.exit(1)

    if provided_args:
        # 非交互模式
        models = _parse_models_arg(args.models)
        if not args.url.strip() or not args.key.strip() or not models:
            print(t("prov.add_empty_error"), file=sys.stderr)
            sys.exit(1)

        provider = {
            "base_url": args.url.strip(),
            "api_key": args.key.strip(),
            "models": models,
        }
    else:
        # 交互模式
        print(t("prov.add_intro", name=name))
        provider = prompt_provider_fields()

    _validate_url(provider["base_url"])

    providers[name] = provider
    save_providers(providers)
    _mark_sync_dirty()
    print(t("prov.add_done", name=name))


def cmd_provider_list(_args):
    """列出所有提供商。"""
    providers = load_providers()

    if not providers:
        print(t("prov.list_empty"))
        return

    body = []
    for name, prov in providers.items():
        url = prov.get("base_url", "N/A")
        models = ", ".join(prov.get("models", []))
        body.append(f"{BOLD}{name}{RESET}")
        body.append(f"  {DIM}{url}{RESET}")
        body.append(f"  {t('prov.list_models')}: {models}")
        body.append("")

    print(panel(t("prov.panel_title"), t("prov.list_total", n=len(providers)), body))


def cmd_provider_show(args):
    """显示提供商详情。"""
    providers = load_providers()
    name = args.name
    if name is None:
        name = pick_provider(t("prov.show_pick"))
        if name is None:
            return

    if name not in providers:
        print(t("prov.show_not_found", name=name))
        sys.exit(1)

    prov = providers[name]
    body = []
    body.append("")
    body.append(kv(t("prov.api_address"), prov.get("base_url", "N/A")))
    body.append(kv(t("prov.api_key"), mask_token(prov.get("api_key", ""))))
    models = prov.get("models", [])
    body.append(kv(t("prov.available_models"), ", ".join(models) if models else f"{DIM}N/A{RESET}"))
    body.append("")

    print(panel(name, t("prov.panel_provider"), body))


def cmd_provider_edit(args):
    """编辑提供商。"""
    providers = load_providers()
    name = args.name
    if name is None:
        name = pick_provider(t("prov.edit_pick"))
        if name is None:
            return

    if name not in providers:
        print(t("prov.edit_not_found", name=name))
        sys.exit(1)

    print(t("prov.edit_intro", name=name))
    provider = prompt_provider_fields(providers[name])
    _validate_url(provider["base_url"])
    providers[name] = provider
    save_providers(providers)
    _mark_sync_dirty()
    print(t("prov.edit_done", name=name))


def cmd_provider_delete(args):
    """删除提供商。"""
    providers = load_providers()
    name = args.name
    if name is None:
        name = pick_provider(t("prov.delete_pick"))
        if name is None:
            return

    if name not in providers:
        print(t("prov.delete_not_found", name=name))
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
        print(t("prov.delete_in_use", name=name, profiles=", ".join(referring)))
        print(t("prov.delete_in_use_hint"))
        sys.exit(1)

    if not confirm_action(t("prov.delete_confirm", name=name), default_yes=False):
        print("已取消。")
        return

    del providers[name]
    save_providers(providers)
    _mark_sync_dirty()
    print(t("prov.delete_done", name=name))
