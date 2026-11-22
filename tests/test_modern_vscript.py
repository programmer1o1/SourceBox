import lzma
import os
import struct
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from source_bridge import SourceBridge
from sourcebox.bridges import BridgeManager
from sourcebox.bridges import csgo_addons
from sourcebox import install_manifest
from sourcebox.bridges.cube_precache import prepare_csgo_physics_map
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


MAP_ENTITIES = b'{\n"classname" "worldspawn"\n}\n\0'


def _map_with_entities(revision, *, compressed=False):
    entities = MAP_ENTITIES
    uncompressed_size = 0
    if compressed:
        stream = lzma.compress(entities, format=lzma.FORMAT_ALONE)
        uncompressed_size = len(entities)
        entities = struct.pack("<4sII5s", b"LZMA", uncompressed_size, len(stream) - 13, stream[:5]) + stream[13:]
    header = bytearray(1036)
    struct.pack_into("<4s5i", header, 0, b"VBSP", 21, len(header), len(entities), 0, uncompressed_size)
    struct.pack_into("<i", header, len(header) - 4, revision)
    return bytes(header) + entities


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

    def test_swarm_stages_custom_cube_and_map_precache_until_cleanup(self):
        mod = self.root / "swarm"
        cube_path = Path("models/props/srcbox/srcbox.mdl")
        custom = mod / "custom" / "srcbox"
        for suffix in (".mdl", ".vvd", ".dx90.vtx", ".phy"):
            _write(custom / cube_path.with_suffix(suffix), suffix)
        existing_model_file = _write(mod / cube_path.with_suffix(".phy"), "existing")

        map_bytes = _map_with_entities(42)
        maps = mod / "maps"
        maps.mkdir()
        for name in ("mission", "patched", "lobby"):
            (maps / f"{name}.bsp").write_bytes(map_bytes)
        user_override = _write(maps / "patched_l_1.lmp", "user override")
        manifest = install_manifest.InstallManifest(self.root / "manifest")
        bridge = ModernVScriptBridge("swarm", mod)
        with mock.patch.object(install_manifest, "_current", manifest), mock.patch("builtins.print"):
            self.assertTrue(bridge.prepare_paths())
            bridge.install_scripts()
            bridge.install_scripts()

        lump = maps / "mission_l_0.lmp"
        data = lump.read_bytes()
        self.assertEqual(struct.unpack_from("<5i", data), (20, 0, 0, len(data) - 20, 42))
        self.assertTrue(data[20:].startswith(map_bytes[1036:-1]))
        self.assertIn(b'"model" "models/props/srcbox/srcbox.mdl"', data)
        self.assertIn(b'"classname" "prop_physics_override"', data)
        self.assertIn(b'"spawnflags" "8192"', data)
        self.assertIn(b'"Template01" "sourcebox_cube_prop"', data)
        self.assertIn(b'"EntityTemplate" "sourcebox_cube_template"', data)
        self.assertTrue(data.endswith(b"\0"))
        self.assertEqual((mod / cube_path).read_text(), ".mdl")
        self.assertEqual(existing_model_file.read_text(), "existing")
        self.assertFalse((maps / "patched_l_0.lmp").exists())
        self.assertFalse((maps / "lobby_l_0.lmp").exists())

        manifest.undo()
        self.assertFalse(lump.exists())
        self.assertFalse((mod / cube_path).exists())
        self.assertTrue((custom / cube_path).exists())
        self.assertEqual(user_override.read_text(), "user override")
        self.assertEqual((maps / "mission.bsp").read_bytes(), map_bytes)
        self.assertEqual(existing_model_file.read_text(), "existing")

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

    def test_portal2_precaches_loose_base_and_dlc_maps(self):
        mod = self.root / "portal2"
        base_maps = mod / "maps"
        dlc_maps = self.root / "portal2_dlc2" / "maps"
        for suffix in (".mdl", ".vvd", ".dx90.vtx", ".phy"):
            _write(mod / "models" / "props" / "srcbox" / f"srcbox{suffix}", suffix)
        base_maps.mkdir()
        dlc_maps.mkdir(parents=True)
        (base_maps / "base.bsp").write_bytes(_map_with_entities(1))
        (base_maps / "shared.bsp").write_bytes(_map_with_entities(2))
        (dlc_maps / "shared.bsp").write_bytes(_map_with_entities(3))
        (dlc_maps / "overridden.bsp").write_bytes(_map_with_entities(4))
        override = _write(base_maps / "overridden_l_0.lmp", "existing patch")

        manifest = install_manifest.InstallManifest(self.root / "manifest")
        bridge = ModernVScriptBridge("portal2", mod)
        with mock.patch.object(install_manifest, "_current", manifest), mock.patch("builtins.print"):
            self.assertTrue(bridge.prepare_paths())
            bridge.install_scripts()

        base_lump = base_maps / "base_l_0.lmp"
        dlc_lump = dlc_maps / "shared_l_0.lmp"
        for path, revision in ((base_lump, 1), (dlc_lump, 3)):
            data = path.read_bytes()
            self.assertEqual(struct.unpack_from("<5i", data)[-1], revision)
            self.assertIn(b'"model" "models/props/srcbox/srcbox.mdl"', data)
            self.assertIn(b'"classname" "env_entity_maker"', data)
        self.assertFalse((base_maps / "shared_l_0.lmp").exists())
        self.assertFalse((dlc_maps / "overridden_l_0.lmp").exists())

        manifest.undo()
        self.assertFalse(base_lump.exists())
        self.assertFalse(dlc_lump.exists())
        self.assertEqual(override.read_text(), "existing patch")

    def test_csgo_prepares_a_separate_bsp_with_a_physics_template(self):
        mod = self.root / "csgo"
        for suffix in (".mdl", ".vvd", ".dx90.vtx", ".phy"):
            _write(mod / "models" / "props" / "srcbox" / f"srcbox{suffix}", suffix)
        maps = mod / "maps"
        maps.mkdir()
        bsp = maps / "de_example.bsp"
        original = _map_with_entities(7, compressed=True)
        bsp.write_bytes(original)
        _write(bsp.with_suffix(".nav"), "stock navigation")
        prepared = prepare_csgo_physics_map(mod, "de_example")
        self.assertEqual(prepared, maps / "de_example_sourcebox.bsp")
        data = prepared.read_bytes()
        offset, length, version, uncompressed_size = struct.unpack_from("<4i", data, 8)
        self.assertEqual(version, 0)
        self.assertEqual(uncompressed_size, 0)
        self.assertEqual(offset % 4, 0)
        self.assertEqual(data[24:len(original)], original[24:])
        entities = data[offset:offset + length]
        self.assertTrue(entities.startswith(MAP_ENTITIES[:-1]))
        self.assertIn(b'"classname" "prop_physics_override"', entities)
        self.assertIn(b'"spawnflags" "8192"', entities)
        self.assertIn(b'"EntityTemplate" "sourcebox_cube_template"', entities)
        self.assertEqual(prepared.with_suffix(".nav").read_text(), "stock navigation")
        with self.assertRaises(FileExistsError):
            prepare_csgo_physics_map(mod, "de_example")
        self.assertEqual(bsp.read_bytes(), original)
        self.assertEqual(prepared.read_bytes(), data)

    def test_csgo_entity_lump_decodes_when_known_size_is_rejected(self):
        # Simulate liblzma < 5.4, which rejects a known size followed by an end marker.
        real = lzma.LZMADecompressor
        calls = []

        def old_liblzma(*args, **kwargs):
            calls.append(None)
            decoder = real(*args, **kwargs)
            if len(calls) == 1:
                decoder = mock.Mock(decompress=mock.Mock(side_effect=lzma.LZMAError("Corrupt input data")))
            return decoder

        mod = self.root / "csgo"
        for suffix in (".mdl", ".vvd", ".dx90.vtx", ".phy"):
            _write(mod / "models" / "props" / "srcbox" / f"srcbox{suffix}", suffix)
        (mod / "maps").mkdir()
        (mod / "maps" / "de_example.bsp").write_bytes(_map_with_entities(7, compressed=True))
        with mock.patch("sourcebox.bridges.cube_precache.lzma.LZMADecompressor", side_effect=old_liblzma):
            prepared = prepare_csgo_physics_map(mod, "de_example")
        self.assertIn(b'"classname" "prop_physics_override"', prepared.read_bytes())
        self.assertEqual(len(calls), 2)

    def test_csgo_installs_missing_addons_once_and_keeps_custom_configuration(self):
        mod = self.root / "legacy" / "csgo"
        gameinfo = _write(mod / "gameinfo.txt", "original")
        executable = mod.parent / "csgo.exe"
        exe_header = bytearray(64)
        exe_header[:2] = b"MZ"
        struct.pack_into("<I", exe_header, 60, 64)
        executable.write_bytes(exe_header + b"PE\0\0\x4c\x01")
        for suffix in (".mdl", ".vvd", ".dx90.vtx", ".phy"):
            _write(mod / "models" / "props" / "srcbox" / f"srcbox{suffix}", suffix)
        config = _write(mod / csgo_addons.STRIPPER_CONFIG, "; custom rules\n")
        original = config.read_bytes()
        manifest = install_manifest.InstallManifest(self.root / "manifest")
        bridge = ModernVScriptBridge("csgo", mod)
        with (
            mock.patch.object(install_manifest, "_current", manifest),
            mock.patch.object(csgo_addons, "_download_members",
                              side_effect=lambda url, digest, members: dict.fromkeys(members, b"release file")) as download,
            mock.patch("builtins.print"),
        ):
            self.assertTrue(bridge.prepare_paths())
            bridge.install_scripts()
            bridge.install_scripts()
        self.assertEqual(download.call_count, len(csgo_addons.PACKAGES))
        self.assertIn(b"; SourceBox cube template", config.read_bytes())
        self.assertEqual(gameinfo.read_text(), "original")
        manifest.undo()
        self.assertEqual(config.read_bytes(), original)
        self.assertTrue((mod / "addons/metamod.vdf").is_file())
        self.assertTrue((mod / "addons/metamod/stripper.vdf").is_file())

    def test_csgo_installs_and_restores_the_stripper_template(self):
        mod = self.root / "csgo"
        for suffix in (".mdl", ".vvd", ".dx90.vtx", ".phy"):
            _write(mod / "models" / "props" / "srcbox" / f"srcbox{suffix}", suffix)
        stripper = mod / "addons" / "stripper"
        _write(stripper / "bin" / "stripper.2.csgo.dll")
        config = _write(stripper / "global_filters.cfg", "; custom rules\r\n")
        original = config.read_bytes()
        manifest = install_manifest.InstallManifest(self.root / "manifest")
        bridge = ModernVScriptBridge("csgo", mod)
        with mock.patch.object(install_manifest, "_current", manifest), mock.patch("builtins.print"):
            self.assertTrue(bridge.prepare_paths())
            bridge.install_scripts()
            bridge.install_scripts()

        staged = config.read_bytes()
        self.assertTrue(staged.startswith(original))
        self.assertEqual(staged.count(b"; SourceBox cube template"), 1)
        self.assertIn(b'"targetname" "/^sourcebox_cube_(prop|template|maker)$/"', staged)
        self.assertIn(b'"classname" "prop_physics_override"', staged)
        self.assertIn(b'"spawnflags" "8192"', staged)
        self.assertIn(b'"EntityTemplate" "sourcebox_cube_template"', staged)
        manifest.undo()
        self.assertEqual(config.read_bytes(), original)

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

    def test_older_revolution_runtime_is_recognised(self):
        runtime_dir = self.root / "bin" / "win64"
        (runtime_dir / "scriptsystem.dll").rename(runtime_dir / "vscript.dll")

        self.assertEqual(find_strata_game(self.exe), (
            "Portal: Revolution", str(self.root / "revolution"), str(self.root),
        ))
        self.assertIsNone(find_strata_game(str(_write(runtime_dir / "portal2.exe"))))


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
        self.detected_games = []
        self.modern_bridge = None
        self.mapbase_bridge = None
        self._running_exe = running_exe

    def _log(self, message):
        pass


