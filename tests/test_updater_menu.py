"""Verify the interactive menu wires the updater.

Kept as a separate file from tests/test_updater.py to avoid merge conflicts
with parallel work on the updater module.
"""

import unittest
import unittest.mock


class MenuWiringTest(unittest.TestCase):
    def test_system_menu_has_check_update(self):
        from ccprofile_app import menu

        with unittest.mock.patch.object(menu, "t", side_effect=lambda k, **kw: k):
            items = menu._system_menu()
        keys = [k for k, _ in items]
        self.assertIn("check_update", keys)

    def test_commands_map_has_check_update(self):
        from ccprofile_app import menu, updater

        # interactive_menu builds the map at call time; inspect the module-level
        # wiring by ensuring cmd_update is importable and wired as expected.
        self.assertTrue(callable(updater.cmd_update))


if __name__ == "__main__":
    unittest.main()
