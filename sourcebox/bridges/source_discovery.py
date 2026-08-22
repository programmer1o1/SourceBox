"""Source Engine game and sourcemod discovery."""

import os
import traceback

import psutil

from mapbase_bridge import MapbaseBridge
from sourcebox.steam import command_mentions_executable, steam_library_from_process_info


class SourceGameDiscoveryMixin:
    def _get_running_game_library(self, game_name):
        """detect which steam library the running game is in"""
        try:
            for proc in psutil.process_iter(['name', 'exe', 'cmdline']):
                try:
                    proc_name = proc.info.get('name') or ''
                    cmdline = proc.info['cmdline']

                    if not cmdline:
                        continue

                    cmdline_str = ' '.join(cmdline).lower()
                    game_info = self.SUPPORTED_GAMES.get(game_name)

                    if not game_info:
                        continue

                    executable_names = game_info['executables']
                    process_matches = (
                        proc_name.lower() in [exe.lower() for exe in executable_names]
                        or command_mentions_executable(cmdline, executable_names)
                    )
                    if process_matches:
                        if game_info['cmdline_contains'].lower() in cmdline_str or \
                           game_info['game_dir'] in cmdline_str:
                            library = steam_library_from_process_info(proc.info)
                            if library:
                                self._log(f"detected running game library: {library}")
                                return library
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
        except Exception as e:
            if self.verbose:
                print(f"[warning] running game library detection failed: {e}")

        return None

    def _resolve_game_path(self, game_arg, exe_path=None):
        """resolve -game argument into an absolute path if possible"""
        if not game_arg:
            return None

        self._log(f"resolving -game argument: '{game_arg}'")

        cleaned = os.path.expanduser(game_arg.strip('"'))
        candidates = []

        if os.path.isabs(cleaned):
            candidates.append(os.path.normpath(cleaned))
            self._log(f"  candidate (absolute): {candidates[-1]}")

        # candidates from exe directory
        exe_dir = os.path.dirname(exe_path) if exe_path else None
        if exe_dir:
            self._log(f"  exe directory: {exe_dir}")

            # candidate 2: relative to exe dir
            candidate = os.path.normpath(os.path.join(exe_dir, cleaned))
            candidates.append(candidate)
            self._log(f"  candidate (exe_dir): {candidate}")

            # candidate 3: relative to parent of exe dir
            parent_dir = os.path.dirname(exe_dir)
            if parent_dir and parent_dir != exe_dir:
                candidate = os.path.normpath(os.path.join(parent_dir, cleaned))
                candidates.append(candidate)
                self._log(f"  candidate (parent): {candidate}")

            # candidate 4 & 5: try resolving against steam library root if path contains steamapps
            steamapps_index = exe_dir.lower().find('steamapps')
            if steamapps_index != -1:
                steamapps_root = exe_dir[:steamapps_index + len('steamapps')]
                self._log(f"  found steamapps root: {steamapps_root}")

                candidate = os.path.normpath(os.path.join(steamapps_root, 'sourcemods', cleaned))
                candidates.append(candidate)
                self._log(f"  candidate (sourcemods): {candidate}")

                candidate = os.path.normpath(os.path.join(steamapps_root, 'common', cleaned))
                candidates.append(candidate)
                self._log(f"  candidate (common): {candidate}")
        else:
            self._log("  no exe_path provided, cannot resolve relative paths")

        # deduplicate while preserving order
        seen = set()
        unique_candidates = []
        for cand in candidates:
            if cand not in seen:
                unique_candidates.append(cand)
                seen.add(cand)

        # test each candidate
        self._log(f"  testing {len(unique_candidates)} unique candidates...")
        for i, cand in enumerate(unique_candidates, 1):
            exists = os.path.isdir(cand)
            self._log(f"  [{i}] {cand} - {'EXISTS' if exists else 'not found'}")
            if exists:
                self._log(f"  resolved successfully: {cand}")
                return cand

        self._log("  resolution failed: no valid path found")
        return None

    def _is_mapbase_path(self, path):
        """return True if the path looks like a mapbase-based mod"""
        if not path:
            return False

        abs_path = os.path.abspath(path)
        base_name = os.path.basename(abs_path).lower()

        self._log(f"checking for mapbase in: {abs_path}")

        # check if the folder itself is named mapbase
        if base_name == 'mapbase':
            self._log("  folder name is 'mapbase' - detected")
            return True

        # check if there's a mapbase subfolder inside this mod
        mapbase_subdir = os.path.join(abs_path, 'mapbase')
        if os.path.isdir(mapbase_subdir):
            self._log(f"  found mapbase subdirectory: {mapbase_subdir}")
            return True

        # check if there's a mapbase folder in the parent directory
        parent_dir = os.path.dirname(abs_path)
        mapbase_parent = os.path.join(parent_dir, 'mapbase')
        if os.path.isdir(mapbase_parent):
            self._log(f"  found mapbase in parent: {mapbase_parent}")
            return True

        self._log("  not a mapbase mod")
        return False

    def _setup_mapbase_mod(self, mod_name, mod_path):
        """setup paths and files for a mapbase-based sourcemod"""
        try:
            bridge = MapbaseBridge(mod_path, verbose=self.verbose)
            if not bridge.prepare_paths():
                return False
            bridge.install_scripts()

            self.mapbase_bridge = bridge
            self.active_game = f"Mapbase: {mod_name}"
            self.game_path = bridge.scriptdata_path
            self.vscripts_path = bridge.vscripts_path
            self.command_file = bridge.command_file
            self.response_file = bridge.response_file

            print(f"\n[active] Mapbase Mod: {mod_name} (running)")
            print(f"  mod path: {mod_path}")
            print(f"  scriptdata: {self.game_path}")
            print(f"  vscripts: {self.vscripts_path}")
            print("  mode: VScript bridge (mapbase)")
            return True
        except Exception as e:
            print(f"[error] failed to setup mapbase mod: {e}")
            if self.verbose:
                traceback.print_exc()
            return False

    def _setup_mapbase_path(self, mod_name, steam_libraries):
        """try to locate and setup a mapbase-based mod by name"""
        for library_path in steam_libraries:
            sourcemods_path = os.path.join(library_path, 'steamapps', 'sourcemods')
            if not os.path.exists(sourcemods_path):
                sourcemods_path = os.path.join(library_path, 'SteamApps', 'sourcemods')

            candidate = os.path.join(sourcemods_path, mod_name)
            if os.path.isdir(candidate) and self._is_mapbase_path(candidate):
                return self._setup_mapbase_mod(mod_name, candidate)

        return False

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
        running_mapbase = False
        gmod_executables = [
            'hl2.exe', 'hl2_linux', 'gmod.exe', 'gmod',
            'gmod64', 'gmod32', 'gmod_linux'
        ]

        try:
            for proc in psutil.process_iter(['name', 'cmdline', 'exe']):
                try:
                    proc_name = proc.info.get('name')
                    if not proc_name:
                        continue

                    cmdline = proc.info.get('cmdline')
                    if not cmdline:
                        continue

                    # skip gamescope wrapper processes
                    if proc_name in ['gamescope', 'gamescope-session', 'gamescopereaper']:
                        continue

                    cmdline_str = ' '.join(cmdline)
                    proc_name_lower = proc_name.lower()

                    # check for gmod processes first
                    if (
                        proc_name_lower in gmod_executables
                        or command_mentions_executable(cmdline, gmod_executables)
                    ):
                        for i, arg in enumerate(cmdline):
                            if arg.lower() == '-game' and i + 1 < len(cmdline):
                                game_arg = cmdline[i + 1].strip('"').lower()

                                # check if it's a gmod sourcemod
                                if 'gmod9' in game_arg or 'garrysmod9' in game_arg:
                                    running_game = 'Garry\'s Mod 9'
                                    print(f"  [found] {running_game}")
                                    if self._setup_gmod_path(running_game, self.SUPPORTED_GAMES[running_game], all_steam_libraries):
                                        return
                                    break
                                elif 'garrysmod10classic' in game_arg:
                                    running_game = 'Garry\'s Mod 10'
                                    print(f"  [found] {running_game}")
                                    if self._setup_gmod_path(running_game, self.SUPPORTED_GAMES[running_game], all_steam_libraries):
                                        return
                                    break
                                elif 'garrysmod12' in game_arg:
                                    running_game = 'Garry\'s Mod 12'
                                    print(f"  [found] {running_game}")
                                    if self._setup_gmod_path(running_game, self.SUPPORTED_GAMES[running_game], all_steam_libraries):
                                        return
                                    break
                                elif 'garrysmod' in game_arg and 'garrysmod10' not in game_arg and 'garrysmod12' not in game_arg:
                                    # check if it's sourcemod (has 'sourcemods' in path) or retail
                                    is_sourcemod = False
                                    try:
                                        exe_path = proc.info.get('exe')
                                        if exe_path:
                                            is_sourcemod = 'sourcemods' in exe_path.lower()
                                    except:
                                        pass

                                    # also check cmdline for sourcemods path
                                    if not is_sourcemod:
                                        for cmd_part in cmdline:
                                            if 'sourcemods' in cmd_part.lower():
                                                is_sourcemod = True
                                                break

                                    if is_sourcemod:
                                        # sourcemod garrysmod (11)
                                        running_game = 'Garry\'s Mod 11'
                                        print(f"  [found] {running_game}")
                                        if self._setup_gmod_path(running_game, self.SUPPORTED_GAMES[running_game], all_steam_libraries):
                                            return
                                    else:
                                        # try retail gmod 13
                                        gmod13_info = self.SUPPORTED_GAMES.get('Garry\'s Mod 13')
                                        if gmod13_info and self._setup_gmod_path('Garry\'s Mod 13', gmod13_info, all_steam_libraries):
                                            running_game = 'Garry\'s Mod 13'
                                            print(f"  [found] {running_game}")
                                            return

                                        # fallback to sourcemod if retail not found
                                        running_game = 'Garry\'s Mod 11'
                                        print(f"  [found] {running_game}")
                                        if self._setup_gmod_path(running_game, self.SUPPORTED_GAMES[running_game], all_steam_libraries):
                                            return
                                    break

                    # check for supported games
                    for game_name, game_info in self.SUPPORTED_GAMES.items():
                        if game_info.get('is_gmod'):
                            continue

                        executable_names = game_info['executables']
                        process_matches = (
                            proc_name.lower() in [exe.lower() for exe in executable_names]
                            or command_mentions_executable(cmdline, executable_names)
                        )
                        if process_matches:
                            if game_info['cmdline_contains'].lower() in cmdline_str.lower() or \
                            game_info['game_dir'] in cmdline_str.lower():
                                running_game = game_name
                                print(f"  [found] {game_name}")
                                self._log(f"  process: {proc_name}")
                                break

                    if running_game:
                        break

                    # check for hl2.exe with -game argument (source mods and standalone games)
                    if (
                        proc_name_lower in ['hl2.exe', 'hl2_linux']
                        or command_mentions_executable(cmdline, ['hl2.exe', 'hl2_linux'])
                    ):
                        game_paths = []
                        resolved_game_paths = []

                        exe_path = proc.info.get('exe')

                        if exe_path:
                            self._log(f"found hl2 process: {proc_name}")
                            self._log(f"  exe location: {exe_path}")
                        else:
                            self._log(f"found hl2 process: {proc_name} (no exe path available)")

                        # extract -game arguments
                        for i, arg in enumerate(cmdline):
                            if arg.lower() == '-game' and i + 1 < len(cmdline):
                                game_arg = cmdline[i + 1].strip('"')
                                if not game_arg:
                                    continue

                                self._log(f"  -game argument: '{game_arg}'")
                                game_paths.append(game_arg)

                                # try to resolve the path
                                resolved_path = self._resolve_game_path(game_arg, exe_path)

                                if resolved_path:
                                    self._log("  resolved successfully")
                                    resolved_game_paths.append(resolved_path)
                                else:
                                    self._log("  failed to resolve path")

                                # if exe_path is unavailable (gamescope/proton), search steam libraries
                                if not resolved_game_paths and game_paths and not exe_path:
                                    self._log("  exe_path unavailable, searching steam libraries...")
                                    for game_arg in game_paths:
                                        self._log(f"  searching for: {game_arg}")

                                        # normalize the game_arg for fuzzy matching (remove spaces, lowercase)
                                        normalized_arg = game_arg.replace(' ', '').lower()

                                        # search in all steam libraries for standalone games
                                        for library_path in all_steam_libraries:
                                            self._log(f"    checking library: {library_path}")

                                            # check both common and sourcemods
                                            search_paths = [
                                                ('common', os.path.join(library_path, 'steamapps', 'common')),
                                                ('common', os.path.join(library_path, 'SteamApps', 'common')),
                                                ('sourcemods', os.path.join(library_path, 'steamapps', 'sourcemods')),
                                                ('sourcemods', os.path.join(library_path, 'SteamApps', 'sourcemods'))
                                            ]

                                            for search_type, search_path in search_paths:
                                                if not os.path.exists(search_path):
                                                    continue

                                                self._log(f"      searching {search_type}: {search_path}")

                                                try:
                                                    for folder in os.listdir(search_path):
                                                        # fuzzy match: compare with spaces removed
                                                        normalized_folder = folder.replace(' ', '').lower()

                                                        if normalized_folder == normalized_arg:
                                                            self._log(f"        found matching folder: {folder}")
                                                            game_root = os.path.join(search_path, folder)

                                                            # check for nested directory with same/similar name
                                                            nested_candidates = [
                                                                os.path.join(game_root, folder),  # exact match
                                                                os.path.join(game_root, game_arg),  # game arg name
                                                                os.path.join(game_root, game_arg.replace(' ', '')),  # no spaces
                                                            ]

                                                            # also check all subdirs that might match
                                                            try:
                                                                for subdir in os.listdir(game_root):
                                                                    subdir_path = os.path.join(game_root, subdir)
                                                                    if os.path.isdir(subdir_path):
                                                                        normalized_subdir = subdir.replace(' ', '').lower()
                                                                        if normalized_subdir == normalized_arg:
                                                                            nested_candidates.append(subdir_path)
                                                            except:
                                                                pass

                                                            # test nested candidates
                                                            for candidate in nested_candidates:
                                                                if os.path.isdir(candidate):
                                                                    # verify it's a real game folder (has gameinfo.txt or bin folder)
                                                                    if (os.path.exists(os.path.join(candidate, 'gameinfo.txt')) or
                                                                        os.path.exists(os.path.join(candidate, 'bin'))):
                                                                        self._log(f"        valid game folder: {candidate}")
                                                                        resolved_game_paths.append(candidate)
                                                                        break

                                                            # if no nested folder worked, try the root itself
                                                            if not resolved_game_paths:
                                                                if (os.path.exists(os.path.join(game_root, 'gameinfo.txt')) or
                                                                    os.path.exists(os.path.join(game_root, 'bin'))):
                                                                    self._log(f"        valid game folder (root): {game_root}")
                                                                    resolved_game_paths.append(game_root)

                                                            if resolved_game_paths:
                                                                break

                                                    if resolved_game_paths:
                                                        break
                                                except Exception as e:
                                                    self._log(f"        error listing directory: {e}")

                                            if resolved_game_paths:
                                                break

                                        if resolved_game_paths:
                                            break

                        # if no resolved path but we have exe_path, try to find game from exe location
                        if not resolved_game_paths and exe_path and game_paths:
                            self._log("  attempting resolution from exe location...")
                            exe_dir = os.path.dirname(exe_path)
                            for game_arg in game_paths:
                                # try the subfolder with the game_arg name (case-insensitive)
                                for variant in [game_arg.lower(), game_arg]:
                                    game_folder_path = os.path.join(exe_dir, variant)
                                    self._log(f"    checking: {game_folder_path}")
                                    if os.path.isdir(game_folder_path):
                                        self._log(f"    found: {game_folder_path}")
                                        resolved_game_paths.append(game_folder_path)
                                        break

                        # mapbase detection using resolved paths or exe directory
                        mapbase_candidates = list(resolved_game_paths)
                        self._log(f"  checking {len(mapbase_candidates)} resolved paths for mapbase...")

                        if exe_path:
                            exe_dir = os.path.dirname(exe_path)
                            # check if exe_dir itself has mapbase (for standalone games)
                            if self._is_mapbase_path(exe_dir):
                                self._log("  exe_dir is mapbase location")
                                for game_arg in game_paths:
                                    for variant in [game_arg.lower(), game_arg]:
                                        game_folder = os.path.join(exe_dir, variant)
                                        if os.path.isdir(game_folder):
                                            self._log(f"    adding mapbase candidate: {game_folder}")
                                            mapbase_candidates.append(game_folder)
                                            break

                        for candidate in mapbase_candidates:
                            if self._is_mapbase_path(candidate):
                                running_mod = os.path.basename(candidate.rstrip('/\\'))
                                running_mod_path = candidate
                                running_mapbase = True
                                print(f"  [found] Mapbase Game: {running_mod}")
                                print(f"  [process] {proc_name} -game {candidate}")
                                self._log(f"  detected as mapbase mod: {running_mod}")
                                break

                        if running_mapbase:
                            break

                        if not running_mod and not running_mapbase and resolved_game_paths:
                            for resolved_path in resolved_game_paths:
                                # verify it's a valid source game with gameinfo.txt
                                gameinfo_path = os.path.join(resolved_path, 'gameinfo.txt')
                                if os.path.exists(gameinfo_path):
                                    running_mod = os.path.basename(resolved_path.rstrip('/\\'))
                                    running_mod_path = resolved_path
                                    print(f"  [found] Standalone Source Game: {running_mod}")
                                    print(f"  [process] {proc_name} -game {resolved_path}")
                                    self._log(f"  detected as standalone source game: {running_mod}")

                                    # check if it has VScript support (scripts/vscripts folder)
                                    vscripts_check = os.path.join(resolved_path, 'scripts', 'vscripts')
                                    if os.path.exists(vscripts_check):
                                        self._log("  has VScript support")
                                    else:
                                        self._log("  no VScript support detected")

                                    break

                        if running_mod:
                            break

                        # check if it's a standalone source game (not sourcemod, not mapbase)
                        self._log("  checking for standalone source game...")
                        if not running_mod and not running_mapbase and resolved_game_paths:
                            for resolved_path in resolved_game_paths:
                                # check multiple possible locations for gameinfo.txt
                                gameinfo_candidates = [
                                    resolved_path,  # direct path
                                    os.path.join(resolved_path, os.path.basename(resolved_path.rstrip('/\\'))),  # nested folder with same name
                                ]

                                # also check subdirectories that might contain the actual game
                                try:
                                    for subdir in os.listdir(resolved_path):
                                        subdir_path = os.path.join(resolved_path, subdir)
                                        if os.path.isdir(subdir_path):
                                            gameinfo_candidates.append(subdir_path)
                                except:
                                    pass

                                # test each candidate
                                for candidate in gameinfo_candidates:
                                    gameinfo_path = os.path.join(candidate, 'gameinfo.txt')
                                    self._log(f"    checking gameinfo.txt at: {gameinfo_path}")

                                    if os.path.exists(gameinfo_path):
                                        running_mod = os.path.basename(candidate.rstrip('/\\'))
                                        running_mod_path = candidate
                                        print(f"  [found] Standalone Source Game: {running_mod}")
                                        print(f"  [process] {proc_name} -game {candidate}")
                                        self._log(f"  detected as standalone source game: {running_mod}")
                                        break

                                if running_mod:
                                    break

                        if running_mod:
                            break

                        # look for sourcemods path in resolved paths
                        self._log("  checking for sourcemod paths...")
                        for game_path in resolved_game_paths + game_paths:
                            if 'sourcemods' in str(game_path).lower():
                                self._log(f"    found sourcemods in path: {game_path}")
                                parts = str(game_path).replace('\\', '/').split('/')
                                for i, part in enumerate(parts):
                                    if part.lower() == 'sourcemods' and i + 1 < len(parts):
                                        running_mod = parts[i + 1]
                                        running_mod_path = self._resolve_game_path(game_path, exe_path) or game_path
                                        print(f"  [found] Source Mod: {running_mod}")
                                        print(f"  [process] {proc_name} -game {running_mod_path}")
                                        self._log(f"  detected as sourcemod: {running_mod}")
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
            # prefer mapbase setup when detected
            if running_mapbase or (running_mod_path and self._is_mapbase_path(running_mod_path)):
                if running_mod_path:
                    if self._setup_mapbase_mod(running_mod, running_mod_path):
                        return
                else:
                    if self._setup_mapbase_path(running_mod, all_steam_libraries):
                        return
            else:
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
                print("  [warning] couldn't detect active library, checking all libraries")

            if not self._setup_game_path(running_game, steam_libraries):
                print(f"[error] failed to locate {running_game} files")
                self._scan_installed_games(all_steam_libraries)
                self._scan_sourcemods(all_steam_libraries)

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
                            if self._is_mapbase_path(mod_path):
                                scriptdata_path = os.path.join(mod_path, 'scriptdata')
                                vscripts_path = os.path.join(mod_path, 'scripts', 'vscripts')
                                os.makedirs(scriptdata_path, exist_ok=True)
                                os.makedirs(vscripts_path, exist_ok=True)

                                self.detected_games.append({
                                    'name': f"Mapbase: {mod_name}",
                                    'library': library_path,
                                    'scriptdata_path': scriptdata_path,
                                    'vscripts_path': vscripts_path,
                                    'is_sourcemod': True,
                                    'is_mapbase': True
                                })
                                print(f"  [mapbase] {mod_name} (in {library_path})")
                                continue

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

        if game_info.get('is_gmod'):
            return self._setup_gmod_path(game_name, game_info, steam_libraries)

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

    def _setup_gmod_path(self, game_name, game_info, steam_libraries):
        """setup paths for gmod (sourcemod or retail)"""
        install_type = game_info.get('install_type', 'sourcemod')

        # prioritize the library that actually holds the running executable, so a
        # leftover/empty game folder in another library (e.g. an old garrysmod on C:)
        # doesn't win over the library the game is really launched from (e.g. D:)
        ordered_libraries = list(steam_libraries)
        active_library = self._get_running_game_library(game_name)
        if active_library:
            active_norm = os.path.normcase(os.path.normpath(active_library))
            ordered_libraries.sort(key=lambda lib: os.path.normcase(os.path.normpath(lib)) != active_norm)
            self._log(f"prioritizing running game library: {active_library}")

        for library_path in ordered_libraries:
            mod_path = None

            if install_type == 'standalone':
                install_dir = game_info.get('install_dir', game_name)
                game_root = os.path.join(library_path, 'steamapps', 'common', install_dir)
                if not os.path.exists(game_root):
                    game_root = os.path.join(library_path, 'SteamApps', 'common', install_dir)

                candidate_path = os.path.join(game_root, game_info['game_dir'])
                if os.path.exists(candidate_path):
                    mod_path = candidate_path
            else:
                sourcemods_path = os.path.join(library_path, 'steamapps', 'sourcemods')
                if not os.path.exists(sourcemods_path):
                    sourcemods_path = os.path.join(library_path, 'SteamApps', 'sourcemods')

                if os.path.exists(sourcemods_path):
                    candidate_path = os.path.join(sourcemods_path, game_info['game_dir'])
                    if os.path.exists(candidate_path):
                        mod_path = candidate_path

            if mod_path:
                try:
                    data_path = os.path.join(mod_path, 'data')
                    os.makedirs(data_path, exist_ok=True)

                    self.active_game = game_name
                    self.game_path = data_path
                    self.vscripts_path = None  # gmod uses lua, not vscript
                    self.command_file = os.path.join(data_path, "sourcebox_command.txt")
                    self.response_file = os.path.join(data_path, "sourcebox_response.txt")

                    try:
                        from gmod_bridge import GModBridge
                        self.gmod_bridge = GModBridge()
                    except ImportError:
                        print("[warning] gmod_bridge not available")
                        self.gmod_bridge = None

                    install_label = "standalone" if install_type == 'standalone' else "sourcemod"
                    print(f"\n[active] {game_name}")
                    print(f"  library: {library_path}")
                    print(f"  data: {data_path}")
                    print(f"  mode: lua bridge ({install_label})")

                    return True
                except Exception as e:
                    print(f"[error] failed to setup gmod paths: {e}")
                    if self.verbose:
                        traceback.print_exc()
                    return False

        return False

    def _scan_installed_games(self, steam_libraries):
        """fallback to first installed game if none running"""
        for library_path in steam_libraries:
            for game_name, game_info in self.SUPPORTED_GAMES.items():
                try:
                    if game_info.get('is_gmod'):
                        continue  # gmod handled by lua bridge when running

                    game_root = os.path.join(library_path, 'steamapps', 'common', game_name)
                    if not os.path.exists(game_root):
                        game_root = os.path.join(library_path, 'SteamApps', 'common', game_name)

                    if os.path.exists(game_root):
                        # check if this game uses Mapbase
                        game_dir_path = os.path.join(game_root, game_info['game_dir'])
                        is_mapbase_game = self._is_mapbase_path(game_dir_path)

                        if is_mapbase_game:
                            # this is a Mapbase game - use vscript_io instead of scriptdata
                            scriptdata_path = os.path.join(game_dir_path, 'vscript_io')
                            vscripts_path = os.path.join(game_dir_path, 'scripts', 'vscripts')

                            os.makedirs(scriptdata_path, exist_ok=True)
                            os.makedirs(vscripts_path, exist_ok=True)

                            self.detected_games.append({
                                'name': f"Mapbase: {game_name}",
                                'library': library_path,
                                'scriptdata_path': scriptdata_path,
                                'vscripts_path': vscripts_path,
                                'is_mapbase': True,
                                'mod_path': game_dir_path
                            })
                            print(f"  [mapbase] {game_name} (in {library_path})")
                        else:
                            # regular Source Engine game
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
                selected = self.detected_games[0]
                print(f"\n[active] using {selected['name']} (not running)")
                self.active_game = selected['name']
                self.game_path = selected['scriptdata_path']
                self.vscripts_path = selected['vscripts_path']

                # if it's a Mapbase game, set up MapbaseBridge
                if selected.get('is_mapbase') and 'mod_path' in selected:
                    self.mapbase_bridge = MapbaseBridge(selected['mod_path'], verbose=self.verbose)
                    self.command_file = self.mapbase_bridge.command_file
                    self.response_file = self.mapbase_bridge.response_file
                elif self.vscripts_path:
                    self.command_file = os.path.join(self.game_path, "python_command.txt")
                    self.response_file = os.path.join(self.game_path, "python_response.txt")
                else:
                    self.command_file = None
                    self.response_file = None
            except Exception as e:
                print(f"[error] failed to setup fallback game: {e}")
        else:
            print("\n[error] no source engine games found in any steam library")
