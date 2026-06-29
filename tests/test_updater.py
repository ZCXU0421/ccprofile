import contextlib
import io
import os
import unittest
import unittest.mock
import hashlib
import platform
import sys
import tarfile
import tempfile
from pathlib import Path
from types import SimpleNamespace

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


class ShaAndThrottleTest(unittest.TestCase):
    def test_expected_sha256_found(self):
        text = "abc123  ccprofile-linux.tar.gz\nffff  other.zip\n"
        self.assertEqual(
            updater.expected_sha256("ccprofile-linux.tar.gz", text), "abc123"
        )

    def test_expected_sha256_missing(self):
        self.assertIsNone(updater.expected_sha256("nope.zip", "abc123  other.zip\n"))

    def test_should_check_when_never_checked(self):
        self.assertTrue(updater.should_check_now({}, now_ts=1000))

    def test_should_not_check_within_interval(self):
        cache = {"last_check_ts": 1000}
        self.assertFalse(updater.should_check_now(cache, now_ts=1000 + 100))

    def test_should_check_after_interval(self):
        cache = {"last_check_ts": 1000}
        self.assertTrue(
            updater.should_check_now(cache, now_ts=1000 + updater.UPDATE_CHECK_INTERVAL)
        )


class FetchReleaseTest(unittest.TestCase):
    def test_fetch_maps_api_response(self):
        api_data = {
            "tag_name": "v0.4.0",
            "body": "changes",
            "assets": [
                {"name": "ccprofile-linux.tar.gz", "browser_download_url": "https://x/linux"},
                {"name": "SHA256SUMS", "browser_download_url": "https://x/sums"},
            ],
        }
        with unittest.mock.patch.object(updater, "_http_get_json", return_value=api_data):
            rel = updater.fetch_latest_release()
        self.assertEqual(rel["version"], "0.4.0")
        self.assertEqual(rel["tag"], "v0.4.0")
        self.assertEqual(rel["body"], "changes")
        self.assertEqual(rel["assets"]["ccprofile-linux.tar.gz"], "https://x/linux")

    def test_fetch_falls_back_on_rate_limit(self):
        def fake_get(url, timeout=10):
            raise updater.RateLimitedError("limited")

        with unittest.mock.patch.object(updater, "_http_get_json", side_effect=fake_get), \
             unittest.mock.patch.object(updater, "_http_head_location", return_value="v0.4.0"):
            rel = updater.fetch_latest_release()
        self.assertEqual(rel["version"], "0.4.0")
        self.assertEqual(rel["assets"], {})

    def test_fetch_propagates_network_error(self):
        with unittest.mock.patch.object(
            updater, "_http_get_json", side_effect=updater.UpdateError("net")
        ):
            with self.assertRaises(UpdateError):
                updater.fetch_latest_release()


