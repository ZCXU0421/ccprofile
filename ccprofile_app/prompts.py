"""profile 字段交互输入。"""

import socket
import sys

from .constants import DISABLE_FLAGS, ENABLE_FLAGS, FIELDS


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
