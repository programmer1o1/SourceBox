"""Load the custom cube during map startup on branches that use a map template."""

import lzma
import os
import re
import shutil
import struct
from pathlib import Path

from sourcebox import install_manifest


MODEL_PATH = Path("models/props/srcbox/srcbox.mdl")
MATERIALS_PATH = Path("materials/models/srcbox")
REQUIRED_MODEL_FILES = tuple(
    MODEL_PATH.with_suffix(suffix) for suffix in (".mdl", ".vvd", ".dx90.vtx", ".phy")
)
BSP_HEADER_SIZE = 8 + 64 * 16 + 4
LUMP_HEADER = struct.Struct("<5i")
SOURCE_LZMA_HEADER = struct.Struct("<4sII5s")
MAX_ENTITY_LUMP_SIZE = 16 * 1024 * 1024
# Force server-side physics so the cube remains interactive in multiplayer.
PHYSICS_FORCE_SERVER_SIDE = 8192
CUBE_TEMPLATE_ENTITIES = f'''{{
"classname" "prop_physics_override"
"targetname" "sourcebox_cube_prop"
"model" "{MODEL_PATH.as_posix()}"
"origin" "0 0 0"
"spawnflags" "{PHYSICS_FORCE_SERVER_SIDE}"
}}
{{
"classname" "point_template"
"targetname" "sourcebox_cube_template"
"origin" "0 0 0"
"Template01" "sourcebox_cube_prop"
"spawnflags" "2"
}}
{{
"classname" "env_entity_maker"
"targetname" "sourcebox_cube_maker"
"origin" "0 0 0"
"EntityTemplate" "sourcebox_cube_template"
"spawnflags" "0"
}}
'''.encode("ascii")

STRIPPER_CUBE_MARKER = "; SourceBox cube template"


def install_csgo_cube_filter(mod_path):
    """Let Stripper:Source inject the cube template into the stock map at load."""
    mod = Path(mod_path)
    stripper = mod / "addons" / "stripper"
    if not any((stripper / "bin" / f"stripper.2.csgo{suffix}").is_file()
               for suffix in (".dll", ".so")):
        return False
    if not all((mod / path).is_file() for path in REQUIRED_MODEL_FILES):
        print("  [warning] custom cube files are missing")
        return False

    config = stripper / "global_filters.cfg"
    try:
        original = config.read_bytes().decode("latin-1")
    except FileNotFoundError:
        original = ""
    if STRIPPER_CUBE_MARKER not in original:
        # Also allow a previously prepared BSP to load with Stripper present.
        block = (
            f"\n{STRIPPER_CUBE_MARKER}\n"
            'filter:\n{\n"targetname" "/^sourcebox_cube_(prop|template|maker)$/"\n}\n'
            "add:\n" + CUBE_TEMPLATE_ENTITIES.decode("ascii")
        )
        install_manifest.write_text(
            config, original + block, encoding="latin-1", newline="",
            ours_marker=STRIPPER_CUBE_MARKER,
        )
    return True


def _decompress_entities(data, expected_size):
    if len(data) < SOURCE_LZMA_HEADER.size or not 0 < expected_size <= MAX_ENTITY_LUMP_SIZE:
        return None
    magic, size, compressed_size, properties = SOURCE_LZMA_HEADER.unpack_from(data)
    compressed = data[SOURCE_LZMA_HEADER.size:]
    if magic != b"LZMA" or size != expected_size or compressed_size != len(compressed):
        return None
    # Source stores the LZMA properties and sizes in its own header. Try the known
    # size first; fall back to "unknown size" so streams that end with an
    # end-of-payload marker also decode on liblzma releases older than 5.4.
    for declared in (size, 0xFFFF_FFFF_FFFF_FFFF):
        header = properties + struct.pack("<Q", declared)
        try:
            decoder = lzma.LZMADecompressor(format=lzma.FORMAT_ALONE, memlimit=64 * 1024 * 1024)
            entities = decoder.decompress(header + compressed, max_length=size + 1)
        except lzma.LZMAError:
            continue
        if len(entities) == size:
            return entities
    return None


def _precache_lump(map_path):
    """Append a cube template that precaches its prop when the map loads."""
    with map_path.open("rb") as bsp:
        header = bsp.read(BSP_HEADER_SIZE)
        if len(header) != BSP_HEADER_SIZE or header[:4] != b"VBSP":
            return None
        offset, length, version, uncompressed_size = struct.unpack_from("<4i", header, 8)
        revision, = struct.unpack_from("<i", header, BSP_HEADER_SIZE - 4)
        if (offset < BSP_HEADER_SIZE or length <= 0
                or offset + length > map_path.stat().st_size):
            return None
        bsp.seek(offset)
        entities = bsp.read(length)

    # Keep the original entity list byte for byte up to its terminating NUL.
    if uncompressed_size:
        entities = _decompress_entities(entities, uncompressed_size)
    if not entities or not entities.endswith(b"\0") or not entities[:-1].rstrip().endswith(b"}"):
        return None
    payload = entities[:-1] + b"\n" + CUBE_TEMPLATE_ENTITIES + b"\0"
    return LUMP_HEADER.pack(LUMP_HEADER.size, 0, version, len(payload), revision) + payload


