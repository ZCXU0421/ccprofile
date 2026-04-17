"""profiles / meta / settings 文件读写和备份。"""

import json
import os
import shutil
import stat
import tempfile

from .constants import (
    CLAUDE_DIR,
    KEY_FILE,
    META_FILE,
    PROFILE_DIR,
    PROFILES_ENC,
    PROVIDERS_ENC,
    PROXY_CONFIG,
    SETTINGS_BAK,
    SETTINGS_FILE,
)
from .crypto import decrypt_data, encrypt_data, load_key
from .filelock import FileLock


def atomic_write_bytes(path, data, mode=None):
    """原子写入字节数据：先写临时文件，再 replace。"""
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        if mode is not None and hasattr(os, "fchmod"):
            os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        if mode is not None:
            os.chmod(tmp_name, mode)
        os.replace(tmp_name, str(path))
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def atomic_write_text(path, content, encoding="utf-8", mode=None):
    """原子写入文本数据：先写临时文件，再 replace。"""
    atomic_write_bytes(path, content.encode(encoding), mode=mode)


# Legacy paths (pre-migration, stored under ~/.claude/)
_LEGACY_KEY_FILE = CLAUDE_DIR / ".profile_key"
_LEGACY_PROFILES_ENC = CLAUDE_DIR / "profiles.enc"
_LEGACY_META_FILE = CLAUDE_DIR / "profiles_meta.json"
_LEGACY_FILES = [
    (_LEGACY_KEY_FILE, KEY_FILE),
    (_LEGACY_PROFILES_ENC, PROFILES_ENC),
    (_LEGACY_META_FILE, META_FILE),
]


def migrate_from_legacy():
    """如果旧配置文件在 ~/.claude/ 下，逐项迁移到 ~/.ccprofile/。"""
    moved = []
    for src, dst in _LEGACY_FILES:
        if src.exists() and not dst.exists():
            if not PROFILE_DIR.exists():
                PROFILE_DIR.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            moved.append(src.name)

    if moved:
        print(f"已将旧配置迁移到 {PROFILE_DIR}：{', '.join(moved)}")
    return bool(moved)


def load_profiles():
    """加载并解密所有配置。"""
    key = load_key()
    if not PROFILES_ENC.exists():
        return {}
    with FileLock(PROFILES_ENC, exclusive=False):
        return decrypt_data(PROFILES_ENC.read_bytes(), key)


def save_profiles(profiles):
    """加密并保存所有配置。"""
    key = load_key()
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    encrypted = encrypt_data(profiles, key)
    with FileLock(PROFILES_ENC, exclusive=True):
        atomic_write_bytes(PROFILES_ENC, encrypted)


def load_meta():
    """加载元数据。"""
    if not META_FILE.exists():
        return {}
    with FileLock(META_FILE, exclusive=False):
        return json.loads(META_FILE.read_text("utf-8"))


def save_meta(meta):
    """保存元数据。"""
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    content = json.dumps(meta, indent=2, ensure_ascii=False)
    with FileLock(META_FILE, exclusive=True):
        atomic_write_text(META_FILE, content, "utf-8")


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
    content = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    with FileLock(SETTINGS_FILE, exclusive=True):
        atomic_write_text(SETTINGS_FILE, content, "utf-8")


# ── Provider storage ──


def load_providers():
    """加载并解密所有提供商配置。"""
    key = load_key()
    if not PROVIDERS_ENC.exists():
        return {}
    with FileLock(PROVIDERS_ENC, exclusive=False):
        return decrypt_data(PROVIDERS_ENC.read_bytes(), key)


def save_providers(providers):
    """加密并保存所有提供商配置。"""
    key = load_key()
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    encrypted = encrypt_data(providers, key)
    with FileLock(PROVIDERS_ENC, exclusive=True):
        atomic_write_bytes(PROVIDERS_ENC, encrypted)


# ── Proxy config ──


def load_proxy_config():
    """加载代理运行时配置。"""
    if not PROXY_CONFIG.exists():
        return None
    return json.loads(PROXY_CONFIG.read_text("utf-8"))


def save_proxy_config(config):
    """保存代理运行时配置（包含明文 API key，需限制权限）。"""
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    content = json.dumps(config, indent=2, ensure_ascii=False) + "\n"
    with FileLock(PROXY_CONFIG, exclusive=True):
        atomic_write_text(
            PROXY_CONFIG,
            content,
            "utf-8",
            mode=stat.S_IRUSR | stat.S_IWUSR,
        )


def clear_proxy_config():
    """清除代理运行时配置。"""
    if PROXY_CONFIG.exists():
        PROXY_CONFIG.unlink()
