import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from sourcebox.bridges import BridgeManager
from sourcebox.bridges.modern_vscript import (
    BRIDGE_SCRIPT,
    MANAGED_MARKER,
    ORIGINAL_HOOK,
    ModernVScriptBridge,
    bridge_script,
    command_script,
    find_strata_game,
    strata_shadowed_hooks,
)
from sourcebox.bridges.source_discovery import SourceGameDiscoveryMixin

ROOT = Path(__file__).resolve().parent.parent


def _write(path, text=""):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _squirrel_code_only(text):
    """Strip comments and string literals so brackets can be counted."""
    out, i, n = [], 0, len(text)
    while i < n:
        if text.startswith("//", i):
            i = text.find("\n", i)
            i = n if i < 0 else i
        elif text[i] == '"':
            i += 1
            while i < n and text[i] != '"':
                i += 2 if text[i] == "\\" else 1
            i += 1
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


class BridgeScriptTests(unittest.TestCase):
    def test_brackets_balance(self):
        code = _squirrel_code_only((ROOT / "bridge_scripts/modern/sourcebox_bridge.nut").read_text())
        for opening, closing in ("{}", "()", "[]"):
            with self.subTest(pair=opening + closing):
                self.assertEqual(code.count(opening), code.count(closing))

    def test_header_names_branch_and_transport(self):
        script = bridge_script("l4d2")
        self.assertTrue(script.startswith(MANAGED_MARKER))
        self.assertIn('::SOURCEBOX_BRANCH <- "l4d2";', script)
        self.assertIn('::SOURCEBOX_TRANSPORT <- "file";', script)
        self.assertIn('::SOURCEBOX_TRANSPORT <- "include";', bridge_script("strata"))

    def test_command_script_is_one_escaped_line(self):
        script = command_script('{"command":"spawn_model","model":"a\\b\n"}')
        self.assertEqual(script.count("\n"), 1)
        self.assertEqual(
            script,
            '::g_sourcebox_command <- "{\\"command\\":\\"spawn_model\\",\\"model\\":\\"a\\\\b \\"}";\n',
        )

    def test_unknown_branch_is_rejected(self):
        with self.assertRaises(ValueError):
            ModernVScriptBridge("source2", "/tmp/x")


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_l4d2_uses_ems_files_and_addon_hook(self):
        mod = self.root / "left4dead2"
        bridge = ModernVScriptBridge("l4d2", mod)
        self.assertTrue(bridge.prepare_paths())
        bridge.install_scripts()

        vscripts = mod / "scripts" / "vscripts"
        self.assertEqual(Path(bridge.command_file), mod / "ems" / "sourcebox_command.txt")
        self.assertEqual(Path(bridge.response_file), mod / "ems" / "sourcebox_response.txt")
        self.assertTrue((vscripts / BRIDGE_SCRIPT).exists())
        hook = (vscripts / "mapspawn_addon.nut").read_text()
        self.assertIn('DoIncludeScript("sourcebox_bridge"', hook)
        self.assertNotIn("sourcebox_original_mapspawn", hook)
        # "{}" when idle: a missing file is how the bridge learns SourceBox closed
        self.assertEqual(Path(bridge.command_file).read_text(), "{}")

        self.assertTrue(bridge.send_command('{"id":1}'))
        self.assertEqual(Path(bridge.command_file).read_text(), '{"id":1}')
        self.assertFalse(Path(bridge.command_file + ".tmp").exists())

    def test_portal2_keeps_the_games_mapspawn_running_first(self):
        mod = self.root / "portal2"
        original = 'printl("==== calling mapspawn.nut")\n'
        _write(mod / "scripts" / "vscripts" / "mapspawn.nut", original)

        bridge = ModernVScriptBridge("portal2", mod)
        bridge.prepare_paths()
        bridge.install_scripts()
        bridge.install_scripts()  # reinstalling must not back up our own hook

        vscripts = mod / "scripts" / "vscripts"
        self.assertEqual((vscripts / ORIGINAL_HOOK).read_text(), original)
        hook = (vscripts / "mapspawn.nut").read_text()
        self.assertLess(hook.index("sourcebox_original_mapspawn"), hook.index("sourcebox_bridge"))
        self.assertIsNone(bridge.response_file)

        self.assertTrue(bridge.send_command('{"command":"spawn_model"}'))
        self.assertEqual(
            Path(bridge.command_file).read_text(),
            '::g_sourcebox_command <- "{\\"command\\":\\"spawn_model\\"}";\n',
        )
        bridge.reset_command()
        self.assertEqual(Path(bridge.command_file).read_text(), '::g_sourcebox_command <- "";\n')

    def test_shutdown_sends_quit_and_gives_the_game_time_to_read_it(self):
        for branch, expected in (
            ("portal2", '::g_sourcebox_command <- "quit";\n'),
            ("l4d2", "quit"),
        ):
            with self.subTest(branch=branch):
                bridge = ModernVScriptBridge(branch, self.root / branch)
                bridge.prepare_paths()
                bridge.install_scripts()
                waits = []
                bridge.shutdown(sleep=waits.append)
                self.assertEqual(Path(bridge.command_file).read_text(), expected)
                self.assertEqual(waits, [ModernVScriptBridge.QUIT_GRACE])

    def test_strata_copies_the_mounted_portal2_mapspawn_it_hides(self):
        game_root = self.root / "Portal 2 Community Edition"
        shadowed = _write(game_root / "portal2" / "portal2" / "scripts" / "vscripts" / "mapspawn.nut", "printl(1)\n")
        bridge = ModernVScriptBridge("strata", game_root / "p2ce", strata_shadowed_hooks(str(game_root)))
        bridge.prepare_paths()
        bridge.install_scripts()

        vscripts = game_root / "p2ce" / "scripts" / "vscripts"
        self.assertEqual((vscripts / ORIGINAL_HOOK).read_text(), "printl(1)\n")
        self.assertIn("sourcebox_original_mapspawn", (vscripts / "mapspawn.nut").read_text())
        self.assertEqual(shadowed.read_text(), "printl(1)\n")


class StrataDetectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "Portal Revolution"
        _write(self.root / "bin" / "win64" / "scriptsystem.dll")
        _write(self.root / "bin" / "win64" / "revolution.exe")
        _write(self.root / "portal2" / "gameinfo.txt", '"GameInfo" { game "Portal 2" }')
        _write(self.root / "revolution" / "gameinfo.txt", '"GameInfo"\n{\n\tgame\t\t"Portal: Revolution"\n}\n')
        self.exe = str(self.root / "bin" / "win64" / "revolution.exe")

    def tearDown(self):
        self.temp.cleanup()

    def test_finds_mod_from_launcher_name(self):
        title, mod_path, root = find_strata_game(self.exe)
        self.assertEqual(title, "Portal: Revolution")
        self.assertEqual(Path(mod_path), self.root / "revolution")
        self.assertEqual(Path(root), self.root)

    def test_game_argument_wins(self):
        _write(self.root / "other" / "gameinfo.txt", 'game "Other Mod"')
        title, mod_path, _root = find_strata_game(self.exe, [self.exe, "-game", "other"])
        self.assertEqual(title, "Other Mod")
        self.assertEqual(Path(mod_path), self.root / "other")

    def test_valve_branch_layout_is_not_strata(self):
        os.remove(self.root / "bin" / "win64" / "scriptsystem.dll")
        self.assertIsNone(find_strata_game(self.exe))
        self.assertIsNone(find_strata_game(None))


class FakeDiscovery(SourceGameDiscoveryMixin):
    SUPPORTED_GAMES = {
        "Portal 2": {
            "executables": ["portal2.exe"],
            "game_dir": "portal2",
            "scriptdata": "scripts/vscripts",
            "cmdline_contains": "Portal 2",
            "vscript_branch": "portal2",
        },
    }

    def __init__(self, running_exe=None):
        self.verbose = False
        self.modern_bridge = None
        self.mapbase_bridge = None
        self._running_exe = running_exe

    def _log(self, message):
        pass


class DiscoveryTests(unittest.TestCase):
    def test_portal2_install_found_from_steam_library(self):
        with tempfile.TemporaryDirectory() as library:
            mod = Path(library) / "steamapps" / "common" / "Portal 2" / "portal2"
            _write(mod / "gameinfo.txt", 'game "Portal 2"')
            discovery = FakeDiscovery()
            with mock.patch("builtins.print"):
                self.assertTrue(discovery._setup_game_path("Portal 2", [library]))
            self.assertEqual(discovery.active_game, "Portal 2")
            self.assertEqual(discovery.modern_bridge.branch, "portal2")
            self.assertTrue((mod / "scripts" / "vscripts" / "sourcebox_bridge.nut").exists())

    def test_running_executable_folder_is_preferred(self):
        with tempfile.TemporaryDirectory() as temp:
            elsewhere = Path(temp) / "games" / "portal2_copy"
            _write(elsewhere / "portal2" / "gameinfo.txt", 'game "Portal 2"')
            discovery = FakeDiscovery(running_exe=str(elsewhere / "portal2.exe"))
            with mock.patch("builtins.print"):
                self.assertTrue(discovery._setup_game_path("Portal 2", []))
            self.assertEqual(Path(discovery.modern_bridge.mod_path), elsewhere / "portal2")

    def test_missing_install_fails_cleanly(self):
        with tempfile.TemporaryDirectory() as library:
            self.assertFalse(FakeDiscovery()._setup_game_path("Portal 2", [library]))


class ManagerTests(unittest.TestCase):
    def test_modern_bridge_skips_tf2_scripts_and_awp(self):
        source = mock.Mock(active_game="Portal 2", vscripts_path="/v", mapbase_bridge=None, session_id=1)
        source.modern_bridge.description = "VScript bridge (portal2, script include)"
        source.modern_bridge.response_file = None
        manager = BridgeManager(lambda: source)

        with mock.patch("builtins.print"):
            manager.initialize()
        source.start_listening.assert_called_once()
        source.install_listener.assert_not_called()
        source.setup_mapspawn.assert_not_called()

        with mock.patch("sourcebox.bridges.manager.time.sleep"):
            manager.spawn_default_cube()
        source.spawn.assert_called_once_with("props/srcbox/srcbox.mdl", 200)
        source.reinstall_awp_outputs.assert_not_called()


if __name__ == "__main__":
    unittest.main()
