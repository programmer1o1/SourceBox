"""
Universal Source Engine VScript Bridge
Connects Python to any Source game with VScript support or console
"""

import os
import json
import time
import threading
import platform
import psutil
import traceback
import random
from sourcebox.bridges.source_discovery import SourceGameDiscoveryMixin
from sourcebox.resources import load_text_resource
from sourcebox.steam import (
    find_steam_from_process,
    find_steam_install,
    parse_library_folders,
)

if platform.system() == 'Windows':
    try:
        import win32gui
        import win32con
        import win32api
        import win32process
        import win32clipboard
        WINDOWS_API_AVAILABLE = True
    except ImportError:
        WINDOWS_API_AVAILABLE = False
        print("Warning: pywin32 not available - install with: pip install pywin32")
else:
    WINDOWS_API_AVAILABLE = False
    print("Note: Console injection only supported on Windows")
    print(f"      {platform.system()} users: VScript features work, but legacy spawning requires manual console")

class SourceBridge(SourceGameDiscoveryMixin):
    SUPPORTED_GAMES = {
        'Team Fortress 2': {
            'executables': ['hl2.exe', 'hl2_linux', 'tf_win64.exe', 'tf_linux64'],
            'game_dir': 'tf',
            'scriptdata': 'scriptdata',
            'cmdline_contains': 'Team Fortress 2'
        },
        'Counter-Strike Source': {
            'executables': ['hl2.exe', 'hl2_linux', 'cstrike.exe', 'cstrike_win64.exe', 'cstrike_linux64'],
            'game_dir': 'cstrike',
            'scriptdata': 'scriptdata',
            'cmdline_contains': 'Counter-Strike Source'
        },
        'Day of Defeat Source': {
            'executables': ['hl2.exe', 'hl2_linux', 'dod.exe', 'dod_win64.exe', 'dod_linux64'],
            'game_dir': 'dod',
            'scriptdata': 'scriptdata',
            'cmdline_contains': 'Day of Defeat Source'
        },
        'Half-Life 2 Deathmatch': {
            'executables': ['hl2.exe', 'hl2_linux', 'hl2mp.exe', 'hl2mp_win64.exe', 'hl2mp_linux64'],
            'game_dir': 'hl2mp',
            'scriptdata': 'scriptdata',
            'cmdline_contains': 'Half-Life 2 Deathmatch'
        },
        'Half-Life 1 Source Deathmatch': {
            'executables': ['hl2.exe', 'hl2_linux', 'hl1mp.exe', 'hl1mp_win64.exe', 'hl1mp_linux64'],
            'game_dir': 'hl1mp',
            'scriptdata': 'scriptdata',
            'cmdline_contains': 'Half-Life 1 Source Deathmatch'
        },
        'Garry\'s Mod 9': {
            'executables': ['hl2.exe', 'hl2_linux'],
            'game_dir': 'gmod9',
            'scriptdata': 'data',
            'cmdline_contains': 'gmod9',
            'is_gmod': True
        },
        'Garry\'s Mod 10': {
            'executables': ['hl2.exe', 'hl2_linux'],
            'game_dir': 'garrysmod10classic',
            'scriptdata': 'data',
            'cmdline_contains': 'garrysmod10classic',
            'is_gmod': True
        },
        'Garry\'s Mod 11': {
            'executables': ['hl2.exe', 'hl2_linux'],
            'game_dir': 'garrysmod',
            'scriptdata': 'data',
            'cmdline_contains': 'garrysmod',
            'is_gmod': True
        },
        'Garry\'s Mod 12': {
            'executables': ['hl2.exe', 'hl2_linux'],
            'game_dir': 'garrysmod12',
            'scriptdata': 'data',
            'cmdline_contains': 'garrysmod12',
            'is_gmod': True
        },
        'Garry\'s Mod 13': {
            'executables': ['hl2.exe', 'hl2_linux', 'gmod.exe', 'gmod', 'gmod64', 'gmod32', 'gmod_linux'],
            'game_dir': 'garrysmod',
            'scriptdata': 'data',
            'cmdline_contains': 'garrysmod',
            'is_gmod': True,
            'install_type': 'standalone',
            'install_dir': 'GarrysMod'
        }
    }

    def __init__(self, verbose=False):
        self.game_path = None
        self.vscripts_path = None
        self.command_file = None
        self.response_file = None
        self.running = False
        self.watcher_thread = None
        self.last_response_time = 0
        self.detected_games = []
        self.active_game = None
        self.verbose = verbose
        self.command_count = 0
        self.session_id = int(time.time() * 1000) + random.randint(0, 9999)
        self.gmod_bridge = None
        self.mapbase_bridge = None

        try:
            self._cleanup_old_files()
            self._detect_running_game()
        except Exception as e:
            print(f"[error] initialization failed: {e}")
            if self.verbose:
                traceback.print_exc()

    def _log(self, message):
        if self.verbose:
            print(f"[trace] {message}")

    def _safe_file_operation(self, operation, filepath, error_msg):
        """safely perform file operations with error handling"""
        try:
            return operation(filepath)
        except (PermissionError, FileNotFoundError):
            return False
        except Exception as e:
            if self.verbose:
                print(f"[error] {error_msg}: {e}")
            return False

    def _cleanup_old_files(self):
        """remove stale command/response files from previous sessions"""
        steam_install_path = self._get_steam_install_path()
        if not steam_install_path:
            return

        steam_libraries = self._parse_library_folders_vdf(steam_install_path)

        for library_path in steam_libraries:
            for game_name, game_info in self.SUPPORTED_GAMES.items():
                try:
                    if game_info.get('is_gmod'):
                        continue  # gmod cleanup handled by gmod bridge

                    game_root = os.path.join(library_path, 'steamapps', 'common', game_name)
                    if not os.path.exists(game_root):
                        game_root = os.path.join(library_path, 'SteamApps', 'common', game_name)

                    if not os.path.exists(game_root):
                        continue

                    scriptdata_path = os.path.join(game_root, game_info['game_dir'], game_info['scriptdata'])

                    if os.path.exists(scriptdata_path):
                        for filename in ["python_command.txt", "python_response.txt"]:
                            filepath = os.path.join(scriptdata_path, filename)
                            self._safe_file_operation(
                                lambda p: os.remove(p) if os.path.exists(p) else None,
                                filepath,
                                f"failed to cleanup {filename}"
                            )
                except:
                    continue

    def _get_steam_path_from_process(self):
        """Detect Steam from its running process."""
        return find_steam_from_process(self._log)

    def _get_steam_install_path(self):
        """Find the platform's Steam installation."""
        return find_steam_install(self._log)


    def _parse_library_folders_vdf(self, steam_path):
        """Return every valid Steam library in libraryfolders.vdf."""
        return parse_library_folders(steam_path, self._log)






    def _setup_sourcemod_from_path(self, mod_name, mod_path):
        """setup paths for a sourcemod using direct path from process"""
        try:
            # check if this is actually a mapbase mod
            if self._is_mapbase_path(mod_path):
                return self._setup_mapbase_mod(mod_name, mod_path)

            scriptdata_path = os.path.join(mod_path, 'scriptdata')
            cfg_path = os.path.join(mod_path, 'cfg')

            os.makedirs(scriptdata_path, exist_ok=True)
            os.makedirs(cfg_path, exist_ok=True)

            self.active_game = mod_name
            self.game_path = scriptdata_path
            self.vscripts_path = None
            self.command_file = None

            print(f"\n[active] Source Mod: {mod_name} (running)")
            print(f"  mod path: {mod_path}")

            if platform.system() == 'Windows' and WINDOWS_API_AVAILABLE:
                print("  mode: legacy console injection (no VScript)")
            else:
                print("  mode: no VScript support (manual spawning only)")

            print("="*70 + "\n")

            return True
        except Exception as e:
            print(f"[error] failed to setup paths: {e}")
            if self.verbose:
                traceback.print_exc()
            return False






    def install_listener(self):
        """write the vscript listener to game folder"""
        if not self.vscripts_path:
            if self.verbose:
                print("[info] VScript not supported, skipping listener install")
            return False

        vscript_code = self._get_listener_code()
        output_file = os.path.join(self.vscripts_path, "python_listener.nut")

        try:
            with open(output_file, 'w', encoding='utf-8', newline='\n') as f:
                f.write(vscript_code)

            print("\n[success] listener installed")
            print(f"  {output_file}")
            return True
        except PermissionError:
            print(f"[error] permission denied: {output_file}")
            return False
        except Exception as e:
            print(f"[error] install failed: {e}")
            if self.verbose:
                traceback.print_exc()
            return False

    def install_picker(self):
        """install the picker (aimbot) script"""
        if not self.vscripts_path:
            if self.verbose:
                print("[info] VScript not supported, skipping picker install")
            return False

        picker_code = load_text_resource("bridge_scripts/source/picker.nut")

        output_file = os.path.join(self.vscripts_path, "picker.nut")

        try:
            with open(output_file, 'w', encoding='utf-8', newline='\n') as f:
                f.write(picker_code)

            print("\n[success] picker installed")
            print(f"  {output_file}")
            return True
        except Exception as e:
            print(f"[error] picker install failed: {e}")
            if self.verbose:
                traceback.print_exc()
            return False

    def install_awp_quit(self):
        """install the AWP quit trigger script"""
        if not self.vscripts_path:
            if self.verbose:
                print("[info] VScript not supported, skipping AWP quit install")
            return False

        awp_quit_code = load_text_resource("bridge_scripts/source/awp_quit.nut")
        output_file = os.path.join(self.vscripts_path, "awp_quit_trigger.nut")

        try:
            with open(output_file, 'w', encoding='utf-8', newline='\n') as f:
                f.write(awp_quit_code)

            print("\n[success] awp quit trigger installed")
            print(f"  {output_file}")
            return True
        except Exception as e:
            print(f"[error] awp quit install failed: {e}")
            if self.verbose:
                traceback.print_exc()
            return False


    def reinstall_awp_outputs(self):
        """reinstall AWP damage outputs for newly spawned props"""
        if not self.game_path or not self.command_file:
            return False

        self.command_count += 1

        command_json = '{{"command":"reinstall_awp","id":{},"session":{}}}'.format(
            self.command_count,
            self.session_id
        )

        try:
            with open(self.command_file, 'w', encoding='ascii', newline='') as f:
                f.write(command_json)
                f.flush()
                os.fsync(f.fileno())

            time.sleep(0.05)
            return True
        except:
            return False

    def install_auto_spawner(self):
        """install the auto-spawner script that spawns cubes at smart locations on map load"""
        if not self.vscripts_path:
            if self.verbose:
                print("[info] VScript not supported, skipping auto-spawner install")
            return False

        auto_spawner_code = load_text_resource("bridge_scripts/source/auto_spawner.nut")

        output_file = os.path.join(self.vscripts_path, "auto_spawner.nut")

        try:
            with open(output_file, 'w', encoding='utf-8', newline='\n') as f:
                f.write(auto_spawner_code)

            print("\n[success] auto-spawner installed")
            print(f"  {output_file}")
            print("  features: smart spawning + AWP quit trigger")
            return True
        except Exception as e:
            print(f"[error] auto-spawner install failed: {e}")
            if self.verbose:
                traceback.print_exc()
            return False

    def setup_mapspawn(self):
        """create mapspawn.nut that auto-loads on every map"""
        if not self.vscripts_path:
            if self.verbose:
                print("[info] VScript not supported, skipping mapspawn setup")
            return False

        mapspawn_file = os.path.join(self.vscripts_path, "mapspawn.nut")

        mapspawn_content = '''// auto-load python bridge listener on map spawn
    if (!("g_scripts_loaded" in getroottable())) {
        ::g_scripts_loaded <- false;
        ::g_load_time <- 0.0;
    }

    ::LoadPythonScripts <- function() {
        local current_time = Time();

        if (current_time < g_load_time + 2.0) {
            return 0.1;
        }

        if (g_scripts_loaded) {
            return;
        }

        try {
            IncludeScript("python_listener");
        } catch(e) {}

        try {
            IncludeScript("picker");
        } catch(e) {}

        try {
            IncludeScript("awp_quit_trigger");
        } catch(e) {}

        try {
            IncludeScript("auto_spawner");
        } catch(e) {}

        g_scripts_loaded = true;

        return;
    }

    g_load_time = Time();
    g_scripts_loaded = false;

    local worldspawn = Entities.FindByClassname(null, "worldspawn");
    if (worldspawn != null) {
        AddThinkToEnt(worldspawn, "LoadPythonScripts");
    }
    '''

        try:
            with open(mapspawn_file, 'w', encoding='utf-8', newline='\n') as f:
                f.write(mapspawn_content)

            print("\n[success] mapspawn configured")
            print(f"  {mapspawn_file}")
            return True
        except Exception as e:
            print(f"[error] failed to setup mapspawn: {e}")
            if self.verbose:
                traceback.print_exc()
            return False

    def _get_listener_code(self):
        """generate the vscript listener code"""
        return load_text_resource("bridge_scripts/source/python_listener.nut")

    def start_listening(self):
        """start background thread to watch for responses"""
        if not self.game_path:
            print("[error] no game path set")
            return False

        try:
            self.running = True
            self.watcher_thread = threading.Thread(target=self._watch_responses, daemon=True)
            self.watcher_thread.start()
            return True
        except Exception as e:
            print(f"[error] failed to start listener: {e}")
            if self.verbose:
                traceback.print_exc()
            return False

    def _watch_responses(self):
        """background thread that monitors response file"""
        while self.running:
            try:
                if self.response_file and os.path.exists(self.response_file):
                    try:
                        modified_time = os.path.getmtime(self.response_file)
                        if modified_time > self.last_response_time:
                            self.last_response_time = modified_time
                            self._handle_response()
                    except (FileNotFoundError, PermissionError):
                        pass
                time.sleep(0.05)
            except Exception as e:
                if self.verbose:
                    print(f"[warning] watcher error: {e}")
                time.sleep(1)

    def _handle_response(self):
        """process response from vscript"""
        if not self.response_file:
            return

        try:
            with open(self.response_file, 'r') as f:
                content = f.read().strip()

            if not content:
                return

            data = json.loads(content)
            status = data.get('status')
            message = data.get('message', '')

            if status == 'spawned':
                print(f"  [spawned] {message}")
            elif status == 'error':
                print(f"  [error] {message}")
            else:
                print(f"  [response] {status}: {message}")
        except json.JSONDecodeError as e:
            if self.verbose:
                print(f"[warning] invalid response JSON: {e}")
        except Exception as e:
            if self.verbose:
                print(f"[warning] response handling error: {e}")

    def spawn(self, model_path, distance=200):
        """send spawn command to game (auto-detects method)"""
        if not self.game_path and not self.active_game:
            print("[error] no game configured")
            return False

        if not model_path or not isinstance(model_path, str):
            print("[error] invalid model path")
            return False

        if self.gmod_bridge and self.gmod_bridge.is_connected():
            return self.gmod_bridge.spawn_model(model_path, distance)

        # check if this is a supported VScript game with command file
        if self.command_file and (not self.active_game or "Garry's Mod" not in self.active_game):
            # use vscript method
            if not isinstance(distance, (int, float)) or distance <= 0:
                distance = 200

            self.command_count += 1
            safe_model_path = model_path.replace('\\', '\\\\').replace('"', '\\"')

            command_json = '{{"command":"spawn_model","model":"{}","distance":{},"id":{},"session":{}}}'.format(
                safe_model_path,
                int(distance),
                self.command_count,
                self.session_id
            )

            print(f"\n[command #{self.command_count}] {model_path}")

            try:
                with open(self.command_file, 'w', encoding='ascii', newline='') as f:
                    f.write(command_json)
                    f.flush()
                    os.fsync(f.fileno())

                time.sleep(0.05)
                return True
            except PermissionError:
                print(f"  [error] permission denied: {self.command_file}")
                return False
            except Exception as e:
                print(f"  [error] {e}")
                if self.verbose:
                    traceback.print_exc()
                return False
        else:
            # use legacy console injection method for unsupported games
            return self.spawn_legacy(model_path)

    def spawn_legacy(self, model_path):
        """spawn prop using sendmessage with frozen window (windows only)"""
        if self.active_game and 'Garry\'s Mod' in self.active_game:
            print("[info] GMod uses Lua bridge, not console injection")
            return False

        if not self.active_game or platform.system() != 'Windows':
            return False

        if not WINDOWS_API_AVAILABLE:
            return False

        try:
            # find hl2.exe window
            hl2_pid = None
            for proc in psutil.process_iter(['name', 'pid']):
                try:
                    if proc.info['name'].lower() == 'hl2.exe':
                        hl2_pid = proc.info['pid']
                        break
                except:
                    continue

            if not hl2_pid:
                return False

            def enum_windows_callback(hwnd, windows):
                if win32gui.IsWindowVisible(hwnd):
                    _, window_pid = win32process.GetWindowThreadProcessId(hwnd)
                    if window_pid == hl2_pid:
                        title = win32gui.GetWindowText(hwnd)
                        if title:
                            windows.append((hwnd, title))
                return True

            windows = []
            win32gui.EnumWindows(enum_windows_callback, windows)

            if not windows:
                return False

            game_hwnd = windows[0][0]

            # freeze window - disable redrawing
            WM_SETREDRAW = 0x000B
            win32api.SendMessage(game_hwnd, WM_SETREDRAW, 0, 0)

            # save user's clipboard
            original_clipboard = None
            try:
                win32clipboard.OpenClipboard()
                if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_UNICODETEXT):
                    original_clipboard = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
                elif win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_TEXT):
                    original_clipboard = win32clipboard.GetClipboardData(win32clipboard.CF_TEXT)
                win32clipboard.CloseClipboard()
            except:
                pass

            # set command to clipboard
            full_command = f'sv_cheats 1; prop_physics_create {model_path}'
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardText(full_command, win32clipboard.CF_TEXT)
            win32clipboard.CloseClipboard()

            # send keys to game window
            def send_key(vk_code, key_down=True):
                scan_code = win32api.MapVirtualKey(vk_code, 0)
                lparam = (scan_code << 16) | 1
                if not key_down:
                    lparam |= 0xC0000000
                msg = win32con.WM_KEYDOWN if key_down else win32con.WM_KEYUP
                win32api.SendMessage(game_hwnd, msg, vk_code, lparam)

            VK_OEM_3 = 0xC0  # backtick
            VK_CONTROL = 0x11
            VK_V = 0x56
            VK_RETURN = 0x0D

            # execute instantly
            send_key(VK_OEM_3, True)
            send_key(VK_OEM_3, False)
            send_key(VK_CONTROL, True)
            send_key(VK_V, True)
            send_key(VK_V, False)
            send_key(VK_CONTROL, False)
            send_key(VK_RETURN, True)
            send_key(VK_RETURN, False)
            send_key(VK_OEM_3, True)
            send_key(VK_OEM_3, False)

            # wait before unfreezing
            time.sleep(0.2)

            # unfreeze window - re-enable redrawing
            win32api.SendMessage(game_hwnd, WM_SETREDRAW, 1, 0)
            win32gui.InvalidateRect(game_hwnd, None, True)

            # restore user's clipboard
            try:
                win32clipboard.OpenClipboard()
                win32clipboard.EmptyClipboard()
                if original_clipboard:
                    if isinstance(original_clipboard, str):
                        win32clipboard.SetClipboardText(original_clipboard, win32clipboard.CF_UNICODETEXT)
                    else:
                        win32clipboard.SetClipboardData(win32clipboard.CF_TEXT, original_clipboard)
                win32clipboard.CloseClipboard()
            except:
                pass

            return True
        except:
            return False

    def stop(self):
        """stop background threads and cleanup"""
        self.running = False

        if self.watcher_thread:
            self.watcher_thread.join(timeout=1.0)

        if self.gmod_bridge and hasattr(self.gmod_bridge, 'cleanup'):
            try:
                self.gmod_bridge.cleanup()
            except:
                pass

        try:
            files_to_cleanup = [self.command_file, self.response_file]
            for filepath in files_to_cleanup:
                if filepath and os.path.exists(filepath):
                    try:
                        os.remove(filepath)
                    except:
                        pass
        except Exception as e:
            if self.verbose:
                print(f"[warning] cleanup error: {e}")


