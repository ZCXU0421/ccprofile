"""profile 字段交互输入。"""

import socket
import sys

from .constants import DISABLE_FLAGS, ENABLE_FLAGS, FIELDS, MODEL_SLOTS, PROVIDER_FIELDS
from .display import DIM, RESET
from .i18n import t, DISABLE_FLAG_I18N_KEYS, FIELD_I18N_KEYS, PROVIDER_FIELD_I18N_KEYS
from .storage import load_providers
from .terminal import confirm_action, select_from_list


def prompt_profile_fields(defaults=None):
    """交互式输入配置字段。返回配置字典。"""
    defaults = defaults or {}
    env_defaults = defaults.get("env", {})
    result = {"env": {}}

    for key, raw_label, required, default in FIELDS:
        label = t(FIELD_I18N_KEYS.get(key, "")) or raw_label
        # 模型选择：使用箭头选择
        if key == "model":
            current_val = defaults.get("model") or default
            items = [
                ("opus",   "Opus"),
                ("sonnet",  "Sonnet"),
                ("haiku",   "Haiku"),
            ]
            default_idx = 0
            for i, (v, _) in enumerate(items):
                if v == current_val:
                    default_idx = i
                    break
            value = select_from_list(items, t("prompt.select_label", label=label), default_index=default_idx)
            if value is None:
                value = current_val
            result["model"] = value
            continue

        # 努力等级选择：使用箭头选择
        if key == "effortLevel":
            current_val = defaults.get("effortLevel") or default
            items = [
                ("low",    "Low"),
                ("medium", "Medium"),
                ("high",   "High"),
            ]
            default_idx = 0
            for i, (v, _) in enumerate(items):
                if v == current_val:
                    default_idx = i
                    break
            value = select_from_list(items, t("prompt.select_label", label=label), default_index=default_idx)
            if value is None:
                value = current_val
            result["effortLevel"] = value
            continue

        current = env_defaults.get(key)
        display = current or default
        hint = f" [{display}]" if display else ""
        value = input(f"  {label}{hint}: ").strip()
        if not value:
            value = display
        if required and not value:
            print(t("prompt.required_field", label=label))
            sys.exit(1)
        if value is not None:
            result["env"][key] = value

    print(f"  {t('prompt.disable_options')}:")
    for flag, raw_desc in DISABLE_FLAGS:
        desc = t(DISABLE_FLAG_I18N_KEYS.get(flag, "")) or raw_desc
        cur = env_defaults.get(flag)
        default_on = str(cur) == "1" if cur is not None else True
        if confirm_action(t("prompt.disable_flag", desc=desc), default_yes=default_on):
            result["env"][flag] = "1"

    if ENABLE_FLAGS:
        print(f"  {t('prompt.enable_options')}:")
        for flag, desc in ENABLE_FLAGS:
            cur = env_defaults.get(flag)
            default_on = str(cur) == "1" if cur is not None else False
            if confirm_action(t("prompt.enable_flag", desc=desc), default_yes=default_on):
                result["env"][flag] = "1"

    # 推送通知配置
    print(f"  {t('prompt.hooks_config')}:")
    hooks_defaults = defaults.get("hooks", {}) if defaults else {}
    bark_key = input(f"    {t('prompt.bark_key')} [{hooks_defaults.get('bark_key', '')}]: ").strip()
    if bark_key or hooks_defaults.get("bark_key"):
        if not bark_key:
            bark_key = hooks_defaults["bark_key"]
        host_label_default = hooks_defaults.get("host_label", socket.gethostname())
        sound_default = hooks_defaults.get("sound", "minuet")
        host_label = input(f"    {t('prompt.host_label')} [{host_label_default}]: ").strip() or host_label_default
        sound = input(f"    {t('prompt.notify_sound')} [{sound_default}]: ").strip() or sound_default
        result["hooks"] = {
            "bark_key": bark_key,
            "host_label": host_label,
            "sound": sound,
        }

    return result


def prompt_provider_fields(defaults=None):
    """交互式输入提供商字段。返回提供商字典。"""
    defaults = defaults or {}
    result = {}

    for key, raw_label, required, default in PROVIDER_FIELDS:
        label = t(PROVIDER_FIELD_I18N_KEYS.get(key, "")) or raw_label
        current = defaults.get(key)
        display = current or default
        hint = f" [{display}]" if display else ""
        value = input(f"  {label}{hint}: ").strip()
        if not value:
            value = display
        if required and not value:
            print(t("prompt.required_field", label=label))
            sys.exit(1)
        if value is not None:
            result[key] = value

    # 解析 models 为列表
    if "models" in result and isinstance(result["models"], str):
        result["models"] = [m.strip() for m in result["models"].split(",") if m.strip()]

    return result