def _csgo_map_source(mod_path, map_name):
    if not re.fullmatch(r"[a-zA-Z0-9_]+", map_name) or map_name.endswith("_sourcebox"):
        raise ValueError("use a base map name such as cs_office")
    mod = Path(mod_path)
    if not all((mod / path).is_file() for path in REQUIRED_MODEL_FILES):
        raise ValueError("install the SRCBOX model files in the CS:GO game folder first")

    return mod / "maps" / f"{map_name}.bsp"


def _write_csgo_physics_bsp(source, destination):
    lump = _precache_lump(source)
    if lump is None:
        raise ValueError(f"could not read the entity lump in {source.name}")
    offset, _, version, length, _ = LUMP_HEADER.unpack_from(lump)

    # Copy the BSP byte for byte before appending so the other lump offsets stay valid.
    with source.open("rb") as original, destination.open("xb") as patched:
        try:
            shutil.copyfileobj(original, patched)
            padding = (-patched.tell()) % 4
            patched.write(b"\0" * padding)
            entity_offset = patched.tell()
            patched.write(lump[offset:])
            patched.seek(8)
            patched.write(struct.pack("<4i", entity_offset, length, version, 0))
        except BaseException:
            patched.close()
            destination.unlink()
            raise


def prepare_csgo_physics_map(mod_path, map_name):
    """Create a separate playable BSP whose entity lump includes the cube template."""
    source = _csgo_map_source(mod_path, map_name)
    destination = source.with_stem(f"{source.stem}_sourcebox")
    _write_csgo_physics_bsp(source, destination)

    # Keep the stock bot navigation on the renamed copy when available.
    navigation = source.with_suffix(".nav")
    if navigation.is_file():
        try:
            with destination.with_suffix(".nav").open("xb") as output:
                output.write(navigation.read_bytes())
        except FileExistsError:
            pass
    return destination


def _map_directories(mod, branch):
    if branch != "portal2":
        return [mod / "maps"]

    # Portal 2 searches its update and numbered DLC directories before the
    # base game. Patch the same BSP the game will open when names overlap.
    dlc_prefix = "portal2_dlc"
    dlc_dirs = sorted(
        (path for path in mod.parent.glob(f"{dlc_prefix}*")
         if path.name.removeprefix(dlc_prefix).isdigit()),
        key=lambda path: int(path.name.removeprefix(dlc_prefix)),
        reverse=True,
    )
    return [root / "maps" for root in (mod.parent / "update", *dlc_dirs, mod)]


def install_cube_precache(mod_path, branch):
    """Stage the cube and entity lumps for loose maps, including the campaign."""
    mod = Path(mod_path)
    custom = mod / "custom" / "srcbox"
    map_dirs = _map_directories(mod, branch)
    map_paths = {}
    for directory in map_dirs:
        for map_path in sorted(directory.glob("*.bsp")):
            map_paths.setdefault(map_path.stem.casefold(), map_path)
    if not map_paths and branch != "revolution":
        return False

    # Make the existing cube pack available in the game's mounted directory.
    manifest = install_manifest.current()
    if not all((mod / path).is_file() or (custom / path).is_file() for path in REQUIRED_MODEL_FILES):
        print("  [warning] custom cube files are missing")
        return False

    assets = list((custom / MODEL_PATH.parent).glob("srcbox.*"))
    assets.extend((custom / MATERIALS_PATH).glob("*"))
    for asset in assets:
        destination = mod / asset.relative_to(custom)
        if asset.is_file() and not destination.exists():
            manifest.write_new_bytes(destination, asset.read_bytes())

    # An override may live in any of the game's mounted map directories.
    overrides = {
        path.stem.rsplit("_l_", 1)[0].casefold()
        for directory in map_dirs
        for path in directory.glob("*_l_*.lmp")
    }
    installed = 0
    for name, map_path in map_paths.items():
        if name == "lobby" or name in overrides:
            continue
        try:
            lump = _precache_lump(map_path)
            destination = map_path.with_name(f"{map_path.stem}_l_0.lmp")
            if lump is not None and manifest.write_new_bytes(destination, lump):
                installed += 1
        except OSError as error:
            print(f"  [warning] couldn't prepare cube precache for {map_path.name}: {error}")
    if installed:
        print(f"  [cube] custom model precache prepared for {installed} map(s)")
    return all((mod / path).is_file() for path in REQUIRED_MODEL_FILES)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Prepare a local legacy CS:GO map with SourceBox cube physics.")
    parser.add_argument("game_dir", type=Path, help="path to the legacy CS:GO csgo directory")
    parser.add_argument("map", help="base map name, for example cs_office")
    arguments = parser.parse_args()
    try:
        prepared = prepare_csgo_physics_map(arguments.game_dir, arguments.map)
    except (OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")
    print(f"Load with: map {prepared.stem}")
