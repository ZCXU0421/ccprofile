"""共享选择器：pick_profile() 和 pick_provider()。"""

from .constants import KEY_FILE, PROFILES_ENC
from .i18n import t
from .storage import load_meta, load_profiles, load_providers
from .terminal import select_from_list


def pick_profile(prompt_text=None):
    """列出配置供用户箭头选择。CLI 和 menu 共用。返回配置名或 None。"""
    if prompt_text is None:
        prompt_text = t("picker.select_profile")
    if not KEY_FILE.exists() or not PROFILES_ENC.exists():
        print(f"  {t('picker.no_profiles_init')}")
        return None
    profiles = load_profiles()
    if not profiles:
        print(f"  {t('picker.no_profiles_add')}")
        return None
    meta = load_meta()
    items = []
    for n, prof in profiles.items():
        mark = " *" if n == meta.get("active") else ""
        mode = prof.get("mode", "single")
        url = t("cmd.mode_mixed") if mode == "mixed" else prof.get("env", {}).get("ANTHROPIC_BASE_URL", "N/A")
        items.append((n, f"{n}{mark}  ({url})"))
    items.append((None, t("picker.cancel")))
    return select_from_list(items, prompt_text)


def pick_provider(prompt_text=None):
    """列出提供商供用户箭头选择。CLI 和 menu 共用。返回提供商名或 None。"""
    if prompt_text is None:
        prompt_text = t("picker.select_provider")
    providers = load_providers()
    if not providers:
        print(f"  {t('picker.no_providers')}")
        return None
    items = []
    for name, prov in providers.items():
        url = prov.get("base_url", "")
        items.append((name, f"{name}  ({url})"))
    items.append((None, t("picker.cancel")))
    return select_from_list(items, prompt_text)
