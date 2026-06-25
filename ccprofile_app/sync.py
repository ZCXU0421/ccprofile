"""WebDAV 同步核心逻辑。"""

import base64
import getpass
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from .constants import (
    KEY_FILE,
    PROFILE_DIR,
    PROFILES_ENC,
    PROVIDERS_ENC,
    SYNC_CONFIG_FILE,
    SYNC_SNAPSHOT_DIR,
    SYNC_SNAPSHOT_PROFILES,
    SYNC_SNAPSHOT_PROVIDERS,
)
from .crypto import encrypt_data, load_key
from .display import panel, kv, GREEN, RED, DIM, RESET, YELLOW, BOLD
from .filelock import FileLock
from .i18n import t
from .storage import (
    atomic_write_bytes,
    atomic_write_text,
    load_profiles,
    load_providers,
    save_profiles,
    save_providers,
)
from .terminal import select_from_list, confirm_action
from .webdav import (
    WebDAVClient,
    WebDAVAuthError,
    WebDAVConnectionError,
    WebDAVError,
    WebDAVNotFoundError,
    WebDAVServerError,
)

# ── Constants ────────────────────────────────────────────────────────────────

# 远端文件名沿用本地密文文件名，便于跨设备识别对应载荷。
REMOTE_SYNC_META_FILE = "sync_meta.json"
REMOTE_PROFILES_FILE = "profiles.enc"
REMOTE_PROVIDERS_FILE = "providers.enc"
REMOTE_SALT_FILE = "salt.bin"

_MISSING = object()

# ── Helper functions ──────────────────────────────────────────────────────────


class SyncConfigError(Exception):
    """同步配置损坏或不可读取。"""


class SyncConfigPasswordUnavailableError(SyncConfigError):
    """同步配置中的 WebDAV 密码无法用当前本地密钥解密。"""


class SyncLocalKeyError(Exception):
    """本地加密密钥不可用。"""


def _derive_sync_key(passphrase: str, salt: bytes) -> bytes:
    """PBKDF2HMAC 派生同步密钥。"""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=600_000,
    )
    raw_key = kdf.derive(passphrase.encode("utf-8"))
    return base64.urlsafe_b64encode(raw_key)


def _generate_salt() -> bytes:
    """生成随机盐值。"""
    return os.urandom(16)


def _re_encrypt(encrypted_data: bytes, old_key: bytes, new_key: bytes) -> bytes:
    """用新密钥重新加密数据。"""
    plaintext = Fernet(old_key).decrypt(encrypted_data)
    return Fernet(new_key).encrypt(plaintext)


def _compute_digest(data: bytes) -> str:
    """计算数据内容摘要。"""
    return hashlib.sha256(data).hexdigest()


