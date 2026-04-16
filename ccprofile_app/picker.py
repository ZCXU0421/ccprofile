"""共享选择器：pick_profile() 和 pick_provider()。"""

from .constants import KEY_FILE, PROFILES_ENC
from .storage import load_meta, load_profiles, load_providers
from .terminal import select_from_list


def pick_profile(prompt_text="选择配置"):
    """列出配置供用户箭头选择。CLI 和 menu 共用。返回配置名或 None。"""
    if not KEY_FILE.exists() or not PROFILES_ENC.exists():
        print("  暂无配置。请先 init 并 add。")
        return None
    profiles = load_profiles()
    if not profiles:
        print("  暂无配置。请先添加。")
        return None
    meta = load_meta()
    items = []
    for n, prof in profiles.items():
        mark = " *" if n == meta.get("active") else ""
        mode = prof.get("mode", "single")
        url = "混合模式" if mode == "mixed" else prof.get("env", {}).get("ANTHROPIC_BASE_URL", "N/A")
        items.append((n, f"{n}{mark}  ({url})"))
    items.append((None, "取消"))
    return select_from_list(items, prompt_text)


def pick_provider(prompt_text="选择提供商"):
    """列出提供商供用户箭头选择。CLI 和 menu 共用。返回提供商名或 None。"""
    providers = load_providers()
    if not providers:
        print("  暂无提供商。请先添加。")
        return None
    items = []
    for name, prov in providers.items():
        url = prov.get("base_url", "")
        items.append((name, f"{name}  ({url})"))
    items.append((None, "取消"))
    return select_from_list(items, prompt_text)
