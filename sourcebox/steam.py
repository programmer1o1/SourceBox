"""Shared Steam installation and library discovery."""

import os
import platform
import plistlib
import re
from pathlib import Path
from typing import Callable, List, Optional


LogFunction = Optional[Callable[[str], None]]

CROSSOVER_BUNDLE_IDS = (
    "com.codeweavers.CrossOver",
    "com.codeweavers.CrossOverGames",
)
CROSSOVER_STEAM_PATHS = (
    Path("drive_c/Program Files (x86)/Steam"),
    Path("drive_c/Program Files/Steam"),
    Path("drive_c/Steam"),
)


def _log(log: LogFunction, message: str) -> None:
    if log:
        log(message)


def _append_unique(paths: List[Path], candidate) -> None:
    if not candidate:
        return
    path = Path(os.path.expandvars(os.path.expanduser(str(candidate))))
    if path not in paths:
        paths.append(path)


def _preference_bottle_roots() -> List[Path]:
    roots: List[Path] = []
    preferences = Path.home() / "Library" / "Preferences"
    for bundle_id in CROSSOVER_BUNDLE_IDS:
        plist_path = preferences / f"{bundle_id}.plist"
        try:
            with plist_path.open("rb") as handle:
                values = plistlib.load(handle)
        except (OSError, plistlib.InvalidFileException):
            continue

        for key in ("BottleDir", "ManagedBottleDirs"):
            value = values.get(key)
            if isinstance(value, str):
                for item in value.split(os.pathsep):
                    _append_unique(roots, item)
            elif isinstance(value, (list, tuple)):
                for item in value:
                    _append_unique(roots, item)
    return roots


def crossover_bottle_roots() -> List[Path]:
    """Return configured private and published CrossOver bottle directories."""
    roots: List[Path] = []
    for item in os.environ.get("CX_BOTTLE_PATH", "").split(os.pathsep):
        _append_unique(roots, item)

    for item in _preference_bottle_roots():
        _append_unique(roots, item)

    _append_unique(
        roots, Path.home() / "Library" / "Application Support" / "CrossOver" / "Bottles"
    )
    _append_unique(roots, Path("/Library/Application Support/CrossOver/Bottles"))
    return [path for path in roots if path.is_dir()]


def _running_crossover_bottle(bottles: List[Path]) -> Optional[Path]:
    wine_prefix = os.environ.get("WINEPREFIX")
    if wine_prefix:
        prefix = Path(os.path.expanduser(wine_prefix))
        if (prefix / "drive_c").is_dir():
            return prefix

    selected_name = os.environ.get("CX_BOTTLE")
    if selected_name:
        for bottle in bottles:
            if bottle.name == selected_name:
                return bottle

    try:
        import psutil
    except ImportError:
        return None

    bottle_strings = [(bottle, str(bottle)) for bottle in bottles]
    for process in psutil.process_iter(["name", "exe", "cmdline"]):
        try:
            info = process.info
            parts = [info.get("name") or "", info.get("exe") or ""]
            parts.extend(info.get("cmdline") or [])
            text = " ".join(parts)
            for bottle, bottle_text in bottle_strings:
                if bottle_text in text:
                    return bottle

            process_name = (info.get("name") or "").lower()
            if any(marker in process_name for marker in ("wine", "steam", "hl2", "gmod")):
                try:
                    environment = process.environ()
                except (psutil.AccessDenied, psutil.NoSuchProcess, OSError):
                    environment = {}
                prefix = environment.get("WINEPREFIX")
                if prefix:
                    prefix_path = Path(prefix)
                    if (prefix_path / "drive_c").is_dir():
                        return prefix_path
        except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
            continue
    return None


def find_crossover_bottles(bottle_roots=None) -> List[Path]:
    """Find valid CrossOver bottles, prioritizing the active bottle."""
    roots = list(bottle_roots) if bottle_roots is not None else crossover_bottle_roots()
    bottles: List[Path] = []

    wine_prefix = os.environ.get("WINEPREFIX")
    if wine_prefix:
        prefix = Path(os.path.expanduser(wine_prefix))
        if (prefix / "drive_c").is_dir():
            _append_unique(bottles, prefix)

    for root_value in roots:
        root = Path(root_value)
        if (root / "drive_c").is_dir():
            _append_unique(bottles, root)
            continue
        if not root.is_dir():
            continue
        try:
            children = sorted(root.iterdir(), key=lambda path: path.name.lower())
        except OSError:
            continue
        for child in children:
            if child.is_dir() and (child / "drive_c").is_dir():
                _append_unique(bottles, child)

    active = _running_crossover_bottle(bottles)
    if active:
        _append_unique(bottles, active)
        bottles.sort(key=lambda bottle: bottle != active)
    return bottles


def find_crossover_steam_installs(bottle_roots=None) -> List[str]:
    """Return Steam roots inside every discovered CrossOver bottle."""
    installs: List[str] = []
    for bottle in find_crossover_bottles(bottle_roots):
        for relative_path in CROSSOVER_STEAM_PATHS:
            steam_path = bottle / relative_path
            if (steam_path / "steamapps").is_dir():
                value = str(steam_path)
                if value not in installs:
                    installs.append(value)
                break
    return installs


def command_mentions_executable(cmdline, executable_names) -> bool:
    """Match Windows executable names embedded in Wine/CrossOver commands."""
    names = {name.lower() for name in executable_names}
    for argument in cmdline or []:
        normalized = str(argument).strip('"').replace("\\", "/")
        if normalized.rsplit("/", 1)[-1].lower() in names:
            return True
    return False


