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

    def test_load_snapshot_exits_with_friendly_error_when_local_key_is_unavailable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir) / "sync_snapshot"
            snapshot_dir.mkdir()
            profiles_path = snapshot_dir / "profiles.json"
            profiles_path.write_bytes(b"encrypted-data")

            with patch.object(sync, "SYNC_SNAPSHOT_PROFILES", profiles_path), patch.object(
                sync, "SYNC_SNAPSHOT_PROVIDERS", snapshot_dir / "providers.json"
            ), patch.object(sync, "load_key", side_effect=RuntimeError("missing key")), patch(
                "builtins.print"
            ) as print_mock:
                with self.assertRaises(SystemExit) as exc:
                    sync._load_snapshot()

        self.assertEqual(exc.exception.code, 1)
        printed = "\n".join(str(call.args[0]) for call in print_mock.call_args_list if call.args)
        self.assertIn(sync.t("sync.error_local_key_unavailable"), printed)

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

    def test_cmd_sync_config_exits_when_new_salt_upload_fails(self):
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
                sync, "_save_sync_config"
            ) as save_sync_config, patch.object(
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
            ):
                with self.assertRaises(SystemExit) as exc:
                    sync.cmd_sync_config(SimpleNamespace())

        self.assertEqual(exc.exception.code, 1)
        save_sync_config.assert_not_called()
        save_snapshot.assert_not_called()

    def test_cmd_sync_config_rotates_remote_salt_and_reencrypts_remote_data(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            key_file = Path(tmpdir) / "key.bin"
            key_file.write_text("initialized", "utf-8")
            old_salt = b"old-sync-salt-01"
            new_salt = b"new-sync-salt-02"
            old_password = "old-sync-pass"
            new_password = "new-sync-pass"
            old_sync_key = sync._derive_sync_key(old_password, old_salt)
            new_sync_key = sync._derive_sync_key(new_password, new_salt)
            remote_profiles = {"remote": {"token": "value"}}
            remote_providers = {"provider": {"api_key": "value"}}
            remote_profiles_enc = Fernet(old_sync_key).encrypt(
                json.dumps(remote_profiles).encode("utf-8")
            )
            remote_providers_enc = Fernet(old_sync_key).encrypt(
                json.dumps(remote_providers).encode("utf-8")
            )
            client = FakeWebDAVClient(
                downloads={
                    "ccprofile/salt.bin": old_salt,
                    "ccprofile/profiles.enc": remote_profiles_enc,
                    "ccprofile/providers.enc": remote_providers_enc,
                }
            )

            with patch.object(sync, "KEY_FILE", key_file), patch.object(
                sync, "WebDAVClient", return_value=client
            ), patch.object(
                sync, "confirm_action", return_value=False
            ), patch.object(
                sync, "select_from_list", return_value="merge"
            ), patch.object(
                sync, "_generate_salt", return_value=new_salt
            ), patch.object(
                sync, "_save_sync_config"
            ) as save_sync_config, patch.object(
                sync, "_save_snapshot"
            ) as save_snapshot, patch.object(
                sync, "load_profiles", return_value={}
            ), patch.object(
                sync, "load_providers", return_value={}
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
                side_effect=["webdav-pass", new_password, new_password, old_password],
            ):
                sync.cmd_sync_config(SimpleNamespace())

        saved_config = save_sync_config.call_args.args[0]
        uploads = {path: data for path, data, _ in client.upload_calls}
        rotated_profiles = json.loads(
            Fernet(new_sync_key).decrypt(uploads["ccprofile/profiles.enc"]).decode("utf-8")
        )
        rotated_providers = json.loads(
            Fernet(new_sync_key).decrypt(uploads["ccprofile/providers.enc"]).decode("utf-8")
        )
        meta = json.loads(uploads["ccprofile/sync_meta.json"].decode("utf-8"))

        self.assertEqual(saved_config["salt"], base64.b64encode(new_salt).decode("ascii"))
        self.assertEqual(saved_config["device_name"], "host-a")
        self.assertEqual(uploads["ccprofile/salt.bin.bak"], old_salt)
        self.assertEqual(uploads["ccprofile/profiles.enc.bak"], remote_profiles_enc)
        self.assertEqual(uploads["ccprofile/providers.enc.bak"], remote_providers_enc)
        self.assertEqual(uploads["ccprofile/salt.bin"], new_salt)
        self.assertEqual(rotated_profiles, remote_profiles)
        self.assertEqual(rotated_providers, remote_providers)
        self.assertEqual(meta["profiles_hash"], sync._compute_digest(uploads["ccprofile/profiles.enc"]))
        self.assertEqual(meta["providers_hash"], sync._compute_digest(uploads["ccprofile/providers.enc"]))
        save_snapshot.assert_called_once_with({}, {})


if __name__ == "__main__":
    unittest.main()
