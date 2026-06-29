"""Tests for CLI wiring of the `update` subcommand and launch check.

Extracted to a separate file (per task brief deviation) to avoid colliding
with parallel work that also touches tests/test_updater.py.
"""

import unittest
import unittest.mock


class CliWiringTest(unittest.TestCase):
    def test_parser_has_update_flags(self):
        from ccprofile_app import cli

        with unittest.mock.patch.object(cli, "init_language"), \
             unittest.mock.patch.object(cli, "migrate_from_legacy"):
            parser = cli.build_parser()
        ns = parser.parse_args(["update", "--check", "-y", "--force", "--prerelease"])
        self.assertTrue(ns.check)
        self.assertTrue(ns.yes)
        self.assertTrue(ns.force)
        self.assertTrue(ns.prerelease)
        self.assertEqual(ns.command, "update")

    def test_main_dispatches_update_and_runs_launch_check(self):
        from ccprofile_app import cli

        with unittest.mock.patch("sys.argv", ["ccprofile", "update", "-y"]), \
             unittest.mock.patch.object(cli, "cmd_update") as cmd, \
             unittest.mock.patch.object(cli, "migrate_from_legacy"), \
             unittest.mock.patch.object(cli, "maybe_check_on_launch") as launch:
            cli.main()
        cmd.assert_called_once()
        self.assertTrue(cmd.call_args.args[0].yes)
        launch.assert_called_once()


if __name__ == "__main__":
    unittest.main()
