"""Tests for --prerelease release selection and post-update launch-check skip.

Kept separate from tests/test_updater.py to avoid merge conflicts with
parallel work on the updater module (same convention as test_updater_cli.py).
"""

import contextlib
import io
import sys
import unittest
import unittest.mock
from pathlib import Path
from types import SimpleNamespace

from ccprofile_app import updater


def _release(tag, body="", assets=None, draft=False):
    return {"tag_name": tag, "body": body, "draft": draft, "assets": assets or []}


class PrereleaseSelectionTest(unittest.TestCase):
    def setUp(self):
        updater._updated_this_run = False

    def _serve(self, items):
        """Side effect: serve the list for /releases, stable items for /releases/latest."""
        def fake(url, timeout=10):
            if "/releases/latest" in url:
                stables = [i for i in items if "-" not in i["tag_name"]]
                return stables[0] if stables else items[0]
            return items
        return fake

    def test_picks_newest_prerelease_over_older_stable(self):
        items = [_release("v1.5.0", body="stable"), _release("v1.6.0-rc1", body="pre")]
        with unittest.mock.patch.object(updater, "_http_get_json",
                                        side_effect=self._serve(items)):
            rel = updater.fetch_latest_release(include_prerelease=True)
        self.assertEqual(rel["version"], "1.6.0-rc1")
        self.assertEqual(rel["body"], "pre")

    def test_default_path_remains_stable_only(self):
        items = [_release("v1.5.0"), _release("v1.6.0-rc1")]
        with unittest.mock.patch.object(updater, "_http_get_json",
                                        side_effect=self._serve(items)):
            rel = updater.fetch_latest_release()
        self.assertEqual(rel["version"], "1.5.0")

    def test_skips_drafts_even_if_highest(self):
        items = [_release("v9.9.9", draft=True), _release("v1.5.0")]
        with unittest.mock.patch.object(updater, "_http_get_json",
                                        side_effect=self._serve(items)):
            rel = updater.fetch_latest_release(include_prerelease=True)
        self.assertEqual(rel["version"], "1.5.0")

    def test_skips_unparseable_tags(self):
        items = [_release("nightly"), _release("v1.4.0")]
        with unittest.mock.patch.object(updater, "_http_get_json",
                                        side_effect=self._serve(items)):
            rel = updater.fetch_latest_release(include_prerelease=True)
        self.assertEqual(rel["version"], "1.4.0")

    def test_numeric_identifier_compared_numerically(self):
        # SemVer 11: numeric identifiers compared numerically, so alpha.10 > alpha.9.
        items = [_release("v1.0.0-alpha.2"),
                 _release("v1.0.0-alpha.9"),
                 _release("v1.0.0-alpha.10")]
        with unittest.mock.patch.object(updater, "_http_get_json",
                                        side_effect=self._serve(items)):
            rel = updater.fetch_latest_release(include_prerelease=True)
        self.assertEqual(rel["version"], "1.0.0-alpha.10")

    def test_release_outranks_prerelease_of_same_base(self):
        items = [_release("v1.6.0-rc1"), _release("v1.6.0")]
        with unittest.mock.patch.object(updater, "_http_get_json",
                                        side_effect=self._serve(items)):
            rel = updater.fetch_latest_release(include_prerelease=True)
        self.assertEqual(rel["version"], "1.6.0")

    def test_empty_list_raises_update_error(self):
        with unittest.mock.patch.object(updater, "_http_get_json", return_value=[]):
            with self.assertRaises(updater.UpdateError):
                updater.fetch_latest_release(include_prerelease=True)

    def test_rate_limit_propagates(self):
        def rl(url, timeout=10):
            raise updater.RateLimitedError("limited")
        with unittest.mock.patch.object(updater, "_http_get_json", side_effect=rl):
            with self.assertRaises(updater.RateLimitedError):
                updater.fetch_latest_release(include_prerelease=True)

    def test_cmd_update_forwards_prerelease_flag(self):
        with unittest.mock.patch.object(updater, "VERSION", "0.3.0"), \
             unittest.mock.patch.object(
                 updater, "fetch_latest_release",
                 return_value={"tag": "v1.6.0-rc1", "version": "1.6.0-rc1",
                               "body": "", "assets": {}}) as fetch:
            updater.cmd_update(SimpleNamespace(check=True, yes=False,
                                              force=False, prerelease=True))
        self.assertEqual(fetch.call_args, unittest.mock.call(include_prerelease=True))

    def test_cmd_update_download_url_uses_release_tag(self):
        captured = {}

        def fake_download(url, dest, timeout=30):
            captured[url] = dest
            Path(dest).write_bytes(b"data")

        with unittest.mock.patch.object(updater, "VERSION", "0.3.0"), \
             unittest.mock.patch.object(sys, "platform", "linux"), \
             unittest.mock.patch.object(updater, "is_frozen", return_value=True), \
             unittest.mock.patch.object(updater, "fetch_latest_release", return_value={
                 "tag": "v1.6.0-rc1", "version": "1.6.0-rc1", "body": "",
                 "assets": {}}), \
             unittest.mock.patch.object(updater, "download_to", side_effect=fake_download), \
             unittest.mock.patch.object(updater, "platform_asset",
                                        return_value="ccprofile-linux.tar.gz"), \
             unittest.mock.patch.object(updater, "expected_sha256",
                                        return_value="abc"), \
             unittest.mock.patch.object(updater, "verify_sha256", return_value=True), \
             unittest.mock.patch.object(updater, "extract_bundle",
                                        side_effect=lambda a, d: Path(str(a))), \
             unittest.mock.patch.object(updater, "replace_bundle_unix"):
            updater.cmd_update(SimpleNamespace(check=False, yes=True,
                                               force=False, prerelease=True))
        urls = list(captured.keys())
        self.assertTrue(all("releases/download/v1.6.0-rc1/" in u for u in urls), urls)
        self.assertFalse(any("releases/latest/download" in u for u in urls), urls)


