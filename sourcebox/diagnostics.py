"""Persistent runtime diagnostics for windowed SourceBox builds."""

import os
import platform
import sys
from datetime import datetime
from pathlib import Path


_LOG_HANDLE = None
_CONFIGURED_PATH = None


class _TeeStream:
    def __init__(self, original, log_handle):
        self.original = original
        self.log_handle = log_handle

    def write(self, value):
        if self.original is not None:
            self.original.write(value)
        self.log_handle.write(value)
        return len(value)

    def flush(self):
        if self.original is not None:
            self.original.flush()
        self.log_handle.flush()

    def isatty(self):
        return bool(self.original and self.original.isatty())

    def __getattr__(self, name):
        if self.original is None:
            raise AttributeError(name)
        return getattr(self.original, name)


def diagnostic_log_path(system=None, environment=None, home=None):
    """Return the conventional per-user SourceBox log path."""
    system = system or platform.system()
    environment = os.environ if environment is None else environment
    home = Path.home() if home is None else Path(home)

    if system == "Darwin":
        directory = home / "Library" / "Logs" / "SourceBox"
    elif system == "Windows":
        base = environment.get("LOCALAPPDATA")
        directory = Path(base) / "SourceBox" if base else home / "AppData" / "Local" / "SourceBox"
    else:
        base = environment.get("XDG_STATE_HOME")
        directory = Path(base) / "sourcebox" if base else home / ".local" / "state" / "sourcebox"
    return directory / "sourcebox.log"


def configure_runtime_diagnostics():
    """Mirror stdout/stderr to a persistent log, including windowed app builds."""
    global _CONFIGURED_PATH, _LOG_HANDLE
    if _CONFIGURED_PATH is not None:
        return _CONFIGURED_PATH

    log_path = diagnostic_log_path()
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        _LOG_HANDLE = log_path.open("a", encoding="utf-8", buffering=1)
    except OSError:
        return None

    sys.stdout = _TeeStream(sys.stdout, _LOG_HANDLE)
    sys.stderr = _TeeStream(sys.stderr, _LOG_HANDLE)
    _CONFIGURED_PATH = log_path
    print(f"\n[{datetime.now().isoformat(timespec='seconds')}] SourceBox starting")
    print(f"[diagnostics] {log_path}")
    return log_path
