"""Fernet 密钥管理：加载、保存、加解密。"""

import json
import os
import sys

from cryptography.fernet import Fernet, InvalidToken

from .constants import PROFILE_DIR, KEY_FILE
from .filelock import FileLock


def _init_hint():
    """返回当前环境下正确的初始化命令。"""
    if getattr(sys, 'frozen', False):
        return f"{os.path.basename(sys.executable)} init"
    return "python ccprofile.py init"


def load_key():
    """加载 Fernet 密钥。"""
    if not KEY_FILE.exists():
        print(f"错误: 未初始化。请先运行: {_init_hint()}")
        sys.exit(1)
    return KEY_FILE.read_bytes().strip()


def save_key(key):
    """保存密钥并设置隐藏属性（Windows）。"""
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    with FileLock(KEY_FILE, exclusive=True):
        KEY_FILE.write_bytes(key)
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.kernel32.SetFileAttributesW(str(KEY_FILE), 0x2)
    try:
        os.chmod(str(KEY_FILE), 0o600)
    except OSError:
        pass


def encrypt_data(data, key):
    """将字典加密为字节。"""
    return Fernet(key).encrypt(json.dumps(data).encode())


def decrypt_data(raw, key):
    """将加密字节解密为字典。"""
    try:
        return json.loads(Fernet(key).decrypt(raw).decode())
    except InvalidToken:
        print("错误: 解密失败，密钥可能不匹配或数据已损坏。请尝试重新初始化。")
        sys.exit(1)
