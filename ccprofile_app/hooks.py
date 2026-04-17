"""hooks 生成和 Bark key 脱敏。"""

import json
import shlex

from .constants import HOOK_EVENTS


def generate_hooks(hooks_config):
    """从简化配置生成完整的 Claude Code hooks 结构。"""
    bark_key = hooks_config["bark_key"]
    host = hooks_config.get("host_label", "unknown")
    sound = hooks_config.get("sound", "")

    result = {}
    for event, tpl in HOOK_EVENTS.items():
        payload = {
            "title": tpl["title"].format(host=host),
            "body": tpl["body"].format(host=host),
            "group": "ClaudeCode",
            "icon": "https://claude.ai/apple-touch-icon.png",
        }
        if event == "PermissionRequest" and sound:
            payload["sound"] = sound

        cmd = (
            f"curl -s -X POST "
            f"-H \"Content-Type: application/json\" "
            f"-d {shlex.quote(json.dumps(payload))} "
            f"https://api.day.app/{bark_key}/"
        )
        result[event] = [{"matcher": "", "hooks": [{"type": "command", "command": cmd}]}]

    return result


def mask_bark_key(key):
    """脱敏显示 Bark key，保留前4后4字符。"""
    if not key or len(key) < 8:
        return "***"
    return key[:4] + "..." + key[-4:]
