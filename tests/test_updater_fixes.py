"""Targeted regression tests for the updater review fixes.

Separate from tests/test_updater.py to avoid merge collisions with parallel
work on the updater module (same convention as test_updater_cli.py).
"""

import contextlib
import io
import sys
import tarfile
import tempfile
import unittest
import unittest.mock
from email.message import Message
from pathlib import Path
from urllib.error import HTTPError

from ccprofile_app import updater


# ── expected_sha256: binary-mode `sha256sum -b` (* prefix) ──

class BinaryModeShaTest(unittest.TestCase):
    def test_parses_binary_mode_star_prefix(self):
        text = "abc123 *ccprofile-linux.tar.gz\n"
        self.assertEqual(
            updater.expected_sha256("ccprofile-linux.tar.gz", text), "abc123"
        )

    def test_still_parses_text_mode(self):
        text = "abc123  ccprofile-linux.tar.gz\nffff  other.zip\n"
        self.assertEqual(
            updater.expected_sha256("ccprofile-linux.tar.gz", text), "abc123"
        )


# ── tar extraction: symlink / hardlink escape ──

class TarLinkTraversalTest(unittest.TestCase):
    def _archive_with(self, work, member_type, linkname):
        archive = work / "bundle.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            data = b"exe"
            info = tarfile.TarInfo("ccprofile/ccprofile")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
            link = tarfile.TarInfo("ccprofile/evil")
            link.type = member_type
            link.linkname = linkname
            tar.addfile(link)
        return archive

    def test_rejects_escaping_symlink(self):
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            archive = self._archive_with(work, tarfile.SYMTYPE, "../../escape")
            with self.assertRaises(updater.UpdateError):
                updater.extract_bundle(archive, work / "extracted")
            # nothing materialized outside the extraction dir
            self.assertFalse((work / "escape").exists())

    def test_rejects_escaping_hardlink(self):
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            archive = self._archive_with(work, tarfile.LNKTYPE, "../../escape_hard")
            with self.assertRaises(updater.UpdateError):
                updater.extract_bundle(archive, work / "extracted")
            self.assertFalse((work / "escape_hard").exists())


# ── _http_get_json: 403 rate-limit vs non-rate-limit ──

def _http_err(code, remaining=None):
    hdrs = Message()
    if remaining is not None:
        hdrs["X-RateLimit-Remaining"] = remaining
    return HTTPError("https://api.github.com/x", code, "Forbidden", hdrs, io.BytesIO(b"{}"))


class RateLimitDetectionTest(unittest.TestCase):
    def test_403_with_zero_remaining_is_rate_limited(self):
        with unittest.mock.patch("urllib.request.urlopen", side_effect=_http_err(403, "0")):
            with self.assertRaises(updater.RateLimitedError):
                updater._http_get_json("https://api.github.com/x")

    def test_403_with_budget_remaining_is_generic_error(self):
        with unittest.mock.patch("urllib.request.urlopen", side_effect=_http_err(403, "58")):
            with self.assertRaises(updater.UpdateError) as cm:
                updater._http_get_json("https://api.github.com/x")
        self.assertNotIsInstance(cm.exception, updater.RateLimitedError)

    def test_429_is_rate_limited(self):
        with unittest.mock.patch("urllib.request.urlopen", side_effect=_http_err(429)):
            with self.assertRaises(updater.RateLimitedError):
                updater._http_get_json("https://api.github.com/x")


# ── replace_bundle() dispatcher ──

class ReplaceDispatchTest(unittest.TestCase):
    def test_unix_routes_to_unix_replacer(self):
        with unittest.mock.patch.object(sys, "platform", "linux"), \
             unittest.mock.patch.object(updater, "replace_bundle_unix") as u, \
             unittest.mock.patch.object(updater, "replace_bundle_windows") as w:
            updater.replace_bundle(Path("/x"), version="1.0.0")
        u.assert_called_once()
        w.assert_not_called()

    def test_windows_routes_to_windows_replacer(self):
        with unittest.mock.patch.object(sys, "platform", "win32"), \
             unittest.mock.patch.object(updater, "replace_bundle_unix") as u, \
             unittest.mock.patch.object(updater, "replace_bundle_windows") as w:
            updater.replace_bundle(Path("/x"), version="1.0.0")
        w.assert_called_once()
        u.assert_not_called()


# ── _download_pair: concurrent, error propagation ──

class DownloadPairTest(unittest.TestCase):
    def test_downloads_both(self):
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            calls = []

            def fake(url, dest, timeout=30):
                calls.append(url)
                Path(dest).write_bytes(b"x")

            with unittest.mock.patch.object(updater, "download_to", side_effect=fake):
                updater._download_pair(
                    "https://a/asset", work / "asset",
                    "https://a/sums", work / "sums",
                )
            self.assertEqual(sorted(calls), ["https://a/asset", "https://a/sums"])

    def test_propagates_error_from_either_fetch(self):
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)

            def fake(url, dest, timeout=30):
                if "sums" in url:
                    raise updater.UpdateError("net")
                Path(dest).write_bytes(b"x")

            with unittest.mock.patch.object(updater, "download_to", side_effect=fake):
                with self.assertRaises(updater.UpdateError):
                    updater._download_pair(
                        "https://a/asset", work / "asset",
                        "https://a/sums", work / "sums",
                    )


# ── Windows .bat hardening ──

class WindowsBatHardeningTest(unittest.TestCase):
    def _write_bat(self, work, target):
        new_bundle = work / "new" / "ccprofile"
        new_bundle.mkdir(parents=True)
        (new_bundle / "ccprofile.exe").write_text("NEW")
        with unittest.mock.patch.object(updater, "_bundle_dir", return_value=target), \
             unittest.mock.patch.object(updater.tempfile, "gettempdir", return_value=str(work)), \
             unittest.mock.patch.object(updater.os, "getpid", return_value=4242), \
             unittest.mock.patch.object(updater.subprocess, "Popen"):
            updater.replace_bundle_windows(new_bundle)
        return (work / "ccprofile-update-4242.bat").read_text("utf-8")

    def test_wait_loop_is_bounded(self):
        with tempfile.TemporaryDirectory() as work:
            content = self._write_bat(Path(work), Path(work) / "target" / "ccprofile")
        self.assertIn("waits", content)
        self.assertIn("if %waits% gtr 60 goto giveup", content)

    def test_giveup_cleans_up_and_self_deletes(self):
        with tempfile.TemporaryDirectory() as work:
            content = self._write_bat(Path(work), Path(work) / "target" / "ccprofile")
        giveup = content[content.index(":giveup"):content.index(":done")]
        self.assertIn('rmdir /s /q', giveup)
        self.assertIn('del "%~f0"', giveup)

    def test_post_move_check_is_non_destructive(self):
        # After a successful move the verify line must NOT branch back to the
        # destructive :replace loop (which would rmdir the just-installed bundle).
        with tempfile.TemporaryDirectory() as work:
            content = self._write_bat(Path(work), Path(work) / "target" / "ccprofile")
        verify_line = next(
            ln for ln in content.splitlines() if "ccprofile.exe" in ln
        )
        self.assertNotIn("goto replace", verify_line)

    def test_percent_in_path_is_escaped(self):
        # A literal % in the install path must be doubled so cmd won't expand it.
        target = Path("/fake/a%NAME%b/ccprofile")
        with tempfile.TemporaryDirectory() as work:
            content = self._write_bat(Path(work), target)
        self.assertIn("%%NAME%%", content)
        self.assertNotIn("%NAME%", content.replace("%%NAME%%", "X"))


if __name__ == "__main__":
    unittest.main()
