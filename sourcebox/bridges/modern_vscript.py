"""VScript bridge for L4D2, Portal 2, CS:GO, Alien Swarm and Strata games.

These games share one Squirrel script (bridge_scripts/modern/sourcebox_bridge.nut)
but differ in how SourceBox can hand it commands:

* "file": L4D2 scripts can read files, but only inside the game's ems/ folder.
* "include": Portal 2, CS:GO, Alien Swarm and Strata cannot read files at all,
  so each command is written as a tiny script (sourcebox_command.nut) that the
  game re-runs with DoIncludeScript every poll.

The bridge loads from the game's map-start hook. Where that hook is a file the
game already ships (Portal 2's mapspawn.nut), the original is kept as
sourcebox_original_mapspawn.nut and still runs first.
"""

import os
import time
import zipfile

from sourcebox import install_manifest
from sourcebox.bridges.cube_precache import (
    install_csgo_cube_filter,
    install_cube_precache,
)
from sourcebox.bridges.csgo_addons import install_csgo_addons
from sourcebox.resources import load_text_resource

BRANCHES = {
    "l4d2": {"transport": "file", "hook": "mapspawn_addon.nut"},
    "portal2": {"transport": "include", "hook": "mapspawn.nut"},
    "csgo": {"transport": "include", "hook": "mapspawn.nut"},
    "swarm": {"transport": "include", "hook": "mapspawn.nut"},
    "revolution": {"transport": "include", "hook": "mapspawn.nut"},
    "strata": {"transport": "include", "hook": "mapspawn.nut"},
}

BRIDGE_SCRIPT = "sourcebox_bridge.nut"
ORIGINAL_HOOK = "sourcebox_original_mapspawn.nut"
MANAGED_MARKER = "// sourcebox-managed"


def command_script(command_json):
    """Wrap a JSON command as the one-line script the include transport runs."""
    escaped = command_json.replace("\\", "\\\\").replace('"', '\\"')
    escaped = escaped.replace("\r", "").replace("\n", " ")
    return f'::g_sourcebox_command <- "{escaped}";\n'


def bridge_script(branch):
    """The installed bridge script: branch header plus the shared template."""
    transport = BRANCHES[branch]["transport"]
    header = (
        f"{MANAGED_MARKER}\n"
        f'::SOURCEBOX_BRANCH <- "{branch}";\n'
        f'::SOURCEBOX_TRANSPORT <- "{transport}";\n\n'
    )
    script = header + load_text_resource("bridge_scripts/modern/sourcebox_bridge.nut")
    if branch == "l4d2":
        script += "\n" + load_text_resource("bridge_scripts/modern/l4d2_picker.nut")
    elif branch == "portal2":
        script += "\n" + load_text_resource("bridge_scripts/modern/portal2_picker.nut")
    elif branch == "csgo":
        script += "\n" + load_text_resource("bridge_scripts/modern/csgo_picker.nut")
    return script


def hook_script(run_original, branch=None, cube_assets_ready=False):
    """The map-start hook: the game's original first, then the bridge."""
    lines = [
        f"{MANAGED_MARKER}: loads the SourceBox bridge on every map.",
    ]
    if run_original:
        lines += [
            f"// The game's own version of this file is kept in {ORIGINAL_HOOK} and runs first.",
            "// To undo SourceBox, delete this file and rename that one back.",
            "try {",
            f'    DoIncludeScript("{ORIGINAL_HOOK[:-4]}", getroottable());',
            "} catch (e) {}",
        ]
    if branch == "portal2":
        lines.append(load_text_resource("bridge_scripts/modern/portal2_mapspawn.nut"))
        return "\n".join(lines)
    if branch == "revolution" and cube_assets_ready:
        lines.append(load_text_resource("bridge_scripts/modern/revolution_mapspawn.nut"))

    lines += [
        "try {",
        f'    if (DoIncludeScript("{BRIDGE_SCRIPT[:-4]}", getroottable()) == false) {{',
        f'        printl("[SourceBox] {BRIDGE_SCRIPT} could not be loaded from the map-start hook");',
        "    }",
        "} catch (e) {",
        '    printl("[SourceBox] map-start hook failed: " + e);',
        "}",
        "",
    ]
    return "\n".join(lines)


