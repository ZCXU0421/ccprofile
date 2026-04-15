"""profile 字段交互输入。"""

import socket
import sys

from .constants import DISABLE_FLAGS, ENABLE_FLAGS, FIELDS, MODEL_SLOTS, PROVIDER_FIELDS
from .storage import load_providers


def prompt_profile_fields(defaults=None):
    """交互式输入配置字段。返回配置字典。"""
    defaults = defaults or {}
    env_defaults = defaults.get("env", {})
    result = {"env": {}}

    for key, label, required, default in FIELDS:
        if key in ("model", "effortLevel"):
            current = defaults.get(key)
        else:
            current = env_defaults.get(key)
        display = current or default
        hint = f" [{display}]" if display else ""
        value = input(f"  {label}{hint}: ").strip()
        if not value:
            value = display
        if required and not value:
            print(f"错误: {label} 为必填项。")
            sys.exit(1)
        if value is not None:
            if key in ("model", "effortLevel"):
                result[key] = value
            else:
                result["env"][key] = value

    print("  禁用选项 (y/n，留空使用当前值):")
    for flag, desc in DISABLE_FLAGS:
        cur = env_defaults.get(flag)
        if cur is not None:
            d = "y" if str(cur) == "1" else "n"
        else:
            d = "y"
        value = input(f"    {desc} [{d}]: ").strip().lower()
        if not value:
            value = d
        if value == "y":
            result["env"][flag] = "1"

    print("  启用选项 (y/n，留空使用当前值):")
    for flag, desc in ENABLE_FLAGS:
        cur = env_defaults.get(flag)
        if cur is not None:
            d = "y" if str(cur) == "1" else "n"
        else:
            d = "n"
        value = input(f"    {desc} [{d}]: ").strip().lower()
        if not value:
            value = d
        if value == "y":
            result["env"][flag] = "1"

    # 推送通知配置
    print("  推送通知配置 (留空跳过):")
    hooks_defaults = defaults.get("hooks", {}) if defaults else {}
    bark_key = input(f"    Bark Key [{hooks_defaults.get('bark_key', '')}]: ").strip()
    if bark_key or hooks_defaults.get("bark_key"):
        if not bark_key:
            bark_key = hooks_defaults["bark_key"]
        host_label_default = hooks_defaults.get("host_label", socket.gethostname())
        sound_default = hooks_defaults.get("sound", "minuet")
        host_label = input(f"    主机名标签 [{host_label_default}]: ").strip() or host_label_default
        sound = input(f"    通知铃声 [{sound_default}]: ").strip() or sound_default
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

    for key, label, required, default in PROVIDER_FIELDS:
        current = defaults.get(key)
        display = current or default
        hint = f" [{display}]" if display else ""
        value = input(f"  {label}{hint}: ").strip()
        if not value:
            value = display
        if required and not value:
            print(f"错误: {label} 为必填项。")
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
        print("错误: 暂无可用提供商。请先使用 'ccprofile provider add' 添加提供商。")
        sys.exit(1)

    result = {}
    model_mapping = {}

    # 显示可用提供商
    print("  可用提供商:")
    provider_list = list(providers.items())
    for idx, (name, prov) in enumerate(provider_list, 1):
        models = ", ".join(prov.get("models", []))
        print(f"    [{idx}] {name} - {models}")

    # 为每个模型槽位选择提供商和模型
    for slot in MODEL_SLOTS:
        print(f"\n  配置 {slot} 槽位:")
        default_mapping = defaults.get("model_mapping", {}).get(slot, {})
        default_provider = default_mapping.get("provider")
        default_model = default_mapping.get("model")

        # 选择提供商
        while True:
            if default_provider in providers:
                prompt_text = (
                    f"    选择提供商 (1-{len(provider_list)}，"
                    f"回车保留 {default_provider}，0 跳过): "
                )
            else:
                prompt_text = f"    选择提供商 (1-{len(provider_list)}，回车跳过): "
            prov_choice = input(prompt_text).strip()
            if not prov_choice:
                if default_provider in providers:
                    provider_name = default_provider
                    break
                print(f"    已跳过 {slot} 槽位。")
                break
            if prov_choice == "0":
                print(f"    已跳过 {slot} 槽位。")
                break
            try:
                prov_idx = int(prov_choice) - 1
                if 0 <= prov_idx < len(provider_list):
                    provider_name = provider_list[prov_idx][0]
                    break
                print(f"    错误: 请输入 1-{len(provider_list)} 之间的数字。")
            except ValueError:
                print(f"    错误: 请输入有效的数字。")

        if not prov_choice and default_provider not in providers:
            continue
        if prov_choice == "0":
            continue

        # 选择模型
        provider = providers[provider_name]
        available_models = provider.get("models", [])
        if not available_models:
            print(f"    错误: 提供商 '{provider_name}' 没有可用模型，跳过此槽位。")
            continue
        print(f"    {provider_name} 可用模型: {', '.join(available_models)}")

        # 使用默认值（如果有）
        default_model = default_model if default_provider == provider_name else None

        while True:
            model_hint = f" [{default_model}]" if default_model else ""
            model_choice = input(f"    选择模型{model_hint}，回车跳过: ").strip()
            if not model_choice and default_model:
                model_choice = default_model
            if not model_choice:
                print(f"    已跳过 {slot} 槽位。")
                break
            if model_choice:
                if model_choice in available_models:
                    model_mapping[slot] = {
                        "provider": provider_name,
                        "model": model_choice,
                    }
                    break
                print(f"    错误: 模型 '{model_choice}' 不在可用列表中。")

    if not model_mapping:
        print("错误: 混合配置至少需要配置一个模型槽位。")
        sys.exit(1)

    result["model_mapping"] = model_mapping

    # 通用配置（model、effortLevel、hooks）
    mapped_slots = [slot for slot in MODEL_SLOTS if slot in model_mapping]
    model_default = defaults.get("model", "opus")
    if model_default not in model_mapping:
        model_default = mapped_slots[0]

    slot_options = "/".join(mapped_slots)
    while True:
        model = input(f"\n  默认模型 ({slot_options}) [{model_default}]: ").strip() or model_default
        if model in model_mapping:
            result["model"] = model
            break
        print(f"  错误: 默认模型必须是已配置的槽位: {', '.join(mapped_slots)}。")

    effort_default = defaults.get("effortLevel", "high")
    effort = input(f"  努力等级 (low/medium/high) [{effort_default}]: ").strip() or effort_default
    result["effortLevel"] = effort

    # 推送通知配置（与单一模式相同）
    print("  推送通知配置 (留空跳过):")
    hooks_defaults = defaults.get("hooks", {}) if defaults else {}
    bark_key = input(f"    Bark Key [{hooks_defaults.get('bark_key', '')}]: ").strip()
    if bark_key or hooks_defaults.get("bark_key"):
        if not bark_key:
            bark_key = hooks_defaults["bark_key"]
        host_label_default = hooks_defaults.get("host_label", socket.gethostname())
        sound_default = hooks_defaults.get("sound", "minuet")
        host_label = input(f"    主机名标签 [{host_label_default}]: ").strip() or host_label_default
        sound = input(f"    通知铃声 [{sound_default}]: ").strip() or sound_default
        result["hooks"] = {
            "bark_key": bark_key,
            "host_label": host_label,
            "sound": sound,
        }

    return result