class PostUpdateLaunchCheckTest(unittest.TestCase):
    def setUp(self):
        updater._updated_this_run = False
        updater._bg_latest = None

    def _emit_stderr(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            updater.emit_launch_hint()
        return err.getvalue()

    def test_hint_shown_when_not_updated(self):
        updater._bg_latest = "9.9.9"
        with unittest.mock.patch.object(updater, "VERSION", "0.3.0"):
            self.assertIn("9.9.9", self._emit_stderr())

    def test_hint_suppressed_after_update(self):
        updater._bg_latest = "9.9.9"
        updater._updated_this_run = True
        with unittest.mock.patch.object(updater, "VERSION", "0.3.0"):
            self.assertEqual(self._emit_stderr(), "")

    def test_cmd_update_sets_flag_after_unix_replace(self):
        def fake_download(url, dest, timeout=30):
            Path(dest).write_bytes(b"data")

        with unittest.mock.patch.object(updater, "VERSION", "0.3.0"), \
             unittest.mock.patch.object(sys, "platform", "linux"), \
             unittest.mock.patch.object(updater, "is_frozen", return_value=True), \
             unittest.mock.patch.object(updater, "fetch_latest_release", return_value={
                 "tag": "v0.4.0", "version": "0.4.0", "body": "x",
                 "assets": {"ccprofile-linux.tar.gz": "u", "SHA256SUMS": "s"}}), \
             unittest.mock.patch.object(updater, "download_to", side_effect=fake_download), \
             unittest.mock.patch.object(updater, "platform_asset",
                                        return_value="ccprofile-linux.tar.gz"), \
             unittest.mock.patch.object(updater, "expected_sha256",
                                        return_value="abc"), \
             unittest.mock.patch.object(updater, "verify_sha256", return_value=True), \
             unittest.mock.patch.object(updater, "extract_bundle",
                                        side_effect=lambda a, d: Path(str(a))), \
             unittest.mock.patch.object(updater, "replace_bundle_unix"):
            updater.cmd_update(SimpleNamespace(check=False, yes=True,
                                               force=False, prerelease=False))
        self.assertTrue(updater._updated_this_run)

    def test_cmd_update_does_not_set_flag_on_not_frozen_abort(self):
        # Aborting before replace (not frozen) must not suppress a later hint.
        with unittest.mock.patch.object(updater, "VERSION", "0.3.0"), \
             unittest.mock.patch.object(updater, "is_frozen", return_value=False), \
             unittest.mock.patch.object(updater, "fetch_latest_release", return_value={
                 "tag": "v0.4.0", "version": "0.4.0", "body": "",
                 "assets": {}}):
            updater.cmd_update(SimpleNamespace(check=False, yes=True,
                                               force=False, prerelease=False))
        self.assertFalse(updater._updated_this_run)


if __name__ == "__main__":
    unittest.main()
