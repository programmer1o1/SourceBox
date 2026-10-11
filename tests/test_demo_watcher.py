import unittest
from types import SimpleNamespace
from unittest import mock

from sourcebox import demo_watcher


class FakePsutilError(Exception):
    pass


def _proc(paths=None, error=None):
    proc = mock.Mock()
    if error:
        proc.open_files.side_effect = error
    else:
        proc.open_files.return_value = [SimpleNamespace(path=p) for p in paths or []]
    return proc


def _fake_psutil(procs):
    return SimpleNamespace(
        Error=FakePsutilError, process_iter=lambda: iter(procs)
    )


class ScanTests(unittest.TestCase):
    def test_detects_open_dem_case_insensitively(self):
        procs = [_proc(["/x/log.txt"]), _proc(["/games/cstrike/A.DEM"])]
        with mock.patch.object(demo_watcher, "psutil", _fake_psutil(procs)):
            self.assertTrue(demo_watcher.scan_for_open_dem())

    def test_ignores_other_files(self):
        with mock.patch.object(
            demo_watcher, "psutil", _fake_psutil([_proc(["/x/a.demo", "/x/b.txt"])])
        ):
            self.assertFalse(demo_watcher.scan_for_open_dem())

    def test_skips_inaccessible_processes(self):
        procs = [_proc(error=FakePsutilError()), _proc(["/x/a.dem"])]
        with mock.patch.object(demo_watcher, "psutil", _fake_psutil(procs)):
            self.assertTrue(demo_watcher.scan_for_open_dem())

    def test_without_psutil_reports_no_demo(self):
        with mock.patch.object(demo_watcher, "psutil", None):
            self.assertFalse(demo_watcher.scan_for_open_dem())


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
                import time

                time.sleep(0.01)
            self.assertTrue(watcher.demo_playing)
        finally:
            watcher.stop()


if __name__ == "__main__":
    unittest.main()