class DownloadVerifyExtractTest(unittest.TestCase):
    def test_verify_sha256_match(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "f"
            p.write_bytes(b"hello")
            digest = hashlib.sha256(b"hello").hexdigest()
            self.assertTrue(updater.verify_sha256(p, digest))

    def test_verify_sha256_mismatch(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "f"
            p.write_bytes(b"hello")
            self.assertFalse(updater.verify_sha256(p, "0" * 64))

    def test_extract_bundle_tar(self):
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            # build a tar.gz with layout ccprofile/ccprofile
            src = work / "ccprofile"
            src.mkdir()
            (src / "ccprofile").write_text("exe")
            archive = work / "bundle.tar.gz"
            with tarfile.open(archive, "w:gz") as tar:
                tar.add(src, arcname="ccprofile")
            out = work / "extracted"
            bundle = updater.extract_bundle(archive, out)
            self.assertTrue((bundle / "ccprofile").exists())
            self.assertEqual(bundle.name, "ccprofile")

    def test_extract_bundle_bad_layout_raises(self):
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            (work / "other").mkdir()
            archive = work / "bundle.tar.gz"
            with tarfile.open(archive, "w:gz") as tar:
                tar.add(work / "other", arcname="other")
            with self.assertRaises(UpdateError):
                updater.extract_bundle(archive, work / "extracted")

    def test_extract_zip_rejects_traversal(self):
        import io, zipfile as zf
        bad = io.BytesIO()
        with zf.ZipFile(bad, "w") as z:
            z.writestr("../evil.txt", "pwn")
        with tempfile.TemporaryDirectory() as work:
            archive = Path(work) / "bundle.zip"
            archive.write_bytes(bad.getvalue())
            with self.assertRaises(UpdateError):
                updater.extract_bundle(archive, Path(work) / "extracted")
            # nothing escaped
            self.assertFalse((Path(work).parent / "evil.txt").exists())


class ReplaceUnixTest(unittest.TestCase):
    def test_replace_swaps_bundle_and_cleans_backup(self):
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            # simulate installed bundle: work/install/ccprofile (+ _internal)
            install = work / "install"
            bundle = install / "ccprofile"
            bundle.mkdir(parents=True)
            (bundle / "ccprofile").write_text("OLD")
            (bundle / "_internal").mkdir()
            (bundle / "_internal" / "lib.so").write_text("old-lib")

            # the "new" extracted bundle
            new_bundle = work / "new" / "ccprofile"
            new_bundle.mkdir(parents=True)
            (new_bundle / "ccprofile").write_text("NEW")

            with unittest.mock.patch.object(updater, "_bundle_dir", return_value=bundle), \
                 unittest.mock.patch.object(updater, "is_frozen", return_value=True):
                updater.replace_bundle_unix(new_bundle)

            self.assertEqual((bundle / "ccprofile").read_text(), "NEW")
            self.assertFalse((install / "ccprofile.old").exists())

    def test_replace_rolls_back_on_move_failure(self):
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            install = work / "install"
            bundle = install / "ccprofile"
            bundle.mkdir(parents=True)
            (bundle / "ccprofile").write_text("OLD")

            # A non-existent new bundle makes the second move fail for real,
            # exercising the rollback path without mocking shutil.move.
            missing_new = work / "does-not-exist" / "ccprofile"

            with unittest.mock.patch.object(updater, "_bundle_dir", return_value=bundle), \
                 unittest.mock.patch.object(updater, "is_frozen", return_value=True):
                with self.assertRaises(UpdateError):
                    updater.replace_bundle_unix(missing_new)
            # rolled back: original exe restored, backup cleaned up
            self.assertEqual((bundle / "ccprofile").read_text(), "OLD")
            self.assertFalse((install / "ccprofile.old").exists())


class ReplaceWindowsTest(unittest.TestCase):
    def test_writes_bat_and_spawns_detached(self):
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            new_bundle = work / "new" / "ccprofile"
            new_bundle.mkdir(parents=True)
            (new_bundle / "ccprofile.exe").write_text("NEW")

            target = work / "target" / "ccprofile"

            with unittest.mock.patch.object(updater, "_bundle_dir", return_value=target), \
                 unittest.mock.patch.object(updater.tempfile, "gettempdir", return_value=str(work)), \
                 unittest.mock.patch.object(updater.os, "getpid", return_value=4242), \
                 unittest.mock.patch.object(updater.subprocess, "Popen") as popen:
                updater.replace_bundle_windows(new_bundle)

            staging_parent = work / "ccprofile-update-4242"
            self.assertTrue((staging_parent / "ccprofile" / "ccprofile.exe").exists())
            bat = staging_parent.with_suffix(".bat")
            self.assertTrue(bat.exists())
            content = bat.read_text("utf-8")
            self.assertIn("4242", content)
            self.assertIn(str(target), content)
            self.assertIn("tries", content)
            self.assertIn("giveup", content)
            # success path must jump past :giveup so a successful replace
            # never writes the failure marker / exits 1
            self.assertIn("goto done", content)
            self.assertLess(content.index("goto done"), content.index(":giveup"))
            popen.assert_called_once()


class LaunchCheckTest(unittest.TestCase):
    def test_skips_when_env_set(self):
        with unittest.mock.patch.dict(os.environ, {"CCPROFILE_NO_UPDATE_CHECK": "1"}), \
             unittest.mock.patch.object(updater, "is_frozen", return_value=True), \
             unittest.mock.patch.object(updater, "fetch_latest_release") as fetch:
            updater.maybe_check_on_launch()
        fetch.assert_not_called()

    def test_skips_when_not_frozen(self):
        with unittest.mock.patch.object(updater, "is_frozen", return_value=False), \
             unittest.mock.patch.object(updater, "fetch_latest_release") as fetch:
            updater.maybe_check_on_launch()
        fetch.assert_not_called()

    def test_prints_hint_when_cached_version_is_newer(self):
        cache = {"last_check_ts": 0, "latest_known": "9.9.9"}  # 0 -> always re-check allowed
        with unittest.mock.patch.object(updater, "is_frozen", return_value=True), \
             unittest.mock.patch.object(updater, "_load_check_cache", return_value=cache), \
             unittest.mock.patch.object(updater, "_save_check_cache") as save, \
             unittest.mock.patch.object(updater, "fetch_latest_release", return_value={"version": "9.9.9"}):
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                updater.maybe_check_on_launch()
        self.assertIn("9.9.9", err.getvalue())
        save.assert_called_once()

    def test_silent_when_up_to_date(self):
        cache = {"last_check_ts": 0}
        with unittest.mock.patch.object(updater, "is_frozen", return_value=True), \
             unittest.mock.patch.object(updater, "_load_check_cache", return_value=cache), \
             unittest.mock.patch.object(updater, "_save_check_cache"), \
             unittest.mock.patch.object(updater, "fetch_latest_release", return_value={"version": "0.0.1"}):
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                updater.maybe_check_on_launch()
        self.assertEqual(err.getvalue(), "")

    def test_silent_on_network_error(self):
        cache = {"last_check_ts": 0}
        with unittest.mock.patch.object(updater, "is_frozen", return_value=True), \
             unittest.mock.patch.object(updater, "_load_check_cache", return_value=cache), \
             unittest.mock.patch.object(updater, "_save_check_cache"), \
             unittest.mock.patch.object(updater, "fetch_latest_release", side_effect=updater.UpdateError("net")):
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                updater.maybe_check_on_launch()  # must not raise
        self.assertEqual(err.getvalue(), "")


class CmdUpdateTest(unittest.TestCase):
    def _upd_args(self, **kw):
        base = dict(check=False, yes=False, force=False, prerelease=False)
        base.update(kw)
        return SimpleNamespace(**base)

    def _patches(self, **overrides):
        defaults = dict(
            fetch_latest_release=unittest.mock.DEFAULT,
            download_to=unittest.mock.DEFAULT,
            expected_sha256=unittest.mock.DEFAULT,
            verify_sha256=unittest.mock.DEFAULT,
            extract_bundle=unittest.mock.DEFAULT,
            replace_bundle_unix=unittest.mock.DEFAULT,
            replace_bundle_windows=unittest.mock.DEFAULT,
            is_frozen=unittest.mock.DEFAULT,
            platform_asset=unittest.mock.DEFAULT,
            confirm_action=unittest.mock.DEFAULT,
        )
        defaults.update(overrides)
        patches = []
        for k, v in defaults.items():
            if v is not unittest.mock.DEFAULT and not isinstance(v, unittest.mock.Mock):
                mock = unittest.mock.MagicMock(side_effect=v)
                patches.append(unittest.mock.patch.object(updater, k, mock))
            else:
                patches.append(unittest.mock.patch.object(updater, k, v))
        return patches

    def test_up_to_date_does_not_download(self):
        with unittest.mock.patch.object(updater, "VERSION", "0.9.0"):
            for p in self._patches(
                fetch_latest_release=lambda: {"version": "0.9.0", "body": "", "assets": {}}
            ):
                p.start()
            self.addCleanup(unittest.mock.patch.stopall)
            updater.cmd_update(self._upd_args())
        updater.download_to.assert_not_called()

    def test_check_only_does_not_replace(self):
        with unittest.mock.patch.object(updater, "VERSION", "0.3.0"):
            for p in self._patches(
                fetch_latest_release=lambda: {"version": "0.4.0", "body": "x", "assets": {}}
            ):
                p.start()
            self.addCleanup(unittest.mock.patch.stopall)
            updater.cmd_update(self._upd_args(check=True))
        updater.replace_bundle_unix.assert_not_called()

    def test_yes_updates_on_unix(self):
        def fake_download(url, dest, timeout=30):
            Path(dest).write_bytes(b"data")

        with unittest.mock.patch.object(updater, "VERSION", "0.3.0"), \
             unittest.mock.patch.object(sys, "platform", "linux"):
            for p in self._patches(
                fetch_latest_release=lambda: {
                    "version": "0.4.0", "body": "x",
                    "assets": {"ccprofile-linux.tar.gz": "u", "SHA256SUMS": "s"},
                },
                download_to=fake_download,
                platform_asset=lambda: "ccprofile-linux.tar.gz",
                expected_sha256=lambda name, text: "abc",
                verify_sha256=lambda path, expected: True,
                extract_bundle=lambda a, d: Path(str(a)),
            ):
                p.start()
            self.addCleanup(unittest.mock.patch.stopall)
            updater.cmd_update(self._upd_args(yes=True))
        updater.download_to.assert_called()
        updater.replace_bundle_unix.assert_called_once()
        updater.replace_bundle_windows.assert_not_called()

    def test_not_frozen_aborts_before_replace(self):
        with unittest.mock.patch.object(updater, "VERSION", "0.3.0"):
            for p in self._patches(
                fetch_latest_release=lambda: {"version": "0.4.0", "body": "", "assets": {}},
                is_frozen=lambda: False,
                verify_sha256=lambda path, expected: True,
                extract_bundle=lambda a, d: Path(str(a)),
            ):
                p.start()
            self.addCleanup(unittest.mock.patch.stopall)
            updater.cmd_update(self._upd_args(yes=True))
        updater.replace_bundle_unix.assert_not_called()


if __name__ == "__main__":
    unittest.main()