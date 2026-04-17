import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ccprofile_app.filelock import FileLock
from ccprofile_app import storage


class StorageTest(unittest.TestCase):
    def test_filelock_uses_sibling_lock_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "profiles.enc"

            with FileLock(target):
                self.assertFalse(target.exists())
                self.assertTrue(target.with_name("profiles.enc.lock").exists())

    def test_save_proxy_config_uses_private_unique_temp_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            profile_dir = Path(tmpdir)
            proxy_config = profile_dir / "proxy_config.json"
            stale_tmp = profile_dir / "proxy_config.json.tmp"
            stale_tmp.write_text("stale", "utf-8")
            os.chmod(stale_tmp, 0o644)

            with patch.object(storage, "PROFILE_DIR", profile_dir), patch.object(
                storage, "PROXY_CONFIG", proxy_config
            ):
                storage.save_proxy_config({"api_key": "secret"})

            self.assertEqual(stale_tmp.read_text("utf-8"), "stale")
            self.assertIn("secret", proxy_config.read_text("utf-8"))
            if os.name != "nt":
                mode = stat.S_IMODE(proxy_config.stat().st_mode)
                self.assertEqual(mode, 0o600)


if __name__ == "__main__":
    unittest.main()
