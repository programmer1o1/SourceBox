import unittest
from unittest import mock

from sourcebox.bridges import BridgeManager


class FakeSourceBridge:
    def __init__(self):
        self.active_game = "Team Fortress 2"
        self.vscripts_path = "/tmp/vscripts"
        self.mapbase_bridge = None
        self.session_id = 1
        self.calls = []

    def __getattr__(self, name):
        if name.startswith("install_") or name in {
            "setup_mapspawn",
            "start_listening",
            "reinstall_awp_outputs",
            "stop",
        }:
            return lambda *args: self.calls.append((name, args))
        raise AttributeError(name)

    def spawn(self, *args):
        self.calls.append(("spawn", args))


class BridgeManagerTests(unittest.TestCase):
    def test_vscript_bridge_setup_and_spawn_are_coordinated(self):
        bridge = FakeSourceBridge()
        manager = BridgeManager(lambda: bridge)

        with mock.patch("builtins.print"):
            manager.initialize()

        setup_names = [name for name, _ in bridge.calls]
        self.assertEqual(
            setup_names,
            [
                "install_listener",
                "install_picker",
                "install_awp_quit",
                "install_auto_spawner",
                "setup_mapspawn",
                "start_listening",
            ],
        )

        with mock.patch("sourcebox.bridges.manager.time.sleep"):
            manager.spawn_default_cube()

        self.assertEqual(bridge.calls[-2][0], "spawn")
        self.assertEqual(
            bridge.calls[-2][1], ("props/srcbox/srcbox.mdl", 200)
        )
        self.assertEqual(bridge.calls[-1][0], "reinstall_awp_outputs")

    def test_no_game_has_actionable_macos_status(self):
        source = mock.Mock(active_game=None)
        gmod = mock.Mock()
        gmod.is_connected.return_value = False
        manager = BridgeManager(
            lambda: source,
            lambda: gmod,
            platform_name="Darwin",
        )

        with mock.patch("builtins.print") as print_mock:
            manager.initialize()
            manager.spawn_default_cube()

        self.assertEqual(manager.status, "no_game")
        self.assertIn("CrossOver", manager.diagnostic_message)
        self.assertIn("sourcebox.log", manager.diagnostic_message)
        self.assertTrue(
            any("Cube spawn skipped" in str(call) for call in print_mock.call_args_list)
        )


if __name__ == "__main__":
    unittest.main()
