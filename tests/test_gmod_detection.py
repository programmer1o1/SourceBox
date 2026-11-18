import unittest
from unittest import mock

import gmod_bridge
import source_bridge
from gmod_bridge import GModBridge
from source_bridge import SourceBridge

RETAIL_WIN64 = r"C:\Program Files (x86)\Steam\steamapps\common\GarrysMod\gmod_win64.exe"


class FakeProcess:
    def __init__(self, name, exe, cmdline):
        self.info = {"name": name, "exe": exe, "cmdline": cmdline}


def _bare(cls):
    """An instance without running the constructor's live process scan."""
    bridge = cls.__new__(cls)
    bridge.verbose = False
    return bridge


class GModWin64DetectionTests(unittest.TestCase):
    def test_gmod_bridge_recognises_the_64_bit_launcher(self):
        processes = [FakeProcess("gmod_win64.exe", RETAIL_WIN64, [RETAIL_WIN64, "-steam"])]
        with mock.patch.object(gmod_bridge.psutil, "process_iter", return_value=processes):
            self.assertEqual(_bare(GModBridge)._detect_running_gmod(), "gmod13")

    def test_source_scan_sets_up_retail_gmod_launched_without_game_argument(self):
        bridge = _bare(SourceBridge)
        bridge.modern_bridge = None
        bridge.mapbase_bridge = None
        bridge._running_exe = None
        processes = [FakeProcess("gmod_win64.exe", RETAIL_WIN64, [RETAIL_WIN64, "-steam"])]
        with mock.patch.object(source_bridge.SourceBridge, "_get_steam_install_path", return_value="C:/Steam"), \
             mock.patch.object(source_bridge.SourceBridge, "_parse_library_folders_vdf", return_value=["C:/Steam"]), \
             mock.patch("sourcebox.bridges.source_discovery.psutil.process_iter", return_value=processes), \
             mock.patch.object(source_bridge.SourceBridge, "_setup_gmod_path", return_value=True) as setup_gmod, \
             mock.patch.object(source_bridge.SourceBridge, "_scan_installed_games") as fallback, \
             mock.patch("builtins.print"):
            bridge._detect_running_game()

        self.assertEqual(setup_gmod.call_args[0][0], "Garry's Mod 13")
        fallback.assert_not_called()

    def test_other_games_without_game_argument_are_not_taken_for_gmod(self):
        bridge = _bare(SourceBridge)
        bridge.modern_bridge = None
        bridge.mapbase_bridge = None
        bridge._running_exe = None
        tf2 = r"C:\Program Files (x86)\Steam\steamapps\common\Team Fortress 2\hl2.exe"
        processes = [FakeProcess("hl2.exe", tf2, [tf2, "-steam"])]
        with mock.patch.object(source_bridge.SourceBridge, "_get_steam_install_path", return_value="C:/Steam"), \
             mock.patch.object(source_bridge.SourceBridge, "_parse_library_folders_vdf", return_value=["C:/Steam"]), \
             mock.patch("sourcebox.bridges.source_discovery.psutil.process_iter", return_value=processes), \
             mock.patch.object(source_bridge.SourceBridge, "_setup_gmod_path", return_value=True) as setup_gmod, \
             mock.patch.object(source_bridge.SourceBridge, "_scan_installed_games"), \
             mock.patch.object(source_bridge.SourceBridge, "_scan_sourcemods"), \
             mock.patch("builtins.print"):
            bridge._detect_running_game()

        setup_gmod.assert_not_called()


if __name__ == "__main__":
    unittest.main()