def _get_sync_config() -> Optional[dict]:
    """读取并解密同步配置。"""
    if not SYNC_CONFIG_FILE.exists():
        return None

    try:
        with FileLock(SYNC_CONFIG_FILE, exclusive=False):
            with open(SYNC_CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        raise SyncConfigError(t("sync.error_config_invalid")) from exc

    try:
        if "password_encrypted" in config:
            enc_bytes = base64.b64decode(config["password_encrypted"])
            try:
                key = load_key()
            except Exception as exc:
                raise SyncConfigPasswordUnavailableError(
                    t("sync.error_config_password_unreadable")
                ) from exc

            try:
                decrypted = json.loads(Fernet(key).decrypt(enc_bytes).decode("utf-8"))
            except (InvalidToken, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise SyncConfigPasswordUnavailableError(
                    t("sync.error_config_password_unreadable")
                ) from exc
            config["password"] = decrypted.get("p", "")
    except (ValueError, TypeError) as exc:
        raise SyncConfigError(t("sync.error_config_invalid")) from exc

    return config


def _load_sync_config_or_exit() -> dict:
    """读取同步配置，不可用时直接给出用户友好错误。"""
    try:
        config = _get_sync_config()
    except SyncConfigError as exc:
        print(f"  {RED}{exc}{RESET}")
        sys.exit(1)

    if not config:
        print(t("sync.error_no_config"))
        sys.exit(1)

    return config


def _save_sync_config(config: dict) -> None:
    """保存同步配置（密码加密存储）。"""
    config_to_save = dict(config)
    password = config_to_save.pop("password", "")
    if password:
        enc_bytes = encrypt_data({"p": password}, _load_local_key())
        config_to_save["password_encrypted"] = base64.b64encode(enc_bytes).decode()
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    with FileLock(SYNC_CONFIG_FILE, exclusive=True):
        atomic_write_text(
            SYNC_CONFIG_FILE,
            json.dumps(config_to_save, indent=2, ensure_ascii=False),
            mode=0o600,
        )


def _save_snapshot(profiles: dict, providers: dict) -> None:
    """保存本地快照。"""
    SYNC_SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    key = _load_local_key()
    atomic_write_bytes(
        SYNC_SNAPSHOT_PROFILES,
        Fernet(key).encrypt(json.dumps(profiles, sort_keys=True).encode("utf-8")),
        mode=0o600,
    )
    atomic_write_bytes(
        SYNC_SNAPSHOT_PROVIDERS,
        Fernet(key).encrypt(json.dumps(providers, sort_keys=True).encode("utf-8")),
        mode=0o600,
    )


def _load_snapshot() -> tuple[dict, dict]:
    """加载本地快照。"""
    profiles = {}
    providers = {}
    cipher = None
    if SYNC_SNAPSHOT_PROFILES.exists() or SYNC_SNAPSHOT_PROVIDERS.exists():
        cipher = Fernet(_load_local_key())
    if SYNC_SNAPSHOT_PROFILES.exists():
        raw = SYNC_SNAPSHOT_PROFILES.read_bytes()
        profiles = _load_snapshot_file(raw, cipher)
    if SYNC_SNAPSHOT_PROVIDERS.exists():
        raw = SYNC_SNAPSHOT_PROVIDERS.read_bytes()
        providers = _load_snapshot_file(raw, cipher)
    return profiles, providers


def _load_snapshot_file(raw: bytes, cipher: Optional[Fernet] = None) -> dict:
    """加载单个快照文件，兼容旧版明文快照。"""
    if not raw:
        return {}

    try:
        if cipher is None:
            cipher = Fernet(load_key())
        decrypted = cipher.decrypt(raw)
    except InvalidToken:
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            print(f"  {YELLOW}{t('sync.warning_snapshot_invalid')}{RESET}")
            return {}
    return json.loads(decrypted.decode("utf-8"))


def _load_local_key() -> bytes:
    """读取本地加密密钥，失败时抛出 SyncLocalKeyError。"""
    try:
        return load_key()
    except Exception as exc:
        raise SyncLocalKeyError(t("sync.error_local_key_unavailable") + f": {exc}") from exc


def _update_sync_state(config: dict, profiles_md5: str, providers_md5: str) -> None:
    """仅在同步成功后更新本地同步状态。"""
    # 兼容旧字段名，同时将内容摘要升级为 SHA-256。
    config["remote_profiles_hash"] = profiles_md5
    config["remote_providers_hash"] = providers_md5
    config["remote_profiles_md5"] = profiles_md5
    config["remote_providers_md5"] = providers_md5
    config["last_sync"] = datetime.now(timezone.utc).isoformat()
    config["_local_dirty"] = False
    _save_sync_config(config)


def _verify_remote_sync_key(client, config, sync_key) -> bool:
    """在覆盖远端前校验 sync_key 是否可解密现有远端数据。"""
    try:
        remote_profiles_enc, remote_providers_enc = _download_remote_payloads(
            client,
            config["remote_dir"],
        )
    except WebDAVError as e:
        print(f"  {RED}{t('sync.error_download')}{RESET}: {e}")
        return False

    if not remote_profiles_enc and not remote_providers_enc:
        return True

    try:
        if remote_profiles_enc:
            json.loads(Fernet(sync_key).decrypt(remote_profiles_enc).decode())
        if remote_providers_enc:
            json.loads(Fernet(sync_key).decrypt(remote_providers_enc).decode())
    except InvalidToken:
        print(f"  {RED}{t('sync.error_sync_key_invalid')}{RESET}")
        return False

    return True


def _download_remote_payloads(client, remote_dir: str) -> tuple[bytes, bytes]:
    """下载远端 profiles/providers 文件；缺失文件按空数据处理。"""
    try:
        remote_profiles_enc = client.download(f"{remote_dir}/{REMOTE_PROFILES_FILE}")
    except WebDAVNotFoundError:
        remote_profiles_enc = b""

    try:
        remote_providers_enc = client.download(f"{remote_dir}/{REMOTE_PROVIDERS_FILE}")
    except WebDAVNotFoundError:
        remote_providers_enc = b""

    return remote_profiles_enc, remote_providers_enc


def _sync_mark_dirty():
    """标记本地数据已变更。可安全地从任意模块调用。"""
    try:
        config = _get_sync_config()
    except SyncConfigError:
        return
    if not config:
        return
    config["_local_dirty"] = True
    _save_sync_config(config)


def _upload_sync_meta(client, remote_dir, profiles_md5, providers_md5, device_name):
    """上传同步元数据。"""
    meta = {
        "device": device_name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "profiles_hash": profiles_md5,
        "providers_hash": providers_md5,
        "profiles_md5": profiles_md5,
        "providers_md5": providers_md5,
    }
    client.upload(
        f"{remote_dir}/{REMOTE_SYNC_META_FILE}",
        json.dumps(meta, sort_keys=True, indent=2, ensure_ascii=False).encode(),
    )


def _download_sync_meta(client, remote_dir) -> Optional[dict]:
    """下载同步元数据。"""
    try:
        data = client.download(f"{remote_dir}/{REMOTE_SYNC_META_FILE}")
        return json.loads(data)
    except WebDAVNotFoundError:
        return None


def _get_meta_digest(meta: Optional[dict], key: str) -> Optional[str]:
    """兼容旧 sync_meta 字段。"""
    if not meta:
        return None
    return meta.get(f"{key}_hash") or meta.get(f"{key}_md5")


def _get_stored_remote_digest(config: dict, key: str) -> Optional[str]:
    """兼容旧本地配置字段。"""
    return config.get(f"remote_{key}_hash") or config.get(f"remote_{key}_md5")


def _detect_sync_action(snapshot_profiles, snapshot_providers, current_profiles, current_providers,
                         remote_meta, stored_remote_profiles_md5, stored_remote_providers_md5):
    """检测同步动作。"""
    local_profiles_md5 = _compute_digest(json.dumps(current_profiles, sort_keys=True).encode())
    local_providers_md5 = _compute_digest(json.dumps(current_providers, sort_keys=True).encode())

    snapshot_profiles_md5 = _compute_digest(json.dumps(snapshot_profiles, sort_keys=True).encode())
    snapshot_providers_md5 = _compute_digest(json.dumps(snapshot_providers, sort_keys=True).encode())

    local_changed = (
        local_profiles_md5 != snapshot_profiles_md5
        or local_providers_md5 != snapshot_providers_md5
    )

    # 远端无 sync_meta 意味着远端从未被同步过
    if remote_meta is None:
        has_local = bool(current_profiles or current_providers)
        return "push" if has_local else "up-to-date"

    remote_changed = (
        _get_meta_digest(remote_meta, "profiles") != stored_remote_profiles_md5
        or _get_meta_digest(remote_meta, "providers") != stored_remote_providers_md5
    )

    if not local_changed and not remote_changed:
        return "up-to-date"
    if local_changed and not remote_changed:
        return "push"
    if not local_changed and remote_changed:
        return "pull"
    return "conflict"


def _merge_data(local, remote, base, device_name):
    """三方合并算法，处理新增/修改/冲突。"""
    merged = {}
    warnings = []

    all_keys = set(local.keys()) | set(remote.keys())
    for key in all_keys:
        local_val = local.get(key, _MISSING)
        remote_val = remote.get(key, _MISSING)
        base_val = base.get(key, _MISSING)

        if local_val == base_val and remote_val == base_val:
            if base_val is not _MISSING:
                merged[key] = base_val
        elif local_val == base_val:
            if remote_val is not _MISSING:
                merged[key] = remote_val
        elif remote_val == base_val:
            if local_val is not _MISSING:
                merged[key] = local_val
        else:
            if local_val == remote_val:
                if local_val is not _MISSING:
                    merged[key] = local_val
            else:
                if remote_val is not _MISSING:
                    merged[key] = remote_val
                if local_val is not _MISSING:
                    suffix = device_name
                    new_key = f"{key} ({suffix})"
                    counter = 1
                    while new_key in merged:
                        suffix = f"{device_name}-{counter}"
                        new_key = f"{key} ({suffix})"
                        counter += 1
                    merged[new_key] = local_val
                    warnings.append(
                        t(
                            "sync.conflict_key_remote_kept",
                            conflict_key=key,
                            duplicate_key=new_key,
                        )
                    )

    return merged, warnings


# ── CLI commands ─────────────────────────────────────────────────────────────


def _test_sync_connection(webdav_url: str, username: str, password: str, verify_ssl: bool):
    """测试 WebDAV 连接并返回可复用的 client。"""
    print()
    print(f"  {t('sync.testing_connection')}...")
    last_error = None
    for attempt in range(3):
        try:
            client = WebDAVClient(webdav_url, username, password, verify_ssl=verify_ssl)
            if client.test_connection():
                print(f"  {GREEN}{t('sync.test_connection_ok')}{RESET}")
                return client
            last_error = t("sync.error_connection")
        except WebDAVConnectionError as exc:
            last_error = str(exc)
        except WebDAVAuthError:
            last_error = t("sync.error_auth")
        except WebDAVError as exc:
            last_error = str(exc)
        if attempt < 2:
            print(f"  {t('sync.retry_attempt', n=attempt + 1)}: {last_error}")

    print(f"  {RED}{t('sync.error_connection_failed')}{RESET}: {last_error}")
    sys.exit(1)


def _prompt_sync_connection_inputs() -> Optional[dict]:
    """读取 WebDAV 连接信息和设备标识。"""
    import socket

    webdav_url = input(f"  {t('sync.prompt_url')}: ").strip()
    if not webdav_url:
        print(f"  {t('cmd.canceled')}")
        return None
    if webdav_url.startswith("http://"):
        print(f"  {YELLOW}{t('sync.error_http_warning')}{RESET}")

    username = input(f"  {t('sync.prompt_username')}: ").strip()
    if not username:
        print(f"  {t('cmd.canceled')}")
        return None

    password = getpass.getpass(f"  {t('sync.prompt_password')}: ").strip()
    if not password:
        print(f"  {t('cmd.canceled')}")
        return None

    remote_dir = input(f"  {t('sync.prompt_remote_dir')} [{t('sync.default_remote_dir')}]: ").strip()
    if not remote_dir:
        remote_dir = "ccprofile"
    # 规范化：去除前导 ./ 和首尾 /
    while remote_dir.startswith("./"):
        remote_dir = remote_dir[2:]
    remote_dir = remote_dir.strip("/")

    default_device_name = socket.gethostname()
    device_name = input(
        f"  {t('sync.prompt_device_name')} [{default_device_name}]: "
    ).strip()
    if not device_name:
        device_name = default_device_name

    return {
        "webdav_url": webdav_url,
        "username": username,
        "password": password,
        "remote_dir": remote_dir,
        "device_name": device_name,
    }


def _connect_sync_client_or_exit(connection_info: dict, verify_ssl: bool):
    """建立并校验 WebDAV client。"""
    client = _test_sync_connection(
        connection_info["webdav_url"],
        connection_info["username"],
        connection_info["password"],
        verify_ssl,
    )
    try:
        client.ensure_directory(connection_info["remote_dir"])
    except WebDAVError as exc:
        print(f"  {RED}{t('sync.error_ensure_dir')}{RESET}: {exc}")
        sys.exit(1)
    return client


def _prompt_sync_password() -> str:
    """读取并确认同步密码。"""
    print()
    print(f"  {DIM}{t('sync.prompt_sync_password_intro')}{RESET}")
    while True:
        sync_password = getpass.getpass(f"  {t('sync.prompt_sync_password')}: ").strip()
        if not sync_password:
            print(f"  {t('cmd.canceled')}")
            return ""
        sync_password_confirm = getpass.getpass(
            f"  {t('sync.prompt_sync_password_confirm')}: "
        ).strip()
        if sync_password == sync_password_confirm:
            return sync_password
        print(f"  {RED}{t('sync.error_password_mismatch')}{RESET}")


def _select_sync_strategy() -> Optional[str]:
    """选择冲突解决策略。"""
    strategy = select_from_list(
        [
            ("merge", t("sync.strategy_merge")),
            ("local-wins", t("sync.strategy_local")),
            ("remote-wins", t("sync.strategy_remote")),
        ],
        t("sync.prompt_strategy"),
        default_index=0,
    )
    if strategy is None:
        print(f"  {t('cmd.canceled')}")
    return strategy


def _rotate_remote_salt_if_needed(client, remote_dir: str, sync_password: str, device_name: str):
    """如远端已有数据，验证旧密码并轮换 salt。"""
    remote_salt = None
    salt_uploaded = False

    try:
        remote_salt = client.download(f"{remote_dir}/{REMOTE_SALT_FILE}")
        remote_profiles_enc, remote_providers_enc = _download_remote_payloads(client, remote_dir)
    except WebDAVNotFoundError:
        return _generate_salt(), salt_uploaded, remote_salt
    except WebDAVError as exc:
        print(f"  {RED}{t('sync.error_download')}{RESET}: {exc}")
        sys.exit(1)

    if not remote_profiles_enc and not remote_providers_enc:
        return _generate_salt(), salt_uploaded, remote_salt

    print(f"  {DIM}{t('sync.rotate_remote_salt')}{RESET}")
    current_sync_password = getpass.getpass(
        f"  {t('sync.prompt_current_sync_password')}: "
    ).strip()
    if not current_sync_password:
        print(f"  {t('cmd.canceled')}")
        return None, salt_uploaded, remote_salt

    old_sync_key = _derive_sync_key(current_sync_password, remote_salt)
    salt = _generate_salt()
    new_sync_key = _derive_sync_key(sync_password, salt)

    try:
        rotated_profiles_enc = (
            _re_encrypt(remote_profiles_enc, old_sync_key, new_sync_key)
            if remote_profiles_enc else b""
        )
        rotated_providers_enc = (
            _re_encrypt(remote_providers_enc, old_sync_key, new_sync_key)
            if remote_providers_enc else b""
        )
    except InvalidToken:
        print(f"  {RED}{t('sync.error_sync_key_invalid')}{RESET}")
        sys.exit(1)

    try:
        _upload_payload_with_backup(
            client,
            f"{remote_dir}/{REMOTE_PROFILES_FILE}",
            rotated_profiles_enc,
        )
        _upload_payload_with_backup(
            client,
            f"{remote_dir}/{REMOTE_PROVIDERS_FILE}",
            rotated_providers_enc,
        )
        _upload_payload_with_backup(
            client,
            f"{remote_dir}/{REMOTE_SALT_FILE}",
            salt,
        )
        _upload_sync_meta(
            client,
            remote_dir,
            _compute_digest(rotated_profiles_enc),
            _compute_digest(rotated_providers_enc),
            device_name,
        )
    except WebDAVError as exc:
        print(f"  {RED}{t('sync.error_upload')}{RESET}: {exc}")
        sys.exit(1)

    return salt, True, remote_salt


def _save_sync_setup(config: dict) -> None:
    """保存同步配置和初始快照。"""
    _save_sync_config(config)
    _save_snapshot(load_profiles(), load_providers())


def _build_sync_config(connection_info: dict, verify_ssl: bool, strategy: str, salt: bytes) -> dict:
    """构造待保存的同步配置。"""
    return {
        "webdav_url": connection_info["webdav_url"],
        "username": connection_info["username"],
        "password": connection_info["password"],
        "remote_dir": connection_info["remote_dir"],
        "device_name": connection_info["device_name"],
        "verify_ssl": verify_ssl,
        "strategy": strategy,
        "salt": base64.b64encode(salt).decode(),
        "_local_dirty": False,
        "last_sync": None,
    }


def cmd_sync_config(args):
    """交互式配置 WebDAV 同步。"""
    if not KEY_FILE.exists():
        print(t("sync.error_not_initialized"))
        sys.exit(1)

    print(panel(t("sync.config_title"), "", []))
    print()

    connection_info = _prompt_sync_connection_inputs()
    if connection_info is None:
        return

    # SSL 验证
    verify_ssl = not confirm_action(t("sync.prompt_no_ssl"), default_yes=False)
    client = _connect_sync_client_or_exit(connection_info, verify_ssl)

    sync_password = _prompt_sync_password()
    if not sync_password:
        return

    strategy = _select_sync_strategy()
    if strategy is None:
        return

    salt, salt_uploaded, remote_salt = _rotate_remote_salt_if_needed(
        client,
        connection_info["remote_dir"],
        sync_password,
        connection_info["device_name"],
    )
    if salt is None:
        return

    config = _build_sync_config(connection_info, verify_ssl, strategy, salt)
    _save_sync_setup(config)

    if not salt_uploaded and (remote_salt is None or remote_salt != salt):
        try:
            _upload_payload_with_backup(
                client,
                f"{connection_info['remote_dir']}/{REMOTE_SALT_FILE}",
                salt,
            )
        except WebDAVError as exc:
            print(f"  {YELLOW}{t('sync.error_upload_salt')}{RESET}: {exc}")
            print(f"  {DIM}{t('sync.config_saved_no_salt')}{RESET}")

    print()
    print(f"  {GREEN}{t('sync.config_saved')}{RESET}")


def cmd_sync_auto(args):
    """自动同步：检测变更并决定 push/pull/conflict。"""
    config = _load_sync_config_or_exit()

    sync_password = getpass.getpass(f"  {t('sync.prompt_sync_password')}: ").strip()
    if not sync_password:
        print(f"  {t('cmd.canceled')}")
        return

    salt = base64.b64decode(config["salt"])
    sync_key = _derive_sync_key(sync_password, salt)

    try:
        client = WebDAVClient(
            config["webdav_url"],
            config["username"],
            config["password"],
            verify_ssl=config.get("verify_ssl", True),
        )
    except WebDAVError as e:
        print(f"  {RED}{t('sync.error_connection')}{RESET}: {e}")
        sys.exit(1)

    current_profiles = load_profiles()
    current_providers = load_providers()
    try:
        snapshot_profiles, snapshot_providers = _load_snapshot()
    except SyncLocalKeyError as exc:
        print(f"  {RED}{exc}{RESET}")
        return

    remote_meta = _download_sync_meta(client, config["remote_dir"])

    action = _detect_sync_action(
        snapshot_profiles, snapshot_providers,
        current_profiles, current_providers,
        remote_meta,
        _get_stored_remote_digest(config, "profiles"),
        _get_stored_remote_digest(config, "providers"),
    )

    if action == "up-to-date":
        print(f"  {GREEN}{t('sync.already_up_to_date')}{RESET}")
        return

    strategy = config.get("strategy", "merge")

    if action == "push":
        print(t("sync.auto_push_intro"))
        try:
            new_remote_profiles_md5, new_remote_providers_md5 = _do_push(
                client, config, sync_key, current_profiles, current_providers
            )
        except WebDAVError as exc:
            print(f"  {RED}{t('sync.error_upload')}{RESET}: {exc}")
            return
        if new_remote_profiles_md5 is None or new_remote_providers_md5 is None:
            return
        _update_sync_state(config, new_remote_profiles_md5, new_remote_providers_md5)
        print(f"  {GREEN}{t('sync.push_done')}{RESET}")

    elif action == "pull":
        print(t("sync.auto_pull_intro"))
        try:
            new_remote_profiles_md5, new_remote_providers_md5 = _do_pull(
                client, config, sync_key, remote_meta
            )
        except WebDAVError as exc:
            print(f"  {RED}{t('sync.error_download')}{RESET}: {exc}")
            return
        if new_remote_profiles_md5 is None or new_remote_providers_md5 is None:
            return
        _update_sync_state(config, new_remote_profiles_md5, new_remote_providers_md5)
        print(f"  {GREEN}{t('sync.pull_done')}{RESET}")

    else:  # conflict
        print(f"  {YELLOW}{t('sync.conflict_detected')}{RESET}")
        print(t("sync.conflict_strategy", strategy=strategy))
        if strategy == "local-wins":
            print(t("sync.conflict_local_wins"))
            try:
                new_remote_profiles_md5, new_remote_providers_md5 = _do_push(
                    client, config, sync_key, current_profiles, current_providers
                )
            except WebDAVError as exc:
                print(f"  {RED}{t('sync.error_upload')}{RESET}: {exc}")
                return
            if new_remote_profiles_md5 is None or new_remote_providers_md5 is None:
                return
            _update_sync_state(config, new_remote_profiles_md5, new_remote_providers_md5)
            print(f"  {GREEN}{t('sync.push_done')}{RESET}")
        elif strategy == "remote-wins":
            print(t("sync.conflict_remote_wins"))
            try:
                new_remote_profiles_md5, new_remote_providers_md5 = _do_pull(
                    client, config, sync_key, remote_meta
                )
            except WebDAVError as exc:
                print(f"  {RED}{t('sync.error_download')}{RESET}: {exc}")
                return
            if new_remote_profiles_md5 is None or new_remote_providers_md5 is None:
                return
            _update_sync_state(config, new_remote_profiles_md5, new_remote_providers_md5)
            print(f"  {GREEN}{t('sync.pull_done')}{RESET}")
        else:  # merge
            print(t("sync.conflict_merge"))
            try:
                new_remote_profiles_md5, new_remote_providers_md5 = _do_merge(
                    client, config, sync_key, snapshot_profiles, snapshot_providers,
                    current_profiles, current_providers
                )
            except WebDAVError as exc:
                print(f"  {RED}{t('sync.error_upload')}{RESET}: {exc}")
                return
            if new_remote_profiles_md5 is None or new_remote_providers_md5 is None:
                return
            _update_sync_state(config, new_remote_profiles_md5, new_remote_providers_md5)


def _do_push(client, config, sync_key, current_profiles, current_providers):
    """执行 push 操作。返回 (remote_profiles_md5, remote_providers_md5)。"""
    if not _verify_remote_sync_key(client, config, sync_key):
        return None, None

    try:
        local_key = _load_local_key()
    except SyncLocalKeyError as exc:
        print(f"  {RED}{exc}{RESET}")
        return None, None
    remote_profiles_enc = _build_remote_encrypted_payload(PROFILES_ENC, local_key, sync_key)
    remote_providers_enc = _build_remote_encrypted_payload(PROVIDERS_ENC, local_key, sync_key)

    _upload_payload_with_backup(
        client,
        f"{config['remote_dir']}/{REMOTE_PROFILES_FILE}",
        remote_profiles_enc,
    )
    _upload_payload_with_backup(
        client,
        f"{config['remote_dir']}/{REMOTE_PROVIDERS_FILE}",
        remote_providers_enc,
    )

    profiles_md5 = _compute_digest(remote_profiles_enc)
    providers_md5 = _compute_digest(remote_providers_enc)
    _upload_sync_meta(client, config["remote_dir"], profiles_md5, providers_md5, config["device_name"])

    _save_snapshot(current_profiles, current_providers)

    return profiles_md5, providers_md5


def _build_remote_encrypted_payload(local_file: Path, local_key: bytes, sync_key: bytes) -> bytes:
    """将本地密文文件转换为远端同步密文；空数据统一编码为加密的空对象。"""
    try:
        encrypted_data = local_file.read_bytes()
    except FileNotFoundError:
        encrypted_data = b""

    if not encrypted_data:
        return Fernet(sync_key).encrypt(b"{}")
    try:
        return _re_encrypt(encrypted_data, local_key, sync_key)
    except InvalidToken as exc:
        raise SyncConfigError(
            t("sync.error_local_key_unavailable")
        ) from exc


def _upload_payload_with_backup(client, remote_path: str, data: bytes,
                                content_type: str = "application/octet-stream") -> None:
    """覆盖远端文件前保留一份 .bak。"""
    try:
        existing = client.download(remote_path)
    except WebDAVError:
        existing = None

    if existing is not None:
        client.upload(f"{remote_path}.bak", existing, content_type=content_type)

    client.upload(remote_path, data, content_type=content_type)


def _do_pull(client, config, sync_key, remote_meta):
    """执行 pull 操作。返回 (remote_profiles_md5, remote_providers_md5)。"""
    try:
        remote_profiles_enc, remote_providers_enc = _download_remote_payloads(
            client,
            config["remote_dir"],
        )
    except WebDAVError:
        return None, None

    if not remote_profiles_enc and not remote_providers_enc:
        return None, None

    try:
        decrypted_profiles = Fernet(sync_key).decrypt(remote_profiles_enc).decode() if remote_profiles_enc else "{}"
        decrypted_providers = Fernet(sync_key).decrypt(remote_providers_enc).decode() if remote_providers_enc else "{}"
    except InvalidToken:
        print(f"  {RED}{t('sync.error_sync_key_invalid')}{RESET}")
        return None, None

    try:
        pulled_profiles = json.loads(decrypted_profiles)
        pulled_providers = json.loads(decrypted_providers)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        print(f"  {RED}{t('sync.error_download')}{RESET}: {exc}")
        return None, None

    old_profiles = load_profiles()
    old_providers = load_providers()

    try:
        save_profiles(pulled_profiles)
        save_providers(pulled_providers)
    except Exception:
        save_profiles(old_profiles)
        save_providers(old_providers)
        raise

    try:
        _save_snapshot(pulled_profiles, pulled_providers)
    except SyncLocalKeyError as exc:
        print(f"  {RED}{exc}{RESET}")
        return None, None

    new_profiles_md5 = _get_meta_digest(remote_meta, "profiles") if remote_meta else _compute_digest(remote_profiles_enc)
    new_providers_md5 = _get_meta_digest(remote_meta, "providers") if remote_meta else _compute_digest(remote_providers_enc)
    return new_profiles_md5, new_providers_md5


def _do_merge(client, config, sync_key, snapshot_profiles, snapshot_providers,
              current_profiles, current_providers):
    """执行合并操作。返回 (remote_profiles_md5, remote_providers_md5)。"""
    try:
        remote_profiles_enc, remote_providers_enc = _download_remote_payloads(
            client,
            config["remote_dir"],
        )
    except WebDAVError:
        return None, None

    if not remote_profiles_enc and not remote_providers_enc:
        print(f"  {RED}{t('sync.error_no_remote_data')}{RESET}")
        return None, None

    try:
        decrypted_profiles = Fernet(sync_key).decrypt(remote_profiles_enc).decode() if remote_profiles_enc else "{}"
        decrypted_providers = Fernet(sync_key).decrypt(remote_providers_enc).decode() if remote_providers_enc else "{}"
    except InvalidToken:
        print(f"  {RED}{t('sync.error_sync_key_invalid')}{RESET}")
        return None, None

    try:
        remote_profiles = json.loads(decrypted_profiles)
        remote_providers = json.loads(decrypted_providers)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        print(f"  {RED}{t('sync.error_download')}{RESET}: {exc}")
        return None, None

    merged_profiles, profile_warnings = _merge_data(
        current_profiles, remote_profiles, snapshot_profiles, config["device_name"]
    )
    merged_providers, provider_warnings = _merge_data(
        current_providers, remote_providers, snapshot_providers, config["device_name"]
    )

    remote_merged_profiles_enc = Fernet(sync_key).encrypt(json.dumps(merged_profiles, sort_keys=True).encode())
    remote_merged_providers_enc = Fernet(sync_key).encrypt(json.dumps(merged_providers, sort_keys=True).encode())

    _upload_payload_with_backup(
        client,
        f"{config['remote_dir']}/{REMOTE_PROFILES_FILE}",
        remote_merged_profiles_enc,
    )
    _upload_payload_with_backup(
        client,
        f"{config['remote_dir']}/{REMOTE_PROVIDERS_FILE}",
        remote_merged_providers_enc,
    )

    profiles_md5 = _compute_digest(remote_merged_profiles_enc)
    providers_md5 = _compute_digest(remote_merged_providers_enc)
    _upload_sync_meta(client, config["remote_dir"], profiles_md5, providers_md5, config["device_name"])

    save_profiles(merged_profiles)
    save_providers(merged_providers)

    try:
        _save_snapshot(merged_profiles, merged_providers)
    except SyncLocalKeyError as exc:
        print(f"  {RED}{exc}{RESET}")
        return None, None

    for w in profile_warnings:
        print(f"  {YELLOW}{w}{RESET}")
    for w in provider_warnings:
        print(f"  {YELLOW}{w}{RESET}")

    print(f"  {GREEN}{t('sync.merge_done')}{RESET}")
    return profiles_md5, providers_md5


def cmd_sync_status(args):
    """显示同步状态。"""
    config = _load_sync_config_or_exit()

    body = []
    body.append(kv(t("sync.status_url"), config.get("webdav_url", "N/A")))
    body.append(kv(t("sync.status_username"), config.get("username", "N/A")))
    body.append(kv(t("sync.status_remote_dir"), config.get("remote_dir", "N/A")))
    body.append(kv(t("sync.status_device"), config.get("device_name", "N/A")))
    body.append(kv(t("sync.status_strategy"), config.get("strategy", "N/A")))
    body.append(kv(t("sync.status_last_sync"), config.get("last_sync") or "N/A"))

    # 快照状态
    snapshot_profiles, snapshot_providers = _load_snapshot()
    body.append("")
    body.append(kv(t("sync.status_snapshot_profiles"), str(len(snapshot_profiles))))
    body.append(kv(t("sync.status_snapshot_providers"), str(len(snapshot_providers))))
    body.append(kv(t("sync.status_local_dirty"), t("sync.status_dirty") if config.get("_local_dirty") else t("sync.status_clean")))

    # 远端连接测试（静默失败，不阻塞状态展示）
    body.append("")
    try:
        password = config.get("password")
        if not password:
            body.append(f"{DIM}{t('sync.status_remote_error')}{RESET}")
        else:
            client = WebDAVClient(
                config["webdav_url"],
                config["username"],
                password,
                verify_ssl=config.get("verify_ssl", True),
            )
            if client.test_connection():
                body.append(f"{GREEN}{t('sync.status_remote_ok')}{RESET}")
            else:
                body.append(f"{RED}{t('sync.status_remote_error')}{RESET}")
    except Exception:
        body.append(f"{RED}{t('sync.status_remote_error')}{RESET}")

    print(panel(t("sync.status_title"), "", body))


def cmd_sync_strategy(args):
    """设置冲突解决策略。"""
    config = _load_sync_config_or_exit()

    strategy_arg = getattr(args, "strategy_arg", None)
    if strategy_arg:
        strategy = strategy_arg
    else:
        strategy = select_from_list(
            [
                ("merge",       t("sync.strategy_merge")),
                ("local-wins",  t("sync.strategy_local")),
                ("remote-wins", t("sync.strategy_remote")),
            ],
            t("sync.prompt_strategy"),
            default_index=0,
        )
        if strategy is None:
            print(f"  {t('cmd.canceled')}")
            return

    config["strategy"] = strategy
    _save_sync_config(config)
    print(f"  {GREEN}{t('sync.strategy_done')}{RESET}")


def cmd_sync_reset(args):
    """重置同步配置。"""
    _load_sync_config_or_exit()

    if not confirm_action(t("sync.reset_confirm"), default_yes=False):
        print(f"  {t('cmd.canceled')}")
        return

    # 删除配置和快照
    if SYNC_CONFIG_FILE.exists():
        SYNC_CONFIG_FILE.unlink()
    if SYNC_SNAPSHOT_DIR.exists():
        import shutil
        shutil.rmtree(SYNC_SNAPSHOT_DIR)

    print(f"  {GREEN}{t('sync.reset_done')}{RESET}")
