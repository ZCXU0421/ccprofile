import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ccprofile_app import commands


class CommandsTest(unittest.TestCase):
    def test_cmd_add_marks_sync_dirty_and_sets_default_advanced_flags(self):
        args = SimpleNamespace(
            name="demo",
            mode="single",
            token="token",
            url="https://example.com",
            model="opus",
            effort="high",
            anthropic_model=None,
            haiku_model=None,
            sonnet_model=None,
            opus_model=None,
            disable_all=False,
            enable_teams=False,
            bark_key=None,
            host_label=None,
            notify_sound=None,
            hooks_json=None,
        )

        with patch.object(commands, "load_profiles", return_value={}), patch.object(
            commands, "save_profiles"
        ) as save_profiles, patch.object(commands, "_mark_sync_dirty") as mark_dirty:
            commands.cmd_add(args)

        saved_profiles = save_profiles.call_args.args[0]
        self.assertTrue(saved_profiles["demo"]["enableTeams"])
        self.assertFalse(saved_profiles["demo"]["enable1MContext"])
        mark_dirty.assert_called_once()

    def test_cmd_edit_preserves_1m_context_and_marks_sync_dirty(self):
        profiles = {
            "demo": {
                "mode": "single",
                "env": {
                    "ANTHROPIC_AUTH_TOKEN": "old-token",
                    "ANTHROPIC_BASE_URL": "https://old.example.com",
                },
                "model": "opus",
                "enableTeams": True,
                "enable1MContext": True,
            }
        }
        args = SimpleNamespace(name="demo", enable_teams=False, disable_teams=False)

        with patch.object(commands, "load_profiles", return_value=profiles), patch.object(
            commands, "prompt_profile_fields", return_value={"env": {}, "model": "sonnet"}
        ), patch.object(commands, "save_profiles") as save_profiles, patch.object(
            commands, "_mark_sync_dirty"
        ) as mark_dirty:
            commands.cmd_edit(args)

        saved_profiles = save_profiles.call_args.args[0]
        self.assertTrue(saved_profiles["demo"]["enable1MContext"])
        mark_dirty.assert_called_once()

    def test_cmd_delete_marks_sync_dirty(self):
        args = SimpleNamespace(name="demo")

        with patch.object(commands, "load_profiles", return_value={"demo": {}}), patch.object(
            commands, "load_meta", return_value={"active": None}
        ), patch.object(commands, "confirm_action", return_value=True), patch.object(
            commands, "save_profiles"
        ) as save_profiles, patch.object(commands, "_mark_sync_dirty") as mark_dirty:
            commands.cmd_delete(args)

        save_profiles.assert_called_once_with({})
        mark_dirty.assert_called_once()

    def test_cmd_context_1m_toggle_updates_settings_when_apply_is_set(self):
        profiles = {"demo": {"env": {}, "enable1MContext": False}}
        args = SimpleNamespace(action="toggle", apply=True)

        with patch.object(commands, "load_meta", return_value={"active": "demo"}), patch.object(
            commands, "load_profiles", return_value=profiles
        ), patch.object(commands, "save_profiles") as save_profiles, patch.object(
            commands, "_mark_sync_dirty"
        ) as mark_dirty, patch.object(
            commands, "read_settings", return_value={"env": {"CLAUDE_CODE_DISABLE_1M_CONTEXT": "1"}}
        ), patch.object(commands, "write_settings") as write_settings:
            commands.cmd_context_1m(args)

        saved_profiles = save_profiles.call_args.args[0]
        self.assertTrue(saved_profiles["demo"]["enable1MContext"])
        self.assertNotIn(
            "CLAUDE_CODE_DISABLE_1M_CONTEXT",
            write_settings.call_args.args[0]["env"],
        )
        mark_dirty.assert_called_once()

    def test_cmd_switch_writes_disable_1m_context_for_disabled_profiles(self):
        profile = {
            "mode": "single",
            "env": {
                "ANTHROPIC_AUTH_TOKEN": "token",
                "ANTHROPIC_BASE_URL": "https://example.com",
            },
            "model": "opus",
            "effortLevel": "high",
            "enableTeams": True,
            "enable1MContext": False,
        }
        args = SimpleNamespace(name="demo")

        with patch.object(commands, "load_profiles", return_value={"demo": profile}), patch.object(
            commands, "backup_settings"
        ), patch.object(
            commands, "read_settings", return_value={"env": {"CLAUDE_CODE_DISABLE_1M_CONTEXT": "stale"}}
        ), patch.object(commands, "stop_proxy", return_value=True), patch.object(
            commands, "write_settings"
        ) as write_settings, patch.object(commands, "save_profiles"), patch.object(
            commands, "load_meta", return_value={}
        ), patch.object(commands, "save_meta"):
            commands.cmd_switch(args)

        written_settings = write_settings.call_args.args[0]
        self.assertEqual(written_settings["env"]["CLAUDE_CODE_DISABLE_1M_CONTEXT"], "1")
        self.assertEqual(
            written_settings["env"]["CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"],
            "1",
        )

    def test_cmd_init_clears_sync_artifacts_when_reinitializing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            key_file = Path(tmpdir) / ".profile_key"
            providers_enc = Path(tmpdir) / "providers.enc"
            sync_config = Path(tmpdir) / "sync_config.json"
            snapshot_dir = Path(tmpdir) / "sync_snapshot"
            snapshot_dir.mkdir()
            snapshot_file = snapshot_dir / "profiles.json"

            key_file.write_text("old-key", "utf-8")
            providers_enc.write_text("providers", "utf-8")
            sync_config.write_text("sync-config", "utf-8")
            snapshot_file.write_text("snapshot", "utf-8")

            with patch("ccprofile_app.constants.KEY_FILE", key_file), patch(
                "ccprofile_app.constants.PROVIDERS_ENC", providers_enc
            ), patch(
                "ccprofile_app.constants.SYNC_CONFIG_FILE", sync_config
            ), patch(
                "ccprofile_app.constants.SYNC_SNAPSHOT_DIR", snapshot_dir
            ), patch.object(
                commands, "confirm_action", side_effect=[True, True]
            ), patch.object(
                commands, "save_key"
            ), patch.object(
                commands, "save_profiles"
            ), patch.object(
                commands, "save_meta"
            ):
                commands.cmd_init(SimpleNamespace())

        self.assertFalse(providers_enc.exists())
        self.assertFalse(sync_config.exists())
        self.assertFalse(snapshot_dir.exists())


if __name__ == "__main__":
    unittest.main()
