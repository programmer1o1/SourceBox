"""Detect Source demo playback by watching for open .dem files."""

import threading

try:
    import psutil
except ImportError:  # pragma: no cover - psutil is a declared requirement
    psutil = None


def scan_for_open_dem():
    """Return True if any process we can inspect holds a .dem file open."""
    if psutil is None:
        return False

    for proc in psutil.process_iter():
        try:
            for open_file in proc.open_files():
                if open_file.path.lower().endswith(".dem"):
                    return True
        except (psutil.Error, OSError):
            continue
    return False


class DemoWatcher:
    """Polls in a background thread so scanning never stalls rendering."""

    def __init__(self, interval=1.0, scan=scan_for_open_dem):
        self._interval = interval
        self._scan = scan
        self._stop = threading.Event()
        self._thread = None
        self.demo_playing = False

    def poll_once(self):
        try:
            self.demo_playing = bool(self._scan())
        except Exception:
            self.demo_playing = False

    def start(self):
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run, name="demo-watcher", daemon=True
        )
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _run(self):
        while not self._stop.is_set():
            self.poll_once()
            self._stop.wait(self._interval)
