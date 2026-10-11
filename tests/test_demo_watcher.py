import io
import time
import unittest
from types import SimpleNamespace
from unittest import mock

from sourcebox import demo_watcher


class FakePsutilError(Exception):
    pass


class FakeNoSuchProcess(FakePsutilError):
    pass


def _proc(paths=None, error=None, name="game", cmdline=None, exe=None):
    proc = mock.Mock()
    proc.info = {"name": name, "cmdline": cmdline or [], "exe": exe}
    if error:
        proc.open_files.side_effect = error
    else:
        proc.open_files.return_value = [SimpleNamespace(path=p) for p in paths or []]
    return proc


def _fake_psutil(procs):
    return SimpleNamespace(
        Error=FakePsutilError,
        NoSuchProcess=FakeNoSuchProcess,
        process_iter=lambda attrs=None: iter(procs),
    )


STEAM_CMD = ["Z:\\SteamLibrary\\steamapps\\common\\Counter-Strike Source\\hl2.exe"]


class CandidateTests(unittest.TestCase):
    def test_steamapps_game_is_candidate(self):
        self.assertTrue(demo_watcher.is_candidate("hl2.exe", None, STEAM_CMD))

    def test_exe_path_under_steamapps_is_candidate(self):
        self.assertTrue(
            demo_watcher.is_candidate("hl2_linux", "/home/u/steamapps/common/x/hl2_linux", [])
        )

    def test_wineserver_is_candidate(self):
        self.assertTrue(demo_watcher.is_candidate("wineserver", None, []))

    def test_unrelated_process_is_not_candidate(self):
        self.assertFalse(demo_watcher.is_candidate("Safari", "/Applications/Safari", []))

    def test_missing_fields_do_not_crash(self):
        self.assertFalse(demo_watcher.is_candidate(None, None, None))


class ScannerTests(unittest.TestCase):
    def _scanner(self, procs, clock=None):
        scanner = demo_watcher.DemoScanner(
            refresh_interval=5.0, clock=clock or (lambda: 0.0)
        )
        patcher = mock.patch.object(demo_watcher, "psutil", _fake_psutil(procs))
        patcher.start()
        self.addCleanup(patcher.stop)
        return scanner

    def test_detects_open_dem_in_candidate(self):
        game = _proc(["/games/A.DEM"], cmdline=STEAM_CMD)
        self.assertTrue(self._scanner([game])())

    def test_ignores_other_files(self):
        game = _proc(["/x/a.demo", "/x/b.txt"], cmdline=STEAM_CMD)
        self.assertFalse(self._scanner([game])())

    def test_never_inspects_non_candidates(self):
        other = _proc(["/x/a.dem"], name="Safari")
        game = _proc([], cmdline=STEAM_CMD)
        self.assertFalse(self._scanner([other, game])())
        other.open_files.assert_not_called()

    def test_skips_inaccessible_candidates(self):
        denied = _proc(error=FakePsutilError(), cmdline=STEAM_CMD)
        good = _proc(["/x/a.dem"], name="wineserver")
        self.assertTrue(self._scanner([denied, good])())

    def test_candidate_list_is_cached_between_scans(self):
        game = _proc([], cmdline=STEAM_CMD)
        now = [0.0]
        scanner = self._scanner([game], clock=lambda: now[0])
        calls = []
        real = demo_watcher.psutil.process_iter
        demo_watcher.psutil.process_iter = lambda attrs=None: (
            calls.append(1) or real(attrs)
        )
        scanner()
        now[0] = 1.0
        scanner()
        self.assertEqual(len(calls), 1)
        now[0] = 6.0
        scanner()
        self.assertEqual(len(calls), 2)

    def test_vanished_process_is_dropped(self):
        game = _proc(error=FakeNoSuchProcess(), cmdline=STEAM_CMD)
        scanner = self._scanner([game])
        self.assertFalse(scanner())
        self.assertFalse(scanner())
        self.assertEqual(game.open_files.call_count, 1)

    def test_without_psutil_reports_no_demo(self):
        scanner = demo_watcher.DemoScanner()
        with mock.patch.object(demo_watcher, "psutil", None):
            self.assertFalse(scanner())