def _read(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return None


def _write(path, text):
    # recorded so closing SourceBox can remove it (or restore what it replaced)
    install_manifest.write_text(path, text, encoding="utf-8", newline="\n", ours_marker=MANAGED_MARKER)


def write_atomically(path, text, attempts=5):
    """Replace a file in one step so the game never reads half a command.

    The game may hold the file open for a moment while reading it, which makes
    the rename fail on Windows, so a few retries are allowed.
    """
    install_manifest.track(path)
    temporary = path + ".tmp"
    for attempt in range(attempts):
        try:
            with open(temporary, "w", encoding="ascii", newline="\n") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            return True
        except OSError:
            if attempt == attempts - 1:
                break
            time.sleep(0.02)
    try:
        os.remove(temporary)
    except OSError:
        pass
    return False


class ModernVScriptBridge:
    def __init__(self, branch, mod_path, shadowed_hooks=(), verbose=False):
        """
        branch: a BRANCHES key.
        mod_path: the game folder that holds gameinfo.txt (portal2, left4dead2, p2ce...).
        shadowed_hooks: other copies of the hook file that this mod's copy would
            hide, such as Portal 2's mapspawn.nut mounted under P2CE. The first
            one found is kept as the original when the mod has none of its own.
        """
        if branch not in BRANCHES:
            raise ValueError(f"unknown VScript branch: {branch}")
        self.branch = branch
        self.transport = BRANCHES[branch]["transport"]
        self.hook_name = BRANCHES[branch]["hook"]
        self.mod_path = os.path.abspath(mod_path)
        self.shadowed_hooks = list(shadowed_hooks)
        self.verbose = verbose

        self.vscripts_path = os.path.join(self.mod_path, "scripts", "vscripts")
        if self.transport == "file":
            self.data_path = os.path.join(self.mod_path, "ems")
            self.command_file = os.path.join(self.data_path, "sourcebox_command.txt")
            self.response_file = os.path.join(self.data_path, "sourcebox_response.txt")
        else:
            self.data_path = self.vscripts_path
            self.command_file = os.path.join(self.vscripts_path, "sourcebox_command.nut")
            # these games cannot write files; results go to the game console
            self.response_file = None

    def prepare_paths(self):
        try:
            install_manifest.make_dirs(self.vscripts_path)
            install_manifest.make_dirs(self.data_path)
            return True
        except OSError as error:
            if self.verbose:
                print(f"[error] VScript path setup failed: {error}")
            return False

    def install_scripts(self):
        """Install the bridge and the map-start hook; safe to run repeatedly."""
        cube_assets_ready = False
        if self.branch == "csgo":
            try:
                if install_csgo_addons(self.mod_path):
                    print("  [cube] installed Metamod and Stripper; restart CS:GO once with -insecure")
            except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
                print(f"  [warning] couldn't automatically install the CS:GO add-ons: {error}")
            try:
                if install_csgo_cube_filter(self.mod_path):
                    print("  [cube] stock map template staged for Stripper:Source")
            except OSError as error:
                print(f"  [warning] couldn't install the CS:GO cube filter: {error}")
        elif self.branch in ("portal2", "swarm", "revolution"):
            try:
                cube_assets_ready = install_cube_precache(self.mod_path, self.branch)
            except OSError as error:
                print(f"[warning] couldn't install custom cube precache: {error}")
        _write(os.path.join(self.vscripts_path, BRIDGE_SCRIPT), bridge_script(self.branch))
        self._install_hook(cube_assets_ready)
        # an empty command file keeps the include transport from logging
        # "script not found" every poll before the first spawn
        self.reset_command()
        return True

    def _install_hook(self, cube_assets_ready):
        hook_path = os.path.join(self.vscripts_path, self.hook_name)
        original_path = os.path.join(self.vscripts_path, ORIGINAL_HOOK)

        current = _read(hook_path)
        current = self._repair_untracked_install(hook_path, original_path, current)

        if current is not None and MANAGED_MARKER not in current:
            # the game's (or another mod's) hook: keep it running
            _write(original_path, current)
        elif current is None:
            for shadowed in self.shadowed_hooks:
                content = _read(shadowed)
                if content is not None:
                    _write(original_path, content)
                    break

        _write(hook_path, hook_script(os.path.exists(original_path), self.branch, cube_assets_ready))

    def _repair_untracked_install(self, hook_path, original_path, current):
        """Undo hook files left by a SourceBox from before installs were recorded.

        Returns what the hook file holds afterwards (None when there is none).
        """
        original = _read(original_path)
        if original is None:
            return current

        if current is not None and MANAGED_MARKER in current:
            if any(_read(shadowed) == original for shadowed in self.shadowed_hooks):
                # the "original" was only a copy of a hook this mod hides (P2CE):
                # the mod never had its own, so there is nothing to put back
                os.remove(hook_path)
                current = None
            else:
                # the game's own hook only survives in the copy: put it back
                with open(hook_path, "w", encoding="utf-8", newline="\n") as handle:
                    handle.write(original)
                current = original
        # with no SourceBox hook in front of it, the copy is just a stray file
        os.remove(original_path)
        return current

    def send_command(self, command_json):
        if self.transport == "file":
            return write_atomically(self.command_file, command_json)
        return write_atomically(self.command_file, command_script(command_json))

    def reset_command(self):
        if self.transport == "file":
            # "{}" rather than empty: the game may read an empty file as missing,
            # and a missing command file tells the bridge SourceBox has closed
            return write_atomically(self.command_file, "{}")
        return write_atomically(self.command_file, command_script(""))

    QUIT_GRACE = 0.35  # a few of the game's 0.1s polls

    def shutdown(self, sleep=time.sleep):
        """Tell a running bridge to stop before SourceBox removes its files.

        Without this the game finds its command file gone on the next poll and
        prints one "Script not found" before stopping.
        """
        self.send_command("quit")
        sleep(self.QUIT_GRACE)

    @property
    def description(self):
        if self.transport == "file":
            return f"VScript bridge ({self.branch}, ems file)"
        return f"VScript bridge ({self.branch}, script include)"


# ------------------------------------------------------------------ Strata Source

STRATA_IGNORED_FOLDERS = {"bin", "hammer", "platform", "portal2", "sdk_content", "sdk_tools"}


def strata_root_from_exe(exe_path):
    """Install root of a Strata Source game, from its launcher path, or None.

    Strata launchers live in <root>/bin/win64 (or linux64). Older Revolution
    builds have vscript.dll instead of the newer scriptsystem library.
    """
    if not exe_path:
        return None
    exe_dir = os.path.dirname(os.path.abspath(exe_path))
    bin_dir = os.path.dirname(exe_dir)
    if os.path.basename(bin_dir).lower() != "bin":
        return None
    root = os.path.dirname(bin_dir)
    for library in ("scriptsystem.dll", "libscriptsystem.so"):
        if os.path.isfile(os.path.join(exe_dir, library)):
            return root
    if (os.path.basename(exe_path).lower() == "revolution.exe"
            and os.path.isfile(os.path.join(exe_dir, "revolution.exe"))
            and os.path.isfile(os.path.join(exe_dir, "vscript.dll"))
            and game_title(os.path.join(root, "revolution", "gameinfo.txt")) == "Portal: Revolution"):
        return root
    return None


def game_title(gameinfo_path):
    """The 'game' title from a gameinfo.txt, or None."""
    text = _read(gameinfo_path) or ""
    for line in text.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and parts[0].lower() == "game":
            return parts[1].strip().strip('"') or None
    return None


def find_strata_game(exe_path, cmdline=()):
    """(title, mod_path, root) for a running Strata game, or None.

    The mod folder comes from -game when given, then from the launcher's name
    (p2ce.exe -> p2ce), then from the only other folder holding a gameinfo.txt.
    """
    root = strata_root_from_exe(exe_path)
    if not root:
        return None

    candidates = []
    args = list(cmdline)
    for index, arg in enumerate(args):
        if arg.lower() == "-game" and index + 1 < len(args):
            game_arg = args[index + 1].strip('"')
            candidates.append(game_arg if os.path.isabs(game_arg) else os.path.join(root, game_arg))
    candidates.append(os.path.join(root, os.path.splitext(os.path.basename(exe_path))[0]))
    try:
        for folder in sorted(os.listdir(root)):
            if folder.lower() not in STRATA_IGNORED_FOLDERS:
                candidates.append(os.path.join(root, folder))
    except OSError:
        pass

    for candidate in candidates:
        gameinfo = os.path.join(candidate, "gameinfo.txt")
        if os.path.isfile(gameinfo):
            mod_path = os.path.abspath(candidate)
            title = game_title(gameinfo) or os.path.basename(mod_path)
            return title, mod_path, root
    return None


def strata_shadowed_hooks(root):
    """Hook files a Strata mod's own mapspawn.nut would hide (mounted Portal 2)."""
    return [
        os.path.join(root, "portal2", "portal2", "scripts", "vscripts", "mapspawn.nut"),
        os.path.join(root, "portal2", "scripts", "vscripts", "mapspawn.nut"),
    ]
