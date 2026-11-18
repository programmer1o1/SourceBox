import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from sourcebox import install_manifest
from sourcebox.bridges import BridgeManager
from sourcebox.bridges.modern_vscript import ModernVScriptBridge
from sourcebox.install_manifest import (
    GUARD_FLAG,
    InstallManifest,
    build_guard_command,
    run_cleanup_guard,
)


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.game = self.root / "game"
        self.game.mkdir()
        self.manifest = InstallManifest(self.root / "state")

    def tearDown(self):
        self.temp.cleanup()

    def test_created_files_and_folders_are_removed(self):
        target = self.game / "scripts" / "vscripts" / "bridge.nut"
        self.manifest.write_text(target, "print(1)\n")
        self.assertTrue(target.exists())

        self.manifest.undo()
        self.assertFalse(target.exists())
        self.assertFalse((self.game / "scripts").exists())
        self.assertTrue(self.game.exists(), "folders that existed before are kept")
        self.assertFalse(Path(self.manifest.path).exists())

    def test_replaced_file_gets_its_original_back(self):
        target = self.game / "mapspawn.nut"
        target.write_text("original\n")
        self.manifest.write_text(target, "sourcebox\n")
        self.manifest.write_text(target, "sourcebox again\n")  # rewrites keep the first backup
        self.assertEqual(target.read_text(), "sourcebox again\n")

        self.manifest.undo()
        self.assertEqual(target.read_text(), "original\n")
        self.assertFalse(Path(self.manifest.backup_dir).exists())

    def test_file_edited_after_install_is_left_alone(self):
        target = self.game / "picker.nut"
        self.manifest.write_text(target, "ours\n")
        target.write_text("edited by hand\n")

        done = self.manifest.undo()
        self.assertEqual(target.read_text(), "edited by hand\n")
        self.assertIn(("kept, changed since install", str(target)), done)

    def test_existing_sourcebox_file_is_not_treated_as_an_original(self):
        # left by an older SourceBox that did not record anything
        target = self.game / "mapspawn.nut"
        target.write_text("// auto-load python bridge listener on map spawn\nold version\n")
        self.manifest.write_text(target, "new version\n", ours_marker="auto-load python bridge listener")

        self.manifest.undo()
        self.assertFalse(target.exists())

    def test_transient_files_go_whatever_they_contain(self):
        command = self.game / "python_command.txt"
        self.manifest.track(command)
        command.write_text('{"id": 7}')
        self.manifest.track(self.game / "never_written.txt")

        self.manifest.undo()
        self.assertFalse(command.exists())

    def test_leftovers_from_a_killed_sourcebox_are_undone_by_a_new_instance(self):
        target = self.game / "bridge.nut"
        self.manifest.write_text(target, "x\n")
        # the old process is gone; a new manifest object reads its record
        fresh = InstallManifest(self.root / "state")
        fresh.undo_leftovers()
        self.assertFalse(target.exists())
        self.assertEqual(InstallManifest(self.root / "state").undo_leftovers(), [])

    def test_guard_waits_for_the_parent_then_cleans_up(self):
        target = self.game / "bridge.nut"
        self.manifest.write_text(target, "x\n")
        alive = iter([True, True, False])
        sleeps = []
        run_cleanup_guard(
            1234,
            manifest=InstallManifest(self.root / "state"),
            parent_alive=lambda pid: next(alive),
            sleep=sleeps.append,
        )
        self.assertEqual(len(sleeps), 2)
        self.assertFalse(target.exists())

    def test_guard_command_relaunches_this_program(self):
        self.assertEqual(build_guard_command(True, "SourceBox.exe", "x.py", 5), ["SourceBox.exe", GUARD_FLAG, "5"])
        self.assertEqual(build_guard_command(False, "python", "Sourcebox.py", 5),
                         ["python", "Sourcebox.py", GUARD_FLAG, "5"])


class BridgeCleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.manifest = install_manifest.use(InstallManifest(self.root / "state"))

    def tearDown(self):
        install_manifest.use(InstallManifest(tempfile.mkdtemp(prefix="sourcebox-test-manifest-")))
        self.temp.cleanup()

    def test_portal2_install_is_fully_reverted(self):
        mod = self.root / "Portal 2" / "portal2"
        vscripts = mod / "scripts" / "vscripts"
        vscripts.mkdir(parents=True)
        (vscripts / "mapspawn.nut").write_text('printl("==== calling mapspawn.nut")\n')
        before = sorted(str(p.relative_to(mod)) for p in mod.rglob("*"))

        bridge = ModernVScriptBridge("portal2", mod)
        bridge.prepare_paths()
        bridge.install_scripts()
        bridge.send_command('{"id":1}')
        self.assertIn("sourcebox_bridge.nut", os.listdir(vscripts))

        self.manifest.undo()
        after = sorted(str(p.relative_to(mod)) for p in mod.rglob("*"))
        self.assertEqual(after, before)
        self.assertEqual((vscripts / "mapspawn.nut").read_text(), 'printl("==== calling mapspawn.nut")\n')

    def _untracked_files(self, folder):
        return sorted(p.name for p in folder.iterdir())

    def test_stray_original_copy_from_an_old_version_is_cleaned_up(self):
        # P2CE after an old SourceBox: its loader is gone but the copy stayed
        game_root = self.root / "Portal 2 Community Edition"
        shadowed = game_root / "portal2" / "portal2" / "scripts" / "vscripts" / "mapspawn.nut"
        shadowed.parent.mkdir(parents=True)
        shadowed.write_text("printl(1)\n")
        vscripts = game_root / "p2ce" / "scripts" / "vscripts"
        vscripts.mkdir(parents=True)
        (vscripts / "document.nut").write_text("// game file\n")
        (vscripts / "sourcebox_original_mapspawn.nut").write_text("printl(1)\n")

        bridge = ModernVScriptBridge("strata", game_root / "p2ce", [str(shadowed)])
        bridge.prepare_paths()
        bridge.install_scripts()
        self.assertIn("sourcebox_original_mapspawn", (vscripts / "mapspawn.nut").read_text())

        self.manifest.undo()
        self.assertEqual(self._untracked_files(vscripts), ["document.nut"])
        self.assertEqual(shadowed.read_text(), "printl(1)\n")

    def test_portal2_mapspawn_saved_only_in_the_copy_is_put_back(self):
        # Portal 2 after an old SourceBox: its loader still in place, the game's
        # own mapspawn.nut only in the copy
        mod = self.root / "Portal 2" / "portal2"
        vscripts = mod / "scripts" / "vscripts"
        vscripts.mkdir(parents=True)
        (vscripts / "mapspawn.nut").write_text("// sourcebox-managed: old loader\n")
        (vscripts / "sourcebox_original_mapspawn.nut").write_text('printl("==== calling mapspawn.nut")\n')

        bridge = ModernVScriptBridge("portal2", mod)
        bridge.prepare_paths()
        bridge.install_scripts()
        self.manifest.undo()

        self.assertEqual(self._untracked_files(vscripts), ["mapspawn.nut"])
        self.assertEqual((vscripts / "mapspawn.nut").read_text(), 'printl("==== calling mapspawn.nut")\n')

    def test_manager_cleans_up_on_close_and_leftovers_on_start(self):
        leftover = self.root / "old" / "bridge.nut"
        self.manifest.write_text(leftover, "x\n")

        source = mock.Mock(active_game=None)
        gmod = mock.Mock()
        gmod.is_connected.return_value = False
        manager = BridgeManager(lambda: source, lambda: gmod, manifest=InstallManifest(self.root / "state"))
        with mock.patch("builtins.print"):
            manager.initialize()
        self.assertFalse(leftover.exists(), "leftovers from a killed SourceBox are removed at start")

        installed = self.root / "game" / "bridge.nut"
        manager.manifest.write_text(installed, "y\n")
        with mock.patch("builtins.print"):
            manager.cleanup()
        self.assertFalse(installed.exists())


if __name__ == "__main__":
    unittest.main()
