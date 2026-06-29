import unittest
import unittest.mock
import hashlib
import platform
import sys
import tarfile
import tempfile
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()