class WatcherTests(unittest.TestCase):
    def test_poll_tracks_open_and_close(self):
        results = iter([True, False])
        watcher = demo_watcher.DemoWatcher(scan=lambda: next(results))
        watcher.poll_once()
        self.assertTrue(watcher.demo_playing)
        watcher.poll_once()
        self.assertFalse(watcher.demo_playing)

    def test_scan_failure_means_not_playing(self):
        def boom():
            raise RuntimeError("scan failed")

        watcher = demo_watcher.DemoWatcher(scan=boom)
        watcher.demo_playing = True
        watcher.poll_once()
        self.assertFalse(watcher.demo_playing)

    def test_thread_starts_and_stops(self):
        watcher = demo_watcher.DemoWatcher(interval=0.01, scan=lambda: True)
        watcher.start()
        try:
            for _ in range(200):
                if watcher.demo_playing:
                    break
                time.sleep(0.01)
            self.assertTrue(watcher.demo_playing)
        finally:
            watcher.stop()


class WorkerCommandTests(unittest.TestCase):
    def test_frozen_build_relaunches_the_executable(self):
        cmd = demo_watcher.build_worker_command(
            frozen=True, executable="C:/SourceBox.exe", script="ignored.py", pid=42
        )
        self.assertEqual(cmd, ["C:/SourceBox.exe", "--demo-scan-worker", "42"])

    def test_source_run_launches_script_with_python(self):
        cmd = demo_watcher.build_worker_command(
            frozen=False, executable="/usr/bin/python3", script="/app/Sourcebox.py", pid=42
        )
        self.assertEqual(
            cmd, ["/usr/bin/python3", "/app/Sourcebox.py", "--demo-scan-worker", "42"]
        )


class RunScanWorkerTests(unittest.TestCase):
    def test_writes_one_line_per_scan(self):
        results = iter([False, True, False])
        out = io.StringIO()
        alive = iter([True, True, True, False])
        demo_watcher.run_scan_worker(
            1,
            out,
            scanner=lambda: next(results),
            parent_alive=lambda pid: next(alive),
            sleep=lambda _: None,
        )
        self.assertEqual(out.getvalue(), "0\n1\n0\n")

    def test_exits_immediately_if_parent_is_gone(self):
        out = io.StringIO()
        demo_watcher.run_scan_worker(
            1, out, scanner=lambda: True, parent_alive=lambda pid: False,
            sleep=lambda _: None,
        )
        self.assertEqual(out.getvalue(), "")

    def test_exits_when_pipe_closes(self):
        class Closed:
            def write(self, _):
                raise BrokenPipeError

            def flush(self):
                pass

        demo_watcher.run_scan_worker(
            1, Closed(), scanner=lambda: True, parent_alive=lambda pid: True,
            sleep=lambda _: None,
        )

    def test_scanner_error_reports_no_demo(self):
        def boom():
            raise RuntimeError("scan failed")

        out = io.StringIO()
        alive = iter([True, False])
        demo_watcher.run_scan_worker(
            1, out, scanner=boom, parent_alive=lambda pid: next(alive),
            sleep=lambda _: None,
        )
        self.assertEqual(out.getvalue(), "0\n")


class FakeProcess:
    def __init__(self, lines):
        self.stdout = iter(lines)
        self.terminated = False

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        return 0


class WorkerWatcherTests(unittest.TestCase):
    def _watch(self, lines):
        proc = FakeProcess(lines)
        watcher = demo_watcher.DemoWatcher(spawn=lambda: proc)
        watcher.start()
        watcher._thread.join(timeout=2.0)
        return watcher, proc

    def test_reads_worker_output(self):
        seen = []
        proc = FakeProcess(["0\n", "1\n"])
        watcher = demo_watcher.DemoWatcher(spawn=lambda: proc)
        original = watcher._handle_line

        def spy(line):
            original(line)
            seen.append(watcher.demo_playing)

        watcher._handle_line = spy
        watcher.start()
        watcher._thread.join(timeout=2.0)
        self.assertEqual(seen, [False, True])

    def test_worker_exit_clears_demo_state(self):
        watcher, _ = self._watch(["1\n"])
        self.assertFalse(watcher.demo_playing)

    def test_stop_terminates_worker(self):
        watcher, proc = self._watch([])
        watcher.stop()
        self.assertTrue(proc.terminated)

    def test_spawn_failure_leaves_detection_off(self):
        def boom():
            raise OSError("cannot spawn")

        watcher = demo_watcher.DemoWatcher(spawn=boom)
        watcher.start()
        self.assertFalse(watcher.demo_playing)


if __name__ == "__main__":
    unittest.main()