if __name__ == "__main__":
    bridge = SourceBridge(verbose=False)

    if bridge.active_game:
        # only install VScript features for supported games
        if bridge.vscripts_path:
            # check if this is a Mapbase mod - MapbaseBridge already installed scripts
            is_mapbase = bridge.mapbase_bridge is not None

            if not is_mapbase:
                # install standard Source VScript files for TF2/CS:S/etc
                bridge.install_listener()
                bridge.install_picker()
                bridge.install_awp_quit()
                bridge.install_auto_spawner()
                bridge.setup_mapspawn()

            bridge.start_listening()

        print("\n" + "="*70)
        print("SETUP COMPLETE")
        print("="*70)
        print(f"\n[game] {bridge.active_game}")
        print(f"[session] {bridge.session_id}")
        print("\n[features]")

        if bridge.vscripts_path:
            print("  python bridge - spawn the cube from sourcebox")
            print("  picker - aimbot (script PickerToggle and PickerNext)")
            print("  awp quit - shoot srcbox with awp to quit the game")
            print("  auto-spawner - spawns 1 cube at random locations on map load")
            print("\n[auto-load] all scripts start automatically on map load")
            print("\n[manual] if needed:")
            if bridge.mapbase_bridge:
                print("         exec mapbase_default")
                print("         script_execute vscript_server")
            else:
                print("         script_execute python_listener")
        else:
            print("  source game with no vscript! ONLY srcbox spawn is supported!")
            print("  mode: automatic console command injection (however you may have issues with this)")
            print("\n[usage] click cube in SourceBox to spawn")

        print("="*70 + "\n")
    else:
        print("\n[error] no source engine games found\n")
