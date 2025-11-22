"""
Universal Source Engine VScript Bridge
Connects Python to any Source game with VScript support
"""

import os
import json
import time
import threading
import platform
import psutil
import traceback
import random

if platform.system() == 'Windows':
    import winreg

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
        except PermissionError:
            if self.verbose:
                print(f"[warning] permission denied: {filepath}")
            return False
        except FileNotFoundError:
            if self.verbose:
                print(f"[warning] file not found: {filepath}")
            return False
        except Exception as e:
            if self.verbose:
                print(f"[error] {error_msg}: {e}")
            return False
    
    def _cleanup_old_files(self):
        """remove stale command/response files from previous sessions"""
        # get steam libraries
        steam_install_path = self._get_steam_install_path()
        
        if not steam_install_path:
            return
        
        steam_libraries = self._parse_library_folders_vdf(steam_install_path)
        
        for library_path in steam_libraries:
            for game_name, game_info in self.SUPPORTED_GAMES.items():
                try:
                    game_root = os.path.join(library_path, 'steamapps', 'common', game_name)
                    
                    # try lowercase variant
                    if not os.path.exists(game_root):
                        game_root = os.path.join(library_path, 'SteamApps', 'common', game_name)
                    
                    if not os.path.exists(game_root):
                        continue
                        
                    scriptdata_path = os.path.join(game_root, game_info['game_dir'], game_info['scriptdata'])
                    
                    if os.path.exists(scriptdata_path):
                        files_to_clean = [
                            "python_command.txt",
                            "python_response.txt",
                        ]
                        
                        for filename in files_to_clean:
                            filepath = os.path.join(scriptdata_path, filename)
                            self._safe_file_operation(
                                lambda p: os.remove(p) if os.path.exists(p) else None,
                                filepath,
                                f"failed to cleanup {filename}"
                            )
                except Exception as e:
                    if self.verbose:
                        print(f"[warning] cleanup error for {game_name}: {e}")
                    continue
                    
    def _get_steam_path_from_process(self):
        """detect steam installation from running steam process"""
        try:
            for proc in psutil.process_iter(['name', 'exe']):
                try:
                    proc_name = proc.info['name']
                    
                    # look for steam process
                    if proc_name and proc_name.lower() in ['steam.exe', 'steam', 'steamwebhelper', 'steamos-session']:
                        exe_path = proc.info.get('exe')
                        
                        if exe_path and os.path.exists(exe_path):
                            # get directory containing steam executable
                            steam_dir = os.path.dirname(exe_path)
                            
                            # verify this is actually steam directory by checking for steamapps
                            if os.path.exists(os.path.join(steam_dir, 'steamapps')):
                                self._log(f"found steam from process: {steam_dir}")
                                return steam_dir
                            
                            # on linux, might need to go up one directory
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
            import winreg
            registry_paths = [
                r"SOFTWARE\Wow6432Node\Valve\Steam",  # 64-bit
                r"SOFTWARE\Valve\Steam"  # 32-bit
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
            
            common_paths = [
                r"C:\Program Files (x86)\Steam",
                r"C:\Program Files\Steam"
            ]
            
            for path in common_paths:
                if os.path.exists(path):
                    self._log(f"found steam at default location: {path}")
                    return path
            
            return None
            
        elif system == 'Linux':
            linux_paths = [
                "~/.local/share/Steam",
                "~/.steam/steam",
                "~/.steam/root"
            ]
            
            for path in linux_paths:
                expanded = os.path.expanduser(path)
                
                # resolve symlinks
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
        
        return None
        
    def _get_running_game_library(self, game_name):
        """detect which steam library the running game is actually in"""
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
                    
                    # check if this is our target game process
                    if proc_name.lower() in [exe.lower() for exe in game_info['executables']]:
                        if game_info['cmdline_contains'].lower() in cmdline_str or \
                           game_info['game_dir'] in cmdline_str:
                            # found the running game, extract its library path
                            # exe_path is like: D:\Steam\steamapps\common\Team Fortress 2\hl2.exe
                            # we need: D:\Steam
                            
                            exe_dir = os.path.dirname(exe_path)
                            
                            # navigate up to find the Steam library root
                            # typical structure: LIBRARY/steamapps/common/GAME/executable
                            current = exe_dir
                            for _ in range(10):  # safety limit
                                if os.path.exists(os.path.join(current, 'steamapps')):
                                    self._log(f"detected running game library: {current}")
                                    return current
                                parent = os.path.dirname(current)
                                if parent == current:  # reached root
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
        # libraryfolders.vdf is in steamapps subfolder
        vdf_path = os.path.join(steam_path, 'steamapps', 'libraryfolders.vdf')
        
        if not os.path.exists(vdf_path):
            # try lowercase variant on linux
            vdf_path = os.path.join(steam_path, 'SteamApps', 'libraryfolders.vdf')
        
        if not os.path.exists(vdf_path):
            self._log(f"libraryfolders.vdf not found at {vdf_path}")
            return [steam_path]
        
        libraries = [steam_path]  # main installation is always a library
        
        try:
            with open(vdf_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # parse vdf structure with numbered library entries containing path field
            import re
            # match patterns like "path" "D:\\Steam" or "path" "/home/user/Steam"
            path_pattern = r'"path"\s+"([^"]+)"'
            matches = re.findall(path_pattern, content)
            
            for match in matches:
                # unescape double backslashes
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
        
        # get steam install path
        steam_install_path = self._get_steam_install_path()
        
        if not steam_install_path:
            print("  [error] steam installation not found")
            print("="*70 + "\n")
            return
        
        print(f"  [steam] {steam_install_path}")
        
        # parse all library folders
        all_steam_libraries = self._parse_library_folders_vdf(steam_install_path)
        print(f"  [libraries] found {len(all_steam_libraries)} steam libraries")
        
        # check for running games
        print("\n[scan] detecting running games...")
        running_game = None
        retry_count = 0
        max_retries = 3
        
        while not running_game and retry_count < max_retries:
            if retry_count > 0:
                print(f"[retry] attempt {retry_count + 1}/{max_retries}")
                time.sleep(0.5)
            
            try:
                for proc in psutil.process_iter(['name', 'cmdline', 'exe']):
                    try:
                        proc_name = proc.info['name']
                        cmdline = proc.info['cmdline']
                        
                        if not cmdline:
                            continue
                        
                        cmdline_str = ' '.join(cmdline).lower()
                        
                        for game_name, game_info in self.SUPPORTED_GAMES.items():
                            if proc_name.lower() in [exe.lower() for exe in game_info['executables']]:
                                if game_info['cmdline_contains'].lower() in cmdline_str or \
                                   game_info['game_dir'] in cmdline_str:
                                    running_game = game_name
                                    print(f"  [found] {game_name}")
                                    self._log(f"  process: {proc_name}")
                                    break
                        
                        if running_game:
                            break
                            
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        continue
                    except Exception as e:
                        if self.verbose:
                            print(f"[warning] process check error: {e}")
                        continue
            except Exception as e:
                print(f"[warning] process enumeration error: {e}")
            
            retry_count += 1
        
        if not running_game:
            print("  [info] no running game found, scanning installed games...")
            self._scan_installed_games(all_steam_libraries)
        else:
            # game is running - detect which library it's in
            active_library = self._get_running_game_library(running_game)
            
            if active_library:
                # prioritize the active library
                steam_libraries = [active_library]
                print(f"  [active library] {active_library}")
            else:
                # fallback to all libraries
                steam_libraries = all_steam_libraries
                print(f"  [warning] couldn't detect active library, checking all libraries")
            
            if not self._setup_game_path(running_game, steam_libraries):
                print(f"[error] failed to locate {running_game} files")
                self._scan_installed_games(all_steam_libraries)
            
    def _setup_game_path(self, game_name, steam_libraries):
        """setup paths for specific game using discovered libraries"""
        game_info = self.SUPPORTED_GAMES.get(game_name)
        
        if not game_info:
            print(f"[error] unknown game: {game_name}")
            return False
        
        # games are in library/steamapps/common/
        for library_path in steam_libraries:
            game_root = os.path.join(library_path, 'steamapps', 'common', game_name)
            
            # try lowercase variant
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
                    
                    # try lowercase variant
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
            print("[error] no vscripts path available")
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
            print("[error] no vscripts path available")
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
            print("[error] no vscripts path available")
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
        """reinstall AWP damage outputs for newly spawned props, this will track all newly spawned props"""
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
            
    def setup_mapspawn(self):
        """create mapspawn.nut that auto-loads on every map"""
        if not self.vscripts_path:
            print("[error] no vscripts path")
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
        """create autoexec config to automatically load vscript on game start, just being extra lol"""
        if not self.active_game:
            print("[error] no active game")
            return False
        
        try:
            game_info = self.SUPPORTED_GAMES[self.active_game]
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
            
            # read existing autoexec if present
            existing_content = ""
            if os.path.exists(cfg_path):
                with open(cfg_path, 'r') as f:
                    existing_content = f.read()
                
                # check if already added
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
        """generate the vscript listener code with multi-think support"""
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
        """send spawn command to game"""
        if not self.game_path or not self.command_file:
            print("[error] no game configured")
            return False
        
        if not model_path or not isinstance(model_path, str):
            print("[error] invalid model path")
            return False
        
        if not isinstance(distance, (int, float)) or distance <= 0:
            print("[error] invalid distance, using default (200)")
            distance = 200
        
        self.command_count += 1
        
        # escape special characters in model path
        safe_model_path = model_path.replace('\\', '\\\\').replace('"', '\\"')
        
        # include session ID in every command so that they cannot spawn twice
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
    
    def stop(self):
        """stop background threads and cleanup"""
        self.running = False
        
        if self.watcher_thread:
            self.watcher_thread.join(timeout=1.0)
        
        try:
            files_to_cleanup = [
                self.command_file,
                self.response_file,
            ]
            
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
        bridge.install_listener()
        bridge.install_picker()     
        bridge.install_awp_quit()    
        bridge.setup_mapspawn()
        bridge.setup_autoexec()
        bridge.start_listening()
        
        print("\n" + "="*70)
        print("SETUP COMPLETE")
        print("="*70)
        print(f"\n[game] {bridge.active_game}")
        print(f"[session] {bridge.session_id}")
        print("\n[features]")
        print("  python bridge - spawn the cube from sourcebox")
        print("  picker - aimbot (do 'script PickerToggle() and script PickerNext() to select next target')")
        print("  awp quit - shoot srcbox with awp to quit the game")
        print("\n[auto-load] all scripts start automatically on map load")
        print("\n[manual] if needed:")
        print("         sv_cheats 1")
        print("         script_execute python_listener")
        print("="*70 + "\n")
    else:
        print("\n[error] no source engine games found\n")