def prompt_mixed_profile_fields(defaults=None):
    """交互式输入混合配置字段。返回混合配置字典。"""
    defaults = defaults or {}
    providers = load_providers()

    if not providers:
        print(t("prompt.no_provider_error"))
        sys.exit(1)

    result = {}
    model_mapping = {}
    provider_list = list(providers.items())

    # 为每个模型槽位选择提供商和模型
    for slot in MODEL_SLOTS:
        print(f"\n  {t('prompt.configure_slot', slot=slot)}:")
        default_mapping = defaults.get("model_mapping", {}).get(slot, {})
        default_provider = default_mapping.get("provider")
        default_model = default_mapping.get("model")

        # 选择提供商
        prov_items = [
            (name, f"{name}  ({', '.join(prov.get('models', []))})")
            for name, prov in provider_list
        ]
        prov_items.append(("_skip", t("prompt.skip_slot")))
        prov_default_idx = len(prov_items) - 1
        if default_provider in providers:
            for i, (n, _) in enumerate(prov_items):
                if n == default_provider:
                    prov_default_idx = i
                    break
        provider_name = select_from_list(prov_items, t("prompt.select_provider_for_slot", slot=slot), default_index=prov_default_idx)
        if provider_name is None or provider_name == "_skip":
            continue

        # 选择模型
        provider = providers[provider_name]
        available_models = provider.get("models", [])
        if not available_models:
            print(f"    {t('prompt.provider_no_models', name=provider_name)}")
            continue

        model_items = [(m, m) for m in available_models]
        model_items.append(("_skip", t("prompt.skip_slot")))
        model_default_idx = len(model_items) - 1
        if default_model and default_model in available_models:
            for i, (m, _) in enumerate(model_items):
                if m == default_model:
                    model_default_idx = i
                    break
        model_choice = select_from_list(model_items, t("prompt.select_model", provider=provider_name), default_index=model_default_idx)
        if model_choice is None or model_choice == "_skip":
            continue

        model_mapping[slot] = {"provider": provider_name, "model": model_choice}

    if not model_mapping:
        print(t("prompt.mixed_min_one"))
        sys.exit(1)

    result["model_mapping"] = model_mapping

    # 通用配置（model、effortLevel、hooks）
    mapped_slots = [slot for slot in MODEL_SLOTS if slot in model_mapping]
    model_default = defaults.get("model", "opus")
    if model_default not in model_mapping:
        model_default = mapped_slots[0]

    # 默认模型选择
    slot_items = [(s, s) for s in mapped_slots]
    model_default_idx = 0
    for i, (s, _) in enumerate(slot_items):
        if s == model_default:
            model_default_idx = i
            break
    model = select_from_list(slot_items, t("prompt.select_default_model"), default_index=model_default_idx)
    if model is None:
        model = mapped_slots[0]
    result["model"] = model

    # 努力等级选择
    effort_default = defaults.get("effortLevel", "high")
    effort_items = [
        ("low",    "Low"),
        ("medium", "Medium"),
        ("high",   "High"),
    ]
    effort_default_idx = 2
    for i, (v, _) in enumerate(effort_items):
        if v == effort_default:
            effort_default_idx = i
            break
    effort = select_from_list(effort_items, t("prompt.select_effort"), default_index=effort_default_idx)
    if effort is None:
        effort = effort_default
    result["effortLevel"] = effort

    # 推送通知配置（与单一模式相同）
    print(f"  {t('prompt.hooks_config_skip')}:")
    hooks_defaults = defaults.get("hooks", {}) if defaults else {}
    bark_key = input(f"    {t('prompt.bark_key')} [{hooks_defaults.get('bark_key', '')}]: ").strip()
    if bark_key or hooks_defaults.get("bark_key"):
        if not bark_key:
            bark_key = hooks_defaults["bark_key"]
        host_label_default = hooks_defaults.get("host_label", socket.gethostname())
        sound_default = hooks_defaults.get("sound", "minuet")
        host_label = input(f"    {t('prompt.host_label')} [{host_label_default}]: ").strip() or host_label_default
        sound = input(f"    {t('prompt.notify_sound')} [{sound_default}]: ").strip() or sound_default
        result["hooks"] = {
            "bark_key": bark_key,
            "host_label": host_label,
            "sound": sound,
        }

    return result
