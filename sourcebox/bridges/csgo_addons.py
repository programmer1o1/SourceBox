"""Install the 32-bit Windows add-ons for legacy CS:GO, including CrossOver."""

import hashlib
import io
import struct
import urllib.request
import zipfile
from pathlib import Path


# Pin the upstream downloads and their published SHA-256 digests.
PACKAGES = (
    (
        "https://github.com/alliedmodders/metamod-source/releases/download/1.12.0.1230/"
        "mmsource-1.12.0-git1230-windows.zip",
        "25387c71c3177b0d8e1e64866b76435482772b992c881eeaac9ab40ec2352183",
        (
            "addons/metamod/bin/server.dll",
            "addons/metamod/bin/metamod.2.csgo.dll",
            "addons/metamod.vdf",
        ),
    ),
    (
        "https://github.com/alliedmodders/stripper-source/releases/download/v1.2.2-git158/"
        "stripper-1.2.2-git158-mms1.12-windows.zip",
        "22bf8a640e46d0f7416433d9809069191292460b3d6408d5d0c3a7179c3666ef",
        (
            "addons/stripper/bin/stripper_mm.dll",
            "addons/stripper/bin/stripper.2.csgo.dll",
            "addons/stripper/bin/stripper.core.dll",
            "addons/stripper/global_filters.cfg",
            "addons/metamod/stripper.vdf",
        ),
    ),
)
STRIPPER_CONFIG = "addons/stripper/global_filters.cfg"
MAX_ARCHIVE_BYTES = 16 * 1024 * 1024


def _is_32bit_windows_game(executable):
    if not executable.is_file():
        return False
    with executable.open("rb") as handle:
        header = handle.read(64)
        if len(header) != 64 or header[:2] != b"MZ":
            return False
        handle.seek(struct.unpack_from("<I", header, 60)[0])
        return handle.read(6) == b"PE\0\0\x4c\x01"


def _download_members(url, digest, members):
    with urllib.request.urlopen(url, timeout=15) as response:
        data = response.read(MAX_ARCHIVE_BYTES + 1)
    if len(data) > MAX_ARCHIVE_BYTES or hashlib.sha256(data).hexdigest() != digest:
        raise ValueError(f"checksum mismatch for {url.rsplit('/', 1)[-1]}")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return {member: archive.read(member) for member in members}


def install_csgo_addons(mod_path):
    """Install missing add-ons, keeping existing versions and user config."""
    mod = Path(mod_path)
    if not _is_32bit_windows_game(mod.parent / "csgo.exe"):
        return False

    pending = {}
    for url, digest, members in PACKAGES:
        required = [member for member in members if member != STRIPPER_CONFIG]
        if all((mod / member).is_file() for member in required):
            continue
        for member, data in _download_members(url, digest, members).items():
            path = mod / member
            if path.exists():
                if member != STRIPPER_CONFIG and path.read_bytes() != data:
                    raise ValueError(f"existing add-on file differs: {path}")
            else:
                pending[path] = data

    # Download and validate all needed files before installing any, so an
    # interrupted network request leaves the existing game setup usable.
    created = []
    try:
        for path, data in pending.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as handle:
                created.append(path)
                handle.write(data)
    except OSError:
        for path in reversed(created):
            path.unlink(missing_ok=True)
        raise
    return bool(pending)
