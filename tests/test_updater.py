import unittest
import unittest.mock
import platform
import sys

from ccprofile_app import updater
from ccprofile_app.updater import UpdateError, is_newer, parse_version


class VersionTest(unittest.TestCase):
    def test_parse_strips_leading_v(self):
        self.assertEqual(parse_version("v0.3.0"), (0, 3, 0, None))

    def test_parse_plain(self):
        self.assertEqual(parse_version("0.4.0"), (0, 4, 0, None))

    def test_parse_prerelease(self):
        self.assertEqual(parse_version("0.4.0-rc1"), (0, 4, 0, "rc1"))

    def test_parse_invalid_raises(self):
        with self.assertRaises(ValueError):
            parse_version("not-a-version")

    def test_is_newer_true(self):
        self.assertTrue(is_newer("0.4.0", "0.3.0"))

    def test_is_newer_false_same(self):
        self.assertFalse(is_newer("0.3.0", "0.3.0"))

    def test_is_newer_false_downgrade(self):
        self.assertFalse(is_newer("0.2.0", "0.3.0"))

    def test_is_newer_ignores_prerelease_by_default(self):
        self.assertFalse(is_newer("0.4.0-rc1", "0.3.0"))

    def test_is_newer_includes_prerelease_when_asked(self):
        self.assertTrue(is_newer("0.4.0-rc1", "0.3.0", include_prerelease=True))

    def test_prerelease_is_older_than_release_of_same_xyz(self):
        self.assertFalse(is_newer("0.4.0-rc1", "0.4.0", include_prerelease=True))


class PlatformAssetTest(unittest.TestCase):
    def test_macos_arm64(self):
        with unittest.mock.patch.object(sys, "platform", "darwin"), \
             unittest.mock.patch.object(platform, "machine", lambda: "arm64"):
            self.assertEqual(updater.platform_asset(), "ccprofile-macos-arm64.tar.gz")

    def test_macos_intel_unsupported(self):
        with unittest.mock.patch.object(sys, "platform", "darwin"), \
             unittest.mock.patch.object(platform, "machine", lambda: "x86_64"):
            with self.assertRaises(UpdateError):
                updater.platform_asset()

    def test_linux(self):
        with unittest.mock.patch.object(sys, "platform", "linux"):
            self.assertEqual(updater.platform_asset(), "ccprofile-linux.tar.gz")

    def test_windows(self):
        with unittest.mock.patch.object(sys, "platform", "win32"):
            self.assertEqual(updater.platform_asset(), "ccprofile-windows.zip")


if __name__ == "__main__":
    unittest.main()