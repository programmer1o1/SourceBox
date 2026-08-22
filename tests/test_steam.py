from pathlib import Path
import os
import tempfile
import unittest
from unittest import mock

from sourcebox.steam import (
    command_mentions_executable,
    find_crossover_bottles,
    find_crossover_steam_installs,
    find_steam_install,
    parse_library_folders,
)


class SteamLibraryTests(unittest.TestCase):
    def test_parse_library_folders_preserves_order_and_deduplicates(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            steam = root / "Steam"
            extra = root / "Games"
            (steam / "steamapps").mkdir(parents=True)
            extra.mkdir()
            escaped_extra = str(extra).replace("\\", "\\\\")
            (steam / "steamapps" / "libraryfolders.vdf").write_text(
                f'"libraryfolders"\n{{\n"0" {{ "path" "{steam}" }}\n'
                f'"1" {{ "path" "{escaped_extra}" }}\n'
                f'"2" {{ "path" "{escaped_extra}" }}\n}}',
                encoding="utf-8",
            )

            self.assertEqual(
                parse_library_folders(str(steam)), [str(steam), str(extra)]
            )

    def test_missing_vdf_falls_back_to_primary_library(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            self.assertEqual(
                parse_library_folders(temporary_directory), [temporary_directory]
            )


class CrossOverDiscoveryTests(unittest.TestCase):
    def _create_steam_bottle(self, root: Path, name: str) -> tuple[Path, Path]:
        bottle = root / name
        steam = bottle / "drive_c" / "Program Files (x86)" / "Steam"
        (steam / "steamapps").mkdir(parents=True)
        return bottle, steam

    def test_discovers_steam_in_every_bottle(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            first_bottle, first_steam = self._create_steam_bottle(root, "Steam")
            second_bottle, second_steam = self._create_steam_bottle(root, "Games")

            with mock.patch(
                "sourcebox.steam._running_crossover_bottle", return_value=None
            ):
                self.assertEqual(
                    find_crossover_bottles([root]),
                    [second_bottle, first_bottle],
                )
                self.assertEqual(
                    find_crossover_steam_installs([root]),
                    [str(second_steam), str(first_steam)],
                )

    def test_wineprefix_prioritizes_active_bottle(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            first_bottle, _ = self._create_steam_bottle(root, "First")
            active_bottle, _ = self._create_steam_bottle(root, "Second")

            with mock.patch.dict(
                os.environ, {"WINEPREFIX": str(active_bottle)}, clear=False
            ):
                bottles = find_crossover_bottles([root])

            self.assertEqual(bottles[0], active_bottle)
            self.assertIn(first_bottle, bottles)

    def test_darwin_uses_crossover_steam(self):
        expected = "/tmp/CrossOver/Bottles/Steam/drive_c/Program Files (x86)/Steam"
        with mock.patch("sourcebox.steam.platform.system", return_value="Darwin"):
            with mock.patch(
                "sourcebox.steam.find_crossover_steam_installs",
                return_value=[expected],
            ):
                self.assertEqual(find_steam_install(), expected)

    def test_translates_windows_library_path_inside_bottle(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            bottle = Path(temporary_directory) / "Steam"
            steam = bottle / "drive_c" / "Program Files (x86)" / "Steam"
            library = bottle / "drive_c" / "Games"
            (steam / "steamapps").mkdir(parents=True)
            library.mkdir(parents=True)
            (steam / "steamapps" / "libraryfolders.vdf").write_text(
                '"libraryfolders" { "1" { "path" "C:\\\\Games" } }',
                encoding="utf-8",
            )

            with mock.patch(
                "sourcebox.steam.find_crossover_steam_installs",
                return_value=[str(steam)],
            ):
                self.assertEqual(
                    parse_library_folders(str(steam)),
                    [str(steam), str(library)],
                )

    def test_matches_windows_executable_in_wine_command(self):
        command = [
            "/Applications/CrossOver.app/Contents/SharedSupport/CrossOver/bin/wine",
            r"C:\Program Files (x86)\Steam\steamapps\common\Half-Life 2\hl2.exe",
            "-game",
            "hl2",
        ]
        self.assertTrue(command_mentions_executable(command, ["hl2.exe"]))


if __name__ == "__main__":
    unittest.main()