def steam_library_from_process_info(process_info) -> Optional[str]:
    """Resolve a Steam library from native or CrossOver process arguments."""
    candidates = [process_info.get("exe") or ""]
    candidates.extend(process_info.get("cmdline") or [])
    for value in candidates:
        normalized = str(value).strip('"')
        if not normalized or not os.path.exists(normalized):
            continue
        current = Path(normalized)
        if current.is_file():
            current = current.parent
        for parent in (current, *current.parents):
            if (parent / "steamapps").is_dir() or (parent / "SteamApps").is_dir():
                return str(parent)
    return None


def _crossover_bottle_for_path(path: str) -> Optional[Path]:
    candidate = Path(path)
    for parent in (candidate, *candidate.parents):
        if parent.name.lower() == "drive_c":
            return parent.parent
    return None


def _translate_wine_library_path(path: str, bottle: Optional[Path]) -> str:
    if not bottle:
        return path
    match = re.match(r"^([a-zA-Z]):[\\/](.*)$", path)
    if not match:
        return path

    drive, remainder = match.groups()
    remainder_path = Path(remainder.replace("\\", "/"))
    if drive.lower() == "c":
        return str(bottle / "drive_c" / remainder_path)
    if drive.lower() == "z":
        return str(Path("/") / remainder_path)

    mapping = bottle / "dosdevices" / f"{drive.lower()}:"
    if mapping.exists():
        return str(mapping.resolve() / remainder_path)
    return path


def find_steam_from_process(log: LogFunction = None) -> Optional[str]:
    try:
        import psutil
    except ImportError:
        _log(log, "psutil is unavailable; process detection skipped")
        return None

    try:
        for process in psutil.process_iter(["name", "exe"]):
            try:
                process_name = process.info["name"]
                if not process_name or process_name.lower() not in ("steam.exe", "steam"):
                    continue

                executable = process.info.get("exe")
                if not executable or not os.path.exists(executable):
                    continue

                steam_directory = os.path.dirname(executable)
                candidates = (steam_directory, os.path.dirname(steam_directory))
                for candidate in candidates:
                    if os.path.exists(os.path.join(candidate, "steamapps")):
                        _log(log, f"found steam from process: {candidate}")
                        return candidate
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
    except Exception as error:
        _log(log, f"process detection failed: {error}")
    return None


def find_steam_install(log: LogFunction = None) -> Optional[str]:
    system = platform.system()

    if system == "Windows":
        try:
            import winreg

            registry_paths = (
                r"SOFTWARE\Wow6432Node\Valve\Steam",
                r"SOFTWARE\Valve\Steam",
            )
            for registry_path in registry_paths:
                try:
                    key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, registry_path)
                    install_path, _ = winreg.QueryValueEx(key, "InstallPath")
                    winreg.CloseKey(key)
                    if install_path and os.path.exists(install_path):
                        _log(log, f"found steam via registry: {install_path}")
                        return install_path
                except (FileNotFoundError, OSError):
                    continue
        except ImportError:
            pass

        process_path = find_steam_from_process(log)
        if process_path:
            return process_path

        for default_path in (r"C:\Program Files (x86)\Steam", r"C:\Program Files\Steam"):
            if os.path.exists(default_path):
                _log(log, f"found steam at default location: {default_path}")
                return default_path

    elif system == "Linux":
        candidates = (
            "~/.local/share/Steam",
            "~/.steam/steam",
            "~/.steam/root",
        )
        for candidate in candidates:
            expanded = os.path.expanduser(candidate)
            if os.path.islink(expanded):
                expanded = os.path.realpath(expanded)
            if os.path.exists(expanded):
                _log(log, f"found steam at: {expanded}")
                return expanded

        flatpak_path = os.path.expanduser(
            "~/.var/app/com.valvesoftware.Steam/.local/share/Steam"
        )
        if os.path.exists(flatpak_path):
            _log(log, f"found flatpak steam at: {flatpak_path}")
            return flatpak_path

        process_path = find_steam_from_process(log)
        if process_path:
            return process_path

    elif system == "Darwin":
        crossover_installs = find_crossover_steam_installs()
        if crossover_installs:
            _log(log, f"found CrossOver Steam at: {crossover_installs[0]}")
            return crossover_installs[0]

    return None


def parse_library_folders(
    steam_path: str, log: LogFunction = None
) -> List[str]:
    libraries = [steam_path]
    bottle = _crossover_bottle_for_path(steam_path)
    vdf_path = os.path.join(steam_path, "steamapps", "libraryfolders.vdf")
    if not os.path.exists(vdf_path):
        vdf_path = os.path.join(steam_path, "SteamApps", "libraryfolders.vdf")

    if not os.path.exists(vdf_path):
        _log(log, "libraryfolders.vdf not found")
        if bottle:
            for crossover_install in find_crossover_steam_installs():
                if crossover_install not in libraries:
                    libraries.append(crossover_install)
        return libraries

    try:
        with open(vdf_path, "r", encoding="utf-8") as handle:
            content = handle.read()

        for match in re.findall(r'"path"\s+"([^"]+)"', content):
            library_path = match.replace("\\\\", "\\")
            library_path = _translate_wine_library_path(library_path, bottle)
            if os.path.exists(library_path) and library_path not in libraries:
                libraries.append(library_path)
                _log(log, f"found library: {library_path}")
    except Exception as error:
        _log(log, f"failed to parse libraryfolders.vdf: {error}")

    if bottle:
        for crossover_install in find_crossover_steam_installs():
            if crossover_install not in libraries:
                libraries.append(crossover_install)
                _log(log, f"found CrossOver library: {crossover_install}")
    return libraries
