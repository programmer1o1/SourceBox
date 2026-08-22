"""
Garry's Mod Bridge for SourceBox (GMod 9-13)
Automatically installs Lua addon to sourcemods and retail installs
"""

import os
import json
import time
import psutil

from sourcebox.resources import load_text_resource
from sourcebox.steam import (
    command_mentions_executable,
    find_steam_from_process,
    find_steam_install,
    parse_library_folders,
    steam_library_from_process_info,
)

class GModBridge:
    # gmod versions as sourcemods (9-12)
    GMOD_SOURCEMODS = {
        'gmod9': 'GMod 9',
        'garrysmod10classic': 'GMod 10 Classic',
        'garrysmod': 'GMod 11',
        'garrysmod12': 'GMod 12'
    }

    # retail gmod 13 install (steamapps/common/GarrysMod/garrysmod)
    GMOD_RETAIL = {
        'gmod13': {
            'name': 'GMod 13',
            'install_dir': 'GarrysMod',
            'game_dir': 'garrysmod'
        }
    }

    def __init__(self):
        self.data_path = None
        self.addon_path = None
        self.command_file = None
        self.response_file = None
        self.session_id = int(time.time())
        self.command_id = 0
        self.active_gmod = None
        self.gmod_version = None
        self.is_gmod9 = False

        self._detect_gmod()

    def _get_steam_path_from_process(self):
        """Detect Steam from its running process."""
        return find_steam_from_process()

    def _get_steam_install_path(self):
        """Find the platform's Steam installation."""
        return find_steam_install()

    def _parse_library_folders_vdf(self, steam_path):
        """Return every valid Steam library in libraryfolders.vdf."""
        return parse_library_folders(steam_path)

    def _get_retail_gmod_path(self, library_path):
        """return retail gmod13 garrysmod directory if it exists"""
        retail_info = self.GMOD_RETAIL['gmod13']
        for steamapps_dir in ['steamapps', 'SteamApps']:
            game_root = os.path.join(library_path, steamapps_dir, 'common', retail_info['install_dir'])
            mod_path = os.path.join(game_root, retail_info['game_dir'])
            if os.path.exists(mod_path):
                return mod_path
        return None

    def _detect_gmod(self):
        """detect gmod installation"""
        print("\n" + "="*70)
        print("GARRY'S MOD BRIDGE")
        print("="*70)
        print("\n[scan] detecting steam libraries...")

        steam_path = self._get_steam_install_path()

        if not steam_path:
            print("  [error] steam installation not found")
            print("="*70 + "\n")
            return

        print(f"  [steam] {steam_path}")

        all_libraries = self._parse_library_folders_vdf(steam_path)
        print(f"  [libraries] found {len(all_libraries)} steam libraries")

        print("\n[scan] detecting gmod installations...")

        running_gmod = self._detect_running_gmod()

        # scan the library that actually holds the running game first, so a
        # leftover/empty install in another library doesn't get picked instead
        active_library = self._get_running_gmod_library()
        if active_library:
            print(f"  [running] library: {active_library}")
        all_libraries = self._prioritize_libraries(all_libraries, active_library)

        # first scan sourcemod variants (gmod 9-12)
        for library_path in all_libraries:
            sourcemods_path = os.path.join(library_path, 'steamapps', 'sourcemods')
            if not os.path.exists(sourcemods_path):
                sourcemods_path = os.path.join(library_path, 'SteamApps', 'sourcemods')

            if os.path.exists(sourcemods_path):
                for mod_folder, mod_name in self.GMOD_SOURCEMODS.items():
                    mod_path = os.path.join(sourcemods_path, mod_folder)
                    if os.path.exists(mod_path):
                        data_path = os.path.join(mod_path, 'data')

                        is_gmod9 = mod_folder == 'gmod9'

                        if is_gmod9:
                            addon_path = os.path.join(mod_path, 'lua', 'init')
                        else:
                            addon_path = os.path.join(mod_path, 'addons', 'sourcebox')

                        os.makedirs(data_path, exist_ok=True)

                        if running_gmod and running_gmod == mod_folder:
                            self._setup_paths(data_path, addon_path, mod_name, is_gmod9, mod_folder)
                            self._install_lua_addon()
                            print(f"  [found] {mod_name} (RUNNING)")
                            print(f"  [library] {library_path}")
                            return
                        elif not self.active_gmod:
                            print(f"  [installed] {mod_name} (in {library_path})")

        # then scan retail gmod 13 install
        for library_path in all_libraries:
            retail_path = self._get_retail_gmod_path(library_path)
            if not retail_path:
                continue

            data_path = os.path.join(retail_path, 'data')
            addon_path = os.path.join(retail_path, 'addons', 'sourcebox')
            os.makedirs(data_path, exist_ok=True)

            if running_gmod in ['gmod13', 'garrysmod']:
                self._setup_paths(data_path, addon_path, self.GMOD_RETAIL['gmod13']['name'], False, 'gmod13')
                self._install_lua_addon()
                print(f"  [found] {self.GMOD_RETAIL['gmod13']['name']} (RUNNING)")
                print(f"  [library] {library_path}")
                return
            elif not self.active_gmod:
                print(f"  [installed] {self.GMOD_RETAIL['gmod13']['name']} (in {library_path})")

    def _detect_running_gmod(self):
        """detect running gmod"""
        gmod_executables = [
            'hl2.exe', 'hl2_linux', 'gmod.exe', 'gmod',
            'gmod64', 'gmod32', 'gmod_linux'
        ]
        try:
            for proc in psutil.process_iter(['name', 'exe', 'cmdline']):
                try:
                    proc_name = proc.info.get('name')
                    if not proc_name:
                        continue

                    cmdline = proc.info.get('cmdline')
                    if not cmdline:
                        continue

                    exe_path = proc.info.get('exe') or ''
                    exe_lower = exe_path.lower()
                    command_text = ' '.join(cmdline).lower().replace('\\', '/')
                    proc_lower = proc_name.lower()

                    # hl2 based binaries or gmod specific binaries
                    if (
                        proc_lower in gmod_executables
                        or command_mentions_executable(cmdline, gmod_executables)
                    ):
                        for i, arg in enumerate(cmdline):
                            if arg.lower() == '-game' and i + 1 < len(cmdline):
                                game_arg = cmdline[i + 1].strip('"').lower()

                                if 'gmod9' in game_arg or 'garrysmod9' in game_arg:
                                    return 'gmod9'
                                elif 'garrysmod12' in game_arg:
                                    return 'garrysmod12'
                                elif 'garrysmod10classic' in game_arg:
                                    return 'garrysmod10classic'
                                elif 'garrysmod' in game_arg:
                                    # differentiate sourcemod vs retail by path hint
                                    if 'sourcemods' in game_arg or 'sourcemods' in exe_lower:
                                        return 'garrysmod'
                                    return 'gmod13'

                        # fallback: detect retail gmod if binary path clearly in GarrysMod
                        if 'garrysmod' in exe_lower and 'sourcemods' not in exe_lower:
                            return 'gmod13'
                        if '/garrysmod/' in command_text and 'sourcemods' not in command_text:
                            return 'gmod13'

                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
        except:
            pass

        return None

    def _get_running_gmod_library(self):
        """find the steam library root that holds the running gmod executable"""
        gmod_executables = [
            'hl2.exe', 'hl2_linux', 'gmod.exe', 'gmod',
            'gmod64', 'gmod32', 'gmod_linux'
        ]
        try:
            for proc in psutil.process_iter(['name', 'exe', 'cmdline']):
                try:
                    proc_name = proc.info.get('name')
                    if not proc_name:
                        continue

                    proc_lower = proc_name.lower()
                    cmdline = proc.info.get('cmdline') or []
                    if (
                        proc_lower not in gmod_executables
                        and not command_mentions_executable(cmdline, gmod_executables)
                    ):
                        continue

                    library = steam_library_from_process_info(proc.info)
                    if library:
                        return library
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
        except:
            pass

        return None

    def _prioritize_libraries(self, libraries, active_library):
        """put the library holding the running game first so a leftover install
        in another library (e.g. an old garrysmod on C:) doesn't win over the
        library the game is actually launched from (e.g. D:)"""
        if not active_library:
            return list(libraries)
        active_norm = os.path.normcase(os.path.normpath(active_library))
        return sorted(libraries, key=lambda lib: os.path.normcase(os.path.normpath(lib)) != active_norm)

    def _setup_paths(self, data_path, addon_path, gmod_name, is_gmod9=False, gmod_version=None):
        """setup paths"""
        self.data_path = data_path
        self.addon_path = addon_path
        self.active_gmod = gmod_name
        self.is_gmod9 = is_gmod9
        self.gmod_version = gmod_version or ('gmod9' if is_gmod9 else None)
        self.command_file = os.path.join(data_path, "sourcebox_command.txt")
        self.response_file = os.path.join(data_path, "sourcebox_response.txt")

        try:
            if os.path.exists(self.command_file):
                os.remove(self.command_file)
            if os.path.exists(self.response_file):
                os.remove(self.response_file)
        except:
            pass

    def _install_lua_addon(self):
        """install lua addon automatically"""
        if not self.addon_path:
            return

        print("\n[install] creating lua addon...")

        try:
            if self.is_gmod9:
                # gmod 9 uses init folder structure
                os.makedirs(self.addon_path, exist_ok=True)

                # write picker script
                picker_content = self._get_gmod9_picker_lua()
                with open(os.path.join(self.addon_path, 'sv_picker_gmod9.lua'), 'w') as f:
                    f.write(picker_content)

                # write spawner script
                spawner_content = self._get_gmod9_spawner_lua()
                with open(os.path.join(self.addon_path, 'sv_auto_spawner_gmod9.lua'), 'w') as f:
                    f.write(spawner_content)

                # write bridge script
                bridge_content = self._get_gmod9_bridge_lua()
                with open(os.path.join(self.addon_path, 'sv_python_listener_gmod9.lua'), 'w') as f:
                    f.write(bridge_content)

                print(f"  [created] {self.addon_path}")
                print("  [files] sv_picker_gmod9.lua, sv_auto_spawner_gmod9.lua, sv_python_listener_gmod9.lua")
                print("  [gmod 9] scripts will auto-load from lua/init/")

            else:
                # gmod 10-12 uses addons structure
                lua_path = os.path.join(self.addon_path, 'lua')
                autorun_path = os.path.join(lua_path, 'autorun')
                sourcebox_path = os.path.join(autorun_path, 'sourcebox')

                os.makedirs(sourcebox_path, exist_ok=True)
                # write addon metadata
                if self.gmod_version == 'gmod13':
                    addon_content = '''"AddonInfo"
{
	"name"		"SourceBox"
	"version"	"1.0"
	"author_name"	"SourceBox Team"
	"info"		"Python bridge for Garry's Mod"
	"override"	"0"
}
'''
                    with open(os.path.join(self.addon_path, 'addon.txt'), 'w') as f:
                        f.write(addon_content)
                else:
                    info_content = '''sourcebox
{
	name		"SourceBox"
	version		"1.0"
	author		"SourceBox Team"
	info		"Python bridge for Garry's Mod"
}
'''
                    with open(os.path.join(self.addon_path, 'info.txt'), 'w') as f:
                        f.write(info_content)

                # write sourcebox_init.lua
                init_content = self._get_init_lua()
                with open(os.path.join(autorun_path, 'sourcebox_init.lua'), 'w') as f:
                    f.write(init_content)

                # write sv_python_bridge.lua
                bridge_content = self._get_bridge_lua()
                with open(os.path.join(sourcebox_path, 'sv_python_bridge.lua'), 'w') as f:
                    f.write(bridge_content)

                # write sv_picker.lua
                picker_content = self._get_picker_lua()
                with open(os.path.join(sourcebox_path, 'sv_picker.lua'), 'w') as f:
                    f.write(picker_content)

                # write sv_auto_spawner.lua
                spawner_content = self._get_spawner_lua()
                with open(os.path.join(sourcebox_path, 'sv_auto_spawner.lua'), 'w') as f:
                    f.write(spawner_content)

                print(f"  [created] {self.addon_path}")
                print("  [files] info.txt, sourcebox_init.lua, sv_*.lua")

        except Exception as e:
            print(f"  [error] failed to install addon: {e}")

    def _get_gmod9_picker_lua(self):
        """get gmod 9 picker script"""
        return load_text_resource("bridge_scripts/gmod/gmod9/sv_picker.lua")

    def _get_gmod9_spawner_lua(self):
        """get gmod 9 spawner script"""
        return load_text_resource("bridge_scripts/gmod/gmod9/sv_auto_spawner.lua")

    def _get_gmod9_bridge_lua(self):
        """get gmod 9 bridge script"""
        return load_text_resource("bridge_scripts/gmod/gmod9/sv_python_listener.lua")

    def _get_init_lua(self):
        """get gmod 10-12 init script"""
        return load_text_resource("bridge_scripts/gmod/modern/sourcebox_init.lua")

    def _get_bridge_lua(self):
        """get gmod 10-12 bridge script"""
        # Use the provided GMod 10-12 bridge code
        return load_text_resource("bridge_scripts/gmod/modern/sv_python_bridge.lua")

    def _get_picker_lua(self):
        """get gmod 10-12 picker script"""
        # Use the provided GMod 10-12 picker code
        return load_text_resource("bridge_scripts/gmod/modern/sv_picker.lua")

    def _get_spawner_lua(self):
        """get gmod 10-12 spawner script"""
        # Use the provided GMod 10-12 spawner code
        return load_text_resource("bridge_scripts/gmod/modern/sv_auto_spawner.lua")

    def is_connected(self):
        """check if bridge is ready"""
        return self.data_path is not None and os.path.exists(self.data_path)

    def spawn_model(self, model_path, distance=200):
        """spawn model at crosshair"""
        if not self.is_connected():
            return False

        self.command_id += 1

        data = {
            "command": "spawn_model",
            "model": model_path,
            "distance": distance,
            "id": self.command_id,
            "session": self.session_id
        }

        try:
            with open(self.command_file, 'w') as f:
                f.write(json.dumps(data))
                f.flush()
                os.fsync(f.fileno())

            print(f"[GMod Command #{self.command_id}] {model_path}")
            time.sleep(0.05)
            return True
        except Exception as e:
            print(f"[GMod Bridge] Error sending command: {e}")
            return False

    def ping(self):
        """test connection"""
        if not self.is_connected():
            return False

        self.command_id += 1

        data = {
            "command": "ping",
            "id": self.command_id,
            "session": self.session_id
        }

        try:
            with open(self.command_file, 'w') as f:
                f.write(json.dumps(data))
            return True
        except:
            return False

    def cleanup(self):
        """cleanup temporary files"""
        try:
            if self.command_file and os.path.exists(self.command_file):
                os.remove(self.command_file)
            if self.response_file and os.path.exists(self.response_file):
                os.remove(self.response_file)
        except:
            pass
