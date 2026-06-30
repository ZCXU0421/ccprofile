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

    def test_main_dispatches_update_skipping_background_check(self):
        from ccprofile_app import cli

        with unittest.mock.patch("sys.argv", ["ccprofile", "update", "-y"]), \
             unittest.mock.patch.object(cli, "cmd_update") as cmd, \
             unittest.mock.patch.object(cli, "migrate_from_legacy"), \
             unittest.mock.patch.object(cli, "maybe_check_on_launch") as launch, \
             unittest.mock.patch.object(cli, "emit_launch_hint") as emit:
            cli.main()
        cmd.assert_called_once()
        self.assertTrue(cmd.call_args.args[0].yes)
        # the update subcommand does its own fetch; skip the background check
        launch.assert_not_called()
        emit.assert_called_once()  # exit hint still emitted (muted by _updated_this_run)

    def test_main_runs_background_check_for_other_commands(self):
        from ccprofile_app import cli

        with unittest.mock.patch("sys.argv", ["ccprofile", "current"]), \
             unittest.mock.patch.object(cli, "cmd_current"), \
             unittest.mock.patch.object(cli, "migrate_from_legacy"), \
             unittest.mock.patch.object(cli, "maybe_check_on_launch") as launch, \
             unittest.mock.patch.object(cli, "emit_launch_hint") as emit:
            cli.main()
        launch.assert_called_once()
        emit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
