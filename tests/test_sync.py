import base64
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from cryptography.fernet import Fernet

from ccprofile_app import sync


class FakeWebDAVClient:
    def __init__(self, downloads=None, upload_errors=None, test_connection_result=True):
        self.downloads = downloads or {}
        self.upload_errors = upload_errors or {}
        self.upload_calls = []
        self.test_connection_result = test_connection_result

    def download(self, remote_path):
        if remote_path not in self.downloads:
            raise sync.WebDAVNotFoundError(remote_path)
        return self.downloads[remote_path]

    def upload(self, remote_path, data, content_type="application/octet-stream"):
        if remote_path in self.upload_errors:
            raise self.upload_errors[remote_path]
        self.upload_calls.append((remote_path, data, content_type))

    def ensure_directory(self, remote_path):
        return None

    def test_connection(self):
        return self.test_connection_result


class SyncTest(unittest.TestCase):
    def test_save_snapshot_keeps_data_encrypted_at_rest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir) / "sync_snapshot"
            profiles_path = snapshot_dir / "profiles.json"
            providers_path = snapshot_dir / "providers.json"
            key = Fernet.generate_key()

            with patch.object(sync, "SYNC_SNAPSHOT_DIR", snapshot_dir), patch.object(
                sync, "SYNC_SNAPSHOT_PROFILES", profiles_path
            ), patch.object(sync, "SYNC_SNAPSHOT_PROVIDERS", providers_path), patch.object(
                sync, "load_key", return_value=key
            ):
                sync._save_snapshot(
                    {"default": {"token": "secret-token"}},
                    {"provider": {"api_key": "secret-key"}},
                )
                profiles, providers = sync._load_snapshot()

                self.assertNotIn(b"secret-token", profiles_path.read_bytes())
                self.assertNotIn(b"secret-key", providers_path.read_bytes())
                self.assertEqual(profiles_path.stat().st_mode & 0o777, 0o600)
                self.assertEqual(providers_path.stat().st_mode & 0o777, 0o600)

            self.assertEqual(profiles["default"]["token"], "secret-token")
            self.assertEqual(providers["provider"]["api_key"], "secret-key")

    def test_load_snapshot_accepts_legacy_plaintext_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir) / "sync_snapshot"
            snapshot_dir.mkdir()
            profiles_path = snapshot_dir / "profiles.json"
            providers_path = snapshot_dir / "providers.json"
            profiles_path.write_text(json.dumps({"legacy": {"token": "plain"}}), "utf-8")
            providers_path.write_text(json.dumps({"provider": {"api_key": "plain"}}), "utf-8")

            with patch.object(sync, "SYNC_SNAPSHOT_PROFILES", profiles_path), patch.object(
                sync, "SYNC_SNAPSHOT_PROVIDERS", providers_path
            ), patch.object(sync, "load_key", return_value=Fernet.generate_key()):
                profiles, providers = sync._load_snapshot()

            self.assertEqual(profiles, {"legacy": {"token": "plain"}})
            self.assertEqual(providers, {"provider": {"api_key": "plain"}})

    def test_load_snapshot_file_returns_empty_dict_for_invalid_data(self):
        raw = Fernet(Fernet.generate_key()).encrypt(json.dumps({"legacy": True}).encode("utf-8"))

        with patch.object(sync, "load_key", return_value=Fernet.generate_key()), patch(
            "builtins.print"
        ) as print_mock:
            loaded = sync._load_snapshot_file(raw)

        self.assertEqual(loaded, {})
        print_mock.assert_called()

    def test_detect_sync_action_covers_core_cases(self):
        cases = [
            ("up-to-date", {"a": 1}, {"p": 1}, {"a": 1}, {"p": 1}, {"profiles_md5": "old", "providers_md5": "old"}, "old", "old"),
            ("push", {"a": 1}, {"p": 1}, {"a": 2}, {"p": 1}, {"profiles_md5": "old", "providers_md5": "old"}, "old", "old"),
            ("pull", {"a": 1}, {"p": 1}, {"a": 1}, {"p": 1}, {"profiles_md5": "new", "providers_md5": "old"}, "old", "old"),
            ("conflict", {"a": 1}, {"p": 1}, {"a": 2}, {"p": 1}, {"profiles_md5": "new", "providers_md5": "old"}, "old", "old"),
        ]

        for expected, snapshot_profiles, snapshot_providers, current_profiles, current_providers, remote_meta, stored_profiles_md5, stored_providers_md5 in cases:
            with self.subTest(expected=expected):
                action = sync._detect_sync_action(
                    snapshot_profiles,
                    snapshot_providers,
                    current_profiles,
                    current_providers,
                    remote_meta,
                    stored_profiles_md5,
                    stored_providers_md5,
                )
                self.assertEqual(action, expected)

    def test_merge_data_keeps_non_conflicting_changes_and_suffixes_conflicts(self):
        merged, warnings = sync._merge_data(
            {"shared": {"v": "local"}, "local-only": {"v": 1}},
            {"shared": {"v": "remote"}, "remote-only": {"v": 2}},
            {"shared": {"v": "base"}},
            "host-a",
        )

        self.assertEqual(merged["remote-only"], {"v": 2})
        self.assertEqual(merged["local-only"], {"v": 1})
        self.assertEqual(merged["shared"], {"v": "remote"})
        self.assertEqual(merged["shared (host-a)"], {"v": "local"})
        self.assertEqual(len(warnings), 1)

    def test_do_push_refuses_to_overwrite_remote_with_wrong_sync_key(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            profiles_enc = Path(tmpdir) / "profiles.enc"
            providers_enc = Path(tmpdir) / "providers.enc"
            local_key = Fernet.generate_key()
            correct_sync_key = Fernet.generate_key()
            wrong_sync_key = Fernet.generate_key()

            profiles_enc.write_bytes(
                Fernet(local_key).encrypt(json.dumps({"local": {"token": "value"}}).encode("utf-8"))
            )
            providers_enc.write_bytes(
                Fernet(local_key).encrypt(json.dumps({"provider": {"api_key": "value"}}).encode("utf-8"))
            )

            client = FakeWebDAVClient(
                {
                    "remote/profiles.enc": Fernet(correct_sync_key).encrypt(
                        json.dumps({"remote": {"token": "value"}}).encode("utf-8")
                    ),
                    "remote/providers.enc": Fernet(correct_sync_key).encrypt(
                        json.dumps({"provider": {"api_key": "value"}}).encode("utf-8")
                    ),
                }
            )

            with patch.object(sync, "PROFILES_ENC", profiles_enc), patch.object(
                sync, "PROVIDERS_ENC", providers_enc
            ), patch.object(sync, "load_key", return_value=local_key), patch.object(
                sync, "_save_snapshot"
            ) as save_snapshot:
                result = sync._do_push(
                    client,
                    {"remote_dir": "remote", "device_name": "host-a"},
                    wrong_sync_key,
                    {"local": {"token": "value"}},
                    {"provider": {"api_key": "value"}},
                )

            self.assertEqual(result, (None, None))
            self.assertEqual(client.upload_calls, [])
            save_snapshot.assert_not_called()

    def test_do_push_encrypts_empty_payloads_for_profiles_and_providers(self):
        sync_key = Fernet.generate_key()
        client = FakeWebDAVClient()

        with tempfile.TemporaryDirectory() as tmpdir:
            profiles_enc = Path(tmpdir) / "profiles.enc"
            providers_enc = Path(tmpdir) / "providers.enc"

            with patch.object(sync, "PROFILES_ENC", profiles_enc), patch.object(
                sync, "PROVIDERS_ENC", providers_enc
            ), patch.object(sync, "load_key", return_value=Fernet.generate_key()), patch.object(
                sync, "_save_snapshot"
            ), patch.object(sync, "_upload_sync_meta"):
                profiles_md5, providers_md5 = sync._do_push(
                    client,
                    {"remote_dir": "remote", "device_name": "host-a"},
                    sync_key,
                    {},
                    {},
                )

        uploads = {path: data for path, data, _ in client.upload_calls}
        remote_profiles = uploads["remote/profiles.enc"]
        remote_providers = uploads["remote/providers.enc"]

        self.assertTrue(remote_profiles)
        self.assertTrue(remote_providers)
        self.assertEqual(json.loads(Fernet(sync_key).decrypt(remote_profiles).decode("utf-8")), {})
        self.assertEqual(json.loads(Fernet(sync_key).decrypt(remote_providers).decode("utf-8")), {})
        self.assertEqual(profiles_md5, sync._compute_digest(remote_profiles))
        self.assertEqual(providers_md5, sync._compute_digest(remote_providers))

    def test_do_pull_treats_missing_remote_file_as_empty_payload(self):
        sync_key = Fernet.generate_key()
        remote_profiles_enc = Fernet(sync_key).encrypt(
            json.dumps({"remote": {"token": "value"}}).encode("utf-8")
        )
        client = FakeWebDAVClient({"remote/profiles.enc": remote_profiles_enc})

        with patch.object(sync, "save_profiles") as save_profiles, patch.object(
            sync, "save_providers"
        ) as save_providers, patch.object(sync, "_save_snapshot") as save_snapshot:
            profiles_md5, providers_md5 = sync._do_pull(
                client,
                {"remote_dir": "remote"},
                sync_key,
                None,
            )

        save_profiles.assert_called_once_with({"remote": {"token": "value"}})
        save_providers.assert_called_once_with({})
        save_snapshot.assert_called_once_with({"remote": {"token": "value"}}, {})
        self.assertEqual(profiles_md5, sync._compute_digest(remote_profiles_enc))
        self.assertEqual(providers_md5, sync._compute_digest(b""))

    def test_do_pull_returns_none_on_invalid_sync_key(self):
        sync_key = Fernet.generate_key()
        wrong_key = Fernet.generate_key()
        remote_profiles_enc = Fernet(wrong_key).encrypt(
            json.dumps({"remote": {"token": "value"}}).encode("utf-8")
        )
        client = FakeWebDAVClient({"remote/profiles.enc": remote_profiles_enc})

        with patch.object(sync, "save_profiles") as save_profiles, patch.object(
            sync, "save_providers"
        ) as save_providers, patch.object(sync, "_save_snapshot") as save_snapshot:
            result = sync._do_pull(
                client,
                {"remote_dir": "remote"},
                sync_key,
                None,
            )

        self.assertEqual(result, (None, None))
        save_profiles.assert_not_called()
        save_providers.assert_not_called()
        save_snapshot.assert_not_called()

    def test_do_merge_merges_uploads_and_keeps_remote_backups(self):
        sync_key = Fernet.generate_key()
        remote_profiles = {"shared": {"v": "remote"}, "remote-only": {"v": 2}}
        remote_providers = {"provider": {"api_key": "remote"}}
        remote_profiles_enc = Fernet(sync_key).encrypt(json.dumps(remote_profiles).encode("utf-8"))
        remote_providers_enc = Fernet(sync_key).encrypt(json.dumps(remote_providers).encode("utf-8"))
        client = FakeWebDAVClient(
            {
                "remote/profiles.enc": remote_profiles_enc,
                "remote/providers.enc": remote_providers_enc,
            }
        )

        with patch.object(sync, "save_profiles") as save_profiles, patch.object(
            sync, "save_providers"
        ) as save_providers, patch.object(sync, "_save_snapshot") as save_snapshot:
            profiles_md5, providers_md5 = sync._do_merge(
                client,
                {"remote_dir": "remote", "device_name": "host-a"},
                sync_key,
                {"shared": {"v": "base"}},
                {"provider": {"api_key": "base"}},
                {"shared": {"v": "local"}, "local-only": {"v": 1}},
                {"provider": {"api_key": "local"}, "provider-local": {"api_key": "v"}},
            )

        uploads = {path: data for path, data, _ in client.upload_calls}
        merged_profiles = json.loads(
            Fernet(sync_key).decrypt(uploads["remote/profiles.enc"]).decode("utf-8")
        )
        merged_providers = json.loads(
            Fernet(sync_key).decrypt(uploads["remote/providers.enc"]).decode("utf-8")
        )
        meta = json.loads(uploads["remote/sync_meta.json"].decode("utf-8"))

        self.assertEqual(uploads["remote/profiles.enc.bak"], remote_profiles_enc)
        self.assertEqual(uploads["remote/providers.enc.bak"], remote_providers_enc)
        self.assertEqual(merged_profiles["shared"], {"v": "remote"})
        self.assertEqual(merged_profiles["shared (host-a)"], {"v": "local"})
        self.assertEqual(merged_profiles["local-only"], {"v": 1})
        self.assertEqual(merged_providers["provider"], {"api_key": "remote"})
        self.assertEqual(merged_providers["provider (host-a)"], {"api_key": "local"})
        self.assertEqual(merged_providers["provider-local"], {"api_key": "v"})
        self.assertEqual(meta["profiles_hash"], profiles_md5)
        self.assertEqual(meta["providers_hash"], providers_md5)
        save_profiles.assert_called_once_with(merged_profiles)
        save_providers.assert_called_once_with(merged_providers)
        save_snapshot.assert_called_once_with(merged_profiles, merged_providers)

    def test_cmd_sync_status_exits_with_friendly_error_for_invalid_sync_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sync_config_path = Path(tmpdir) / "sync_config.json"
            sync_config_path.write_text("{invalid json", "utf-8")

            with patch.object(sync, "SYNC_CONFIG_FILE", sync_config_path), patch(
                "builtins.print"
            ) as print_mock:
                with self.assertRaises(SystemExit) as exc:
                    sync.cmd_sync_status(SimpleNamespace())

        self.assertEqual(exc.exception.code, 1)
        printed = "\n".join(str(call.args[0]) for call in print_mock.call_args_list if call.args)
        self.assertIn(sync.t("sync.error_config_invalid"), printed)

    def test_load_sync_config_exits_with_friendly_error_when_password_uses_old_local_key(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sync_config_path = Path(tmpdir) / "sync_config.json"
            old_key = Fernet.generate_key()
            new_key = Fernet.generate_key()
            encrypted_password = base64.b64encode(
                Fernet(old_key).encrypt(json.dumps({"p": "secret"}).encode("utf-8"))
            ).decode("ascii")
            sync_config_path.write_text(
                json.dumps(
                    {
                        "webdav_url": "https://example.com/webdav",
                        "username": "user",
                        "password_encrypted": encrypted_password,
                    }
                ),
                "utf-8",
            )

            with patch.object(sync, "SYNC_CONFIG_FILE", sync_config_path), patch.object(
                sync, "load_key", return_value=new_key
            ), patch("builtins.print") as print_mock:
                with self.assertRaises(SystemExit) as exc:
                    sync._load_sync_config_or_exit()

        self.assertEqual(exc.exception.code, 1)
        printed = "\n".join(str(call.args[0]) for call in print_mock.call_args_list if call.args)
        self.assertIn(sync.t("sync.error_config_password_unreadable"), printed)

    def test_load_snapshot_raises_friendly_error_when_local_key_is_unavailable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir) / "sync_snapshot"
            snapshot_dir.mkdir()
            profiles_path = snapshot_dir / "profiles.json"
            profiles_path.write_bytes(b"encrypted-data")

            with patch.object(sync, "SYNC_SNAPSHOT_PROFILES", profiles_path), patch.object(
                sync, "SYNC_SNAPSHOT_PROVIDERS", snapshot_dir / "providers.json"
            ), patch.object(sync, "load_key", side_effect=RuntimeError("missing key")):
                with self.assertRaises(sync.SyncLocalKeyError) as exc:
                    sync._load_snapshot()

        self.assertIn(sync.t("sync.error_local_key_unavailable"), str(exc.exception))

    def test_sync_mark_dirty_ignores_config_with_unreadable_password(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sync_config_path = Path(tmpdir) / "sync_config.json"
            old_key = Fernet.generate_key()
            encrypted_password = base64.b64encode(
                Fernet(old_key).encrypt(json.dumps({"p": "secret"}).encode("utf-8"))
            ).decode("ascii")
            original = {
                "webdav_url": "https://example.com/webdav",
                "username": "user",
                "password_encrypted": encrypted_password,
                "_local_dirty": False,
            }
            sync_config_path.write_text(json.dumps(original, indent=2), "utf-8")

            with patch.object(sync, "SYNC_CONFIG_FILE", sync_config_path), patch.object(
                sync, "load_key", return_value=Fernet.generate_key()
            ):
                sync._sync_mark_dirty()

            stored = json.loads(sync_config_path.read_text("utf-8"))
            self.assertEqual(stored, original)

    def test_sync_mark_dirty_reencrypts_plaintext_password(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            profile_dir = Path(tmpdir)
            sync_config_path = profile_dir / "sync_config.json"
            key = Fernet.generate_key()

            sync_config_path.write_text(
                json.dumps(
                    {
                        "webdav_url": "https://example.com/webdav",
                        "username": "user",
                        "password": "plain-secret",
                        "_local_dirty": False,
                    },
                    indent=2,
                ),
                "utf-8",
            )

            with patch.object(sync, "PROFILE_DIR", profile_dir), patch.object(
                sync, "SYNC_CONFIG_FILE", sync_config_path
            ), patch.object(sync, "load_key", return_value=key):
                sync._sync_mark_dirty()
                stored = json.loads(sync_config_path.read_text("utf-8"))
                config = sync._get_sync_config()

            self.assertTrue(stored["_local_dirty"])
            self.assertNotIn("password", stored)
            self.assertIn("password_encrypted", stored)
            self.assertEqual(config["password"], "plain-secret")

    def test_cmd_sync_does_not_mark_failed_merge_as_synced(self):
        config = {
            "webdav_url": "https://example.com/webdav",
            "username": "user",
            "password": "pass",
            "verify_ssl": True,
            "remote_dir": "remote",
            "strategy": "merge",
            "device_name": "host-a",
            "salt": base64.b64encode(b"0123456789abcdef").decode("ascii"),
            "_local_dirty": True,
            "last_sync": None,
            "remote_profiles_md5": "old-profiles",
            "remote_providers_md5": "old-providers",
        }

        with patch.object(sync, "_get_sync_config", return_value=config), patch.object(
            sync.getpass, "getpass", return_value="sync-password"
        ), patch.object(sync, "_derive_sync_key", return_value=Fernet.generate_key()), patch.object(
            sync, "WebDAVClient", return_value=object()
        ), patch.object(
            sync, "load_profiles", return_value={"current": 1}
        ), patch.object(sync, "load_providers", return_value={"provider": 1}), patch.object(
            sync, "_load_snapshot", return_value=({"base": 1}, {"provider": 0})
        ), patch.object(sync, "_download_sync_meta", return_value={"profiles_md5": "new", "providers_md5": "new"}), patch.object(
            sync, "_detect_sync_action", return_value="conflict"
        ), patch.object(sync, "_do_merge", return_value=(None, None)) as do_merge, patch.object(
            sync, "_save_sync_config"
        ) as save_sync_config:
            sync.cmd_sync_auto(SimpleNamespace())

        do_merge.assert_called_once()
        save_sync_config.assert_not_called()
        self.assertTrue(config["_local_dirty"])
        self.assertIsNone(config["last_sync"])
        self.assertEqual(config["remote_profiles_md5"], "old-profiles")
        self.assertEqual(config["remote_providers_md5"], "old-providers")

    def test_cmd_sync_config_warns_when_new_salt_upload_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            key_file = Path(tmpdir) / "key.bin"
            key_file.write_text("initialized", "utf-8")
            client = FakeWebDAVClient(
                upload_errors={
                    "ccprofile/salt.bin": sync.WebDAVError("boom"),
                }
            )

            with patch.object(sync, "KEY_FILE", key_file), patch.object(
                sync, "WebDAVClient", return_value=client
            ), patch.object(
                sync, "confirm_action", return_value=False
            ), patch.object(
                sync, "select_from_list", return_value="merge"
            ), patch.object(
                sync, "_save_sync_setup"
            ) as save_sync_setup, patch.object(
                sync, "_save_snapshot"
            ) as save_snapshot, patch.object(
                sync, "load_profiles", return_value={}
            ), patch.object(
                sync, "load_providers", return_value={}
            ), patch.object(
                sync, "_upload_payload_with_backup", side_effect=sync.WebDAVError("boom")
            ), patch(
                "socket.gethostname", return_value="host-a"
            ), patch(
                "builtins.input",
                side_effect=[
                    "https://example.com/dav",
                    "user",
                    "",
                    "",
                ],
            ), patch.object(
                sync.getpass,
                "getpass",
                side_effect=["webdav-pass", "sync-pass", "sync-pass"],
            ), patch(
                "builtins.print"
            ) as print_mock:
                sync.cmd_sync_config(SimpleNamespace())

        save_sync_setup.assert_called_once()
        save_snapshot.assert_not_called()
        printed = "\n".join(str(call.args[0]) for call in print_mock.call_args_list if call.args)
        self.assertIn(sync.t("sync.config_saved_no_salt"), printed)

class SyncMultiDeviceTest(unittest.TestCase):
    """多设备同步场景:第二台设备配置时必须「加入」而非「轮换」远端盐值。"""

    def _run_config(self, client, getpass_side_effects, local_profiles=None, local_providers=None):
        with tempfile.TemporaryDirectory() as tmpdir:
            key_file = Path(tmpdir) / "key.bin"
            key_file.write_text("initialized", "utf-8")
            with patch.object(sync, "KEY_FILE", key_file), patch.object(
                sync, "WebDAVClient", return_value=client
            ), patch.object(
                sync, "confirm_action", return_value=False
            ), patch.object(
                sync, "select_from_list", return_value="merge"
            ), patch.object(
                sync, "_save_sync_setup"
            ) as save_sync_setup, patch.object(
                sync, "load_profiles", return_value=local_profiles or {}
            ), patch.object(
                sync, "load_providers", return_value=local_providers or {}
            ), patch(
                "socket.gethostname", return_value="host-b"
            ), patch(
                "builtins.input",
                side_effect=["https://example.com/dav", "user", "", ""],
            ), patch.object(
                sync.getpass, "getpass", side_effect=getpass_side_effects
            ), patch(
                "builtins.print"
            ):
                sync.cmd_sync_config(SimpleNamespace())
            return save_sync_setup

    def test_join_reuses_remote_salt_and_does_not_touch_remote_data(self):
        """第二台设备 join 时复用远端盐值,不轮换、不重新加密、不上传任何东西。"""
        shared_password = "shared-sync-pass"
        existing_salt = b"existing-salt-01"
        sync_key = sync._derive_sync_key(shared_password, existing_salt)
        remote_profiles = {"work": {"token": "from-device-a"}}
        remote_profiles_enc = Fernet(sync_key).encrypt(json.dumps(remote_profiles).encode("utf-8"))

        client = FakeWebDAVClient(
            downloads={
                "ccprofile/salt.bin": existing_salt,
                "ccprofile/profiles.enc": remote_profiles_enc,
            }
        )

        # 第 4 个 getpass 值仅供「旧的轮换实现」使用;修复后只消费 3 个。
        save_sync_setup = self._run_config(
            client,
            ["webdav-pass", shared_password, shared_password, shared_password],
        )

        saved_config = save_sync_setup.call_args.args[0]
        # 1. 复用了远端已有盐值(没有轮换)
        self.assertEqual(saved_config["salt"], base64.b64encode(existing_salt).decode("ascii"))
        # 2. 没有任何上传(不重新加密远端数据、不上传新盐值)
        self.assertEqual(client.upload_calls, [])
        # 3. 远端数据原样未动
        self.assertEqual(client.downloads["ccprofile/profiles.enc"], remote_profiles_enc)
        self.assertEqual(client.downloads["ccprofile/salt.bin"], existing_salt)

    def test_join_rejects_wrong_sync_password_without_saving(self):
        """join 时同步密码错误应被拒绝,不保存配置、不上传。"""
        shared_password = "shared-sync-pass"
        wrong_password = "wrong-sync-pass"
        existing_salt = b"existing-salt-02"
        sync_key = sync._derive_sync_key(shared_password, existing_salt)
        remote_profiles_enc = Fernet(sync_key).encrypt(
            json.dumps({"work": {"token": "from-device-a"}}).encode("utf-8")
        )

        client = FakeWebDAVClient(
            downloads={
                "ccprofile/salt.bin": existing_salt,
                "ccprofile/profiles.enc": remote_profiles_enc,
            }
        )

        save_sync_setup = self._run_config(
            client,
            ["webdav-pass", wrong_password, wrong_password],
        )

        save_sync_setup.assert_not_called()
        self.assertEqual(client.upload_calls, [])

    def test_join_reuses_salt_even_when_remote_has_no_payload_data(self):
        """盐值已存在但数据尚未推送时,后续设备仍应复用盐值,绝不生成新的。

        覆盖边界:A 配置后(只上传盐值)还没 sync,B 此时配置。
        若按「是否有数据」判定会生成新盐值覆盖 A 的,再次引发多设备失效。
        """
        existing_salt = b"only-salt-no-data"
        client = FakeWebDAVClient(
            downloads={"ccprofile/salt.bin": existing_salt}
        )

        save_sync_setup = self._run_config(
            client,
            ["webdav-pass", "any-password", "any-password"],
        )

        saved_config = save_sync_setup.call_args.args[0]
        self.assertEqual(saved_config["salt"], base64.b64encode(existing_salt).decode("ascii"))
        # 没有数据可校验,也不应上传任何东西
        self.assertEqual(client.upload_calls, [])

    def test_join_saves_empty_snapshot_so_first_sync_merges_instead_of_pulling(self):
        """加入现有同步时必须保存「空快照」。

        否则首次 sync 会因 快照==本地 而判定 local_changed=False -> 盲目 pull,
        把本机已有数据静默覆盖。空快照使首次 sync 走 conflict -> merge,保住本机数据。
        """
        existing_salt = b"existing-salt-03"
        shared_password = "shared-sync-pass"
        sync_key = sync._derive_sync_key(shared_password, existing_salt)
        remote_profiles_enc = Fernet(sync_key).encrypt(
            json.dumps({"remote-only": {"token": "from-a"}}).encode("utf-8")
        )
        client = FakeWebDAVClient(
            downloads={
                "ccprofile/salt.bin": existing_salt,
                "ccprofile/profiles.enc": remote_profiles_enc,
            }
        )
        # 本机已有自己的本地数据(与远端不同)
        local_profiles = {"my-local": {"token": "mine"}}

        save_sync_setup = self._run_config(
            client,
            ["webdav-pass", shared_password, shared_password],
            local_profiles=local_profiles,
        )

        # join 必须以空快照保存(而非本地数据),这才让首次 sync 检测到本地变更
        self.assertEqual(save_sync_setup.call_args.args[1:], ({}, {}))


class SyncJoinSnapshotTest(unittest.TestCase):
    """加入(join)设备首次同步的方向判定:必须走合并,而非盲目 pull。"""

    def test_detect_sync_action_routes_fresh_join_to_conflict(self):
        """空快照 + 未记录远端摘要 + 远端有数据 + 本机有数据 -> conflict(走合并)。"""
        action = sync._detect_sync_action(
            snapshot_profiles={},
            snapshot_providers={},
            current_profiles={"my-local": {"token": "mine"}},
            current_providers={},
            remote_meta={"profiles_hash": "remote-h", "providers_hash": "rh2"},
            stored_remote_profiles_md5=None,
            stored_remote_providers_md5=None,
        )
        self.assertEqual(action, "conflict")

    def test_detect_sync_action_with_local_snapshot_routes_to_pull(self):
        """对照:若误用「本地数据当快照」(旧 bug),首次 sync 会被判为 pull——覆盖本地。

        此测试锁定该语义,确保 join 必须用空快照而非本地数据。
        """
        action = sync._detect_sync_action(
            snapshot_profiles={"my-local": {"token": "mine"}},  # 旧 bug:快照=本地
            snapshot_providers={},
            current_profiles={"my-local": {"token": "mine"}},
            current_providers={},
            remote_meta={"profiles_hash": "remote-h", "providers_hash": "rh2"},
            stored_remote_profiles_md5=None,
            stored_remote_providers_md5=None,
        )
        self.assertEqual(action, "pull")  # 这正是要避免的破坏性方向

    def test_first_sync_after_join_merges_and_preserves_local_data(self):
        """端到端:加入设备(空快照+本地数据)首次 sync 走 merge,本机数据不丢失。"""
        shared_password = "shared-sync-pass"
        existing_salt = b"join-e2e-salt-01"
        sync_key = sync._derive_sync_key(shared_password, existing_salt)

        remote_profiles = {"from-a": {"token": "remote-value"}}
        remote_profiles_enc = Fernet(sync_key).encrypt(json.dumps(remote_profiles).encode("utf-8"))
        local_profiles = {"my-local": {"token": "mine"}}

        meta = {
            "profiles_hash": sync._compute_digest(remote_profiles_enc),
            "providers_hash": sync._compute_digest(b""),
        }
        client = FakeWebDAVClient(
            downloads={
                "ccprofile/profiles.enc": remote_profiles_enc,
                "ccprofile/sync_meta.json": json.dumps(meta).encode("utf-8"),
            }
        )
        # 加入设备的配置:无 stored remote 摘要、last_sync=None(正是 join 后的状态)
        config = {
            "webdav_url": "https://example.com/dav", "username": "u", "password": "p",
            "verify_ssl": True, "remote_dir": "ccprofile", "strategy": "merge",
            "device_name": "host-b", "salt": base64.b64encode(existing_salt).decode("ascii"),
            "_local_dirty": False, "last_sync": None,
        }

        with patch.object(sync, "_get_sync_config", return_value=config), patch.object(
            sync.getpass, "getpass", return_value=shared_password
        ), patch.object(sync, "WebDAVClient", return_value=client), patch.object(
            sync, "load_profiles", return_value=local_profiles
        ), patch.object(sync, "load_providers", return_value={}), patch.object(
            sync, "_load_snapshot", return_value=({}, {})
        ), patch.object(
            sync, "save_profiles"
        ) as save_profiles, patch.object(
            sync, "save_providers"
        ), patch.object(sync, "_save_snapshot"), patch(
            "builtins.print"
        ):
            sync.cmd_sync_auto(SimpleNamespace())

        saved_profiles = save_profiles.call_args.args[0]
        # 本机数据保住了
        self.assertEqual(saved_profiles.get("my-local"), {"token": "mine"})
        # 远端数据也合并进来了(没有丢失)
        self.assertEqual(saved_profiles.get("from-a"), {"token": "remote-value"})


if __name__ == "__main__":
    unittest.main()
