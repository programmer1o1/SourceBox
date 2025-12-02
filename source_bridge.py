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
import re

if platform.system() == 'Windows':
    import winreg
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
    print("      Linux users: VScript features work, but sourcemod spawning requires manual console")

class SourceBridge:
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
            'executables': ['hl2.exe', 'hl2_linux', 'dod.exe', 'dod_win64.exe'],
            'game_dir': 'dod',
            'scriptdata': 'scriptdata',
            'cmdline_contains': 'Day of Defeat Source'
        },
        'Half-Life 2 Deathmatch': {
            'executables': ['hl2.exe', 'hl2_linux', 'hl2mp.exe', 'hl2mp_win64.exe'],
            'game_dir': 'hl2mp',
            'scriptdata': 'scriptdata',
            'cmdline_contains': 'Half-Life 2 Deathmatch'
        },
        'Half-Life 1 Source Deathmatch': {
            'executables': ['hl2.exe', 'hl2_linux', 'hl1mp.exe', 'hl1mp_win64.exe'],
            'game_dir': 'hl1mp',
            'scriptdata': 'scriptdata',
            'cmdline_contains': 'Half-Life 1 Source Deathmatch'
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
        """detect steam installation from running steam process"""
        try:
            for proc in psutil.process_iter(['name', 'exe']):
                try:
                    proc_name = proc.info['name']
                    if proc_name and proc_name.lower() in ['steam.exe', 'steam']:
                        exe_path = proc.info.get('exe')
                        if exe_path and os.path.exists(exe_path):
                            steam_dir = os.path.dirname(exe_path)
                            if os.path.exists(os.path.join(steam_dir, 'steamapps')):
                                self._log(f"found steam from process: {steam_dir}")
                                return steam_dir
                            
                            parent_dir = os.path.dirname(steam_dir)
                            if os.path.exists(os.path.join(parent_dir, 'steamapps')):
                                self._log(f"found steam from process: {parent_dir}")
                                return parent_dir
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
        except Exception as e:
            if self.verbose:
                print(f"[warning] process detection failed: {e}")
        
        return None
        
    def _get_steam_install_path(self):
        """get steam installation directory using multiple detection methods"""
        system = platform.system()
        
        if system == 'Windows':
            registry_paths = [
                r"SOFTWARE\Wow6432Node\Valve\Steam",
                r"SOFTWARE\Valve\Steam"
            ]
            
            for reg_path in registry_paths:
                try:
                    hkey = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path)
                    install_path, _ = winreg.QueryValueEx(hkey, "InstallPath")
                    winreg.CloseKey(hkey)
                    if install_path and os.path.exists(install_path):
                        self._log(f"found steam via registry: {install_path}")
                        return install_path
                except (FileNotFoundError, OSError):
                    continue
            
            process_path = self._get_steam_path_from_process()
            if process_path:
                return process_path
            
            for path in [r"C:\Program Files (x86)\Steam", r"C:\Program Files\Steam"]:
                if os.path.exists(path):
                    self._log(f"found steam at default location: {path}")
                    return path
            
        elif system == 'Linux':
            for path in ["~/.local/share/Steam", "~/.steam/steam", "~/.steam/root"]:
                expanded = os.path.expanduser(path)
                if os.path.islink(expanded):
                    expanded = os.path.realpath(expanded)
                if os.path.exists(expanded):
                    self._log(f"found steam at: {expanded}")
                    return expanded
            
            flatpak_steam = "~/.var/app/com.valvesoftware.Steam/.local/share/Steam"
            expanded_flatpak = os.path.expanduser(flatpak_steam)
            if os.path.exists(expanded_flatpak):
                self._log(f"found flatpak steam at: {expanded_flatpak}")
                return expanded_flatpak
            
            process_path = self._get_steam_path_from_process()
            if process_path:
                return process_path
        
        return None
        
    def _get_running_game_library(self, game_name):
        """detect which steam library the running game is in"""
        try:
            for proc in psutil.process_iter(['name', 'exe', 'cmdline']):
                try:
                    proc_name = proc.info['name']
                    exe_path = proc.info.get('exe')
                    cmdline = proc.info['cmdline']
                    
                    if not cmdline or not exe_path:
                        continue
                    
                    cmdline_str = ' '.join(cmdline).lower()
                    game_info = self.SUPPORTED_GAMES.get(game_name)
                    
                    if not game_info:
                        continue
                    
                    if proc_name.lower() in [exe.lower() for exe in game_info['executables']]:
                        if game_info['cmdline_contains'].lower() in cmdline_str or \
                           game_info['game_dir'] in cmdline_str:
                            exe_dir = os.path.dirname(exe_path)
                            current = exe_dir
                            for _ in range(10):
                                if os.path.exists(os.path.join(current, 'steamapps')):
                                    self._log(f"detected running game library: {current}")
                                    return current
                                parent = os.path.dirname(current)
                                if parent == current:
                                    break
                                current = parent
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
        except Exception as e:
            if self.verbose:
                print(f"[warning] running game library detection failed: {e}")
        
        return None
        
    def _parse_library_folders_vdf(self, steam_path):
        """parse libraryfolders.vdf to get all steam library locations"""
        vdf_path = os.path.join(steam_path, 'steamapps', 'libraryfolders.vdf')
        if not os.path.exists(vdf_path):
            vdf_path = os.path.join(steam_path, 'SteamApps', 'libraryfolders.vdf')
        
        if not os.path.exists(vdf_path):
            self._log(f"libraryfolders.vdf not found")
            return [steam_path]
        
        libraries = [steam_path]
        
        try:
            with open(vdf_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            path_pattern = r'"path"\s+"([^"]+)"'
            matches = re.findall(path_pattern, content)
            
            for match in matches:
                library_path = match.replace('\\\\', '\\')
                if os.path.exists(library_path) and library_path not in libraries:
                    libraries.append(library_path)
                    self._log(f"found library: {library_path}")
            
            return libraries
        except Exception as e:
            self._log(f"failed to parse libraryfolders.vdf: {e}")
            return [steam_path]
        
    def _detect_running_game(self):
        """find which source game is currently running"""
        print("\n" + "="*70)
        print("SOURCE ENGINE BRIDGE")
        print("="*70)
        print("\n[scan] detecting steam libraries...")
        
        steam_install_path = self._get_steam_install_path()
        
        if not steam_install_path:
            print("  [error] steam installation not found")
            print("="*70 + "\n")
            return
        
        print(f"  [steam] {steam_install_path}")
        
        all_steam_libraries = self._parse_library_folders_vdf(steam_install_path)
        print(f"  [libraries] found {len(all_steam_libraries)} steam libraries")
        
        print("\n[scan] detecting running games...")
        running_game = None
        running_mod = None
        running_mod_path = None
        
        try:
            for proc in psutil.process_iter(['name', 'cmdline', 'exe']):
                try:
                    proc_name = proc.info.get('name')
                    if not proc_name:
                        continue
                    
                    cmdline = proc.info.get('cmdline')
                    if not cmdline:
                        continue
                    
                    cmdline_str = ' '.join(cmdline)
                    
                    # check for supported games first
                    for game_name, game_info in self.SUPPORTED_GAMES.items():
                        if proc_name.lower() in [exe.lower() for exe in game_info['executables']]:
                            if game_info['cmdline_contains'].lower() in cmdline_str.lower() or \
                               game_info['game_dir'] in cmdline_str.lower():
                                running_game = game_name
                                print(f"  [found] {game_name}")
                                self._log(f"  process: {proc_name}")
                                break
                    
                    if running_game:
                        break
                    
                    # check for hl2.exe with -game argument (source mods)
                    if proc_name.lower() == 'hl2.exe':
                        game_paths = []
                        for i, arg in enumerate(cmdline):
                            if arg.lower() == '-game' and i + 1 < len(cmdline):
                                game_arg = cmdline[i + 1].strip('"')
                                game_paths.append(game_arg)
                        
                        # look for the one with full path containing 'sourcemods'
                        for game_path in game_paths:
                            if 'sourcemods' in game_path.lower():
                                parts = game_path.replace('\\', '/').split('/')
                                for i, part in enumerate(parts):
                                    if part.lower() == 'sourcemods' and i + 1 < len(parts):
                                        running_mod = parts[i + 1]
                                        running_mod_path = game_path
                                        print(f"  [found] Source Mod: {running_mod}")
                                        print(f"  [process] hl2.exe -game {running_mod_path}")
                                        break
                                
                                if running_mod:
                                    break
                        
                        if running_mod:
                            break
                        
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
                except Exception as e:
                    if self.verbose:
                        print(f"[warning] process check error: {e}")
                    continue
        except Exception as e:
            print(f"[warning] process enumeration error: {e}")
        
        if running_mod:
            if running_mod_path:
                if self._setup_sourcemod_from_path(running_mod, running_mod_path):
                    return
            else:
                if self._setup_sourcemod_path(running_mod, all_steam_libraries):
                    return
            
            print(f"[warning] found mod '{running_mod}' but couldn't setup paths")
        
        if not running_game:
            print("  [info] no running game found, scanning installed games...")
            self._scan_installed_games(all_steam_libraries)
            self._scan_sourcemods(all_steam_libraries)
        else:
            active_library = self._get_running_game_library(running_game)
            
            if active_library:
                steam_libraries = [active_library]
                print(f"  [active library] {active_library}")
            else:
                steam_libraries = all_steam_libraries
                print(f"  [warning] couldn't detect active library, checking all libraries")
            
            if not self._setup_game_path(running_game, steam_libraries):
                print(f"[error] failed to locate {running_game} files")
                self._scan_installed_games(all_steam_libraries)
                self._scan_sourcemods(all_steam_libraries)
    
    def _setup_sourcemod_from_path(self, mod_name, mod_path):
        """setup paths for a sourcemod using direct path from process"""
        try:
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
            print(f"  mode: console injection (no VScript)")
            print("="*70 + "\n")
            
            return True
        except Exception as e:
            print(f"[error] failed to setup paths: {e}")
            if self.verbose:
                traceback.print_exc()
            return False
    
    def _setup_sourcemod_path(self, mod_name, steam_libraries):
        """setup paths for a sourcemod"""
        for library_path in steam_libraries:
            sourcemod_path = os.path.join(library_path, 'steamapps', 'sourcemods', mod_name)
            if not os.path.exists(sourcemod_path):
                sourcemod_path = os.path.join(library_path, 'SteamApps', 'sourcemods', mod_name)
            
            if os.path.exists(sourcemod_path):
                return self._setup_sourcemod_from_path(mod_name, sourcemod_path)
        
        return False
    
    def _scan_sourcemods(self, steam_libraries):
        """scan for installed source mods in sourcemods folder"""
        print("\n[scan] detecting Source mods...")
        
        for library_path in steam_libraries:
            sourcemods_path = os.path.join(library_path, 'steamapps', 'sourcemods')
            if not os.path.exists(sourcemods_path):
                sourcemods_path = os.path.join(library_path, 'SteamApps', 'sourcemods')
            
            if not os.path.exists(sourcemods_path):
                continue
            
            try:
                for mod_name in os.listdir(sourcemods_path):
                    mod_path = os.path.join(sourcemods_path, mod_name)
                    
                    if os.path.isdir(mod_path):
                        gameinfo_path = os.path.join(mod_path, 'gameinfo.txt')
                        if os.path.exists(gameinfo_path):
                            scriptdata_path = os.path.join(mod_path, 'scriptdata')
                            os.makedirs(scriptdata_path, exist_ok=True)
                            
                            self.detected_games.append({
                                'name': mod_name,
                                'library': library_path,
                                'scriptdata_path': scriptdata_path,
                                'vscripts_path': None,
                                'is_sourcemod': True
                            })
                            print(f"  [sourcemod] {mod_name} (in {library_path})")
            except Exception as e:
                if self.verbose:
                    print(f"[warning] Error scanning sourcemods: {e}")
        
        # if no supported games found, use first sourcemod
        if not self.active_game and self.detected_games:
            for game in self.detected_games:
                if game.get('is_sourcemod'):
                    print(f"\n[active] using Source Mod: {game['name']} (not running)")
                    self.active_game = game['name']
                    self.game_path = game['scriptdata_path']
                    self.vscripts_path = None
                    self.command_file = None
                    print("  mode: console injection (no VScript)")
                    break
    
    def _setup_game_path(self, game_name, steam_libraries):
        """setup paths for specific game using discovered libraries"""
        game_info = self.SUPPORTED_GAMES.get(game_name)
        if not game_info:
            print(f"[error] unknown game: {game_name}")
            return False
        
        for library_path in steam_libraries:
            game_root = os.path.join(library_path, 'steamapps', 'common', game_name)
            if not os.path.exists(game_root):
                game_root = os.path.join(library_path, 'SteamApps', 'common', game_name)
            
            if os.path.exists(game_root):
                try:
                    scriptdata_path = os.path.join(game_root, game_info['game_dir'], game_info['scriptdata'])
                    vscripts_path = os.path.join(game_root, game_info['game_dir'], 'scripts', 'vscripts')
                    
                    os.makedirs(scriptdata_path, exist_ok=True)
                    os.makedirs(vscripts_path, exist_ok=True)
                    
                    self.active_game = game_name
                    self.game_path = scriptdata_path
                    self.vscripts_path = vscripts_path
                    
                    self.command_file = os.path.join(self.game_path, "python_command.txt")
                    self.response_file = os.path.join(self.game_path, "python_response.txt")
                    
                    self._log(f"command file: {self.command_file}")
                    self._log(f"response file: {self.response_file}")
                    self._log(f"session ID: {self.session_id}")
                    
                    print(f"\n[active] {game_name}")
                    print(f"  library: {library_path}")
                    print(f"  scriptdata: {scriptdata_path}")
                    print(f"  vscripts: {vscripts_path}")
                    
                    return True
                except Exception as e:
                    print(f"[error] failed to setup paths: {e}")
                    if self.verbose:
                        traceback.print_exc()
                    return False
        
        return False
        
    def _scan_installed_games(self, steam_libraries):
        """fallback to first installed game if none running"""
        for library_path in steam_libraries:
            for game_name, game_info in self.SUPPORTED_GAMES.items():
                try:
                    game_root = os.path.join(library_path, 'steamapps', 'common', game_name)
                    if not os.path.exists(game_root):
                        game_root = os.path.join(library_path, 'SteamApps', 'common', game_name)
                    
                    if os.path.exists(game_root):
                        scriptdata_path = os.path.join(game_root, game_info['game_dir'], game_info['scriptdata'])
                        vscripts_path = os.path.join(game_root, game_info['game_dir'], 'scripts', 'vscripts')
                        
                        os.makedirs(scriptdata_path, exist_ok=True)
                        os.makedirs(vscripts_path, exist_ok=True)
                        
                        self.detected_games.append({
                            'name': game_name,
                            'library': library_path,
                            'scriptdata_path': scriptdata_path,
                            'vscripts_path': vscripts_path
                        })
                        print(f"  [installed] {game_name} (in {library_path})")
                except Exception as e:
                    if self.verbose:
                        print(f"[warning] scan error for {game_name}: {e}")
                    continue
        
        if self.detected_games:
            try:
                print(f"\n[active] using {self.detected_games[0]['name']} (not running)")
                self.active_game = self.detected_games[0]['name']
                self.game_path = self.detected_games[0]['scriptdata_path']
                self.vscripts_path = self.detected_games[0]['vscripts_path']
                
                self.command_file = os.path.join(self.game_path, "python_command.txt")
                self.response_file = os.path.join(self.game_path, "python_response.txt")
            except Exception as e:
                print(f"[error] failed to setup fallback game: {e}")
        else:
            print("\n[error] no source engine games found in any steam library")
    
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
            
            print(f"\n[success] listener installed")
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
        
        picker_code = r"""
if (!("g_enabled" in getroottable()))
{
    ::g_enabled <- {};
    ::g_target <- {};
    ::g_manual <- {};
    ::g_targets <- {};
    ::g_targetidx <- {};
    ::g_manualtime <- {};
    ::g_lasthud <- {};
    ::g_first <- true;
}
else
{
    ::g_first <- false;
}

if (!("g_teamplay" in getroottable()))
{
    ::g_teamplay <- null;
}

::MAX_DIST <- 5000.0;
::SMOOTH <- 0.15;
::MANUAL_TIMEOUT <- 3.0;

::DetectTeamplay <- function()
{
    if (g_teamplay != null)
        return g_teamplay;
    
    local hasRealTeams = false;
    local teamCounts = {};
    
    local p = null;
    local count = 0;
    while ((p = Entities.FindByClassname(p, "player")) != null)
    {
        if (p.IsAlive())
        {
            local t = p.GetTeam();
            if (t >= 2)
            {
                if (!(t in teamCounts))
                    teamCounts[t] <- 0;
                teamCounts[t]++;
                count++;
            }
        }
    }
    
    local numTeams = 0;
    foreach (team, cnt in teamCounts)
    {
        if (cnt > 0)
            numTeams++;
    }
    
    if (numTeams >= 2)
    {
        g_teamplay = true;
    }
    else
    {
        try
        {
            local val = Convars.GetFloat("mp_teamplay");
            g_teamplay = (val > 0);
        }
        catch (e)
        {
            g_teamplay = false;
        }
    }
    
    return g_teamplay;
}

::InitPlayer <- function(p)
{
    local id = p.GetEntityIndex().tostring();
    g_enabled[id] <- false;
    g_target[id] <- null;
    g_manual[id] <- false;
    g_targets[id] <- [];
    g_targetidx[id] <- 0;
    g_manualtime[id] <- 0.0;
    g_lasthud[id] <- 0.0;
}

::ShowHud <- function(p, msg)
{
    local txt = SpawnEntityFromTable("game_text", {
        message = msg,
        channel = 1,
        x = -1,
        y = 0.53,
        effect = 0,
        color = "255 160 0",
        color2 = "255 160 0",
        fadein = 0.0,
        fadeout = 0.0,
        holdtime = 0.55,
        fxtime = 0,
        spawnflags = 0
    });
    
    if (txt != null)
    {
        EntFireByHandle(txt, "Display", "", 0.0, p, p);
        EntFireByHandle(txt, "Kill", "", 0.6, null, null);
    }
}

::ClearHud <- function(p)
{
    local txt = SpawnEntityFromTable("game_text", {
        message = "",
        channel = 1,
        x = -1,
        y = 0.53,
        holdtime = 0
    });
    
    if (txt != null)
    {
        EntFireByHandle(txt, "Display", "", 0.0, p, p);
        EntFireByHandle(txt, "Kill", "", 0.01, null, null);
    }
}

::Toggle <- function(p)
{
    local id = p.GetEntityIndex().tostring();
    
    if (!(id in g_enabled))
        InitPlayer(p);
    
    g_enabled[id] = !g_enabled[id];
    g_target[id] = null;
    g_manual[id] = false;
    g_targetidx[id] = 0;
    g_manualtime[id] = 0.0;
    g_targets[id] = [];
    
    if (!g_enabled[id])
        ClearHud(p);
}

::NextTarget <- function(p)
{
    local id = p.GetEntityIndex().tostring();
    
    if (!(id in g_enabled) || !g_enabled[id] || !p.IsAlive())
        return;
    
    g_manual[id] = true;
    g_manualtime[id] = Time();
    g_targets[id] = BuildList(p);
    
    if (g_targets[id].len() > 0)
    {
        g_targetidx[id]++;
        if (g_targetidx[id] >= g_targets[id].len())
            g_targetidx[id] = 0;
        
        g_target[id] = g_targets[id][g_targetidx[id]];
    }
}

::BuildList <- function(p)
{
    local list = [];
    local team = p.GetTeam();
    local pos = p.EyePosition();
    local teamplay = DetectTeamplay();
    
    local e = null;
    while ((e = Entities.FindByClassname(e, "player")) != null)
    {
        if (e == p || !e.IsAlive())
            continue;
        
        local t = e.GetTeam();
        
        if (teamplay)
        {
            if (t <= 1 || t == team)
                continue;
        }
        
        local tpos = e.EyePosition();
        local dist = (tpos - pos).Length();
        
        if (dist > MAX_DIST || !CanSee(p, e, tpos))
            continue;
        
        list.append(e);
    }
    
    if (teamplay)
    {
        e = null;
        while ((e = Entities.FindByClassname(e, "player")) != null)
        {
            if (e == p || !e.IsAlive())
                continue;
            
            local t = e.GetTeam();
            if (t <= 1 || t != team)
                continue;
            
            local tpos = e.EyePosition();
            local dist = (tpos - pos).Length();
            
            if (dist > MAX_DIST || !CanSee(p, e, tpos))
                continue;
            
            list.append(e);
        }
    }
    
    local props = ["prop_physics", "prop_physics_multiplayer", "prop_physics_override"];
    foreach (c in props)
    {
        e = null;
        while ((e = Entities.FindByClassname(e, c)) != null)
        {
            local tpos = e.GetOrigin();
            local dist = (tpos - pos).Length();
            
            if (dist > MAX_DIST || !CanSee(p, e, tpos))
                continue;
            
            list.append(e);
        }
    }
    
    return list;
}

::IsValid <- function(p, e)
{
    if (e == null || !e.IsValid())
        return false;
    
    local c = e.GetClassname();
    if (c == "player")
    {
        if (!e.IsAlive() || e == p)
            return false;
        
        local t = e.GetTeam();
        local teamplay = DetectTeamplay();
        
        if (teamplay && t <= 1)
            return false;
        
        return CanSee(p, e, e.EyePosition());
    }
    
    return CanSee(p, e, e.GetOrigin());
}

::GetBest <- function(p)
{
    local team = p.GetTeam();
    local pos = p.EyePosition();
    local teamplay = DetectTeamplay();
    
    local bestEnemy = null;
    local bestTeam = null;
    local bestProp = null;
    local bestEDist = 999999.0;
    local bestTDist = 999999.0;
    local bestPDist = 999999.0;
    
    local e = null;
    while ((e = Entities.FindByClassname(e, "player")) != null)
    {
        if (e == p || !e.IsAlive())
            continue;
        
        local t = e.GetTeam();
        
        local tpos = e.EyePosition();
        local dist = (tpos - pos).Length();
        
        if (dist > MAX_DIST || !CanSee(p, e, tpos))
            continue;
        
        if (teamplay)
        {
            if (t <= 1)
                continue;
            
            if (t != team)
            {
                if (dist < bestEDist)
                {
                    bestEDist = dist;
                    bestEnemy = e;
                }
            }
            else
            {
                if (dist < bestTDist)
                {
                    bestTDist = dist;
                    bestTeam = e;
                }
            }
        }
        else
        {
            if (dist < bestEDist)
            {
                bestEDist = dist;
                bestEnemy = e;
            }
        }
    }
    
    if (bestEnemy != null)
        return bestEnemy;
    
    if (bestTeam != null)
        return bestTeam;
    
    local props = ["prop_physics", "prop_physics_multiplayer", "prop_physics_override"];
    foreach (c in props)
    {
        e = null;
        while ((e = Entities.FindByClassname(e, c)) != null)
        {
            local tpos = e.GetOrigin();
            local dist = (tpos - pos).Length();
            
            if (dist > MAX_DIST || !CanSee(p, e, tpos))
                continue;
            
            if (dist < bestPDist)
            {
                bestPDist = dist;
                bestProp = e;
            }
        }
    }
    
    return bestProp;
}

::CanSee <- function(p, t, tpos)
{
    local start = p.EyePosition();
    local trace = {
        start = start,
        end = tpos,
        ignore = p
    };
    
    TraceLineEx(trace);
    
    if ("enthit" in trace && trace.enthit == t)
        return true;
    
    if ("pos" in trace)
    {
        local d = (trace.pos - tpos).Length();
        if (d < 100.0)
            return true;
    }
    
    return false;
}

::CalcAngles <- function(from, to)
{
    local d = to - from;
    local h = d.Length();
    
    if (h < 0.001)
        return QAngle(0, 0, 0);
    
    local pitch = asin(-d.z / h) * (180.0 / 3.14159);
    local yaw = atan2(d.y, d.x) * (180.0 / 3.14159);
    
    return QAngle(pitch, yaw, 0);
}

::NormAngle <- function(a)
{
    while (a > 180.0) a -= 360.0;
    while (a < -180.0) a += 360.0;
    return a;
}

::Lerp <- function(from, to, amt)
{
    local d = NormAngle(to - from);
    return from + d * amt;
}

::Aim <- function(p, e)
{
    local ppos = p.EyePosition();
    local tpos = e.GetClassname() == "player" ? e.EyePosition() : e.GetOrigin();
    
    local want = CalcAngles(ppos, tpos);
    local cur = p.EyeAngles();
    
    local dp = NormAngle(want.x - cur.x);
    local dy = NormAngle(want.y - cur.y);
    local td = sqrt(dp * dp + dy * dy);
    
    local smooth = SMOOTH;
    if (td < 5.0) smooth *= 0.6;
    else if (td > 30.0) smooth *= 1.3;
    
    local np = Lerp(cur.x, want.x, smooth);
    local ny = Lerp(cur.y, want.y, smooth);
    
    if (np > 89.0) np = 89.0;
    if (np < -89.0) np = -89.0;
    
    while (ny > 180.0) ny -= 360.0;
    while (ny < -180.0) ny += 360.0;
    
    p.SnapEyeAngles(QAngle(np, ny, 0));
}

::PickerThink <- function()
{
    local t = Time();
    
    local p = null;
    try { p = GetListenServerHost() } catch(e) {}
    if (p == null) { 
        try { p = Entities.FindByClassname(null, "player") } catch(e) {} 
    }
    
    if (p == null || !p.IsAlive()) {
        return 0.015;
    }
    
    local id = p.GetEntityIndex().tostring();
    
    if (!(id in g_enabled))
        InitPlayer(p);
    
    if (t - g_lasthud[id] > 0.54)
    {
        if (g_enabled[id])
            ShowHud(p, "PICKER ON");
        else
            ClearHud(p);
        
        g_lasthud[id] = t;
    }
    
    if (!g_enabled[id])
        return 0.015;
    
    if (g_manual[id] && t - g_manualtime[id] > MANUAL_TIMEOUT)
        g_manual[id] = false;
    
    if (g_manual[id])
    {
        if (g_target[id] == null || !IsValid(p, g_target[id]))
        {
            g_manual[id] = false;
        }
        else
        {
            local best = GetBest(p);
            if (best != null)
            {
                local curEnemy = false;
                local curClass = g_target[id].GetClassname();
                
                if (curClass == "player")
                {
                    local ct = g_target[id].GetTeam();
                    local pt = p.GetTeam();
                    local teamplay = DetectTeamplay();
                    
                    if (teamplay)
                    {
                        if (ct != pt && ct > 1)
                            curEnemy = true;
                    }
                    else
                    {
                        curEnemy = true;
                    }
                }
                
                local bestEnemy = false;
                local bestClass = best.GetClassname();
                
                if (bestClass == "player")
                {
                    local bt = best.GetTeam();
                    local pt = p.GetTeam();
                    local teamplay = DetectTeamplay();
                    
                    if (teamplay)
                    {
                        if (bt != pt && bt > 1)
                            bestEnemy = true;
                    }
                    else
                    {
                        bestEnemy = true;
                    }
                }
                
                if (bestEnemy && !curEnemy)
                {
                    g_manual[id] = false;
                    g_target[id] = best;
                }
                else if (bestEnemy && curEnemy)
                {
                    local ppos = p.EyePosition();
                    local cd = (g_target[id].EyePosition() - ppos).Length();
                    local bd = (best.EyePosition() - ppos).Length();
                    
                    if (bd < cd * 0.5)
                    {
                        g_manual[id] = false;
                        g_target[id] = best;
                    }
                }
            }
        }
    }
    else
    {
        local nt = GetBest(p);
        if (nt != null)
            g_target[id] = nt;
    }
    
    if (g_target[id] != null)
        Aim(p, g_target[id]);
    
    return 0.015;
}

::OnGameEvent_round_start <- function(params)
{
    g_teamplay = null;
    
    foreach (id, _ in g_enabled)
    {
        g_target[id] = null;
        g_manual[id] = false;
        g_targetidx[id] = 0;
        g_manualtime[id] = 0.0;
        g_targets[id] = [];
    }
}

__CollectGameEventCallbacks(this);

::PickerToggle <- function() {
    local player = null
    try { player = GetListenServerHost() } catch(e) {}
    if (player == null) { try { player = Entities.FindByClassname(null, "player") } catch(e) {} }
    if (player != null) Toggle(player)
}

::PickerNext <- function() {
    local player = null
    try { player = GetListenServerHost() } catch(e) {}
    if (player == null) { try { player = Entities.FindByClassname(null, "player") } catch(e) {} }
    if (player != null) NextTarget(player)
}

if ("RegisterThinkFunction" in getroottable()) {
    RegisterThinkFunction("picker", PickerThink, 0.0)
} else {
    ::DelayedRegisterPicker <- function() {
        if ("RegisterThinkFunction" in getroottable()) {
            RegisterThinkFunction("picker", PickerThink, 0.0)
        }
    }
    
    DoEntFire("worldspawn", "RunScriptCode", "DelayedRegisterPicker()", 1.0, null, null)
}
"""
        
        output_file = os.path.join(self.vscripts_path, "picker.nut")
        
        try:
            with open(output_file, 'w', encoding='utf-8', newline='\n') as f:
                f.write(picker_code)
            
            print(f"\n[success] picker installed")
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
        
        awp_quit_code = r"""
if (!("g_tracked_props" in getroottable())) {
    ::g_tracked_props <- [];
}

::awp_weapon_classes <- [
    "weapon_awp"
]

::QuitGame <- function() {
    SendToConsole("quit")
}

::TrackExistingProps <- function() {
    local prop = null
    while ((prop = Entities.FindByClassname(prop, "prop_physics")) != null) {
        local model = prop.GetModelName()
        if (model.find("srcbox") != null) {
            local already_tracked = false
            foreach (tracked in g_tracked_props) {
                if (tracked == prop) {
                    already_tracked = true
                    break
                }
            }
            
            if (!already_tracked) {
                g_tracked_props.append(prop)
            }
        }
    }
    
    prop = null
    while ((prop = Entities.FindByClassname(prop, "prop_dynamic")) != null) {
        local model = prop.GetModelName()
        if (model.find("srcbox") != null) {
            local already_tracked = false
            foreach (tracked in g_tracked_props) {
                if (tracked == prop) {
                    already_tracked = true
                    break
                }
            }
            
            if (!already_tracked) {
                g_tracked_props.append(prop)
            }
        }
    }
}

::CheckPropDamage <- function() {
    local prop = null
    while ((prop = Entities.FindByClassname(prop, "prop_physics")) != null) {
        local model = prop.GetModelName()
        if (model.find("srcbox") != null) {
            local already_tracked = false
            foreach (tracked in g_tracked_props) {
                if (tracked == prop) {
                    already_tracked = true
                    break
                }
            }
            
            if (!already_tracked) {
                g_tracked_props.append(prop)
                
                prop.ValidateScriptScope()
                local scope = prop.GetScriptScope()
                scope.last_health <- prop.GetHealth()
            }
        }
    }
    
    foreach (idx, prop in g_tracked_props) {
        if (prop == null || !prop.IsValid()) {
            g_tracked_props.remove(idx)
            continue
        }
        
        prop.ValidateScriptScope()
        local scope = prop.GetScriptScope()
        
        if (!("last_health" in scope)) {
            scope.last_health <- prop.GetHealth()
        }
        
        local current_health = prop.GetHealth()
        
        if (current_health < scope.last_health) {
            CheckAttackerWeapon(prop)
            scope.last_health <- current_health
        }
    }
    
    return 0.1
}

::CheckAttackerWeapon <- function(damaged_prop) {
    local host = null
    try { host = GetListenServerHost() } catch(e) {}
    if (host == null) { 
        try { host = Entities.FindByClassname(null, "player") } catch(e) {} 
    }
    
    if (host == null) return
    
    local player = null
    while ((player = Entities.FindByClassname(player, "player")) != null) {
        if (player != host) continue
        
        local weapon = null
        
        try {
            weapon = player.GetActiveWeapon()
        } catch(e) {
            local search_radius = 100
            local ent = null
            while ((ent = Entities.FindInSphere(ent, player.GetOrigin(), search_radius)) != null) {
                local classname = ent.GetClassname()
                
                foreach (awp_class in awp_weapon_classes) {
                    if (classname == awp_class) {
                        weapon = ent
                        break
                    }
                }
                
                if (weapon != null) break
            }
        }
        
        if (weapon != null) {
            local weapon_class = weapon.GetClassname()
            
            foreach (awp_class in awp_weapon_classes) {
                if (weapon_class == awp_class) {
                    EntFireByHandle(damaged_prop, "RunScriptCode", "QuitGame()", 0.1, null, null)
                    return
                }
            }
        }
    }
}

::SetupDamageOutput <- function() {
    local prop = null
    while ((prop = Entities.FindByClassname(prop, "prop_physics")) != null) {
        local model = prop.GetModelName()
        if (model.find("srcbox") != null) {
            EntFireByHandle(prop, "AddOutput", "OnTakeDamage !self:RunScriptCode:OnPropDamaged():0:-1", 0, null, null)
        }
    }
}

::OnPropDamaged <- function() {
    CheckAttackerWeapon(self)
}

TrackExistingProps()
SetupDamageOutput()

if ("RegisterThinkFunction" in getroottable()) {
    RegisterThinkFunction("awp_quit", CheckPropDamage, 0.0)
} else {
    ::DelayedRegisterAWP <- function() {
        if ("RegisterThinkFunction" in getroottable()) {
            RegisterThinkFunction("awp_quit", CheckPropDamage, 0.0)
        }
    }
    
    DoEntFire("worldspawn", "RunScriptCode", "DelayedRegisterAWP()", 1.5, null, null)
}
"""
    
        output_file = os.path.join(self.vscripts_path, "awp_quit_trigger.nut")
        
        try:
            with open(output_file, 'w', encoding='utf-8', newline='\n') as f:
                f.write(awp_quit_code)
            
            print(f"\n[success] awp quit trigger installed")
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
        
        auto_spawner_code = r"""
    if (!("g_auto_spawn_initialized" in getroottable())) {
        ::g_auto_spawn_initialized <- false;
        ::g_spawned_cubes <- [];
        ::g_spawn_attempts <- 0;
        ::g_spawn_method_index <- 0;
    }

    ::CUBE_MODEL <- "models/props/srcbox/srcbox.mdl";
    ::awp_weapon_classes <- ["weapon_awp"];

    ::QuitGame <- function() {
        SendToConsole("quit")
    }

    ::CheckRespawn <- function() {
        if (g_auto_spawn_initialized && g_spawned_cubes.len() > 0) {
            local cube = g_spawned_cubes[0];
            if (cube == null || !cube.IsValid()) {
                g_spawned_cubes = [];
                g_auto_spawn_initialized = false;
                g_spawn_attempts = 0;
            }
        }
        return 0.5;
    }
    
    ::CheckAttackerWeapon <- function(damaged_prop) {
        local host = null;
        try { host = GetListenServerHost() } catch(e) {}
        if (host == null) { 
            try { host = Entities.FindByClassname(null, "player") } catch(e) {} 
        }
        
        if (host == null) return;
        
        local player = null;
        while ((player = Entities.FindByClassname(player, "player")) != null) {
            if (player != host) continue;
            
            local weapon = null;
            
            try {
                weapon = player.GetActiveWeapon();
            } catch(e) {
                local search_radius = 100;
                local ent = null;
                while ((ent = Entities.FindInSphere(ent, player.GetOrigin(), search_radius)) != null) {
                    local classname = ent.GetClassname();
                    
                    foreach (awp_class in awp_weapon_classes) {
                        if (classname == awp_class) {
                            weapon = ent;
                            break;
                        }
                    }
                    
                    if (weapon != null) break;
                }
            }
            
            if (weapon != null) {
                local weapon_class = weapon.GetClassname();
                
                foreach (awp_class in awp_weapon_classes) {
                    if (weapon_class == awp_class) {
                        EntFireByHandle(damaged_prop, "RunScriptCode", "QuitGame()", 0.1, null, null);
                        return;
                    }
                }
            }
        }
    }

    ::SetupCubeDamageOutput <- function(cube) {
        if (cube != null && cube.IsValid()) {
            EntFireByHandle(cube, "AddOutput", "OnTakeDamage !self:RunScriptCode:CheckAttackerWeapon(self):0:-1", 0, null, null);
        }
    }

    // for testing, or just looking for the cube "script TeleportToCube()"
    ::TeleportToCube <- function() {
        if (g_spawned_cubes.len() > 0) {
            local cube = g_spawned_cubes[0];
            
            if (cube == null || !cube.IsValid()) {
                g_spawned_cubes = [];
                g_auto_spawn_initialized = false;
                g_spawn_attempts = 0;
                return;
            }
            
            local cube_pos = cube.GetOrigin();
            
            local player = null;
            try { player = GetListenServerHost() } catch(e) {}
            if (player == null) { 
                try { player = Entities.FindByClassname(null, "player") } catch(e) {} 
            }
            
            if (player != null) {
                local teleport_pos = Vector(cube_pos.x, cube_pos.y, cube_pos.z + 100);
                
                try {
                    player.SetOrigin(teleport_pos);
                } catch(e) {}
                
                try {
                    cube.SetRenderColor(255, 0, 0);
                } catch(e) {}
            }
        }
    }

    ::IsPositionReachable <- function(pos) {
        local trace_down = {
            start = Vector(pos.x, pos.y, pos.z + 10),
            end = Vector(pos.x, pos.y, pos.z - 500)
        };
        
        try {
            TraceLineEx(trace_down);
        } catch(e) {
            return false;
        }
        
        if (!trace_down.hit || !("pos" in trace_down)) {
            return false;
        }
        
        local ground_pos = trace_down.pos;
        local height_above_ground = pos.z - ground_pos.z;
        
        if (height_above_ground > 150 || height_above_ground < -50) {
            return false;
        }
        
        local trace_up = {
            start = pos,
            end = Vector(pos.x, pos.y, pos.z + 300)
        };
        
        try {
            TraceLineEx(trace_up);
        } catch(e) {}
        
        if (trace_up.hit && "pos" in trace_up) {
            local clearance = trace_up.pos.z - pos.z;
            if (clearance < 100) {
                return false;
            }
        }
        
        local player = null;
        try { player = GetListenServerHost() } catch(e) {}
        if (player == null) { 
            try { player = Entities.FindByClassname(null, "player") } catch(e) {} 
        }
        
        if (player != null) {
            local player_pos = player.GetOrigin();
            local dist = (pos - player_pos).Length();
            
            if (dist > 5000) {
                return false;
            }
            
            if (dist < 200) {
                return false;
            }
        }
        
        return true;
    }

    ::FindNearPlayerSpawn <- function() {
        local spawn_classes = [
            "info_player_start",
            "info_player_deathmatch", 
            "info_player_teamspawn",
            "info_player_terrorist",
            "info_player_counterterrorist",
            "info_player_rebel",
            "info_player_combine",
            "info_player_coop"
        ];
        
        local spawn_positions = [];
        
        foreach (classname in spawn_classes) {
            local spawn = null;
            while ((spawn = Entities.FindByClassname(spawn, classname)) != null) {
                spawn_positions.append(spawn.GetOrigin());
            }
        }
        
        if (spawn_positions.len() == 0) {
            return null;
        }
        
        local random_spawn = spawn_positions[RandomInt(0, spawn_positions.len() - 1)];
        
        local test_distances = [300, 500, 700, 900];
        local test_angles = [0, 45, 90, 135, 180, 225, 270, 315];
        
        foreach (dist in test_distances) {
            foreach (angle_deg in test_angles) {
                local angle = angle_deg * 0.0174533;
                local test_pos = Vector(
                    random_spawn.x + cos(angle) * dist,
                    random_spawn.y + sin(angle) * dist,
                    random_spawn.z + 50
                );
                
                if (IsPositionReachable(test_pos)) {
                    return test_pos;
                }
            }
        }
        
        return null;
    }

    ::FindNearPropPhysics <- function() {
        local props = [];
        local prop = null;
        
        while ((prop = Entities.FindByClassname(prop, "prop_physics")) != null) {
            props.append(prop);
            if (props.len() >= 30) break;
        }
        
        if (props.len() == 0) {
            prop = null;
            while ((prop = Entities.FindByClassname(prop, "prop_dynamic")) != null) {
                props.append(prop);
                if (props.len() >= 30) break;
            }
        }
        
        for (local attempt = 0; attempt < 10; attempt++) {
            if (props.len() == 0) break;
            
            local random_prop = props[RandomInt(0, props.len() - 1)];
            local prop_pos = random_prop.GetOrigin();
            
            local angles = [0, 45, 90, 135, 180, 225, 270, 315];
            local distances = [200, 350, 500];
            
            foreach (dist in distances) {
                foreach (angle_deg in angles) {
                    local angle = angle_deg * 0.0174533;
                    local test_pos = Vector(
                        prop_pos.x + cos(angle) * dist,
                        prop_pos.y + sin(angle) * dist,
                        prop_pos.z + 50
                    );
                    
                    if (IsPositionReachable(test_pos)) {
                        return test_pos;
                    }
                }
            }
        }
        
        return null;
    }

    ::FindWeaponOrItemLocation <- function() {
        local locations = [];
        
        local weapon = null;
        while ((weapon = Entities.FindByClassname(weapon, "weapon_*")) != null) {
            local pos = weapon.GetOrigin();
            pos.z += 50;
            if (IsPositionReachable(pos)) {
                locations.append(pos);
            }
            if (locations.len() >= 15) break;
        }
        
        if (locations.len() == 0) {
            local item = null;
            while ((item = Entities.FindByClassname(item, "item_*")) != null) {
                local pos = item.GetOrigin();
                pos.z += 50;
                if (IsPositionReachable(pos)) {
                    locations.append(pos);
                }
                if (locations.len() >= 15) break;
            }
        }
        
        if (locations.len() > 0) {
            return locations[RandomInt(0, locations.len() - 1)];
        }
        
        return null;
    }

    ::FindNearPlayer <- function() {
        local player = null;
        try { player = GetListenServerHost() } catch(e) {}
        if (player == null) { 
            try { player = Entities.FindByClassname(null, "player") } catch(e) {} 
        }
        
        if (player != null) {
            local ppos = player.GetOrigin();
            
            local test_distances = [400, 600, 800];
            local test_angles = [0, 45, 90, 135, 180, 225, 270, 315];
            
            foreach (dist in test_distances) {
                foreach (angle_deg in test_angles) {
                    local angle = angle_deg * 0.0174533;
                    local test_pos = Vector(
                        ppos.x + cos(angle) * dist,
                        ppos.y + sin(angle) * dist,
                        ppos.z + 50
                    );
                    
                    if (IsPositionReachable(test_pos)) {
                        return test_pos;
                    }
                }
            }
        }
        
        return null;
    }

    ::SpawnCubeAtPosition <- function(pos) {
        local cube = null;
        
        try {
            cube = SpawnEntityFromTable("prop_physics", {
                origin = pos,
                angles = QAngle(0, RandomFloat(0, 360), 0),
                model = CUBE_MODEL
            });
        } catch(e) {}
        
        if (cube == null) {
            try {
                cube = SpawnEntityFromTable("prop_dynamic", {
                    origin = pos,
                    angles = QAngle(0, RandomFloat(0, 360), 0),
                    model = CUBE_MODEL,
                    solid = 6
                });
            } catch(e) {}
        }
        
        if (cube != null) {
            try {
                cube.SetRenderColor(0, 230, 255);
            } catch(e) {}
            
            SetupCubeDamageOutput(cube);
            
            return cube;
        }
        
        return null;
    }

    ::SpawnCubeSmartly <- function() {
        local spawn_methods = [
            { func = FindNearPlayerSpawn, name = "near player spawn" },
            { func = FindNearPropPhysics, name = "near prop_physics" },
            { func = FindWeaponOrItemLocation, name = "near weapon/item" },
            { func = FindNearPlayer, name = "near player" }
        ];
        
        local start_index = g_spawn_method_index % spawn_methods.len();
        
        for (local i = 0; i < spawn_methods.len(); i++) {
            local method_index = (start_index + i) % spawn_methods.len();
            local method = spawn_methods[method_index];
            
            local spawn_pos = method.func();
            
            if (spawn_pos != null) {
                local cube = SpawnCubeAtPosition(spawn_pos);
                
                if (cube != null) {
                    g_spawned_cubes.append(cube);
                    g_spawn_method_index = (method_index + 1) % spawn_methods.len();
                    return true;
                }
            }
        }
        
        return false;
    }

    ::InitializeAutoSpawner <- function() {
        if (g_auto_spawn_initialized) {
            return null;
        }
        
        local current_time = Time();
        
        if (current_time < 3.0) {
            return 0.5;
        }
        
        g_spawn_attempts++;
        
        local success = SpawnCubeSmartly();
        
        if (success || g_spawn_attempts >= 6) {
            g_auto_spawn_initialized = true;
            return null;
        }
        
        return 1.0;
    }

    ::OnGameEvent_round_start <- function(params) {
        foreach (cube in g_spawned_cubes) {
            if (cube != null && cube.IsValid()) {
                try {
                    cube.Kill();
                } catch(e) {}
            }
        }
        
        g_spawned_cubes = [];
        g_auto_spawn_initialized = false;
        g_spawn_attempts = 0;
    }

    __CollectGameEventCallbacks(this);

    if ("RegisterThinkFunction" in getroottable()) {
        RegisterThinkFunction("auto_spawner", InitializeAutoSpawner, 0.0);
        RegisterThinkFunction("respawn_checker", CheckRespawn, 0.0);
    } else {
        ::DelayedRegisterAutoSpawner <- function() {
            if ("RegisterThinkFunction" in getroottable()) {
                RegisterThinkFunction("auto_spawner", InitializeAutoSpawner, 0.0);
                RegisterThinkFunction("respawn_checker", CheckRespawn, 0.0);
            }
        }
        
        DoEntFire("worldspawn", "RunScriptCode", "DelayedRegisterAutoSpawner()", 2.0, null, null);
    }
    """
        
        output_file = os.path.join(self.vscripts_path, "auto_spawner.nut")
        
        try:
            with open(output_file, 'w', encoding='utf-8', newline='\n') as f:
                f.write(auto_spawner_code)
            
            print(f"\n[success] auto-spawner installed")
            print(f"  {output_file}")
            print(f"  features: smart spawning + AWP quit trigger")
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
            
            print(f"\n[success] mapspawn configured")
            print(f"  {mapspawn_file}")
            return True
        except Exception as e:
            print(f"[error] failed to setup mapspawn: {e}")
            if self.verbose:
                traceback.print_exc()
            return False
        
    def setup_autoexec(self):
        """create autoexec config to automatically load vscript on game start"""
        if not self.active_game:
            print("[error] no active game")
            return False
        
        if not self.vscripts_path:
            if self.verbose:
                print("[info] VScript not supported, skipping autoexec setup")
            return False
        
        try:
            game_info = self.SUPPORTED_GAMES.get(self.active_game)
            if not game_info:
                return False
                
            cfg_path = os.path.join(
                os.path.dirname(self.game_path),
                'cfg',
                'autoexec.cfg'
            )
            
            os.makedirs(os.path.dirname(cfg_path), exist_ok=True)
            
            autoexec_content = """// python bridge autoexec
sv_cheats 1
script_execute python_listener
echo "[python] bridge listener auto-loaded"
"""
            
            # check if already added
            existing_content = ""
            if os.path.exists(cfg_path):
                with open(cfg_path, 'r') as f:
                    existing_content = f.read()
                
                if "python_listener" in existing_content:
                    print(f"\n[info] autoexec already configured")
                    print(f"  {cfg_path}")
                    return True
            
            # append to existing autoexec
            with open(cfg_path, 'a') as f:
                f.write("\n" + autoexec_content)
            
            print(f"\n[success] autoexec configured")
            print(f"  {cfg_path}")
            return True
        except Exception as e:
            print(f"[error] failed to setup autoexec: {e}")
            if self.verbose:
                traceback.print_exc()
            return False
        
    def _get_listener_code(self):
        """generate the vscript listener code"""
        return r'''
if (!("g_think_functions" in getroottable())) {
    ::g_think_functions <- {};
    ::g_think_delays <- {};
}

if (!("RegisterThinkFunction" in getroottable())) {
    ::RegisterThinkFunction <- function(name, func, initial_delay = 0.0) {
        g_think_functions[name] <- func;
        g_think_delays[name] <- Time() + initial_delay;
    }
}

// ensure we silence “SCRIPT PERF WARNING …” 
if (!("g_perf_filter_ready" in getroottable())) {
    ::g_perf_filter_ready <- false;

    ::ApplyPerfFilter <- function() {
        local ok = false;
        try {
            SendToConsole("con_filter_enable 1");
            SendToConsole("con_filter_text_out \"SCRIPT PERF WARNING\"");
            local cur = Convars.GetStr("con_filter_text_out");
            if (cur != null && cur.find("SCRIPT PERF WARNING") != null) {
                ok = true;
            }
        } catch(e) {}

        if (!ok) {
            try {
                Convars.SetStr("con_filter_enable", "1");
                Convars.SetStr("con_filter_text_out", "SCRIPT PERF WARNING");
                ok = true;
            } catch(e) {}
        }

        if (ok) {
            g_perf_filter_ready = true;
            return null;  
        }
        return 0.5;        // retry every 0.5s until it sticks
    };

    RegisterThinkFunction("perf_filter", ApplyPerfFilter, 0.0);
}

if (!("UnregisterThinkFunction" in getroottable())) {
    ::UnregisterThinkFunction <- function(name) {
        if (name in g_think_functions) {
            delete g_think_functions[name];
            delete g_think_delays[name];
        }
    }
}

function MasterThink() {
    local current_time = Time();
    
    foreach (name, func in g_think_functions) {
        if (current_time >= g_think_delays[name]) {
            try {
                local delay = func();
                if (delay == null || delay < 0.0) delay = 0.1;
                g_think_delays[name] = current_time + delay;
            } catch(e) {}
        }
    }
    
    return 0.01;
}

if (!("g_python_session_id" in getroottable())) {
    ::g_python_session_id <- 0
}
if (!("g_python_last_command_id" in getroottable())) {
    ::g_python_last_command_id <- 0
}

::last_command_id <- g_python_last_command_id
::current_session_id <- g_python_session_id

function CheckPythonCommand() {
    local command_str = null
    
    try {
        command_str = FileToString("python_command.txt")
    } catch(e) {
        return 0.1
    }
    
    if (command_str == null || command_str.len() == 0) {
        return 0.1
    }
    
    local session_id = ExtractNumber(command_str, "session")
    
    if (session_id > 0 && session_id != current_session_id) {
        current_session_id = session_id
        ::g_python_session_id <- session_id
        
        last_command_id = 0
        ::g_python_last_command_id <- 0
    }
    
    ParseAndExecuteCommand(command_str)
    return 0.1
}

function ParseAndExecuteCommand(json_str) {
    local session_id = ExtractNumber(json_str, "session")
    
    if (session_id == 0) {
        return
    }
    
    if (current_session_id > 0 && session_id != current_session_id) {
        return
    }
    
    local command_id = ExtractNumber(json_str, "id")
    
    if (command_id <= 0) {
        return
    }
    
    if (command_id <= last_command_id) {
        return
    }
    
    last_command_id = command_id
    ::g_python_last_command_id <- command_id
    
    local command = ExtractString(json_str, "command")
    
    if (command == null || command.len() == 0) {
        SendResponse("error", "empty command")
        return
    }
    
    try {
        if (command == "spawn_model") {
            local model = ExtractString(json_str, "model")
            local distance = ExtractNumber(json_str, "distance")
            if (distance == 0) distance = 200
            
            if (model == null || model.len() == 0) {
                SendResponse("error", "no model specified")
                return
            }
            
            SpawnModelAtCrosshair(model, distance)
        } else if (command == "reinstall_awp") {
            if ("SetupDamageOutput" in getroottable()) {
                try {
                    SetupDamageOutput()
                    SendResponse("success", "awp outputs reinstalled")
                } catch(e) {
                    SendResponse("error", "awp reinstall failed")
                }
            } else {
                SendResponse("error", "awp function not found")
            }
        } else {
            SendResponse("error", "unknown command")
        }
    } catch(e) {
        SendResponse("error", "execution failed: " + e)
    }
}

function ExtractString(json_str, key) {
    try {
        local key_str = "\"" + key + "\""
        local key_pos = json_str.find(key_str)
        if (key_pos == null) return null
        
        local value_start = json_str.find("\"", key_pos + key_str.len())
        if (value_start == null) return null
        value_start++
        
        local value_end = json_str.find("\"", value_start)
        if (value_end == null) return null
        
        return json_str.slice(value_start, value_end)
    } catch(e) {
        return null
    }
}

function ExtractNumber(json_str, key) {
    try {
        local key_str = "\"" + key + "\":" 
        local key_pos = json_str.find(key_str)
        if (key_pos == null) return 0
        
        local value_start = key_pos + key_str.len()
        while (value_start < json_str.len()) {
            local char = json_str.slice(value_start, value_start + 1)
            if (char != " " && char != "\t" && char != "\n") break
            value_start++
        }
        
        local value_end = value_start
        while (value_end < json_str.len()) {
            local char = json_str.slice(value_end, value_end + 1)
            if (char == "," || char == "}" || char == " ") break
            value_end++
        }
        
        if (value_end <= value_start) return 0
        
        local num_str = json_str.slice(value_start, value_end)
        try { 
            return num_str.tointeger() 
        } catch(e) { 
            return 0 
        }
    } catch(e) {
        return 0
    }
}

function GetLocalPlayer() {
    local player = null
    try { player = GetListenServerHost() } catch(e) {}
    if (player == null) { try { player = PlayerInstanceFromIndex(1) } catch(e) {} }
    if (player == null) { try { player = Entities.FindByClassname(null, "player") } catch(e) {} }
    return player
}

function SpawnModelAtCrosshair(model_path, distance) {
    local player = GetLocalPlayer()
    if (player == null) {
        SendResponse("error", "no player")
        return
    }
    
    local eye_pos = null
    local eye_angles = null
    
    try {
        eye_pos = player.EyePosition()
        eye_angles = player.EyeAngles()
    } catch(e) {
        SendResponse("error", "failed to get player view")
        return
    }
    
    if (eye_pos == null || eye_angles == null) {
        SendResponse("error", "invalid player view")
        return
    }
    
    local pitch = eye_angles.x * 0.0174533
    local yaw = eye_angles.y * 0.0174533
    
    local forward_x = cos(yaw) * cos(pitch)
    local forward_y = sin(yaw) * cos(pitch)
    local forward_z = -sin(pitch)
    
    local end_pos = Vector(
        eye_pos.x + (forward_x * distance),
        eye_pos.y + (forward_y * distance),
        eye_pos.z + (forward_z * distance)
    )
    
    local trace = {
        start = eye_pos
        end = end_pos
        ignore = player
    }
    
    try {
        TraceLineEx(trace)
    } catch(e) {}
    
    local spawn_pos = end_pos
    
    if (trace.hit && "pos" in trace) {
        spawn_pos = trace.pos
    }
    
    spawn_pos.z += 10
    
    if (model_path.find("models/") != 0) {
        model_path = "models/" + model_path
    }
    
    local prop = null
    
    try {
        prop = SpawnEntityFromTable("prop_physics", {
            origin = spawn_pos,
            angles = QAngle(0, 0, 0),
            model = model_path
        })
    } catch(e) {}
    
    if (prop == null) {
        try {
            prop = SpawnEntityFromTable("prop_dynamic", {
                origin = spawn_pos,
                angles = QAngle(0, 0, 0),
                model = model_path,
                solid = 6
            })
        } catch(e) {}
    }
    
    if (prop != null) {
        try { 
            prop.SetRenderColor(0, 230, 255) 
        } catch(e) {}
        SendResponse("spawned", model_path)
    } else {
        SendResponse("error", "spawn failed - invalid model or missing asset")
    }
}

function SendResponse(status, message) {
    local response = "{\"status\":\"" + status + "\",\"message\":\"" + message + "\"}"
    try { 
        StringToFile("python_response.txt", response) 
    } catch(e) {}
}

RegisterThinkFunction("python_bridge", CheckPythonCommand, 0.0)

if (!("g_master_think_active" in getroottable())) {
    ::g_master_think_active <- true
    try {
        local worldspawn = Entities.FindByClassname(null, "worldspawn")
        if (worldspawn != null) {
            AddThinkToEnt(worldspawn, "MasterThink")
        }
    } catch(e) {}
}
'''

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
        
        # check if this is a supported VScript game with command file
        if self.active_game in self.SUPPORTED_GAMES and self.command_file:
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
            bridge.install_listener()
            bridge.install_picker()     
            bridge.install_awp_quit()
            bridge.install_auto_spawner()  
            bridge.setup_mapspawn()
            bridge.setup_autoexec()
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
            print("         script_execute python_listener")
        else:
            print("  source game with no vscript! ONLY srcbox spawn is supported!")
            print("  mode: automatic console command injection (however you may have issues with this)")
            print("\n[usage] click cube in SourceBox to spawn")
        
        print("="*70 + "\n")
    else:
        print("\n[error] no source engine games found\n")