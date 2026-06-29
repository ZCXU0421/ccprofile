"""Verify all update-related i18n keys have both zh and en strings.

Kept as a separate file from tests/test_updater.py to avoid merge conflicts
with parallel work on the updater module.
"""

import unittest

REQUIRED_UPDATE_KEYS = [
    "cli.update_help",
    "cli.update_check_help",
    "cli.update_yes_help",
    "cli.update_force_help",
    "cli.update_prerelease_help",
    "menu.check_update",
    "update.checking",
    "update.current",
    "update.latest",
    "update.up_to_date",
    "update.new_available",
    "update.changelog",
    "update.confirm",
    "update.canceled",
    "update.downloading",
    "update.verifying",
    "update.extracting",
    "update.success_unix",
    "update.success_windows",
    "update.launch_hint",
    "update.err_network",
    "update.err_rate_limited",
    "update.err_checksum",
    "update.err_checksum_missing",
    "update.err_not_frozen",
    "update.err_unsupported",
    "update.err_extract",
    "update.err_install",
]


class I18nKeysTest(unittest.TestCase):
    def test_all_update_keys_have_zh_and_en(self):
        from ccprofile_app.i18n import STRINGS

        missing = [
            k for k in REQUIRED_UPDATE_KEYS
            if k not in STRINGS or "zh" not in STRINGS[k] or "en" not in STRINGS[k]
        ]
        self.assertEqual(missing, [], f"missing zh/en for: {missing}")


if __name__ == "__main__":
    unittest.main()