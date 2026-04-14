"""profiles / meta / settings 文件读写和备份。"""

import json
import shutil

from .constants import (
    CLAUDE_DIR,
    META_FILE,
    PROFILES_ENC,
    SETTINGS_BAK,
    SETTINGS_FILE,
)
from .crypto import decrypt_data, encrypt_data, load_key


def load_profiles():
    """加载并解密所有配置。"""
    key = load_key()
    if not PROFILES_ENC.exists():
        return {}
    return decrypt_data(PROFILES_ENC.read_bytes(), key)


def save_profiles(profiles):
    """加密并保存所有配置。"""
    key = load_key()
    CLAUDE_DIR.mkdir(parents=True, exist_ok=True)
    PROFILES_ENC.write_bytes(encrypt_data(profiles, key))


def load_meta():
    """加载元数据。"""
    if not META_FILE.exists():
        return {}
    return json.loads(META_FILE.read_text("utf-8"))


def save_meta(meta):
    """保存元数据。"""
    CLAUDE_DIR.mkdir(parents=True, exist_ok=True)
    META_FILE.write_text(json.dumps(meta, indent=2, ensure_ascii=False), "utf-8")


def backup_settings():
    """备份 settings.json。"""
    if SETTINGS_FILE.exists():
        shutil.copy2(str(SETTINGS_FILE), str(SETTINGS_BAK))


def read_settings():
    """读取 settings.json。"""
    if not SETTINGS_FILE.exists():
        return {}
    return json.loads(SETTINGS_FILE.read_text("utf-8"))


def write_settings(data):
    """写入 settings.json。"""
    CLAUDE_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", "utf-8"
    )
