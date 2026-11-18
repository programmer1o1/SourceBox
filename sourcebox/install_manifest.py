"""Undo for everything SourceBox writes into game folders.

Every file and folder a bridge creates goes through this module, which records
it in installed.json next to SourceBox's log. A file that existed before is
backed up first. Undoing the manifest deletes what SourceBox added, restores
what it replaced and removes folders it created once they are empty. A file
changed since SourceBox wrote it (edited by hand, say) is left alone.

The undo runs when SourceBox closes. If SourceBox is killed instead, a small
guard process (this program relaunched with --cleanup-guard) notices that its
parent is gone and runs it, and anything still left over is undone at the next
start.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time

GUARD_FLAG = "--cleanup-guard"
MANIFEST_NAME = "installed.json"


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _file_sha256(path):
    try:
        with open(path, "rb") as handle:
            return _sha256(handle.read())
    except OSError:
        return None


def default_directory():
    from sourcebox.diagnostics import diagnostic_log_path

    return str(diagnostic_log_path().parent)


class InstallManifest:
    def __init__(self, directory=None):
        self.directory = os.path.abspath(directory or default_directory())
        self.path = os.path.join(self.directory, MANIFEST_NAME)
        self.backup_dir = os.path.join(self.directory, "backups")
        # path -> {"kind": "created" | "replaced" | "transient", "sha256", "backup"}
        self.files = {}
        # folders SourceBox created, outermost first
        self.dirs = []
        self._lock = threading.RLock()

    # ------------------------------------------------------------ recording

    def make_dirs(self, path):
        """os.makedirs that remembers which folders it actually created."""
        path = os.path.abspath(path)
        with self._lock:
            missing = []
            probe = path
            while probe and not os.path.isdir(probe):
                missing.append(probe)
                parent = os.path.dirname(probe)
                if parent == probe:
                    break
                probe = parent
            os.makedirs(path, exist_ok=True)
            for folder in reversed(missing):
                if folder not in self.dirs:
                    self.dirs.append(folder)
            if missing:
                self._save()

    def track(self, path):
        """Remember a short-lived file (command or response) to delete on undo."""
        path = os.path.abspath(path)
        with self._lock:
            if path not in self.files:
                self.files[path] = {"kind": "transient", "sha256": None, "backup": None}
                self._save()

    def write_text(self, path, text, encoding=None, newline=None, ours_marker=None):
        """Write a file the way open(path, "w") would, recording it for undo.

        An existing file is backed up unless it is already SourceBox's own: the
        same content, or containing ours_marker (left by an earlier version).
        """
        path = os.path.abspath(path)
        with self._lock:
            self.make_dirs(os.path.dirname(path))
            if path not in self.files:
                entry = {"kind": "created", "sha256": None, "backup": None}
                if os.path.exists(path):
                    with open(path, "rb") as handle:
                        old = handle.read()
                    new = text.encode(encoding or "utf-8", errors="replace")
                    same = old.replace(b"\r\n", b"\n") == new.replace(b"\r\n", b"\n")
                    ours = same or (ours_marker and ours_marker.encode() in old)
                    if not ours:
                        os.makedirs(self.backup_dir, exist_ok=True)
                        backup = os.path.join(self.backup_dir, _sha256(path.encode()) + ".bak")
                        with open(backup, "wb") as handle:
                            handle.write(old)
                        entry = {"kind": "replaced", "sha256": None, "backup": backup}
                self.files[path] = entry

            with open(path, "w", encoding=encoding, newline=newline) as handle:
                handle.write(text)
            if self.files[path]["kind"] != "transient":
                self.files[path]["sha256"] = _file_sha256(path)
            self._save()

    # ------------------------------------------------------------ undo

    def undo(self):
        """Put the game folders back the way they were; returns what was done."""
        done = []
        with self._lock:
            for path in reversed(list(self.files)):
                entry = self.files[path]
                current = _file_sha256(path)
                unchanged = current is not None and current == entry.get("sha256")
                try:
                    if entry["kind"] == "transient":
                        if current is not None:
                            os.remove(path)
                            done.append(("removed", path))
                    elif entry["kind"] == "created":
                        if unchanged:
                            os.remove(path)
                            done.append(("removed", path))
                        elif current is not None:
                            done.append(("kept, changed since install", path))
                    elif entry["kind"] == "replaced":
                        backup = entry.get("backup")
                        if (unchanged or current is None) and backup and os.path.exists(backup):
                            shutil.copyfile(backup, path)
                            os.remove(backup)
                            done.append(("restored", path))
                        elif current is not None:
                            done.append(("kept, changed since install", path))
                except OSError as error:
                    done.append((f"failed: {error}", path))

            for folder in reversed(self.dirs):
                try:
                    os.rmdir(folder)  # only succeeds when empty
                    done.append(("removed folder", folder))
                except OSError:
                    pass

            self.files = {}
            self.dirs = []
            try:
                os.remove(self.path)
            except OSError:
                pass
            try:
                os.rmdir(self.backup_dir)
            except OSError:
                pass
        return done

    def undo_leftovers(self):
        """Undo a manifest left by a SourceBox that did not get to clean up."""
        with self._lock:
            if not self._load():
                return []
            return self.undo()

    # ------------------------------------------------------------ storage

    def _save(self):
        try:
            os.makedirs(self.directory, exist_ok=True)
            temporary = self.path + ".tmp"
            with open(temporary, "w", encoding="utf-8") as handle:
                json.dump({"files": self.files, "dirs": self.dirs}, handle, indent=1)
            os.replace(temporary, self.path)
        except OSError:
            pass

    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            return False
        self.files = dict(data.get("files", {}))
        self.dirs = list(data.get("dirs", []))
        return bool(self.files or self.dirs)


# ---------------------------------------------------------------- shared instance

_current = None


def current():
    global _current
    if _current is None:
        _current = InstallManifest()
    return _current


def use(manifest):
    """Swap the shared manifest (tests point it at a temporary folder)."""
    global _current
    _current = manifest
    return manifest


def make_dirs(path):
    current().make_dirs(path)


def write_text(path, text, encoding=None, newline=None, ours_marker=None):
    current().write_text(path, text, encoding=encoding, newline=newline, ours_marker=ours_marker)


def track(path):
    if path:
        current().track(path)


def report(done):
    for action, path in done:
        print(f"  [cleanup] {action}: {path}")


# ---------------------------------------------------------------- guard process

def build_guard_command(frozen, executable, script, pid):
    if frozen:
        return [executable, GUARD_FLAG, str(pid)]
    return [executable, script, GUARD_FLAG, str(pid)]


def run_cleanup_guard(parent_pid, manifest=None, parent_alive=None, sleep=time.sleep, interval=0.5):
    """Wait for SourceBox to exit, then undo whatever it left installed.

    After a normal close the manifest is already gone and this does nothing.
    """
    if parent_alive is None:
        import psutil

        def parent_alive(pid):
            return psutil.pid_exists(pid)

    while parent_alive(parent_pid):
        sleep(interval)
    return (manifest or InstallManifest()).undo_leftovers()


def start_cleanup_guard(main_script):
    """Launch the guard for this process; returns the Popen or None."""
    command = build_guard_command(
        frozen=getattr(sys, "frozen", False),
        executable=sys.executable,
        script=main_script,
        pid=os.getpid(),
    )
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        return subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **kwargs,
        )
    except OSError as error:
        print(f"[cleanup] guard unavailable ({error}); files are cleaned on close or next start")
        return None