class DiscoveryTests(unittest.TestCase):
    def test_crossover_revolution_uses_the_game_library(self):
        with tempfile.TemporaryDirectory() as temp:
            steam = Path(temp) / "Steam"
            library = Path(temp) / "Games"
            root = library / "steamapps" / "common" / "Portal Revolution"
            mod = root / "revolution"
            _write(mod / "gameinfo.txt", 'game "Portal: Revolution"')
            model = Path("models/props/srcbox/srcbox.mdl")
            for suffix in (".mdl", ".vvd", ".dx90.vtx", ".phy"):
                _write(mod / "custom" / "srcbox" / model.with_suffix(suffix), suffix)
            bsp = mod / "maps" / "sp_a1_begin.bsp"
            bsp.parent.mkdir()
            bsp.write_bytes(_map_with_entities(12))
            _write(root / "bin" / "win64" / "revolution.exe")
            _write(root / "bin" / "win64" / "vscript.dll")
            process = mock.Mock(info={
                "name": "wine64-preloader",
                "exe": str(steam / "wine64-preloader"),
                "cmdline": [r"S:\steamapps\common\Portal Revolution\bin\win64\revolution.exe"],
            })
            discovery = FakeDiscovery()
            discovery._get_steam_install_path = mock.Mock(return_value=str(steam))
            discovery._parse_library_folders_vdf = mock.Mock(return_value=[str(steam), str(library)])
            with (
                mock.patch("sourcebox.bridges.source_discovery.psutil.process_iter", return_value=[process]),
                mock.patch("builtins.print"),
            ):
                discovery._detect_running_game()

            self.assertEqual(discovery.active_game, "Portal: Revolution")
            self.assertEqual(discovery.modern_bridge.branch, "revolution")
            self.assertTrue((mod / "scripts" / "vscripts" / BRIDGE_SCRIPT).is_file())
            self.assertIn('targetname = "sourcebox_cube_precache"', (mod / "scripts/vscripts/mapspawn.nut").read_text())
            self.assertTrue((mod / model).is_file())
            self.assertIn(b'"targetname" "sourcebox_cube_maker"', bsp.with_name("sp_a1_begin_l_0.lmp").read_bytes())

    def test_csgo_uses_crossover_working_directory_for_renamed_install(self):
        with tempfile.TemporaryDirectory() as temp:
            library = Path(temp) / "SteamLibrary"
            common = library / "steamapps" / "common"
            standard = common / "Counter-Strike Global Offensive" / "csgo"
            _write(standard / "gameinfo.txt", 'game "Counter-Strike Global Offensive"')
            legacy_root = common / "csgo legacy"
            legacy = legacy_root / "csgo"
            _write(legacy_root / "csgo.exe")
            _write(legacy / "gameinfo.txt", 'game "Counter-Strike Global Offensive"')
            temporary_exe = _write(Path(temp) / "winetemp" / "csgo.exe")
            process = mock.Mock(info={
                "name": "wine",
                "exe": str(temporary_exe),
                "cwd": str(legacy_root),
                "cmdline": [r"Z:\SteamLibrary\steamapps\common\csgo legacy\csgo.exe"],
            })
            discovery = FakeDiscovery()
            discovery.SUPPORTED_GAMES = SourceBridge.SUPPORTED_GAMES
            discovery._get_steam_install_path = mock.Mock(return_value=str(library))
            discovery._parse_library_folders_vdf = mock.Mock(return_value=[str(library)])
            with (
                mock.patch("sourcebox.bridges.source_discovery.psutil.process_iter", return_value=[process]),
                mock.patch("builtins.print"),
            ):
                discovery._detect_running_game()

            self.assertEqual(discovery.modern_bridge.branch, "csgo")
            self.assertEqual(Path(discovery.modern_bridge.mod_path), legacy)
            self.assertTrue((legacy / "scripts" / "vscripts" / BRIDGE_SCRIPT).is_file())
            self.assertFalse((standard / "scripts").exists())

    def test_wine_launcher_library_does_not_hide_running_alien_swarm(self):
        with tempfile.TemporaryDirectory() as temp:
            launcher_library = Path(temp) / "Steam"
            launcher = _write(launcher_library / "Steam.AppBundle" / "wine")
            (launcher_library / "steamapps").mkdir()
            game_library = Path(temp) / "Games" / "SteamLibrary"
            mod = game_library / "steamapps" / "common" / "Alien Swarm" / "swarm"
            _write(mod / "gameinfo.txt", 'game "Alien Swarm"')
            process = mock.Mock(
                info={
                    "name": "wine",
                    "exe": str(launcher),
                    "cmdline": [str(launcher), r"S:\steamapps\common\Alien Swarm\swarm.exe"],
                },
            )
            discovery = FakeDiscovery()
            discovery.active_game = None
            discovery.SUPPORTED_GAMES = SourceBridge.SUPPORTED_GAMES
            discovery._get_steam_install_path = mock.Mock(return_value=str(launcher_library))
            discovery._parse_library_folders_vdf = mock.Mock(
                return_value=[str(launcher_library), str(game_library)],
            )
            with (
                mock.patch("sourcebox.bridges.source_discovery.psutil.process_iter", return_value=[process]),
                mock.patch("builtins.print"),
            ):
                discovery._detect_running_game()

            self.assertEqual(discovery.active_game, "Alien Swarm")
            self.assertEqual(discovery.modern_bridge.branch, "swarm")
            self.assertEqual(Path(discovery.vscripts_path), mod / "scripts" / "vscripts")
            self.assertTrue((Path(discovery.vscripts_path) / BRIDGE_SCRIPT).is_file())

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
