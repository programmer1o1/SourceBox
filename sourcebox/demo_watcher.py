"""Detect Source demo playback by watching for open .dem files."""

import os
import subprocess
import sys
import threading
import time

try:
    import psutil
except ImportError:  # pragma: no cover - psutil is a declared requirement
    psutil = None


def is_candidate(name, exe, cmdline):
    """Cheap check for processes that could be a running Source game.

    Listing a process's open files is expensive (on Windows it walks the whole
    system handle table), so only game processes are ever inspected.
    """
    if (name or "").lower().startswith("wineserver"):
        return True
    haystack = " ".join([exe or "", *(cmdline or [])]).lower()
    return "steamapps" in haystack


class DemoScanner:
    """Reports whether a likely game process holds a .dem file open."""

    def __init__(self, refresh_interval=5.0, clock=time.monotonic):
        self._refresh_interval = refresh_interval
        self._clock = clock
        self._candidates = []
        self._last_refresh = None

    def _refresh_candidates(self):
        self._candidates = [
            proc
            for proc in psutil.process_iter(["name", "exe", "cmdline"])
            if is_candidate(
                proc.info.get("name"), proc.info.get("exe"), proc.info.get("cmdline")
            )
        ]
        self._last_refresh = self._clock()

    def __call__(self):
        if psutil is None:
            return False

        now = self._clock()
        if (
            self._last_refresh is None
            or now - self._last_refresh >= self._refresh_interval
        ):
            self._refresh_candidates()

        found = False
        for proc in list(self._candidates):
            try:
                if any(f.path.lower().endswith(".dem") for f in proc.open_files()):
                    found = True
            except psutil.NoSuchProcess:
                self._candidates.remove(proc)
            except (psutil.Error, OSError):
                continue
        return found


WORKER_FLAG = "--demo-scan-worker"


def build_worker_command(frozen, executable, script, pid):
    """Command line that starts the scan worker for the given parent pid."""
    if frozen:
        return [executable, WORKER_FLAG, str(pid)]
    return [executable, script, WORKER_FLAG, str(pid)]


def _parent_alive(pid):
    return psutil is not None and psutil.pid_exists(pid)


def _lower_priority():
    if psutil is None:
        return
    try:
        if sys.platform == "win32":
            psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
        else:
            psutil.Process().nice(10)
    except Exception:
        pass


def run_scan_worker(
    parent_pid,
    out,
    interval=1.0,
    scanner=None,
    parent_alive=_parent_alive,
    sleep=time.sleep,
):
    """Worker-process loop: print 1 or 0 per scan until the parent goes away.

    psutil holds the GIL while listing open files, so the scan lives in its own
    process and can never stall the render loop.
    """
    scanner = scanner or DemoScanner()
    while parent_alive(parent_pid):
        try:
            playing = bool(scanner())
        except Exception:
            playing = False
        try:
            out.write("1\n" if playing else "0\n")
            out.flush()
        except (BrokenPipeError, OSError, ValueError):
            return
        sleep(interval)


def _spawn_worker(main_script):
    command = build_worker_command(
        frozen=getattr(sys, "frozen", False),
        executable=sys.executable,
        script=main_script,
        pid=os.getpid(),
    )
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    return subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        **kwargs,
    )


class DemoWatcher:
    """Exposes demo_playing without ever scanning on the render thread.

    By default the scan runs in a separate worker process. Passing `scan` runs
    it in a background thread instead (used by tests); `spawn` lets tests
    supply a fake worker process.
    """

    def __init__(self, interval=1.0, scan=None, spawn=None, main_script=None):
        self._interval = interval
        self._scan = scan
        self._spawn = spawn or (lambda: _spawn_worker(main_script))
        self._stop = threading.Event()
        self._thread = None
        self._process = None
        self.demo_playing = False

    def poll_once(self):
        try:
            self.demo_playing = bool(self._scan())
        except Exception:
            self.demo_playing = False

    def _handle_line(self, line):
        self.demo_playing = line.strip() == "1"

    def start(self):
        if self._thread is not None:
            return
        if self._scan is not None:
            target = self._run_scan_thread
        else:
            try:
                self._process = self._spawn()
            except Exception as e:
                print(f"Demo detection unavailable: {e}")
                return
            target = self._read_worker
        self._thread = threading.Thread(target=target, name="demo-watcher", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._process is not None:
            try:
                self._process.terminate()
                self._process.wait(timeout=2.0)
            except Exception:
                pass
            self._process = None
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _run_scan_thread(self):
        while not self._stop.is_set():
            self.poll_once()
            self._stop.wait(self._interval)

    def _read_worker(self):
        try:
            for line in self._process.stdout:
                self._handle_line(line)
        except (OSError, ValueError):
            pass
        self.demo_playing = False
